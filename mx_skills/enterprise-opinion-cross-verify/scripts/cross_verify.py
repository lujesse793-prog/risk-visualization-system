"""
Enterprise opinion cross verification runtime.

The module treats MCP and mx Skill outputs as clue sources, then verifies
candidate events against publicly fetchable pages. It deliberately avoids
post-loan analysis, risk ratings, scores, and recommendations.
"""

from __future__ import annotations

import asyncio
import ast
import hashlib
import html
import io
import importlib.util
import inspect
import json
import logging
import os
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx


BASE_DIR = Path(__file__).resolve().parents[3]
SKILL_DIR = Path(__file__).resolve().parents[1]
FULL_TEXT_DIR = BASE_DIR / "data" / "opinion_full_text"
BATCH_DIR = BASE_DIR / "data" / "opinion_batches"
LOG_DIR = BASE_DIR / "logs"
DEFAULT_TIMEOUT = 12.0
MAX_SNIPPET_CHARS = 500
MAX_EXCERPT_CHARS = 800
MAX_CLUE_TEXT_CHARS = 1200
MAX_SEARCH_QUERIES_PER_LEAD = 5
MAX_SEARCH_RESULTS_PER_QUERY = 5
DEFAULT_VERIFY_CONCURRENCY = 2
MAX_VERIFICATION_LEADS = 60
BATCH_TIMEZONE = "Asia/Shanghai"
BATCH_TZ = ZoneInfo(BATCH_TIMEZONE)

FORBIDDEN_ANALYSIS_PATTERNS = [
    "建议关注",
    "偿债压力较大",
    "再融资压力较大",
    "风险等级",
    "风险评分",
    "投资建议",
]

PUBLIC_NEGATIVE_TERMS = [
    "行政处罚",
    "被执行人",
    "评级下调",
    "债券公告",
    "违约",
    "逾期",
    "诉讼",
]

PUBLIC_BOND_TERMS = ["债券", "公告", "评级报告", "募集说明书", "重大事项"]

OFFICIAL_DOMAIN_HINTS = [
    "sse.com.cn",
    "szse.cn",
    "chinabond.com.cn",
    "shclearing.com.cn",
    "nafmii.org.cn",
    "cbex.com.cn",
    "court.gov.cn",
    "creditchina.gov.cn",
    "gsxt.gov.cn",
    "gov.cn",
    "csrc.gov.cn",
    "pbc.gov.cn",
]

OFFICIAL_SEARCH_TEMPLATES = [
    ("上海证券交易所", "https://www.sse.com.cn/home/search/?webswd={query}"),
    ("深圳证券交易所", "https://www.szse.cn/application/search/index.html?keyword={query}"),
    ("中国货币网", "https://www.chinamoney.com.cn/chinese/srch/?searchValue={query}"),
    ("上海清算所", "https://www.shclearing.com.cn/search/?keyword={query}"),
    ("交易商协会", "https://www.nafmii.org.cn/was5/web/search?searchword={query}"),
]


LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOG_DIR / "opinion_cross_verify.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)
LOGGER = logging.getLogger("opinion_cross_verify")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


class SharedRateLimiter:
    def __init__(self, min_interval_seconds: float) -> None:
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait_seconds = self.min_interval_seconds - (now - self._last_call)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            self._last_call = time.monotonic()


class DomainRateLimiter:
    def __init__(self, min_interval_seconds: float) -> None:
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self._lock = threading.Lock()
        self._last_by_domain: dict[str, float] = {}

    def wait(self, domain: str) -> None:
        domain = (domain or "").lower()
        with self._lock:
            now = time.monotonic()
            last_call = self._last_by_domain.get(domain, 0.0)
            wait_seconds = self.min_interval_seconds - (now - last_call)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            self._last_by_domain[domain] = time.monotonic()


GLOBAL_MCP_RATE_LIMITER = SharedRateLimiter(_env_float("OPINION_MCP_MIN_INTERVAL_SECONDS", 0.7))
GLOBAL_PUBLIC_SEARCH_RATE_LIMITER = SharedRateLimiter(_env_float("OPINION_PUBLIC_SEARCH_INTERVAL_SECONDS", 1.2))
GLOBAL_DOMAIN_FETCH_RATE_LIMITER = DomainRateLimiter(_env_float("OPINION_DOMAIN_FETCH_INTERVAL_SECONDS", 2.0))


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _batch_now() -> datetime:
    return datetime.now(BATCH_TZ)


def _batch_now_iso() -> str:
    return _batch_now().isoformat(timespec="seconds")


def _sha_id(*parts: str) -> str:
    raw = "\n".join(p or "" for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _clean_text(value: Any, limit: int | None = None) -> str:
    text = "" if value is None else str(value)
    text = html.unescape(text)
    text = re.sub(r"[\u200b\ufeff\xa0]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        return text[:limit].rstrip()
    return text


def _normalize_key(value: str) -> str:
    value = _clean_text(value).lower()
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "", value)
    return value


def _extract_date(text: str) -> str:
    text = text or ""
    patterns = [
        r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?",
        r"(20\d{2})(\d{2})(\d{2})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            y, mo, d = m.groups()
            try:
                return datetime(int(y), int(mo), int(d)).date().isoformat()
            except ValueError:
                continue
    return ""


def _within_lookback(date_text: str, lookback_days: int) -> bool:
    if not date_text:
        return True
    try:
        published = datetime.fromisoformat(date_text[:10]).date()
    except ValueError:
        return True
    return published >= (_batch_now().date() - timedelta(days=lookback_days))


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _load_module(module_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if not spec or not spec.loader:
        raise ImportError(f"Cannot load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def validate_params(params: dict[str, Any] | None) -> dict[str, Any]:
    params = params or {}
    company_name = _clean_text(params.get("company_name"))
    if not company_name:
        raise ValueError("company_name is required")
    sources = params.get("sources") or {}
    aliases = params.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    return {
        "company_name": company_name,
        "credit_code": _clean_text(params.get("credit_code"), 32),
        "province": _clean_text(params.get("province"), 32),
        "city": _clean_text(params.get("city"), 32),
        "aliases": [_clean_text(alias, 80) for alias in aliases if _clean_text(alias, 80)],
        "lookback_days": max(1, int(params.get("lookback_days") or 365)),
        "max_results": max(1, min(100, int(params.get("max_results") or 20))),
        "include_full_text": bool(params.get("include_full_text", True)),
        "sources": {
            "mcp": bool(sources.get("mcp", True)),
            "skill": bool(sources.get("skill", True)),
            "public_search": bool(sources.get("public_search", True)),
        },
    }


def _make_empty_status(status: str = "skipped", error: str = "") -> dict[str, Any]:
    return {"status": status, "result_count": 0, "error": error}


@dataclass
class PublicPage:
    url: str
    title: str = ""
    source: str = ""
    publish_date: str = ""
    text: str = ""
    status: str = "ok"
    error: str = ""


class FullTextStore:
    def save(self, company_name: str, result: dict[str, Any], full_text: str) -> str:
        raise NotImplementedError

    def get(self, full_text_id: str) -> dict[str, Any] | None:
        raise NotImplementedError


class FileFullTextStore(FullTextStore):
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def save(self, company_name: str, result: dict[str, Any], full_text: str) -> str:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        full_text_id = _sha_id(company_name, result.get("url", ""), result.get("title", ""), full_text[:500])
        payload = {
            "full_text_id": full_text_id,
            "company_name": company_name,
            "title": result.get("title", ""),
            "source": result.get("source", ""),
            "url": result.get("url", ""),
            "publish_date": result.get("publish_date", ""),
            "fetched_at": _now_iso(),
            "text": full_text,
            "entity_match": result.get("entity_match", {}),
            "matched_from": result.get("matched_from", []),
        }
        path = self.base_dir / f"{full_text_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return full_text_id

    def get(self, full_text_id: str) -> dict[str, Any] | None:
        safe_id = re.sub(r"[^a-fA-F0-9]", "", full_text_id or "")
        if not safe_id:
            return None
        path = self.base_dir / f"{safe_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


def get_full_text_store() -> FullTextStore:
    return FileFullTextStore(FULL_TEXT_DIR)


class SearchResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = {k.lower(): v or "" for k, v in attrs}
        href = attrs_dict.get("href", "")
        if href.startswith("http") or href.startswith("/ck/a"):
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            title = _clean_text(" ".join(self._text), 160)
            self.links.append({"title": title, "url": self._href})
            self._href = ""
            self._text = []


class LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[dict[str, str]] = []
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = {k.lower(): v or "" for k, v in attrs}
        href = attrs_dict.get("href", "")
        if not href or href.startswith(("javascript:", "#")):
            return
        self._href = urljoin(self.base_url, href)
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            title = _clean_text(" ".join(self._text), 180)
            self.links.append({"title": title, "url": self._href})
            self._href = ""
            self._text = []


class PublicSearcher:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout

    def search(self, query: str, max_results: int = MAX_SEARCH_RESULTS_PER_QUERY) -> list[dict[str, str]]:
        engine = os.environ.get("PUBLIC_SEARCH_ENGINE", "duckduckgo").lower()
        if engine == "disabled":
            return []
        GLOBAL_PUBLIC_SEARCH_RATE_LIMITER.wait()
        if engine in ("duckduckgo", "ddg"):
            try:
                results = self._search_duckduckgo(query, max_results)
                if results:
                    return results
            except Exception as exc:
                LOGGER.warning("DuckDuckGo search failed, falling back to Bing: %s", exc)
            return self._search_bing(query, max_results)
        if engine == "bing":
            return self._search_bing(query, max_results)
        return self._search_duckduckgo(query, max_results)

    def _search_bing(self, query: str, max_results: int) -> list[dict[str, str]]:
        url = f"https://www.bing.com/search?q={quote_plus(query)}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        }
        with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            resp.raise_for_status()
        parser = SearchResultParser()
        parser.feed(resp.text)
        results: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in parser.links:
            clean_url = self._clean_search_url(item["url"])
            if not clean_url or clean_url in seen:
                continue
            domain = urlparse(clean_url).netloc.lower()
            if any(skip in domain for skip in ("bing.com", "microsoft.com", "baidu.com")):
                continue
            seen.add(clean_url)
            results.append({"title": item.get("title", ""), "url": clean_url})
            if len(results) >= max_results:
                break
        return results

    def _search_duckduckgo(self, query: str, max_results: int) -> list[dict[str, str]]:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        }
        with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            resp.raise_for_status()

        results: list[dict[str, str]] = []
        seen: set[str] = set()
        for match in re.finditer(
            r'<a[^>]+class=["\']result__a["\'][^>]+href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
            resp.text,
            re.I,
        ):
            raw_url = html.unescape(match.group(1))
            title = _clean_text(re.sub(r"<[^>]+>", " ", html.unescape(match.group(2))), 180)
            clean_url = self._clean_search_url(raw_url)
            if not clean_url or clean_url in seen:
                continue
            seen.add(clean_url)
            results.append({"title": title, "url": clean_url})
            if len(results) >= max_results:
                break
        return results

    @staticmethod
    def _clean_search_url(url: str) -> str:
        parsed = urlparse(url)
        if url.startswith("/ck/a"):
            url = "https://www.bing.com" + url
            parsed = urlparse(url)
        if url.startswith("//duckduckgo.com/l/"):
            url = "https:" + url
            parsed = urlparse(url)
        if parsed.netloc.endswith("bing.com") and parsed.path.startswith("/ck/a"):
            query = parse_qs(parsed.query)
            target = query.get("u", [""])[0]
            if target:
                return unquote(target)
        if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
            query = parse_qs(parsed.query)
            target = query.get("uddg", [""])[0]
            if target:
                return unquote(target)
        return url


class OfficialSourceSearcher:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout

    def search(self, company_name: str, max_results: int = 20) -> list[dict[str, str]]:
        if os.environ.get("OPINION_OFFICIAL_SEARCH", "true").lower() == "false":
            return []

        names = build_company_search_names(company_name, limit=5)
        queries = []
        for name in names:
            queries.extend(
                [
                    name,
                    f"{name} 公告",
                    f"{name} 通报批评",
                    f"{name} 失信 被执行",
                    f"{name} 债券",
                ]
            )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        }
        results: list[dict[str, str]] = []
        seen: set[str] = set()
        with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
            query_limit = int(os.environ.get("OPINION_OFFICIAL_QUERY_LIMIT", "8"))
            for query in list(dict.fromkeys(queries))[:query_limit]:
                encoded = quote_plus(query)
                for source_name, template in OFFICIAL_SEARCH_TEMPLATES:
                    url = template.format(query=encoded)
                    try:
                        GLOBAL_PUBLIC_SEARCH_RATE_LIMITER.wait()
                        resp = client.get(url)
                        if resp.status_code >= 400:
                            continue
                    except Exception as exc:
                        LOGGER.debug("Official search failed for %s %s: %s", source_name, query, exc)
                        continue
                    parser = LinkParser(str(resp.url))
                    parser.feed(resp.text)
                    for link in parser.links:
                        clean_url = link.get("url", "")
                        if not clean_url or clean_url in seen:
                            continue
                        domain = urlparse(clean_url).netloc.lower()
                        if not any(hint in domain for hint in OFFICIAL_DOMAIN_HINTS):
                            continue
                        title = link.get("title", "")
                        haystack = f"{title} {clean_url}"
                        if not self._looks_relevant(haystack, names):
                            continue
                        seen.add(clean_url)
                        results.append(
                            {
                                "title": title or source_name,
                                "url": clean_url,
                                "source": source_name,
                            }
                        )
                        if len(results) >= max_results:
                            return results
        return results

    @staticmethod
    def _looks_relevant(text: str, names: list[str]) -> bool:
        compact_text = re.sub(r"\s+", "", text)
        for name in names:
            if name in text or re.sub(r"\s+", "", name) in compact_text:
                return True
        return any(term in text for term in ("公告", "通报", "处分", "失信", "债券", "被执行"))


class PageFetcher:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout

    def fetch(self, url: str) -> PublicPage:
        GLOBAL_DOMAIN_FETCH_RATE_LIMITER.wait(urlparse(url).netloc)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        }
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
                resp = client.get(url)
            content_type = resp.headers.get("content-type", "").lower()
            if resp.status_code >= 400:
                return PublicPage(url=url, status="source_unavailable", error=f"http_{resp.status_code}")
            if "pdf" in content_type or str(resp.url).lower().split("?")[0].endswith(".pdf"):
                return extract_pdf_text(str(resp.url), resp.content)
            text = resp.text
            return extract_page_text(str(resp.url), text)
        except Exception as exc:
            return PublicPage(url=url, status="source_unavailable", error=str(exc))


def extract_pdf_text(url: str, content: bytes) -> PublicPage:
    if not content.lstrip().startswith(b"%PDF"):
        return PublicPage(url=url, status="source_unavailable", error="pdf_response_not_pdf")

    try:
        from pypdf import PdfReader
    except Exception as exc:
        return PublicPage(url=url, status="partially_verified", error=f"pypdf_unavailable: {exc}")

    try:
        reader = PdfReader(io.BytesIO(content))
        parts: list[str] = []
        max_pages = int(os.environ.get("OPINION_PDF_MAX_PAGES", "20"))
        for index, page in enumerate(reader.pages[:max_pages], start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception as exc:
                LOGGER.warning("PDF page extraction failed for %s page %s: %s", url, index, exc)
                page_text = ""
            page_text = _clean_text(page_text)
            if page_text:
                parts.append(f"Page {index}\n{page_text}")
        text = "\n".join(parts)
        if len(text) < int(os.environ.get("OPINION_PDF_OCR_MIN_CHARS", "80")):
            ocr_text = extract_pdf_text_with_ocr(content)
            if ocr_text:
                text = "\n".join(part for part in [text, ocr_text] if part)
        metadata = getattr(reader, "metadata", None)
        title = ""
        if metadata:
            title = _clean_text(getattr(metadata, "title", "") or "", 220)
        if not title:
            title = _clean_text(Path(urlparse(url).path).name, 220)
        publish_date = _extract_date(url) or _extract_date(text[:1000])
        if not text:
            return PublicPage(url=url, title=title, publish_date=publish_date, status="partially_verified", error="pdf_text_empty")
        return PublicPage(
            url=url,
            title=title,
            source=urlparse(url).netloc,
            publish_date=publish_date,
            text=text,
            status="ok",
        )
    except Exception as exc:
        LOGGER.warning("PDF extraction failed for %s: %s", url, exc)
        return PublicPage(url=url, status="source_unavailable", error=f"pdf_extract_failed: {exc}")


def extract_pdf_text_with_ocr(content: bytes) -> str:
    if os.environ.get("OPINION_ENABLE_PDF_OCR", "true").lower() == "false":
        return ""
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except Exception as exc:
        LOGGER.debug("PDF OCR dependencies unavailable: %s", exc)
        return ""

    try:
        max_pages = int(os.environ.get("OPINION_PDF_OCR_MAX_PAGES", "3"))
        images = convert_from_bytes(content, first_page=1, last_page=max_pages, dpi=180)
        parts: list[str] = []
        for index, image in enumerate(images, start=1):
            try:
                text = pytesseract.image_to_string(image, lang=os.environ.get("OPINION_OCR_LANG", "chi_sim+eng"))
            except Exception as exc:
                LOGGER.debug("PDF OCR page failed page=%s: %s", index, exc)
                text = ""
            text = _clean_text(text)
            if text:
                parts.append(f"OCR Page {index}\n{text}")
        return "\n".join(parts)
    except Exception as exc:
        LOGGER.debug("PDF OCR failed: %s", exc)
        return ""


def extract_page_text(url: str, html_text: str) -> PublicPage:
    title = ""
    m = re.search(r"<title[^>]*>([\s\S]*?)</title>", html_text, re.I)
    if m:
        title = _clean_text(re.sub(r"<[^>]+>", "", m.group(1)), 220)

    source = ""
    for pattern in [
        r"<meta[^>]+property=[\"']og:site_name[\"'][^>]+content=[\"']([^\"']+)",
        r"<meta[^>]+name=[\"']source[\"'][^>]+content=[\"']([^\"']+)",
        r"来源[:：]\s*([^<\s]{2,30})",
    ]:
        m = re.search(pattern, html_text, re.I)
        if m:
            source = _clean_text(m.group(1), 80)
            break

    publish_date = ""
    for pattern in [
        r"<meta[^>]+(?:property|name)=[\"'](?:article:published_time|pubdate|publishdate|date)[\"'][^>]+content=[\"']([^\"']+)",
        r"(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)",
    ]:
        m = re.search(pattern, html_text, re.I)
        if m:
            publish_date = _extract_date(m.group(1))
            if publish_date:
                break

    cleaned = re.sub(r"(?is)<(script|style|noscript|svg|canvas|iframe)[^>]*>.*?</\1>", " ", html_text)
    paragraphs = re.findall(r"(?is)<p[^>]*>(.*?)</p>", cleaned)
    if paragraphs:
        text = "\n".join(_clean_text(re.sub(r"<[^>]+>", " ", p)) for p in paragraphs)
    else:
        body = re.search(r"(?is)<body[^>]*>(.*?)</body>", cleaned)
        raw_body = body.group(1) if body else cleaned
        text = _clean_text(re.sub(r"<[^>]+>", " ", raw_body))

    lines = [_clean_text(line) for line in re.split(r"[\r\n]+", text) if _clean_text(line)]
    text = "\n".join(lines)
    return PublicPage(url=url, title=title, source=source, publish_date=publish_date, text=text)


def _iter_structured_items(raw: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            items.extend(_iter_structured_items(item))
    elif isinstance(raw, dict):
        likely_keys = {
            "title",
            "source",
            "publish_date",
            "date",
            "url",
            "link",
            "summary",
            "snippet",
            "资讯标题",
            "资讯内容",
            "日期",
            "URL",
            "jumpUrl",
            "content",
        }
        raw_keys = set(raw.keys())
        lead_keys = likely_keys - {"content"}
        if (lead_keys & raw_keys) and not raw_keys <= {"type", "text"}:
            items.append(raw)
        for key in ("data", "result", "results", "items", "list", "news", "articles", "records", "text", "content"):
            value = raw.get(key)
            if isinstance(value, str):
                parsed = _try_parse_json_string(value)
                if parsed is not None:
                    items.extend(_iter_structured_items(parsed))
            elif isinstance(value, (list, dict)):
                items.extend(_iter_structured_items(value))
    elif isinstance(raw, str):
        parsed = _try_parse_json_string(raw)
        if parsed is not None:
            items.extend(_iter_structured_items(parsed))
    return items


def _try_parse_json_string(text: str) -> Any:
    text = (text or "").strip()
    if not text or text[0] not in "[{":
        return None
    try:
        return json.loads(text)
    except Exception:
        try:
            return ast.literal_eval(text)
        except Exception:
            return None


def _text_chunks(raw: Any) -> list[str]:
    chunks: list[str] = []
    if isinstance(raw, str):
        chunks.append(raw)
    elif isinstance(raw, dict):
        for value in raw.values():
            chunks.extend(_text_chunks(value))
    elif isinstance(raw, list):
        for value in raw:
            chunks.extend(_text_chunks(value))
    return chunks


def _keywords_from_text(text: str) -> list[str]:
    keywords: list[str] = []
    for term in PUBLIC_NEGATIVE_TERMS + PUBLIC_BOND_TERMS:
        if term in text and term not in keywords:
            keywords.append(term)
    for m in re.finditer(r"[\u4e00-\u9fffA-Za-z0-9]{3,16}", text):
        token = m.group(0)
        if any(skip in token for skip in ("公司", "集团", "有限公司")):
            continue
        if token not in keywords:
            keywords.append(token)
        if len(keywords) >= 6:
            break
    return keywords[:6]


def normalize_lead(item: dict[str, Any], raw_source: str) -> dict[str, Any]:
    title = _clean_text(
        item.get("title")
        or item.get("资讯标题")
        or item.get("name")
        or item.get("headline")
        or item.get("subject")
        or "",
        180,
    )
    date = _extract_date(
        _clean_text(
            item.get("publish_date")
            or item.get("publishTime")
            or item.get("date")
            or item.get("日期")
            or item.get("time")
            or ""
        )
    )
    source = _clean_text(item.get("source") or item.get("media") or item.get("site") or item.get("origin") or "", 80)
    snippet = _clean_text(
        item.get("snippet")
        or item.get("summary")
        or item.get("content")
        or item.get("资讯内容")
        or item.get("abstract")
        or item.get("description")
        or "",
        MAX_SNIPPET_CHARS,
    )
    possible_url = _clean_text(item.get("url") or item.get("URL") or item.get("jumpUrl") or item.get("link") or item.get("href") or "", 500)
    combined = " ".join([title, source, snippet])
    keywords = item.get("keywords") if isinstance(item.get("keywords"), list) else _keywords_from_text(combined)
    return {
        "title": title or _clean_text(snippet, 80),
        "publish_date": date,
        "source": source,
        "snippet": snippet,
        "keywords": [str(k)[:32] for k in keywords[:8]],
        "possible_url": possible_url,
        "raw_source": raw_source,
    }


def parse_text_leads(text: str, raw_source: str, company_name: str) -> list[dict[str, Any]]:
    text = _clean_text(text, MAX_CLUE_TEXT_CHARS * 3)
    if not text:
        return []
    blocks = [b.strip() for b in re.split(r"(?:\n\s*){2,}|(?:\d+[.、]\s*)", text) if b.strip()]
    leads: list[dict[str, Any]] = []
    for block in blocks[:10]:
        url_match = re.search(r"https?://[^\s)）]+", block)
        possible_url = url_match.group(0) if url_match else ""
        date = _extract_date(block)
        source = ""
        m = re.search(r"来源[:：]\s*([^\s，,。；;]{2,40})", block)
        if m:
            source = m.group(1)
        lines = [line.strip(" -|") for line in re.split(r"[。；;\n]", block) if line.strip()]
        title = next((line for line in lines if company_name in line or len(line) >= 8), lines[0] if lines else company_name)
        leads.append(
            normalize_lead(
                {
                    "title": title,
                    "date": date,
                    "source": source,
                    "summary": block,
                    "url": possible_url,
                },
                raw_source,
            )
        )
    return leads


def extract_leads(raw: Any, raw_source: str, company_name: str, max_items: int = 30) -> list[dict[str, Any]]:
    leads: list[dict[str, Any]] = []
    for item in _iter_structured_items(raw):
        lead = normalize_lead(item, raw_source)
        if lead["title"] or lead["snippet"]:
            leads.append(lead)
    if not leads:
        for chunk in _text_chunks(raw):
            leads.extend(parse_text_leads(chunk, raw_source, company_name))
            if len(leads) >= max_items:
                break
    normalized: list[dict[str, Any]] = []
    for lead in leads[:max_items]:
        lead["snippet"] = _clean_text(lead.get("snippet", ""), MAX_SNIPPET_CHARS)
        normalized.append(lead)
    return normalized


def dedupe_leads(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for lead in leads:
        title = _clean_text(lead.get("title", ""))
        snippet = _clean_text(lead.get("snippet", ""))
        if title in {"0", "text", "SEARCH_NEWS", "成功"} or len(title) <= 1:
            continue
        if title.startswith("请检索近") or snippet.startswith("请检索近"):
            continue
        title_key = _normalize_key(lead.get("title", ""))
        source_key = _normalize_key(lead.get("source", ""))
        date_key = lead.get("publish_date", "")
        keyword_key = _normalize_key("".join(lead.get("keywords") or [])[:60])
        key = "|".join([title_key[:80], source_key[:40], date_key, keyword_key[:40]])
        if not key.strip("|"):
            key = _sha_id(_safe_json(lead))
        if key not in merged:
            lead["matched_from"] = [lead.get("raw_source", "")]
            merged[key] = lead
        else:
            src = lead.get("raw_source", "")
            if src and src not in merged[key]["matched_from"]:
                merged[key]["matched_from"].append(src)
            if not merged[key].get("possible_url") and lead.get("possible_url"):
                merged[key]["possible_url"] = lead["possible_url"]
    return list(merged.values())


def make_company_aliases(company_name: str) -> list[str]:
    aliases: list[str] = []
    base = company_name
    suffixes = [
        "\u6709\u9650\u8d23\u4efb\u516c\u53f8",
        "\u80a1\u4efd\u6709\u9650\u516c\u53f8",
        "\u96c6\u56e2\u6709\u9650\u516c\u53f8",
        "\u6709\u9650\u516c\u53f8",
        "\u96c6\u56e2",
        "\u516c\u53f8",
    ]
    for suffix in suffixes:
        if base.endswith(suffix):
            short = base[: -len(suffix)]
            if len(short) >= 4 and not short.endswith("\u6709\u9650"):
                aliases.append(short)
    if len(company_name) >= 6:
        aliases.append(company_name[:6])
    city_invest_aliases = set()
    for name in [company_name] + aliases:
        compact = name.replace("\uff08\u96c6\u56e2\uff09", "").replace("(\u96c6\u56e2)", "").replace("\u96c6\u56e2", "")
        compact = compact.replace("\u57ce\u5e02\u6295\u8d44", "\u57ce\u6295")
        if compact != name and len(compact) >= 4 and not compact.endswith("\u6709\u9650"):
            city_invest_aliases.add(compact)
    aliases.extend(sorted(city_invest_aliases))
    return list(dict.fromkeys(aliases))


def make_company_name_variants(company_name: str) -> list[str]:
    variants = {company_name}
    normalized = company_name.replace("(", "\uff08").replace(")", "\uff09")
    variants.add(normalized)
    variants.add(normalized.replace("\uff08\u96c6\u56e2\uff09", "(\u96c6\u56e2)"))
    variants.add(normalized.replace("\uff08\u96c6\u56e2\uff09", "\u96c6\u56e2"))
    variants.add(normalized.replace("\uff08", "").replace("\uff09", ""))
    # Common input alias: "韩城城市投资..." vs formal "韩城市城市投资..."
    m = re.match(r"^([\u4e00-\u9fff]{2,4})(\u57ce\u5e02\u6295\u8d44.*)$", normalized)
    if m and not m.group(1).endswith("\u5e02"):
        variants.add(f"{m.group(1)}\u5e02{m.group(2)}")
    return [v for v in variants if v]


def build_company_search_names(company_name: str, limit: int | None = None) -> list[str]:
    variants = make_company_name_variants(company_name)
    aliases = make_company_aliases(company_name)
    priority_aliases = [alias for alias in aliases if "城投" in alias or "城市投资" in alias]
    names = [company_name] + variants + priority_aliases + aliases
    names = list(dict.fromkeys([name for name in names if name]))
    if limit is not None:
        return names[:limit]
    return names


def _split_extra_terms(raw: str) -> list[str]:
    return [_clean_text(part, 80) for part in re.split(r"[,，;；|]+", raw or "") if _clean_text(part, 80)]


def _is_official_source(url: str = "", source: str = "") -> bool:
    domain = urlparse(url or "").netloc.lower()
    source_text = source or ""
    return any(hint in domain for hint in OFFICIAL_DOMAIN_HINTS) or any(
        term in source_text for term in ("交易所", "中国货币网", "上海清算所", "交易商协会", "法院", "政府", "监管")
    )


def is_batch_window(now: datetime | None = None) -> bool:
    now = now or datetime.now(BATCH_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=BATCH_TZ)
    else:
        now = now.astimezone(BATCH_TZ)
    window_minutes = max(1, int(os.environ.get("OPINION_BATCH_WINDOW_MINUTES", "60")))
    allowed_weekdays = {
        int(day.strip())
        for day in os.environ.get("OPINION_BATCH_WEEKDAYS", "3,6").split(",")
        if day.strip().isdigit()
    }
    minutes_since_midnight = now.hour * 60 + now.minute
    return now.weekday() in allowed_weekdays and minutes_since_midnight < window_minutes


def next_scheduled_run(now: datetime | None = None) -> str:
    now = now or datetime.now(BATCH_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=BATCH_TZ)
    else:
        now = now.astimezone(BATCH_TZ)
    allowed_weekdays = sorted(
        int(day.strip())
        for day in os.environ.get("OPINION_BATCH_WEEKDAYS", "3,6").split(",")
        if day.strip().isdigit()
    ) or [3, 6]
    for offset in range(0, 14):
        candidate_date = now.date() + timedelta(days=offset)
        if candidate_date.weekday() not in allowed_weekdays:
            continue
        candidate = datetime.combine(candidate_date, datetime.min.time(), tzinfo=BATCH_TZ)
        if candidate > now:
            return candidate.isoformat(timespec="seconds")
    candidate_date = now.date() + timedelta(days=14)
    return datetime.combine(candidate_date, datetime.min.time(), tzinfo=BATCH_TZ).isoformat(timespec="seconds")


def live_verification_allowed(batch_context: bool = False) -> bool:
    if batch_context:
        return True
    return os.environ.get("OPINION_ALLOW_DIRECT_VERIFY", "false").lower() == "true"


def entity_match(
    company_name: str,
    text: str,
    title: str = "",
    credit_code: str = "",
    province: str = "",
    city: str = "",
    aliases: list[str] | None = None,
    url: str = "",
    source: str = "",
) -> dict[str, Any]:
    corpus = f"{title}\n{text}"
    compact_corpus = re.sub(r"\s+", "", corpus)
    basis: list[str] = []
    compact_company_name = re.sub(r"\s+", "", company_name)
    if company_name in corpus or compact_company_name in compact_corpus:
        basis.append("公开网页正文或标题出现企业全名")
        return {"is_target_company": True, "match_level": "strong", "basis": basis}

    credit_code = re.sub(r"[^0-9A-Z]", "", (credit_code or "").upper())
    if credit_code and credit_code in re.sub(r"[^0-9A-Z]", "", corpus.upper()):
        basis.append("公开网页正文或标题出现匹配的统一社会信用代码")
        return {"is_target_company": True, "match_level": "strong", "basis": basis}

    name_variants = [variant for variant in make_company_name_variants(company_name) if variant != company_name]
    candidate_aliases = list(dict.fromkeys((aliases or []) + name_variants + make_company_aliases(company_name)))
    alias_hit = next((alias for alias in candidate_aliases if alias and len(alias) >= 3 and alias in corpus), "")
    if alias_hit:
        auxiliary: list[str] = []
        if province and province in corpus:
            auxiliary.append(f"省份匹配：{province}")
        if city and city in corpus:
            auxiliary.append(f"城市匹配：{city}")
        if re.search(r"(控股股东|实际控制人|出资人|股东)[^。；;]{0,40}", corpus):
            auxiliary.append("出现控股股东/出资人等股权层级信息")
        if re.search(r"\b\d{6}\.(?:SH|SZ|IB)\b|\b\d{6}\b", corpus, re.I):
            auxiliary.append("出现债券代码")
        if "债券简称" in corpus or "债项简称" in corpus:
            auxiliary.append("出现债券简称字段")
        if _is_official_source(url, source):
            auxiliary.append("来源属于官方披露或监管渠道")
        auxiliary = list(dict.fromkeys(auxiliary))
        if len(auxiliary) >= 2:
            basis.append(f"出现企业简称“{alias_hit}”")
            basis.append("同时出现至少两个辅助条件：" + "、".join(auxiliary[:4]))
            return {"is_target_company": True, "match_level": "medium", "basis": basis}
        generic_terms = [term for term in ("公告", "评级", "债券", "国资", "城投", "集团") if term in corpus]
        if generic_terms:
            basis.append(f"仅出现企业简称“{alias_hit}”和泛化词：" + "、".join(generic_terms[:4]))
        else:
            basis.append(f"仅出现企业简称“{alias_hit}”，缺少至少两个辅助确认条件")
        return {"is_target_company": False, "match_level": "weak", "basis": basis}

    basis.append("未在公开网页中发现企业全名、统一社会信用代码或可确认简称")
    return {"is_target_company": False, "match_level": "weak", "basis": basis}


def classify_source_type(url: str, source: str, title: str) -> str:
    text = f"{url} {source} {title}".lower()
    if any(x in text for x in ("court.gov.cn", "执行", "被执行")):
        return "司法执行"
    if any(x in text for x in ("处罚", "监管", "creditchina", "gsxt", "gov.cn")):
        return "监管处罚"
    if any(x in text for x in ("sse.com.cn", "szse.cn", "chinabond", "债券", "募集说明书", "nafmii")):
        return "债券公告"
    if any(x in text for x in ("公告", "披露", "交易所")):
        return "官方公告"
    if any(x in text for x in ("finance", "eastmoney", "sina", "yicai", "caixin", "证券")):
        return "财经媒体"
    if any(x in text for x in ("日报", "晚报", "地方", "news")):
        return "地方媒体"
    return "其他"


def public_source_priority(url: str) -> tuple[int, str]:
    domain = urlparse(url).netloc.lower()
    if any(hint in domain for hint in OFFICIAL_DOMAIN_HINTS):
        return (0, domain)
    if any(hint in domain for hint in ("dfcfw.com", "eastmoney.com", "sina.com.cn", "cls.cn", "jiemian.com")):
        return (1, domain)
    if any(hint in domain for hint in ("mp.weixin.qq.com", "toutiao.com", "163.com")):
        return (3, domain)
    return (2, domain)


def generate_public_queries(company_name: str, lead: dict[str, Any]) -> list[str]:
    title = lead.get("title", "")
    source = lead.get("source", "")
    date = lead.get("publish_date", "")
    keywords = [k for k in (lead.get("keywords") or []) if k]
    queries = []
    if title:
        queries.append(f"{company_name} {title}")
    if keywords:
        queries.append(f"{company_name} {' '.join(keywords[:3])}")
    if source:
        queries.append(f"{company_name} {source}")
    if date and keywords:
        queries.append(f"{company_name} {date} {' '.join(keywords[:2])}")
    queries.append(f"{company_name} {' '.join(PUBLIC_NEGATIVE_TERMS)}")
    queries.append(f"{company_name} {' '.join(PUBLIC_BOND_TERMS)}")
    deduped = []
    seen = set()
    for query in queries:
        query = _clean_text(query, 220)
        if query and query not in seen:
            seen.add(query)
            deduped.append(query)
    return deduped[:MAX_SEARCH_QUERIES_PER_LEAD]


def generate_discovery_queries(company_name: str) -> list[str]:
    name_limit = int(os.environ.get("OPINION_DISCOVERY_NAME_LIMIT", "8"))
    names = build_company_search_names(company_name, limit=name_limit)
    query_templates = [
        "{name} 逾期债务 未能按期支付 债券",
        "{name} 累计未能按期支付债务",
        "{name} 关于未能按期支付债务的公告",
        "{name} 行政处罚 被执行人 诉讼 债券违约",
        "{name} 工程款 拖欠 诉讼",
        "{name} 净利 暴跌 监管通报",
        "{name} 通报批评 募集资金 信息披露",
    ]
    query_templates.extend(f"{{name}} {term}" for term in _split_extra_terms(os.environ.get("OPINION_EXTRA_DISCOVERY_TERMS", "")))
    queries: list[str] = []
    for name in names:
        for template in query_templates:
            queries.append(template.format(name=name))
    return [_clean_text(q, 220) for q in queries]


def save_full_text(company_name: str, result: dict[str, Any], full_text: str) -> str:
    return get_full_text_store().save(company_name, result, full_text)


def get_full_text(full_text_id: str) -> dict[str, Any] | None:
    return get_full_text_store().get(full_text_id)


def _sanitize_result_text(result: dict[str, Any]) -> dict[str, Any]:
    for key in ("summary", "source_excerpt", "text_excerpt"):
        text = result.get(key, "")
        for phrase in FORBIDDEN_ANALYSIS_PATTERNS:
            text = text.replace(phrase, "")
        result[key] = text
    return result


def dedupe_verified_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        results,
        key=lambda result: (
            public_source_priority(result.get("url", ""))[0],
            0 if result.get("verification_status") == "verified" else 1,
        ),
    )
    deduped_by_event: dict[str, dict[str, Any]] = {}
    for result in ordered:
        event_key = result_event_key(result)
        if event_key not in deduped_by_event:
            deduped_by_event[event_key] = result

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_titles: set[str] = set()
    for result in deduped_by_event.values():
        title_key = _normalize_key(result.get("title", ""))
        key = result.get("id") or result.get("url") or _sha_id(result.get("title", ""), result.get("source", ""))
        if key in seen:
            continue
        if title_key and title_key in seen_titles:
            continue
        seen.add(key)
        if title_key:
            seen_titles.add(title_key)
        deduped.append(result)
    return deduped


def result_event_key(result: dict[str, Any]) -> str:
    text = f"{result.get('title', '')} {result.get('source_excerpt', result.get('summary', ''))} {result.get('text_excerpt', '')}"
    normalized_title = _normalize_key(result.get("title", ""))[:36]
    date = (result.get("publish_date") or "")[:10]
    amounts = re.findall(r"\d+(?:\.\d+)?\s*(?:亿元|亿|万元|万)", text)
    numeric_signature = "".join(re.findall(r"\d+", text))[:16]
    event_terms = [
        term
        for term in (
            PUBLIC_NEGATIVE_TERMS
            + PUBLIC_BOND_TERMS
            + ["失信", "限制消费", "通报批评", "工程款", "未能按期支付", "债务", "监管措施", "警示函"]
        )
        if term in text
    ]
    if amounts or event_terms or numeric_signature:
        return "|".join([date, ",".join(amounts[:3]) or numeric_signature, ",".join(event_terms[:5])])
    return "|".join([date, normalized_title])


async def collect_mcp_leads(company_name: str, lookback_days: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        from mcp.client import MCPClient
    except Exception as exc:
        return [], _make_empty_status("failed", str(exc))

    leads: list[dict[str, Any]] = []
    errors: list[str] = []
    servers = [s.strip() for s in os.environ.get("OPINION_MCP_SERVERS", "news").split(",") if s.strip()]
    for server in servers:
        try:
            tool_name = os.environ.get(f"OPINION_MCP_TOOL_{server}", "search_news")
            client = MCPClient(server)
            query = f"{company_name} 舆情 行政处罚 被执行人 诉讼 债券公告 评级 近{lookback_days}天"
            today = _batch_now().date()
            start_date = today - timedelta(days=lookback_days)
            args = {
                "query": query,
                "dateRange": f"近{lookback_days}天",
                "time_start": start_date.isoformat(),
                "time_end": today.isoformat(),
            }
            raw = None
            last_error: Exception | None = None
            for attempt, delay_seconds in enumerate([0, 5, 15], start=1):
                if delay_seconds:
                    await asyncio.sleep(delay_seconds)
                try:
                    await asyncio.to_thread(GLOBAL_MCP_RATE_LIMITER.wait)
                    raw = await asyncio.to_thread(client.call_tool, tool_name, args)
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    LOGGER.warning("MCP request failed server=%s attempt=%s: %s", server, attempt, exc)
            if last_error is not None:
                raise last_error
            leads.extend(extract_leads(raw, "mcp", company_name))
        except Exception as exc:
            errors.append(f"{server}: {exc}")
            LOGGER.warning("MCP clue collection failed for %s: %s", server, exc)
    status = "success" if leads else ("failed" if errors else "skipped")
    return leads, {"status": status, "result_count": len(leads), "error": "; ".join(errors)}


async def collect_skill_leads(company_name: str, lookback_days: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    module_path = BASE_DIR / "mx_skills" / "mx-finance-search" / "scripts" / "get_data.py"
    if not module_path.exists():
        return [], _make_empty_status("failed", "mx-finance-search script not found")
    try:
        module = _load_module(module_path, "mx_finance_search_runtime")
        query = (
            f"请检索近{lookback_days}天“{company_name}”相关舆情线索。"
            "只返回线索列表，不要返回大段全文；每条尽量包含标题、发布时间、来源、摘要、关键词和链接。"
            "关注行政处罚、被执行人、诉讼、债券公告、评级下调、违约、逾期、重大事项。"
        )
        query_func = module.query_financial_news
        query_kwargs = {"query": query, "output_dir": BASE_DIR / "miaoxiang" / "mx_finance_search", "save_to_file": False}
        if inspect.iscoroutinefunction(query_func):
            raw = await query_func(**query_kwargs)
        else:
            raw = await asyncio.to_thread(query_func, **query_kwargs)
            if inspect.isawaitable(raw):
                raw = await raw
        leads = extract_leads(raw, "skill", company_name)
        raw_error = raw.get("error", "") if isinstance(raw, dict) else ""
        status = "success" if leads else ("failed" if raw_error else "success")
        return leads, {"status": status, "result_count": len(leads), "error": raw_error}
    except Exception as exc:
        LOGGER.warning("Skill clue collection failed: %s", exc)
        return [], _make_empty_status("failed", str(exc))


def verify_lead_with_public_pages(
    company_name: str,
    lead: dict[str, Any],
    searcher: PublicSearcher,
    fetcher: PageFetcher,
    include_full_text: bool,
    lookback_days: int,
    company_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]], int]:
    company_context = company_context or {"company_name": company_name}
    searched_count = 0
    rejected: list[dict[str, Any]] = []
    urls: list[dict[str, str]] = []
    pending_candidate: dict[str, Any] | None = None
    if lead.get("possible_url"):
        urls.append({"title": lead.get("title", ""), "url": lead["possible_url"]})

    source_unavailable = False
    for query in generate_public_queries(company_name, lead):
        try:
            results = searcher.search(query)
            searched_count += len(results)
            urls.extend(results)
        except Exception as exc:
            LOGGER.warning("Public search failed for query %s: %s", query, exc)
            continue

    urls.sort(key=lambda item: public_source_priority(item.get("url", "")))
    seen_urls: set[str] = set()
    for item in urls:
        url = item.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        page = fetcher.fetch(url)
        if page.status == "source_unavailable":
            source_unavailable = True
            continue

        page_title = page.title or item.get("title", "") or lead.get("title", "")
        if page_title.lower().endswith(".pdf") and (lead.get("title") or item.get("title")):
            page_title = lead.get("title") or item.get("title", "")
        page_source = page.source or lead.get("source", "") or urlparse(page.url).netloc
        page_date = page.publish_date or lead.get("publish_date", "")
        if not _within_lookback(page_date, lookback_days):
            rejected.append({"title": page_title, "source": page_source, "reason": "outside_lookback_days"})
            continue

        match = entity_match(
            company_name,
            page.text,
            page_title,
            credit_code=company_context.get("credit_code", ""),
            province=company_context.get("province", ""),
            city=company_context.get("city", ""),
            aliases=company_context.get("aliases", []),
            url=page.url,
            source=page_source,
        )
        title_overlap = _normalize_key(lead.get("title", ""))[:20]
        verifies_title = bool(title_overlap and title_overlap in _normalize_key(page_title + page.text))
        event_terms = [k for k in (lead.get("keywords") or []) if k in PUBLIC_NEGATIVE_TERMS + PUBLIC_BOND_TERMS]
        verifies_event = any(term in (page_title + page.text) for term in event_terms)
        page_text = page.text.strip()

        if match["is_target_company"] and match["match_level"] in ("strong", "medium"):
            if not verifies_title and not verifies_event:
                rejected.append({"title": page_title, "source": page_source, "reason": "entity_matched_but_event_not_verified"})
                continue
            status = "verified" if page_text and verifies_title else "partially_verified"
            source_excerpt = _clean_text(page_text or lead.get("snippet", ""), 300)
            result = {
                "id": _sha_id(company_name, page.url, page_title),
                "title": page_title,
                "publish_date": page_date,
                "source": page_source,
                "source_type": classify_source_type(page.url, page_source, page_title),
                "url": page.url,
                "source_excerpt": source_excerpt,
                "text_excerpt": _clean_text(page_text or lead.get("snippet", ""), MAX_EXCERPT_CHARS),
                "full_text_id": "",
                "full_text_available": bool(page_text and include_full_text),
                "matched_from": sorted(set((lead.get("matched_from") or []) + ["public_search"])),
                "verification_status": status,
                "entity_match": match,
            }
            if include_full_text and page_text:
                result["full_text_id"] = save_full_text(company_name, result, page_text)
            return _sanitize_result_text(result), None, rejected, searched_count

        if match["match_level"] == "weak":
            if pending_candidate is None:
                pending_candidate = {
                    "title": lead.get("title") or page_title,
                    "publish_date": page_date,
                    "source": page_source,
                    "snippet": _clean_text(page_text or lead.get("snippet", ""), 300),
                    "reason": "entity_match_weak",
                    "matched_from": sorted(set((lead.get("matched_from") or []) + ["public_search"])),
                }
            continue

        rejected.append({"title": page_title, "source": page_source, "reason": "not_target_company_or_low_relevance"})

    if pending_candidate is not None:
        return None, pending_candidate, rejected, searched_count

    reason = "source_unavailable" if source_unavailable else "no_public_result_found"
    pending = {
        "title": lead.get("title", ""),
        "publish_date": lead.get("publish_date", ""),
        "source": lead.get("source", ""),
        "snippet": lead.get("snippet", ""),
        "reason": reason,
        "matched_from": lead.get("matched_from", [lead.get("raw_source", "")]),
    }
    return None, pending, rejected, searched_count


async def run_cross_verification(
    params: dict[str, Any] | None,
    searcher: PublicSearcher | None = None,
    fetcher: PageFetcher | None = None,
    batch_context: bool = False,
) -> dict[str, Any]:
    config = validate_params(params)
    company_name = config["company_name"]
    if not live_verification_allowed(batch_context):
        raise PermissionError("live opinion verification is disabled; use the opinion batch service")
    warnings: list[str] = []
    data_sources = {
        "mcp": _make_empty_status(),
        "skill": _make_empty_status(),
        "public_search": _make_empty_status(),
    }

    lead_batches: list[list[dict[str, Any]]] = []
    tasks = []
    if config["sources"]["mcp"]:
        tasks.append(("mcp", collect_mcp_leads(company_name, config["lookback_days"])))
    if config["sources"]["skill"]:
        tasks.append(("skill", collect_skill_leads(company_name, config["lookback_days"])))

    for source_name, task in tasks:
        leads, status = await task
        data_sources[source_name] = status
        lead_batches.append(leads)

    leads = dedupe_leads([lead for batch in lead_batches for lead in batch])
    leads = leads[: max(config["max_results"] * 3, config["max_results"])]

    verified_results: list[dict[str, Any]] = []
    pending_results: list[dict[str, Any]] = []
    rejected_results: list[dict[str, Any]] = []

    if not config["sources"]["public_search"]:
        data_sources["public_search"] = _make_empty_status("skipped", "public_search disabled")
        for lead in leads[: config["max_results"]]:
            pending_results.append(
                {
                    "title": lead.get("title", ""),
                    "publish_date": lead.get("publish_date", ""),
                    "source": lead.get("source", ""),
                    "snippet": lead.get("snippet", ""),
                    "reason": "public_search_disabled",
                    "matched_from": lead.get("matched_from", [lead.get("raw_source", "")]),
                }
            )
    else:
        searcher = searcher or PublicSearcher()
        fetcher = fetcher or PageFetcher()
        official_searcher = OfficialSourceSearcher()
        public_count = 0
        public_error = ""
        discovery_leads: list[dict[str, Any]] = []
        for item in official_searcher.search(company_name, max_results=int(os.environ.get("OPINION_OFFICIAL_MAX_RESULTS", "20"))):
            discovery_leads.append(
                normalize_lead(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "source": item.get("source", ""),
                        "summary": item.get("title", ""),
                    },
                    "public_search",
                )
            )
        public_count += len(discovery_leads)
        discovery_query_limit = int(os.environ.get("OPINION_DISCOVERY_QUERY_LIMIT", "24"))
        for query in generate_discovery_queries(company_name)[:discovery_query_limit]:
            try:
                results = searcher.search(query)
                public_count += len(results)
                for item in results:
                    discovery_leads.append(
                        normalize_lead(
                            {
                                "title": item.get("title", ""),
                                "url": item.get("url", ""),
                                "summary": item.get("title", ""),
                            },
                            "public_search",
                        )
                    )
            except Exception as exc:
                public_error = str(exc)
                LOGGER.warning("Public discovery search failed for query %s: %s", query, exc)
        leads = dedupe_leads(leads + discovery_leads)
        max_verify_leads = min(
            len(leads),
            max(config["max_results"] * 8, int(os.environ.get("OPINION_MAX_VERIFY_LEADS", str(MAX_VERIFICATION_LEADS)))),
        )
        concurrency = max(1, int(os.environ.get("OPINION_VERIFY_CONCURRENCY", str(DEFAULT_VERIFY_CONCURRENCY))))
        semaphore = asyncio.Semaphore(concurrency)

        async def verify_one(lead: dict[str, Any]):
            async with semaphore:
                try:
                    verified, pending, rejected, count = await asyncio.to_thread(
                        verify_lead_with_public_pages,
                        company_name,
                        lead,
                        searcher,
                        fetcher,
                        config["include_full_text"],
                        config["lookback_days"],
                        config,
                    )
                    return verified, pending, rejected, count, ""
                except Exception as exc:
                    LOGGER.exception("Public verification failed for lead %s", lead.get("title"))
                    pending = {
                        "title": lead.get("title", ""),
                        "publish_date": lead.get("publish_date", ""),
                        "source": lead.get("source", ""),
                        "snippet": lead.get("snippet", ""),
                        "reason": "public_search_failed",
                        "matched_from": lead.get("matched_from", [lead.get("raw_source", "")]),
                    }
                    return None, pending, [], 0, str(exc)

        results = await asyncio.gather(*(verify_one(lead) for lead in leads[:max_verify_leads]))
        for verified, pending, rejected, count, error in results:
            public_count += count
            if error:
                public_error = error
            if verified:
                verified_results.append(verified)
            elif pending:
                pending_results.append(pending)
            rejected_results.extend(rejected)
        data_sources["public_search"] = {
            "status": "success" if public_count or verified_results or pending_results else "failed",
            "result_count": public_count,
            "error": public_error,
        }

    if not leads:
        warnings.append("no_clue_results_found")
    if config["sources"]["public_search"] and not verified_results:
        warnings.append("no_public_result_found")
    if any(ds["status"] == "failed" for ds in data_sources.values()):
        warnings.append("one_or_more_sources_failed")

    return {
        "company_name": company_name,
        "search_time": _now_iso(),
        "lookback_days": config["lookback_days"],
        "data_sources": data_sources,
        "verified_results": dedupe_verified_results(verified_results)[: config["max_results"]],
        "pending_verification_results": pending_results[: max(config["max_results"], 20)],
        "rejected_results": rejected_results[: max(config["max_results"], 20)],
        "warnings": warnings,
    }


class OpinionBatchStore:
    def __init__(self, base_dir: Path = BATCH_DIR) -> None:
        self.base_dir = base_dir

    @property
    def latest_path(self) -> Path:
        return self.base_dir / "latest.json"

    @property
    def latest_success_path(self) -> Path:
        return self.base_dir / "latest_success.json"

    @property
    def lock_path(self) -> Path:
        return self.base_dir / "batch.lock"

    def _company_result_path(self, batch_id: str, company_name: str) -> Path:
        return self.base_dir / batch_id / f"{_sha_id(company_name)}.json"

    def _company_item_path(self, batch_id: str, company_name: str) -> Path:
        return self.base_dir / batch_id / "items" / f"{_sha_id(company_name)}.json"

    def _batch_status_path(self, batch_id: str) -> Path:
        return self.base_dir / batch_id / "status.json"

    def save_status(self, status: dict[str, Any]) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        status.setdefault("timezone", BATCH_TIMEZONE)
        status.setdefault("next_scheduled_run", next_scheduled_run())
        if status.get("batch_id"):
            status["latest_batch_id"] = status.get("batch_id", "")
            status["latest_batch_status"] = status.get("status", "")
        success_status = self.get_latest_success_status()
        if status.get("status") in {"success", "partial_success"}:
            success_status = {
                "latest_success_batch_id": status.get("batch_id", ""),
                "latest_success_finished_at": status.get("finished_at", ""),
            }
            self.latest_success_path.write_text(json.dumps(success_status, ensure_ascii=False, indent=2), encoding="utf-8")
        status.setdefault("latest_success_batch_id", success_status.get("latest_success_batch_id", ""))
        status.setdefault("latest_success_finished_at", success_status.get("latest_success_finished_at", ""))
        status.setdefault("latest_effective_batch_id", status.get("latest_success_batch_id", ""))
        status.setdefault("latest_effective_finished_at", status.get("latest_success_finished_at", ""))
        if status.get("batch_id"):
            batch_status_path = self._batch_status_path(status["batch_id"])
            batch_status_path.parent.mkdir(parents=True, exist_ok=True)
            batch_status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        self.latest_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_latest_status(self) -> dict[str, Any]:
        if not self.latest_path.exists():
            status = {
                "status": "none",
                "batch_id": "",
                "latest_batch_id": "",
                "latest_batch_status": "none",
                "latest_success_batch_id": "",
                "latest_success_finished_at": "",
                "latest_effective_batch_id": "",
                "latest_effective_finished_at": "",
                "started_at": "",
                "finished_at": "",
                "companies_total": 0,
                "timezone": BATCH_TIMEZONE,
                "next_scheduled_run": next_scheduled_run(),
            }
            status.update(self.get_latest_success_status())
            return status
        status = json.loads(self.latest_path.read_text(encoding="utf-8"))
        status.setdefault("timezone", BATCH_TIMEZONE)
        status.setdefault("next_scheduled_run", next_scheduled_run())
        status.setdefault("latest_batch_id", status.get("batch_id", ""))
        status.setdefault("latest_batch_status", status.get("status", ""))
        success_status = self.get_latest_success_status()
        status.setdefault("latest_success_batch_id", success_status.get("latest_success_batch_id", ""))
        status.setdefault("latest_success_finished_at", success_status.get("latest_success_finished_at", ""))
        status.setdefault("latest_effective_batch_id", status.get("latest_success_batch_id", ""))
        status.setdefault("latest_effective_finished_at", status.get("latest_success_finished_at", ""))
        return status

    def get_latest_success_status(self) -> dict[str, str]:
        if not self.latest_success_path.exists():
            return {"latest_success_batch_id": "", "latest_success_finished_at": ""}
        return json.loads(self.latest_success_path.read_text(encoding="utf-8"))

    def iter_success_statuses(self) -> list[dict[str, Any]]:
        statuses: dict[str, dict[str, Any]] = {}
        for status_path in self.base_dir.glob("*/status.json"):
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if status.get("status") in {"success", "partial_success"} and status.get("batch_id"):
                statuses[status["batch_id"]] = status
        latest_success = self.get_latest_success_status().get("latest_success_batch_id", "")
        if latest_success and latest_success not in statuses:
            status_path = self._batch_status_path(latest_success)
            if status_path.exists():
                try:
                    statuses[latest_success] = json.loads(status_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
        return sorted(
            statuses.values(),
            key=lambda item: (item.get("finished_at", ""), item.get("batch_id", "")),
            reverse=True,
        )

    def save_company_item_status(self, batch_id: str, company_name: str, item_status: dict[str, Any]) -> None:
        path = self._company_item_path(batch_id, company_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        item_status.setdefault("company_name", company_name)
        item_status.setdefault("batch_id", batch_id)
        item_status.setdefault("timezone", BATCH_TIMEZONE)
        path.write_text(json.dumps(item_status, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_company_result(self, batch_id: str, company_name: str, result: dict[str, Any]) -> str:
        path = self._company_result_path(batch_id, company_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def get_company_result(self, company_name: str, batch_id: str | None = None) -> dict[str, Any] | None:
        latest = self.get_latest_status()
        batch_id = batch_id or latest.get("batch_id", "")
        if not batch_id:
            return None
        path = self._company_result_path(batch_id, company_name)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def acquire_run_lock(self, batch_id: str) -> bool:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(json.dumps({"batch_id": batch_id, "created_at": _batch_now_iso()}, ensure_ascii=False))
        return True

    def release_run_lock(self, batch_id: str) -> None:
        if not self.lock_path.exists():
            return
        try:
            payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if not payload.get("batch_id") or payload.get("batch_id") == batch_id:
            self.lock_path.unlink(missing_ok=True)

    def read_run_lock(self) -> dict[str, Any]:
        if not self.lock_path.exists():
            return {}
        try:
            return json.loads(self.lock_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def is_lock_stale(self) -> bool:
        payload = self.read_run_lock()
        created_at = _parse_batch_time(payload.get("created_at", ""))
        if not created_at:
            return True
        timeout_hours = max(1.0, _env_float("OPINION_BATCH_TIMEOUT_HOURS", 12.0))
        return _batch_now() - created_at > timedelta(hours=timeout_hours)

    def cleanup_stale_lock(self, latest_status: dict[str, Any]) -> bool:
        if not self.lock_path.exists():
            return False
        if latest_status.get("status") != "running" or self.is_lock_stale():
            self.lock_path.unlink(missing_ok=True)
            return True
        return False

    def mark_stale_failed(self, status: dict[str, Any]) -> dict[str, Any]:
        stale_status = dict(status)
        stale_status["status"] = "stale_failed"
        stale_status["latest_batch_status"] = "stale_failed"
        stale_status["finished_at"] = _batch_now_iso()
        stale_status["reason"] = "batch timeout, marked as stale"
        self.save_status(stale_status)
        self.lock_path.unlink(missing_ok=True)
        return stale_status


def get_batch_store() -> OpinionBatchStore:
    return OpinionBatchStore(BATCH_DIR)


def get_latest_batch_status() -> dict[str, Any]:
    return get_batch_store().get_latest_status()


def _parse_batch_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=BATCH_TZ)
    return parsed.astimezone(BATCH_TZ)


def _is_running_status_stale(status: dict[str, Any], now: datetime | None = None) -> bool:
    started_at = _parse_batch_time(status.get("started_at", ""))
    if not started_at:
        return True
    now = now or _batch_now()
    timeout_hours = max(1.0, _env_float("OPINION_BATCH_TIMEOUT_HOURS", 12.0))
    return now.astimezone(BATCH_TZ) - started_at > timedelta(hours=timeout_hours)


def get_cached_opinion_result(company_name: str, batch_id: str | None = None) -> dict[str, Any] | None:
    company_name = _clean_text(company_name)
    if not company_name:
        raise ValueError("company_name is required")
    store = get_batch_store()
    latest = store.get_latest_status()
    if batch_id:
        data_batch_id = batch_id
        data_status = store.get_latest_status() if batch_id == latest.get("batch_id") else {}
        result = store.get_company_result(company_name, data_batch_id)
    else:
        data_batch_id = ""
        data_status = {}
        result = None
        for candidate_status in store.iter_success_statuses():
            candidate_batch_id = candidate_status.get("batch_id", "")
            candidate_result = store.get_company_result(company_name, candidate_batch_id)
            if candidate_result:
                data_batch_id = candidate_batch_id
                data_status = candidate_status
                result = candidate_result
                break
    if not result:
        return None
    if not batch_id:
        is_updating = latest.get("status") == "running"
        result = dict(result)
        result["cache_status"] = {
            "is_updating": is_updating,
            "displaying_previous_batch": bool(is_updating and data_batch_id and data_batch_id != latest.get("batch_id", "")),
            "running_batch_id": latest.get("batch_id", "") if is_updating else "",
            "data_batch_id": data_batch_id,
            "data_batch_status": data_status.get("status", ""),
            "data_is_fallback_from_older_batch": bool(
                latest.get("latest_success_batch_id") and data_batch_id and data_batch_id != latest.get("latest_success_batch_id")
            ),
            "latest_batch_id": latest.get("batch_id", ""),
            "latest_batch_status": latest.get("status", ""),
            "latest_success_batch_id": latest.get("latest_success_batch_id", ""),
            "timezone": BATCH_TIMEZONE,
        }
    return result


async def run_opinion_batch(
    companies: list[dict[str, Any] | str],
    default_params: dict[str, Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    default_params = default_params or {}
    store = get_batch_store()
    batch_id = _batch_now().strftime("%Y%m%d%H%M%S")
    latest = store.get_latest_status()
    if latest.get("status") == "running":
        if not _is_running_status_stale(latest):
            return {
                "status": "skipped",
                "reason": "previous_batch_still_running",
                "running_batch_id": latest.get("batch_id", ""),
                "timezone": BATCH_TIMEZONE,
                "latest_batch_id": latest.get("batch_id", ""),
                "latest_batch_status": latest.get("status", ""),
                "latest_success_batch_id": latest.get("latest_success_batch_id", ""),
                "latest_success_finished_at": latest.get("latest_success_finished_at", ""),
                "next_scheduled_run": next_scheduled_run(),
            }
        store.mark_stale_failed(latest)
    else:
        store.cleanup_stale_lock(latest)

    if not store.acquire_run_lock(batch_id):
        latest = store.get_latest_status()
        if store.cleanup_stale_lock(latest) and store.acquire_run_lock(batch_id):
            pass
        else:
            lock_payload = store.read_run_lock()
            running_batch_id = latest.get("batch_id", "") if latest.get("status") == "running" else lock_payload.get("batch_id", "")
            return {
                "status": "skipped",
                "reason": "previous_batch_still_running",
                "running_batch_id": running_batch_id,
                "timezone": BATCH_TIMEZONE,
                "latest_batch_id": latest.get("batch_id", ""),
                "latest_batch_status": latest.get("status", ""),
                "latest_success_batch_id": latest.get("latest_success_batch_id", ""),
                "latest_success_finished_at": latest.get("latest_success_finished_at", ""),
                "next_scheduled_run": next_scheduled_run(),
            }
    if not force and not is_batch_window():
        status = {
            "status": "skipped",
            "batch_id": batch_id,
            "started_at": _batch_now_iso(),
            "finished_at": _batch_now_iso(),
            "companies_total": len(companies),
            "total_companies": len(companies),
            "companies_completed": 0,
            "completed_companies": 0,
            "companies_failed": 0,
            "failed_companies": 0,
            "error": "outside_batch_window",
            "timezone": BATCH_TIMEZONE,
            "next_scheduled_run": next_scheduled_run(),
        }
        store.save_status(status)
        store.release_run_lock(batch_id)
        return status

    status = {
        "status": "running",
        "batch_id": batch_id,
        "started_at": _batch_now_iso(),
        "finished_at": "",
        "companies_total": len(companies),
        "total_companies": len(companies),
        "companies_completed": 0,
        "completed_companies": 0,
        "companies_failed": 0,
        "failed_companies": 0,
        "errors": [],
        "result_files": {},
        "timezone": BATCH_TIMEZONE,
        "next_scheduled_run": next_scheduled_run(),
    }
    store.save_status(status)
    concurrency = max(1, int(os.environ.get("OPINION_BATCH_COMPANY_CONCURRENCY", "1")))
    semaphore = asyncio.Semaphore(concurrency)

    async def run_one(company_item: dict[str, Any] | str) -> tuple[str, dict[str, Any] | None, str]:
        params = dict(default_params)
        if isinstance(company_item, str):
            params["company_name"] = company_item
        else:
            params.update(company_item)
        name = _clean_text(params.get("company_name"))
        async with semaphore:
            try:
                store.save_company_item_status(
                    batch_id,
                    name,
                    {"status": "running", "started_at": _batch_now_iso(), "finished_at": "", "error": ""},
                )
                result = await run_cross_verification(params, batch_context=True)
                path = store.save_company_result(batch_id, name, result)
                store.save_company_item_status(
                    batch_id,
                    name,
                    {"status": "success", "started_at": result.get("search_time", ""), "finished_at": _batch_now_iso(), "error": "", "result_file": path},
                )
                return name, result, path
            except Exception as exc:
                LOGGER.exception("Opinion batch company failed: %s", name)
                store.save_company_item_status(
                    batch_id,
                    name,
                    {"status": "failed", "started_at": "", "finished_at": _batch_now_iso(), "error": str(exc)},
                )
                return name, None, str(exc)

    try:
        tasks = [asyncio.create_task(run_one(item)) for item in companies]
        for completed in asyncio.as_completed(tasks):
            name, result, info = await completed
            if result is None:
                status["companies_failed"] += 1
                status["failed_companies"] = status["companies_failed"]
                status["errors"].append({"company_name": name, "error": info})
            else:
                status["companies_completed"] += 1
                status["completed_companies"] = status["companies_completed"]
                status["result_files"][name] = info
            store.save_status(status)

        if status["companies_completed"] == len(companies):
            status["status"] = "success"
        elif status["companies_failed"] == len(companies):
            status["status"] = "failed"
        else:
            status["status"] = "partial_success"
        status["latest_batch_status"] = status["status"]
        status["finished_at"] = _batch_now_iso()
        store.save_status(status)
        return status
    finally:
        store.release_run_lock(batch_id)


def run_cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Enterprise opinion cross verification")
    parser.add_argument("company_name")
    parser.add_argument("--lookback-days", type=int, default=365)
    parser.add_argument("--max-results", type=int, default=20)
    parser.add_argument("--no-full-text", action="store_true")
    parser.add_argument("--batch-context", action="store_true")
    args = parser.parse_args()
    params = {
        "company_name": args.company_name,
        "lookback_days": args.lookback_days,
        "max_results": args.max_results,
        "include_full_text": not args.no_full_text,
    }
    result = asyncio.run(run_cross_verification(params, batch_context=args.batch_context))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_cli()
