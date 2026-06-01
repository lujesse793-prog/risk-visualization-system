"""
Post-loan analysis report executor.

Searches 中国货币网, 上海证券交易所, and 深圳证券交易所 for an enterprise's
latest public financial disclosures, classifies results by file type, and returns
structured JSON matching the output schema.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import html
import json
import re
import shutil
import subprocess
import time
import zlib
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen
from urllib.parse import urlencode, urljoin, urlparse


# ── document classification ──────────────────────────────────────────────────

ANNUAL_REPORT_KEYWORDS = [
    "年度报告", "年报", "年度财务报表", "年度审计报告", "经审计财务报告",
    "合并及母公司财务报表", "合并财务报表", "母公司财务报表", "审计报告",
    "财务报表及附注", "年度财务报表及附注",
]

SEMI_ANNUAL_KEYWORDS = [
    "半年度报告", "半年报", "半年度财务报表",
]

QUARTERLY_KEYWORDS = [
    "第一季度报告", "一季度报告", "第一季度财务报表", "一季度财务报表",
    "第三季度报告", "三季度报告", "季度财务报表",
]

PROSPECTUS_KEYWORDS = [
    "募集说明书", "更新募集说明书", "债券募集说明书",
    "中期票据募集说明书", "超短期融资券募集说明书",
]

RATING_REPORT_KEYWORDS = [
    "主体评级报告", "债项评级报告", "跟踪评级报告", "信用评级报告", "评级报告",
]

EXCLUDE_KEYWORDS = [
    "付息公告", "兑付公告", "发行结果公告", "持有人会议公告", "法律意见书",
    "受托管理事务报告", "临时公告", "发行方案", "承诺函", "评级结果公告",
]

ALLOWED_DOMAINS = {
    "中国货币网": ["chinamoney.com.cn"],
    "上海证券交易所": ["sse.com.cn", "bond.sse.com.cn"],
    "深圳证券交易所": ["szse.cn"],
}
ALLOWED_FILE_TYPES = {"annual_report", "semi_annual_report", "quarterly_report", "prospectus", "rating_report"}
NO_LATEST_PUBLIC_DATA_MESSAGE = "未有最新公开财务数据披露，无法基于公开资料生成有效贷后分析。"
CHINAMONEY_ORIGIN = "https://www.chinamoney.com.cn"
_CHINAMONEY_OPENER = build_opener(HTTPCookieProcessor())
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _classify_file_type(title: str) -> str | None:
    """Classify a document title into one of the allowed file types."""
    t = title
    # Exclude non-financial-report announcements first
    for kw in EXCLUDE_KEYWORDS:
        if kw in t:
            # 评级结果公告 without full rating report -> unsupported
            if kw == "评级结果公告" and any(rk in t for rk in RATING_REPORT_KEYWORDS):
                continue
            return None  # unsupported
    for kw in SEMI_ANNUAL_KEYWORDS:
        if kw in t:
            return "semi_annual_report"
    for kw in QUARTERLY_KEYWORDS:
        if kw in t:
            return "quarterly_report"
    for kw in ANNUAL_REPORT_KEYWORDS:
        if kw in t:
            return "annual_report"
    for kw in PROSPECTUS_KEYWORDS:
        if kw in t:
            return "prospectus"
    for kw in RATING_REPORT_KEYWORDS:
        if kw in t:
            return "rating_report"
    return None


def _extract_report_period(title: str) -> str:
    """Extract report period (e.g. 2025, 2025Q1, 2025H1) from title."""
    # Match patterns like 2025年, 2025年度, 2025年半年度, 2025年第一季度
    m = re.search(r"(\d{4})\s*年\s*(第[一二三四]季度|半年度|年度)?", title)
    if m:
        year = m.group(1)
        suffix = m.group(2) or ""
        if "一" in suffix:
            return f"{year}Q1"
        if "二" in suffix:
            return f"{year}Q2" if "半" not in suffix else f"{year}H1"
        if "三" in suffix:
            return f"{year}Q3"
        if "四" in suffix:
            return f"{year}Q4"
        if "半" in suffix:
            return f"{year}H1"
        return year
    # Fallback: just year
    m = re.search(r"(\d{4})", title)
    return m.group(1) if m else ""


def _extract_publish_date(raw_item: dict) -> str:
    """Extract publish date from a raw search result item."""
    for key in ("publishDate", "pubDate", "date", "publish_date", "announcementDate"):
        val = raw_item.get(key)
        if val:
            return str(val)[:10]
    return ""


def _date_from_epoch_millis(value: Any) -> str:
    try:
        return datetime.fromtimestamp(int(value) / 1000).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", str(text or ""))).strip()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _decode_http_body(content: bytes, headers: Any) -> bytes:
    encoding = ""
    try:
        encoding = headers.get("Content-Encoding", "") or ""
    except Exception:
        pass
    encoding = encoding.lower()
    if "gzip" in encoding:
        return gzip.decompress(content)
    if "deflate" in encoding:
        try:
            return zlib.decompress(content)
        except zlib.error:
            return zlib.decompress(content, -zlib.MAX_WBITS)
    return content


def _anti_bot_cookie_from_html(text: str) -> str:
    if "EO_Bot_Ssid" not in text or "__tst_status" not in text:
        return ""
    numbers = [int(x) for x in re.findall(r":(\d{6,})", text)]
    ssid_match = re.search(r"([0-9]{8,})\);continue;case\"4\"", text)
    if len(numbers) >= 3 and ssid_match:
        tst_status = sum(numbers[:3])
        return f"__tst_status={tst_status}#; EO_Bot_Ssid={ssid_match.group(1)}"
    return ""


def _fetch_url(url: str, referer: str = "", timeout: int = 30, retries: int = 2) -> dict[str, Any]:
    last_error = ""
    current = url
    extra_cookie = ""
    for attempt in range(retries + 1):
        try:
            headers = {
                "User-Agent": BROWSER_UA,
                "Accept": "text/html,application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate",
            }
            if referer:
                headers["Referer"] = referer
            if extra_cookie:
                headers["Cookie"] = extra_cookie
            req = Request(current, headers=headers)
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                content = _decode_http_body(raw, resp.headers)
                final_url = resp.geturl()
                text = content[:2000].decode("utf-8", errors="ignore")
                anti_bot_cookie = _anti_bot_cookie_from_html(text)
                if anti_bot_cookie and not extra_cookie:
                    extra_cookie = anti_bot_cookie
                    last_error = "anti_bot_cookie_retry"
                    time.sleep(0.5)
                    continue
                return {
                    "ok": True,
                    "url": url,
                    "final_url": final_url,
                    "status": getattr(resp, "status", 200),
                    "headers": dict(resp.headers.items()),
                    "content": content,
                    "text": content.decode("utf-8", errors="ignore"),
                }
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.4 * (attempt + 1))
    return {"ok": False, "url": url, "final_url": current, "error": last_error, "content": b"", "text": ""}


def _extract_first_json_like_items(raw_result: dict[str, Any]) -> list[dict[str, Any]]:
    containers: list[Any] = []
    raw = raw_result.get("raw") if isinstance(raw_result, dict) else {}
    if isinstance(raw, dict):
        containers.extend([raw, raw.get("data"), raw.get("result"), raw.get("llmSearchResponse"), raw.get("searchResponse")])
    content = raw_result.get("content", "") if isinstance(raw_result, dict) else ""
    if isinstance(content, str) and content.strip().startswith(("{", "[")):
        try:
            containers.append(json.loads(content))
        except Exception:
            pass
    items: list[dict[str, Any]] = []
    seen: set[int] = set()

    def walk(value: Any) -> None:
        if id(value) in seen:
            return
        seen.add(id(value))
        if isinstance(value, list):
            if all(isinstance(x, dict) for x in value):
                for x in value:
                    items.append(x)
            else:
                for x in value:
                    walk(x)
        elif isinstance(value, dict):
            for key in ("items", "list", "records", "pageItems", "resultList", "data"):
                if key in value:
                    walk(value[key])
            if any(k in value for k in ("title", "Title", "announcementTitle", "url", "sourceUrl", "announcementUrl", "jump_url")):
                items.append(value)

    for container in containers:
        walk(container)
    return items


def _text_candidates(content: str) -> list[dict[str, Any]]:
    if not content:
        return []
    candidates: list[dict[str, Any]] = []
    url_pattern = re.compile(r"(https?://[^\s\]\)\"'<>]+)")
    for match in url_pattern.finditer(content):
        url = match.group(1).rstrip("，。；;")
        start = max(0, match.start() - 120)
        prefix = _strip_html(content[start:match.start()])
        title = prefix.splitlines()[-1].strip(" -:：") if prefix else url
        candidates.append({"title": title, "url": url, "sourceUrl": url, "_candidate_source": "content_text"})
    return candidates


def _candidate_url(item: dict[str, Any]) -> str:
    for key in ("pdfUrl", "attachmentUrl", "pdf_url", "downloadUrl", "attachUrl", "fileUrl", "docUrl"):
        val = item.get(key)
        if isinstance(val, str) and val:
            return val
    for key in ("source_url", "detail_url", "url", "jump_url", "jumpUrl", "announcementUrl", "sourceUrl", "link"):
        val = item.get(key)
        if isinstance(val, str) and val:
            return val
    return ""


def _absolute_url(url: str, base_url: str) -> str:
    url = html.unescape(str(url or "").strip())
    if not url or url.startswith("javascript:"):
        return ""
    return urljoin(base_url, url)


def _extract_pdf_candidates_from_html(detail_html: str, detail_url: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(url: str, title: str = "") -> None:
        absolute = _absolute_url(url, detail_url)
        if not absolute or absolute in seen:
            return
        if ".pdf" not in absolute.lower() and "fileDownLoad.do" not in absolute:
            return
        seen.add(absolute)
        candidates.append({"url": absolute, "title": _strip_html(title) or Path(urlparse(absolute).path).name})

    for match in re.finditer(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", detail_html, re.I | re.S):
        href, body = match.groups()
        add(href, body)
    for field in ("downloadUrl", "attachUrl", "fileUrl", "docUrl", "pdfUrl", "attachmentUrl"):
        for match in re.finditer(rf"[\"']{field}[\"']\s*[:=]\s*[\"']([^\"']+)[\"']", detail_html, re.I):
            add(match.group(1), field)
    for match in re.finditer(r"fileDownLoad\.do\?[^\"'<>\\\s]+", detail_html, re.I):
        add(match.group(0), "中国货币网附件")
    for match in re.finditer(r"(?:contentId=|contentId['\"]?\s*[:=]\s*['\"]?)(\d{6,})", detail_html, re.I):
        add(_chinamoney_pdf_url(match.group(1)), "中国货币网附件")
    return candidates


def _attachment_score(candidate: dict[str, str], wanted_type: str) -> int:
    text = f"{candidate.get('title', '')} {candidate.get('url', '')}"
    score = 0
    priority = {
        "annual_report": ANNUAL_REPORT_KEYWORDS,
        "semi_annual_report": SEMI_ANNUAL_KEYWORDS,
        "quarterly_report": QUARTERLY_KEYWORDS,
        "prospectus": PROSPECTUS_KEYWORDS,
        "rating_report": RATING_REPORT_KEYWORDS,
    }.get(wanted_type, [])
    for kw in priority:
        if kw in text:
            score += 100
    for kw in EXCLUDE_KEYWORDS:
        if kw in text:
            score -= 200
    if text.lower().endswith(".pdf"):
        score += 10
    return score


def _select_pdf_candidate(candidates: list[dict[str, str]], file_type: str) -> dict[str, str] | None:
    if not candidates:
        return None
    return sorted(candidates, key=lambda c: _attachment_score(c, file_type), reverse=True)[0]


def _resolve_pdf_from_detail(doc: dict[str, Any]) -> dict[str, Any]:
    source_url = str(doc.get("source_url") or doc.get("url") or "")
    pdf_url = str(doc.get("pdf_url") or "")
    candidates: list[dict[str, str]] = []
    resolved_detail_url = source_url

    if pdf_url:
        candidates.append({"url": _absolute_url(pdf_url, source_url or pdf_url), "title": doc.get("attachment_title") or doc.get("title") or ""})
    else:
        direct = _candidate_url(doc)
        if direct and (direct.lower().endswith(".pdf") or "fileDownLoad.do" in direct):
            candidates.append({"url": _absolute_url(direct, source_url or direct), "title": doc.get("attachment_title") or doc.get("title") or ""})

    if not candidates:
        doc = _fill_chinamoney_pdf_from_known_url(doc)
        if doc.get("pdf_url"):
            candidates.append({"url": doc["pdf_url"], "title": doc.get("attachment_title") or doc.get("title") or ""})

    if not candidates and source_url:
        fetched = _fetch_url(source_url, referer=source_url)
        doc["_detail_fetch_status"] = "success" if fetched.get("ok") else "failed"
        doc["_detail_fetch_error"] = fetched.get("error", "")
        resolved_detail_url = fetched.get("final_url") or source_url
        doc["resolved_detail_url"] = resolved_detail_url
        if fetched.get("ok"):
            content_type = (fetched.get("headers") or {}).get("Content-Type", "")
            body = fetched.get("content") or b""
            if "pdf" in content_type.lower() or body.lstrip().startswith(b"%PDF"):
                candidates.append({"url": resolved_detail_url, "title": doc.get("attachment_title") or doc.get("title") or ""})
            else:
                candidates.extend(_extract_pdf_candidates_from_html(fetched.get("text") or "", resolved_detail_url))

    selected = _select_pdf_candidate(candidates, doc.get("file_type", ""))
    doc["resolved_detail_url"] = resolved_detail_url
    doc["pdf_url_candidates"] = candidates
    if selected:
        doc["pdf_url"] = selected["url"]
        if selected.get("title"):
            doc["attachment_title"] = doc.get("attachment_title") or selected["title"]
    elif source_url or pdf_url:
        doc["skipped_reason"] = "pdf_attachment_not_found"
    return doc


def _verify_pdf_subject(doc: dict[str, Any], enterprise_name: str) -> dict[str, Any]:
    if doc.get("_skip_subject_verification"):
        return doc
    local_path = doc.get("local_pdf_path")
    verification = doc.get("entity_verification") or {}
    if not local_path or not Path(local_path).exists():
        verification.update({
            "input_name": enterprise_name,
            "is_same_subject": False,
            "confidence": "low",
            "verification_evidence": "PDF 未成功下载，无法校验主体",
        })
        doc["entity_verification"] = verification
        return doc
    try:
        import fitz  # type: ignore
        with fitz.open(local_path) as pdf:
            text = pdf[0].get_text("text")[:5000] if len(pdf) else ""
    except Exception:
        try:
            from pypdf import PdfReader  # type: ignore
            reader = PdfReader(local_path)
            text = (reader.pages[0].extract_text() or "")[:5000] if reader.pages else ""
        except Exception:
            text = ""
    normalized = re.sub(r"\s+", "", text)
    candidates = _subject_candidates(enterprise_name)
    matched = next((candidate for candidate in candidates if candidate and candidate in normalized), "")
    if matched:
        verification.update({
            "input_name": enterprise_name,
            "matched_name_in_document": matched,
            "matched_role": verification.get("matched_role") or "披露主体",
            "is_same_subject": True,
            "relationship_to_target": "same_subject" if matched == enterprise_name else "name_alias_or_short_name",
            "verification_evidence": f"PDF 首页文本包含主体名称：{matched}",
            "confidence": "high" if matched == enterprise_name else "medium",
        })
    else:
        title_blob = re.sub(r"\s+", "", f"{doc.get('title', '')} {doc.get('attachment_title', '')}")
        official_title_match = (
            doc.get("source_platform") == "中国货币网"
            and any(candidate in title_blob for candidate in candidates)
            and doc.get("pdf_download_status") == "success"
        )
        if official_title_match:
            verification.update({
                "input_name": enterprise_name,
                "matched_name_in_document": doc.get("title") or doc.get("attachment_title") or "",
                "matched_role": verification.get("matched_role") or "披露主体",
                "is_same_subject": True,
                "relationship_to_target": "same_subject",
                "verification_evidence": "中国货币网官方披露标题匹配且 PDF 已成功下载；当前环境未能从 PDF 首页提取文本，按中置信度进入后续深度解析。",
                "confidence": "medium",
            })
        else:
            verification.update({
                "input_name": enterprise_name,
                "is_same_subject": False,
                "relationship_to_target": "",
                "verification_evidence": "PDF 首页未识别到企业全称或可接受简称",
                "confidence": "low",
            })
            doc["needs_deep_pdf_parse"] = False
            doc["document_status"] = "subject_mismatch"
            doc["skipped_reason"] = "pdf_first_page_subject_unconfirmed"
    doc["entity_verification"] = verification
    return doc


def _domain_to_platform(url: str) -> str:
    """Map a URL domain to one of the three allowed platforms."""
    if not url:
        return ""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return ""
    host_lower = host.lower()
    for platform, domains in ALLOWED_DOMAINS.items():
        for d in domains:
            if d in host_lower:
                return platform
    return ""


def _extract_enterprise_name(query: str) -> str:
    """Extract enterprise name from query string or JSON."""
    query = query.strip()
    if query.startswith("{"):
        try:
            parsed = json.loads(query)
            name = parsed.get("enterprise_name") or parsed.get("company_name") or ""
            if name:
                return name.strip()
        except json.JSONDecodeError:
            repaired = query.replace('\\"', '"')
            try:
                parsed = json.loads(repaired)
                name = parsed.get("enterprise_name") or parsed.get("company_name") or ""
                if name:
                    return name.strip()
            except json.JSONDecodeError:
                match = re.search(r"enterprise_name\s*[:=]\s*['\"]?([^,'\"}]+)", query)
                if match:
                    return match.group(1).strip()
    return query


def _subject_candidates(enterprise_name: str) -> list[str]:
    """Build conservative same-subject match candidates."""
    candidates = [enterprise_name]
    normalized = enterprise_name
    for suffix in ["有限责任公司", "股份有限公司", "集团有限公司", "有限公司"]:
        if normalized.endswith(suffix):
            candidates.append(normalized[: -len(suffix)])
            break
    if "集团" in normalized:
        candidates.append(normalized.replace("集团", ""))
    seen = []
    for candidate in candidates:
        candidate = re.sub(r"\s+", "", candidate)
        if len(candidate) >= 4 and candidate not in seen:
            seen.append(candidate)
    return seen


def _is_same_subject_candidate(enterprise_name: str, item: dict[str, Any], title_text: str) -> bool:
    """Use only results whose visible metadata still points to the requested enterprise."""
    try:
        raw_text = json.dumps(item, ensure_ascii=False)
    except TypeError:
        raw_text = title_text
    normalized_text = re.sub(r"\s+", "", f"{title_text} {raw_text}")
    return any(candidate in normalized_text for candidate in _subject_candidates(enterprise_name))


def _http_json(url: str, method: str = "GET", data: dict[str, Any] | None = None, timeout: int = 20) -> dict[str, Any]:
    body = urlencode(data or {}).encode("utf-8") if data is not None else None
    headers = {
        "User-Agent": BROWSER_UA,
        "Referer": f"{CHINAMONEY_ORIGIN}/chinese/qwjsn/",
        "Origin": CHINAMONEY_ORIGIN,
        "X-Requested-With": "XMLHttpRequest",
    }
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    req = Request(url, data=body, method=method, headers=headers)
    opener = _CHINAMONEY_OPENER if "chinamoney.com.cn" in url else None
    with (opener.open(req, timeout=timeout) if opener else urlopen(req, timeout=timeout)) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    return json.loads(raw)


def _fetch_json_url(url: str, referer: str = "", timeout: int = 20) -> dict[str, Any]:
    fetched = _fetch_url(url, referer=referer or CHINAMONEY_ORIGIN, timeout=timeout, retries=1)
    if fetched.get("ok"):
        return json.loads(fetched.get("text") or "{}")
    curl = shutil.which("curl") or shutil.which("curl.exe")
    if curl and "chinamoney.com.cn" in url:
        proc = subprocess.run(
            [
                curl,
                "-L",
                "-s",
                "-D",
                "-",
                "--max-time",
                str(timeout),
                "-H",
                "User-Agent: Mozilla/5.0",
                "-H",
                f"Referer: {referer or CHINAMONEY_ORIGIN}",
                url,
            ],
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout:
            output = proc.stdout.decode("utf-8", errors="ignore")
            marker = output.find('{"head"')
            if marker < 0:
                output = proc.stdout.decode("gb18030", errors="ignore")
                marker = output.find('{"head"')
            body = output[marker:].strip() if marker >= 0 else output.split("\r\n\r\n")[-1].strip()
            return json.loads(body)
    raise RuntimeError(fetched.get("error") or "json_fetch_failed")


def _chinamoney_pdf_url(content_id: str, mode: str = "open") -> str:
    return (
        f"{CHINAMONEY_ORIGIN}/dqs/cm-s-notice-query/fileDownLoad.do"
        f"?mode={mode}&contentId={content_id}&priority=0"
    )


def _chinamoney_detail_url(content_id: str) -> str:
    try:
        data = _http_json(
            f"{CHINAMONEY_ORIGIN}/dqs/rest/cm-s-notice-query/contentInfo",
            method="POST",
            data={"ctnId": content_id},
        )
        records = data.get("records") or []
        if records and records[0].get("path"):
            return urljoin(CHINAMONEY_ORIGIN, records[0]["path"])
    except Exception:
        pass
    return ""


def _fill_chinamoney_pdf_from_known_url(doc: dict[str, Any]) -> dict[str, Any]:
    """If a ChinaMoney detail/download URL is already present, derive the PDF URL."""
    source_url = str(doc.get("source_url") or doc.get("url") or doc.get("pdf_url") or "")
    if "chinamoney.com.cn" not in source_url:
        return doc
    match = re.search(r"(?:contentId=|/)(\d{6,})(?:\.html|&|$)", source_url)
    if not match:
        return doc
    content_id = match.group(1)
    doc["pdf_url"] = doc.get("pdf_url") or _chinamoney_pdf_url(content_id)
    doc["source_url"] = doc.get("source_url") or _chinamoney_detail_url(content_id)
    return doc


def _query_chinamoney_official(enterprise_name: str, channel_name: str) -> dict[str, Any] | None:
    """Fallback to ChinaMoney's own public site search when the upstream search misses PDF links."""
    if channel_name != "中国货币网":
        return None

    finance_repo_url = (
        f"{CHINAMONEY_ORIGIN}/ags/ms/cm-u-notice-issue/financeRepo?"
        f"year=&type=&orgName={urlencode({'q': enterprise_name})[2:]}"
        "&pageSize=30&pageNo=1&inextp=3,5&limit=1"
    )
    try:
        data = _fetch_json_url(finance_repo_url, referer=f"{CHINAMONEY_ORIGIN}/chinese/zqcwbg/")
        records = data.get("records") or []
        matched: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in records:
            content_id = str(item.get("contentId") or item.get("id") or "")
            title = _strip_html(item.get("title") or "")
            if not content_id or content_id in seen_ids:
                continue
            if not _is_same_subject_candidate(enterprise_name, item, title):
                continue
            file_type = _classify_file_type(title)
            if file_type is None:
                continue
            seen_ids.add(content_id)
            detail_url = urljoin(CHINAMONEY_ORIGIN, item.get("draftPath") or _chinamoney_detail_url(content_id) or "")
            matched.append({
                "title": title,
                "attachment_title": f"{title}.pdf",
                "file_type": file_type,
                "report_period": _extract_report_period(title),
                "publish_date": str(item.get("releaseDate") or "")[:10],
                "url": detail_url,
                "source_url": detail_url,
                "pdf_url": _chinamoney_pdf_url(content_id),
                "source_platform": "中国货币网",
                "entity_match_result": "matched",
                "used_for_main_analysis": file_type == "annual_report",
                "used_as_supplement": file_type != "annual_report",
                "document_status": "",
                "entity_verification": {
                    "input_name": enterprise_name,
                    "matched_name_in_document": title,
                    "matched_role": "披露主体",
                    "is_same_subject": True,
                    "relationship_to_target": "same_subject",
                    "verification_evidence": "中国货币网债券财务报告列表标题精确匹配，下载后继续复核 PDF 首页",
                    "confidence": "medium",
                },
            })
        if matched:
            return {
                "source_name": "中国货币网",
                "searched": True,
                "search_modes": ["中国货币网债券财务报告接口", "平台官网二次确认"],
                "keywords_used": [enterprise_name],
                "total_results": data.get("data", {}).get("total") or len(records),
                "scanned_result_count": len(records),
                "matched_documents": len(matched),
                "selected_documents": matched,
                "skipped_documents": [],
                "skipped_reason": [],
                "download_status": "not_applicable",
                "parse_status": "not_applicable",
                "parse_failed_reason": "",
                "latest_document_publish_date": matched[0]["publish_date"] if matched else "",
                "latest_report_period": matched[0]["report_period"] if matched else "",
                "status": "ok",
                "note": "通过中国货币网债券财务报告官方接口获取披露文件和 PDF 下载地址",
                "query_runs": [{
                    "keyword": enterprise_name,
                    "search_scope": "中国货币网债券财务报告",
                    "search_column": "发行人/披露主体",
                    "total_results": data.get("data", {}).get("total") or len(records),
                    "scanned_result_count": len(records),
                    "matched_documents": len(matched),
                    "annual_report_found": any(d["file_type"] == "annual_report" for d in matched),
                    "matched_titles": [d["title"] for d in matched],
                    "selected_titles": [d["title"] for d in matched],
                    "skipped_titles": [],
                    "matched_items": len(matched),
                    "note": "official_chinamoney_finance_repo",
                }],
            }
    except Exception:
        pass

    try:
        # ChinaMoney initializes an anti-bot token before search; this mirrors the public page.
        try:
            req = Request(
                f"{CHINAMONEY_ORIGIN}/chinese/qwjsn/",
                headers={"User-Agent": BROWSER_UA},
            )
            with _CHINAMONEY_OPENER.open(req, timeout=10) as resp:
                resp.read(256)
        except Exception:
            pass
        key = "==AO3QVZSV0VzkWNYdjSwhjW"[::-1]
        try:
            _http_json(f"{CHINAMONEY_ORIGIN}/dqs/rest/cm-u-rbt/apply", method="POST", data={"key": key}, timeout=10)
        except Exception:
            pass
        lt = _http_json(f"{CHINAMONEY_ORIGIN}/lss/rest/cm-s-account/getLT?type=0", method="POST")
        token = lt.get("data") or {}
        if not token.get("UT") or not token.get("sign"):
            return None

        query_texts = [
            f"{enterprise_name} 2025 年度报告",
            f"{enterprise_name} 年度报告",
            enterprise_name,
        ]
        matched: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for query_text in query_texts:
            params = {
                "sort": "date",
                "text": query_text,
                "date": "all",
                "field": "title",
                "start": "",
                "end": "",
                "pageIndex": "1",
                "pageSize": "50",
                "public": "false",
                "infoLevel": token["UT"],
                "sign": token["sign"],
                "channelIdStr": "2556",
                "nodeLevel": "",
                "op": "top",
                "searchAfter": "",
            }
            url = f"{CHINAMONEY_ORIGIN}/ses/rest/cm-u-notice-ses-cn/query?{urlencode(params)}"
            data = _http_json(url, method="POST")
            items = (((data.get("data") or {}).get("result") or {}).get("pageItems") or [])
            for item in items:
                content_id = str(item.get("id") or "")
                if not content_id or content_id in seen_ids:
                    continue
                title = _strip_html(item.get("title") or "")
                file_names = item.get("fileNames") or []
                attachment_title = _strip_html(file_names[0]) if file_names else ""
                combined_title = f"{title} {attachment_title}"
                if not _is_same_subject_candidate(enterprise_name, item, combined_title):
                    continue
                file_type = _classify_file_type(combined_title)
                if file_type is None:
                    continue
                seen_ids.add(content_id)
                detail_url = _chinamoney_detail_url(content_id)
                matched.append({
                    "title": title,
                    "attachment_title": attachment_title,
                    "file_type": file_type,
                    "report_period": _extract_report_period(combined_title),
                    "publish_date": _date_from_epoch_millis(item.get("releaseDate")),
                    "url": detail_url,
                    "source_url": detail_url,
                    "pdf_url": _chinamoney_pdf_url(content_id),
                    "source_platform": "中国货币网",
                    "entity_match_result": "matched",
                    "used_for_main_analysis": file_type == "annual_report",
                    "used_as_supplement": file_type != "annual_report",
                    "document_status": "",
                    "entity_verification": {
                        "input_name": enterprise_name,
                        "matched_name_in_document": title or attachment_title,
                        "matched_role": "发行人",
                        "is_same_subject": True,
                        "verification_evidence": "中国货币网公开检索结果标题/附件名匹配",
                        "confidence": "medium",
                    },
                })
            if matched:
                break
            time.sleep(0.2)

        return {
            "source_name": "中国货币网",
            "searched": True,
            "search_modes": ["中国货币网公开检索", "按标题/正文"],
            "keywords_used": query_texts,
            "total_results": len(matched),
            "scanned_result_count": 50,
            "matched_documents": len(matched),
            "selected_documents": matched,
            "skipped_documents": [],
            "skipped_reason": [],
            "download_status": "not_applicable",
            "parse_status": "not_applicable",
            "parse_failed_reason": "",
            "latest_document_publish_date": matched[0]["publish_date"] if matched else "",
            "latest_report_period": matched[0]["report_period"] if matched else "",
            "status": "ok" if matched else "empty",
            "note": "通过中国货币网公开检索补齐附件下载地址" if matched else "中国货币网公开检索未命中可用附件",
            "query_runs": [{
                "keyword": " / ".join(query_texts),
                "search_scope": "中国货币网",
                "search_column": "按标题/正文",
                "total_results": len(matched),
                "scanned_result_count": 50,
                "matched_documents": len(matched),
                "annual_report_found": any(d["file_type"] == "annual_report" for d in matched),
                "matched_titles": [d["title"] for d in matched],
                "selected_titles": [d["title"] for d in matched],
                "skipped_titles": [],
                "matched_items": len(matched),
                "note": "fallback_official_chinamoney",
            }],
        }
    except Exception as exc:
        return {
            "source_name": "中国货币网",
            "searched": False,
            "search_modes": ["中国货币网公开检索"],
            "keywords_used": [enterprise_name],
            "total_results": 0,
            "scanned_result_count": 0,
            "matched_documents": 0,
            "selected_documents": [],
            "skipped_documents": [],
            "skipped_reason": [f"official_chinamoney_search_failed: {exc}"],
            "download_status": "error",
            "parse_status": "not_applicable",
            "parse_failed_reason": "",
            "latest_document_publish_date": "",
            "latest_report_period": "",
            "status": "error",
            "note": f"official_chinamoney_search_failed: {exc}",
            "query_runs": [],
        }


# ── channel search ───────────────────────────────────────────────────────────

def _load_search_module():
    """Load the mx-finance-search module via importlib (module path has hyphens)."""
    import importlib.util, sys
    module_name = "post_loan_mx_finance_search.scripts.get_data"
    if module_name in sys.modules:
        module = sys.modules[module_name]
        if hasattr(module, "query_financial_news"):
            return module
        del sys.modules[module_name]
    file_path = Path(__file__).resolve().parent.parent.parent / "mx-finance-search" / "scripts" / "get_data.py"
    if not file_path.exists():
        raise RuntimeError(f"mx-finance-search dependency not found: {file_path.as_posix()}")
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load mx-finance-search from {file_path.as_posix()}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    if not hasattr(module, "query_financial_news"):
        sys.modules.pop(module_name, None)
        raise RuntimeError("mx-finance-search missing query_financial_news")
    return module


class PlatformAdapter:
    source_platform = ""

    def __init__(self, enterprise_name: str, output_dir: Path):
        self.enterprise_name = enterprise_name
        self.output_dir = output_dir

    async def search(self) -> dict[str, Any]:
        raw_result = await self._candidate_search()
        items = _extract_first_json_like_items(raw_result)
        items.extend(_text_candidates(raw_result.get("content", "")))
        return self._build_search_result(raw_result, items)

    async def _candidate_search(self) -> dict[str, Any]:
        search_mod = _load_search_module()
        query_financial_news = getattr(search_mod, "query_financial_news", None)
        if query_financial_news is None:
            raise RuntimeError("mx-finance-search missing query_financial_news")
        query_text = f"{self.enterprise_name} {self.source_platform} 年报 审计报告 募集说明书 评级报告"
        return await query_financial_news(query=query_text, output_dir=self.output_dir, save_to_file=False)

    def _item_to_document(self, item: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        title = _strip_html(item.get("title") or item.get("Title") or item.get("announcementTitle") or item.get("name") or "")
        attachment_title = _strip_html(item.get("attachmentTitle") or item.get("attachment_title") or item.get("fileName") or "")
        combine_title = f"{title} {attachment_title}"
        source_url = _candidate_url(item)
        if not source_url:
            return None, {
                "title": title,
                "file_type": "unknown",
                "source_url": "",
                "pdf_url": "",
                "skipped_reason": "candidate_without_url",
            }
        if not _is_same_subject_candidate(self.enterprise_name, item, combine_title):
            return None, {
                "title": title,
                "file_type": "unknown",
                "source_url": source_url,
                "pdf_url": "",
                "skipped_reason": "subject_mismatch",
            }
        file_type = _classify_file_type(combine_title)
        if file_type is None:
            return None, {
                "title": title,
                "file_type": "unsupported",
                "source_url": source_url,
                "pdf_url": "",
                "skipped_reason": "unsupported_file_type",
            }
        platform = _domain_to_platform(source_url)
        if platform and platform != self.source_platform:
            return None, {
                "title": title,
                "file_type": file_type,
                "source_url": source_url,
                "pdf_url": "",
                "skipped_reason": "wrong_source_platform",
            }
        doc = {
            "title": title,
            "attachment_title": attachment_title,
            "file_type": file_type,
            "report_period": _extract_report_period(combine_title),
            "publish_date": _extract_publish_date(item) or _date_from_epoch_millis(item.get("releaseDate")),
            "url": source_url,
            "source_url": source_url,
            "pdf_url": item.get("pdfUrl") or item.get("attachmentUrl") or item.get("pdf_url") or "",
            "source_platform": self.source_platform,
            "entity_match_result": "matched",
            "used_for_main_analysis": file_type == "annual_report",
            "used_as_supplement": file_type != "annual_report",
            "document_status": "",
            "entity_verification": {
                "input_name": self.enterprise_name,
                "matched_name_in_document": title,
                "matched_role": "披露主体",
                "is_same_subject": True,
                "relationship_to_target": "same_subject",
                "verification_evidence": "搜索结果元数据匹配，待下载 PDF 首页复核",
                "confidence": "medium",
            },
        }
        return doc, None

    def _build_search_result(self, raw_result: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
        error = raw_result.get("error")
        if error:
            return self._error_result(str(error))
        matched_documents: list[dict[str, Any]] = []
        skipped_documents: list[dict[str, Any]] = []
        for item in items[:50]:
            if not isinstance(item, dict):
                continue
            doc, skipped = self._item_to_document(item)
            if doc:
                matched_documents.append(doc)
            elif skipped:
                skipped_documents.append(skipped)
        if not matched_documents:
            official = self.search_official()
            if official and official.get("matched_documents"):
                return official
        return {
            "source_name": self.source_platform,
            "searched": True,
            "search_modes": ["searchNews候选发现", "平台官网二次确认"],
            "keywords_used": [self.enterprise_name],
            "total_results": len(items),
            "scanned_result_count": min(len(items), 50),
            "matched_documents": len(matched_documents),
            "selected_documents": matched_documents,
            "skipped_documents": skipped_documents,
            "skipped_reason": [],
            "download_status": "not_applicable",
            "parse_status": "not_applicable",
            "parse_failed_reason": "",
            "latest_document_publish_date": matched_documents[0]["publish_date"] if matched_documents else "",
            "latest_report_period": matched_documents[0]["report_period"] if matched_documents else "",
            "status": "ok" if matched_documents else "empty",
            "note": "",
            "raw_result": _json_safe(raw_result),
            "query_runs": [{
                "keyword": f"{self.enterprise_name} {self.source_platform}",
                "search_scope": "全部",
                "search_column": "候选发现",
                "total_results": len(items),
                "scanned_result_count": min(len(items), 50),
                "matched_documents": len(matched_documents),
                "annual_report_found": any(d["file_type"] == "annual_report" for d in matched_documents),
                "matched_titles": [d["title"] for d in matched_documents],
                "selected_titles": [d["title"] for d in matched_documents],
                "skipped_titles": [d["title"] for d in skipped_documents],
                "matched_items": len(matched_documents),
                "note": "",
            }],
        }

    def _error_result(self, error: str) -> dict[str, Any]:
        return {
            "source_name": self.source_platform,
            "searched": False,
            "search_modes": [],
            "keywords_used": [self.enterprise_name],
            "total_results": 0,
            "scanned_result_count": 0,
            "matched_documents": 0,
            "selected_documents": [],
            "skipped_documents": [],
            "skipped_reason": [error],
            "download_status": "error",
            "parse_status": "error",
            "parse_failed_reason": error,
            "latest_document_publish_date": "",
            "latest_report_period": "",
            "status": "error",
            "note": error,
            "query_runs": [],
        }

    def search_official(self) -> dict[str, Any] | None:
        return None


class ChinaMoneyAdapter(PlatformAdapter):
    source_platform = "中国货币网"

    async def search(self) -> dict[str, Any]:
        official = self.search_official()
        if official and official.get("matched_documents"):
            return official
        raw_result = await self._candidate_search()
        items = _extract_first_json_like_items(raw_result)
        items.extend(_text_candidates(raw_result.get("content", "")))
        return self._build_search_result(raw_result, items)

    def search_official(self) -> dict[str, Any] | None:
        return _query_chinamoney_official(self.enterprise_name, self.source_platform)


class SSEBondAdapter(PlatformAdapter):
    source_platform = "上海证券交易所"


class SZSEFixedIncomeAdapter(PlatformAdapter):
    source_platform = "深圳证券交易所"


def _adapter_for_channel(enterprise_name: str, channel_name: str, output_dir: Path) -> PlatformAdapter:
    if channel_name == "中国货币网":
        return ChinaMoneyAdapter(enterprise_name, output_dir)
    if channel_name == "上海证券交易所":
        return SSEBondAdapter(enterprise_name, output_dir)
    if channel_name == "深圳证券交易所":
        return SZSEFixedIncomeAdapter(enterprise_name, output_dir)
    return PlatformAdapter(enterprise_name, output_dir)


async def _search_channel(
    enterprise_name: str,
    channel_name: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Search one channel for the enterprise's financial disclosures."""
    return await _adapter_for_channel(enterprise_name, channel_name, output_dir).search()


def _parse_query_payload(query: str) -> dict[str, Any]:
    query = (query or "").strip()
    if query.startswith("{"):
        try:
            parsed = json.loads(query)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {"enterprise_name": _extract_enterprise_name(query)}
    return {"enterprise_name": query}


def _find_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "orchestrator_pkg").is_dir() and (parent / "skills").is_dir():
            return parent
    return current.parents[3]


def _default_pdf_dir(task_id: str) -> Path:
    return _find_project_root() / "data" / "pdfs" / task_id


def _doc_id(enterprise_name: str, title: str, index: int) -> str:
    raw = f"{enterprise_name}|{title}|{index}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_sample_pdf(path: Path) -> None:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfgen import canvas

        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        c = canvas.Canvas(str(path), pagesize=A4)
        c.setFont("STSong-Light", 11)
        pages = [
            [
                "合并资产负债表",
                "单位：亿元",
                "项目 2025 2024",
                "资产总计 100 90",
                "负债合计 60 50",
                "所有者权益合计 40 40",
                "货币资金 20 18",
                "短期借款 10 9",
                "一年内到期的非流动负债 5 4",
                "长期借款 20 18",
                "应付债券 15 12",
                "流动资产合计 50 45",
                "流动负债合计 25 22",
                "存货 10 9",
                "其他应收款 8 7",
            ],
            [
                "合并利润表",
                "单位：亿元",
                "项目 2025 2024",
                "营业收入 30 28",
                "净利润 3 2",
                "财务费用 1 1",
            ],
            [
                "合并现金流量表",
                "单位：亿元",
                "项目 2025 2024",
                "经营活动产生的现金流量净额 4 3",
            ],
        ]
        for page_lines in pages:
            y = 800
            for line in page_lines:
                c.drawString(72, y, line)
                y -= 20
            c.showPage()
            c.setFont("STSong-Light", 11)
        c.save()
    except Exception:
        try:
            import fitz  # type: ignore
            doc = fitz.open()
            for page_lines in pages:
                page = doc.new_page()
                y = 72
                for line in page_lines:
                    page.insert_text((72, y), line, fontsize=11)
                    y += 18
            doc.save(path)
            doc.close()
        except Exception:
            path.write_bytes(b"%PDF-1.4\n% sample pdf for contract tests\n%%EOF\n")


def _period_sort_key(period: str) -> tuple[int, int]:
    text = str(period or "")
    match = re.search(r"(20\d{2}|19\d{2})", text)
    year = int(match.group(1)) if match else 0
    quarter = 0
    if "H1" in text:
        quarter = 2
    q_match = re.search(r"Q([1-4])", text)
    if q_match:
        quarter = int(q_match.group(1))
    return year, quarter


def _is_fresh_document(doc: dict[str, Any], cutoff: str) -> bool:
    publish_date = str(doc.get("publish_date") or "")
    period_year = _period_sort_key(doc.get("report_period", ""))[0]
    return (publish_date >= cutoff) or (period_year >= int(cutoff[:4]))


def _download_pdf(doc: dict[str, Any], pdf_dir: Path, enterprise_name: str = "") -> dict[str, Any]:
    pdf_dir.mkdir(parents=True, exist_ok=True)
    doc = _resolve_pdf_from_detail(doc)
    local_path = doc.get("local_pdf_path")
    if local_path and Path(local_path).exists():
        path = Path(local_path).resolve()
        doc["local_pdf_path"] = path.as_posix()
        doc["pdf_sha256"] = _sha256_file(path)
        doc["pdf_download_status"] = "success"
        if enterprise_name:
            doc = _verify_pdf_subject(doc, enterprise_name)
        return doc

    pdf_url = doc.get("pdf_url") or ""
    if not pdf_url:
        doc["pdf_download_status"] = "failed"
        doc["document_status"] = "download_failed"
        doc["skipped_reason"] = doc.get("skipped_reason") or "pdf_attachment_not_found"
        return doc

    target = pdf_dir / f"{doc['document_id']}.pdf"
    referer = doc.get("resolved_detail_url") or doc.get("source_url") or ""
    fetched = _fetch_url(pdf_url, referer=referer, timeout=30, retries=2)
    try:
        if not fetched.get("ok"):
            raise ValueError(fetched.get("error") or "download_failed")
        content = fetched.get("content") or b""
        headers = fetched.get("headers") or {}
        content_type = str(headers.get("Content-Type") or headers.get("content-type") or "").lower()
        excerpt = content[:500].decode("utf-8", errors="ignore")
        if "<html" in excerpt.lower() or "<!doctype" in excerpt.lower() or "<script" in excerpt.lower():
            doc["download_debug_excerpt"] = excerpt
            raise ValueError("download_failed_html_response")
        if len(content) < 128:
            doc["download_debug_excerpt"] = excerpt
            raise ValueError("download_failed_too_small")
        if "pdf" not in content_type and not content.lstrip().startswith(b"%PDF"):
            doc["download_debug_excerpt"] = excerpt
            if "<html" in excerpt.lower() or "<!doctype" in excerpt.lower():
                raise ValueError("download_failed_html_response")
            raise ValueError("downloaded content is not a PDF")
        target.write_bytes(content)
        doc["local_pdf_path"] = target.resolve().as_posix()
        doc["pdf_sha256"] = hashlib.sha256(content).hexdigest()
        doc["pdf_download_status"] = "success"
        if enterprise_name:
            doc = _verify_pdf_subject(doc, enterprise_name)
    except Exception as exc:
        doc["local_pdf_path"] = ""
        doc["pdf_sha256"] = ""
        doc["pdf_download_status"] = "failed"
        doc["document_status"] = "download_failed"
        doc["skipped_reason"] = f"download_failed: {exc}"
    return doc


def _standard_doc(
    doc: dict[str, Any],
    enterprise_name: str,
    index: int,
    document_status: str,
    pdf_dir: Path,
    selection_reason: str = "",
    skipped_reason: str = "",
) -> dict[str, Any]:
    title = doc.get("title") or doc.get("attachment_title") or ""
    item = {
        "document_id": doc.get("document_id") or _doc_id(enterprise_name, title, index),
        "source_platform": doc.get("source_platform", ""),
        "title": title,
        "attachment_title": doc.get("attachment_title", ""),
        "file_type": doc.get("file_type") if doc.get("file_type") in ALLOWED_FILE_TYPES else "unsupported_file_type",
        "report_period": doc.get("report_period", ""),
        "publish_date": doc.get("publish_date", ""),
        "source_url": doc.get("source_url") or doc.get("url", ""),
        "pdf_url": doc.get("pdf_url", ""),
        "local_pdf_path": doc.get("local_pdf_path", ""),
        "pdf_download_status": doc.get("pdf_download_status", "skipped"),
        "pdf_sha256": doc.get("pdf_sha256", ""),
        "document_status": document_status,
        "selection_reason": selection_reason,
        "skipped_reason": skipped_reason,
        "entity_verification": doc.get("entity_verification") or {
            "input_name": enterprise_name,
            "matched_name_in_document": title,
            "matched_role": "发行人",
            "is_same_subject": document_status != "subject_mismatch",
            "verification_evidence": "搜索结果元数据匹配",
            "confidence": "medium",
        },
        "needs_deep_pdf_parse": document_status in {"selected_main", "selected_supplement"},
    }
    for key in (
        "resolved_detail_url",
        "pdf_url_candidates",
        "download_debug_excerpt",
        "_skip_subject_verification",
    ):
        if key in doc:
            item[key] = doc[key]
    if item["document_status"] in {"selected_main", "selected_supplement"}:
        item = _download_pdf(item, pdf_dir, enterprise_name)
    return item


def _download_log_entry(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": doc.get("title", ""),
        "source_platform": doc.get("source_platform", ""),
        "source_url": doc.get("source_url", ""),
        "resolved_detail_url": doc.get("resolved_detail_url", doc.get("source_url", "")),
        "pdf_url_candidates": doc.get("pdf_url_candidates", []),
        "selected_pdf_url": doc.get("pdf_url", ""),
        "download_status": doc.get("pdf_download_status", ""),
        "fail_reason": doc.get("skipped_reason", ""),
        "local_pdf_path": doc.get("local_pdf_path", ""),
    }


def _build_standard_output(
    status: str,
    enterprise_name: str,
    task_id: str,
    source_documents: list[dict[str, Any]],
    search_log: list[dict[str, Any]],
    freshness_gate: dict[str, Any],
    data_availability: dict[str, Any],
    message: str = "",
) -> dict[str, Any]:
    selected_main = [d for d in source_documents if d.get("document_status") == "selected_main"]
    selected_supplement = [d for d in source_documents if d.get("document_status") == "selected_supplement"]
    documents_needing_pdf_parse = [
        d for d in source_documents
        if d.get("document_status") in {"selected_main", "selected_supplement"}
        and d.get("file_type") in ALLOWED_FILE_TYPES
        and (d.get("entity_verification") or {}).get("is_same_subject") is True
        and (d.get("entity_verification") or {}).get("confidence") in {"high", "medium"}
        and d.get("needs_deep_pdf_parse") is True
        and d.get("pdf_download_status") == "success"
        and d.get("local_pdf_path")
        and Path(d.get("local_pdf_path")).exists()
    ]
    no_data = status != "failed" and len(documents_needing_pdf_parse) == 0
    return {
        "status": status,
        "enterprise_name": enterprise_name,
        "task_id": task_id,
        "source_documents": source_documents,
        "search_log": search_log,
        "freshness_gate": freshness_gate,
        "data_availability": data_availability,
        "pdf_handoff": {
            "enterprise_name": enterprise_name,
            "task_id": task_id,
            "generated_at": datetime.now().isoformat(),
            "selected_main_documents": selected_main,
            "selected_supplement_documents": selected_supplement,
            "documents_needing_pdf_parse": documents_needing_pdf_parse,
            "no_latest_public_data": no_data,
            "message": message or (NO_LATEST_PUBLIC_DATA_MESSAGE if no_data else ""),
        },
    }


def _sample_output(payload: dict[str, Any]) -> dict[str, Any]:
    enterprise_name = payload.get("enterprise_name") or "测试企业"
    task_id = payload.get("task_id") or "sample"
    mode = payload.get("sample_mode") or payload.get("mode")
    if mode == "no_data":
        return _build_no_data_result(enterprise_name, NO_LATEST_PUBLIC_DATA_MESSAGE, task_id)

    pdf_dir = Path(payload.get("pdf_dir") or _default_pdf_dir(task_id))
    pdf_dir.mkdir(parents=True, exist_ok=True)
    sample_pdf = pdf_dir / "sample_annual.pdf"
    _write_sample_pdf(sample_pdf)
    docs = [
        _standard_doc(
            {
                "title": f"{enterprise_name}2025年度报告",
                "attachment_title": "2025年度报告.pdf",
                "file_type": "annual_report",
                "report_period": "2025",
                "publish_date": "2026-04-30",
                "source_platform": "中国货币网",
                "source_url": "https://www.chinamoney.com.cn/sample",
                "local_pdf_path": sample_pdf.as_posix(),
                "_skip_subject_verification": True,
            },
            enterprise_name,
            1,
            "selected_main",
            pdf_dir,
            "最新年度报告",
        ),
        _standard_doc(
            {
                "title": f"{enterprise_name}2025年半年度报告",
                "attachment_title": "2025半年度报告.pdf",
                "file_type": "semi_annual_report",
                "report_period": "2025H1",
                "publish_date": "2025-08-31",
                "source_platform": "上海证券交易所",
                "source_url": "https://www.sse.com.cn/sample",
                "local_pdf_path": sample_pdf.as_posix(),
                "_skip_subject_verification": True,
            },
            enterprise_name,
            2,
            "selected_supplement",
            pdf_dir,
            "补充文件",
        ),
    ]
    return _build_standard_output(
        "ok",
        enterprise_name,
        task_id,
        docs,
        [{"source_name": "sample", "query_runs": []}],
        {"is_fresh_enough_for_analysis": True},
        {"data_level": "full", "has_financial_report": True},
    )


def _build_search_failed_result(
    enterprise_name: str,
    task_id: str,
    search_log: list[dict[str, Any]],
) -> dict[str, Any]:
    reasons: list[str] = []
    for entry in search_log:
        reason = entry.get("note") or entry.get("parse_failed_reason") or ""
        if not reason and entry.get("skipped_reason"):
            reason = "; ".join(str(x) for x in entry.get("skipped_reason", []))
        if reason:
            reasons.append(f"{entry.get('source_name', 'unknown')}: {reason}")
    message = "公开披露搜索失败，无法判断是否存在最新公开数据"
    result = _build_standard_output(
        "failed",
        enterprise_name,
        task_id,
        [],
        search_log,
        {
            "enabled": True,
            "cutoff_publish_date": "2025-01-01",
            "minimum_report_period": "2025年及之后公开披露",
            "latest_document_publish_date": "",
            "latest_report_period": "",
            "is_fresh_enough_for_analysis": False,
            "stop_reason": message,
        },
        {
            "has_financial_report": False,
            "has_prospectus": False,
            "has_rating_report": False,
            "has_financial_data": False,
            "has_public_opinion": False,
            "data_level": "search_failed",
            "data_limitation_note": message,
        },
        message,
    )
    result["errors"] = ["all_search_channels_failed: " + (" | ".join(reasons) if reasons else "unknown")]
    result["pdf_handoff"]["no_latest_public_data"] = False
    result["pdf_handoff"]["message"] = message
    return result


def _write_skill1_debug_logs(task_id: str, search_log: list[dict[str, Any]], source_documents: list[dict[str, Any]], pdf_handoff: dict[str, Any]) -> None:
    debug_dir = _find_project_root() / "outputs" / "orchestrator" / task_id
    debug_dir.mkdir(parents=True, exist_ok=True)
    raw_payload = [
        {
            "source_name": entry.get("source_name"),
            "status": entry.get("status"),
            "raw_result": entry.get("raw_result"),
            "query_runs": entry.get("query_runs", []),
        }
        for entry in search_log
    ]
    candidates_payload = [
        {
            "source_name": entry.get("source_name"),
            "selected_documents": entry.get("selected_documents", []),
            "skipped_documents": entry.get("skipped_documents", []),
        }
        for entry in search_log
    ]
    download_log = [_download_log_entry(doc) for doc in source_documents]
    (debug_dir / "skill1_search_raw.json").write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (debug_dir / "skill1_candidates.json").write_text(json.dumps(candidates_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (debug_dir / "skill1_download_log.json").write_text(json.dumps(download_log, ensure_ascii=False, indent=2), encoding="utf-8")
    (debug_dir / "skill1_pdf_handoff.json").write_text(json.dumps(pdf_handoff, ensure_ascii=False, indent=2), encoding="utf-8")


# ── main entry ───────────────────────────────────────────────────────────────

async def run_analysis(
    query: str,
    output_dir: Path | str | None = None,
    **kwargs,
) -> dict[str, Any]:
    """Run post-loan analysis for the given enterprise.

    Searches all three allowed channels and returns structured JSON.
    """
    payload = _parse_query_payload(query)
    enterprise_name = (payload.get("enterprise_name") or _extract_enterprise_name(query)).strip()
    task_id = payload.get("task_id") or f"skill1_{hashlib.md5(enterprise_name.encode()).hexdigest()[:8]}"
    if payload.get("sample_mode") or payload.get("mode") in {"sample", "no_data"}:
        return _sample_output(payload)
    if not enterprise_name or enterprise_name == "未填写企业":
        return _build_no_data_result("未填写企业", "未提供企业名称。", task_id)

    output_path = Path(output_dir) if output_dir else _find_project_root() / "outputs" / "post-loan-analysis-report"
    output_path.mkdir(parents=True, exist_ok=True)
    pdf_dir = Path(payload.get("pdf_dir") or _default_pdf_dir(task_id))

    today = date.today().isoformat()
    cutoff = "2025-01-01"

    # Search all three channels concurrently
    channels = ["中国货币网", "上海证券交易所", "深圳证券交易所"]
    channel_tasks = [
        _search_channel(enterprise_name, ch, output_path)
        for ch in channels
    ]
    search_log = await asyncio.gather(*channel_tasks, return_exceptions=True)

    # Handle exceptions
    clean_log = []
    for i, result in enumerate(search_log):
        if isinstance(result, Exception):
            clean_log.append({
                "source_name": channels[i],
                "searched": False,
                "search_modes": [],
                "keywords_used": [enterprise_name],
                "total_results": 0,
                "scanned_result_count": 0,
                "matched_documents": 0,
                "selected_documents": [],
                "skipped_documents": [],
                "skipped_reason": [str(result)],
                "download_status": "error",
                "parse_status": "error",
                "parse_failed_reason": str(result),
                "latest_document_publish_date": "",
                "latest_report_period": "",
                "status": "error",
                "note": "",
                "query_runs": [],
            })
        else:
            clean_log.append(result)

    all_channels_failed = bool(clean_log) and all(
        entry.get("searched") is False or entry.get("status") == "error"
        for entry in clean_log
    )
    if all_channels_failed:
        result = _build_search_failed_result(enterprise_name, task_id, clean_log)
        _write_skill1_debug_logs(task_id, clean_log, [], result["pdf_handoff"])
        return result

    # Collect sources
    financial_reports = []
    prospectuses = []
    rating_reports = []
    for log_entry in clean_log:
        for doc in log_entry.get("selected_documents", []):
            ft = doc.get("file_type")
            if ft in ("annual_report", "semi_annual_report", "quarterly_report"):
                financial_reports.append(doc)
            elif ft == "prospectus":
                prospectuses.append(doc)
            elif ft == "rating_report":
                rating_reports.append(doc)

    # Determine data availability
    has_financial = len(financial_reports) > 0
    has_prospectus = len(prospectuses) > 0
    has_rating = len(rating_reports) > 0
    has_any_data = has_financial or has_prospectus or has_rating

    # Check freshness gate
    latest_dates = []
    for doc in financial_reports + prospectuses + rating_reports:
        pd_str = doc.get("publish_date", "")
        if pd_str and pd_str >= cutoff:
            latest_dates.append(pd_str)
    latest_dates.sort(reverse=True)

    is_fresh = len(latest_dates) > 0
    latest_pub = latest_dates[0] if latest_dates else ""
    latest_period = ""
    for doc in financial_reports:
        rp = doc.get("report_period", "")
        if rp and (not latest_period or rp > latest_period):
            latest_period = rp

    # If no fresh data, return no-data result
    if not is_fresh or not has_any_data:
        result = _build_no_data_result(enterprise_name, NO_LATEST_PUBLIC_DATA_MESSAGE, task_id, clean_log)
        _write_skill1_debug_logs(task_id, clean_log, result.get("source_documents", []), result["pdf_handoff"])
        return result

    # Determine analysis basis
    has_annual = any(d["file_type"] == "annual_report" for d in financial_reports)
    has_semi = any(d["file_type"] == "semi_annual_report" for d in financial_reports)
    has_quarterly = any(d["file_type"] == "quarterly_report" for d in financial_reports)

    if has_annual:
        analysis_basis = "年度报告"
        data_period_type = "三年一期"
        data_level = "full"
    elif has_semi:
        analysis_basis = "半年度报告"
        data_period_type = "两年一期"
        data_level = "partial_financial"
    elif has_quarterly:
        analysis_basis = "季度报告补充"
        data_period_type = "两年"
        data_level = "partial_financial"
    elif has_prospectus:
        analysis_basis = "募集说明书补充"
        data_period_type = "可获取数据不足"
        data_level = "partial_financial"
    elif has_rating:
        analysis_basis = "评级报告补充"
        data_period_type = "可获取数据不足"
        data_level = "partial_financial"
    else:
        analysis_basis = "无有效公开资料"
        data_period_type = "可获取数据不足"
        data_level = "no_data"

    freshness_gate = {
        "enabled": True,
        "cutoff_publish_date": cutoff,
        "minimum_report_period": "2025年及之后公开披露",
        "latest_document_publish_date": latest_pub,
        "latest_report_period": latest_period,
        "is_fresh_enough_for_analysis": is_fresh,
        "stop_reason": "",
    }
    data_availability = {
        "has_financial_report": has_financial,
        "has_prospectus": has_prospectus,
        "has_rating_report": has_rating,
        "has_financial_data": has_financial,
        "has_public_opinion": False,
        "data_level": data_level,
        "data_limitation_note": "",
    }

    all_docs = financial_reports + prospectuses + rating_reports
    fresh_docs = [d for d in all_docs if _is_fresh_document(d, cutoff)]
    annual_docs = [d for d in fresh_docs if d.get("file_type") == "annual_report"]
    annual_docs.sort(key=lambda d: (_period_sort_key(d.get("report_period", "")), d.get("publish_date", "")), reverse=True)
    selected_main_id = id(annual_docs[0]) if annual_docs else None
    source_documents = []
    for idx, doc in enumerate(all_docs, start=1):
        if not _is_fresh_document(doc, cutoff):
            doc_status = "stale_or_prior_period_document"
            reason = "未满足2025年以来有效公开资料要求"
            selection = ""
        elif id(doc) == selected_main_id:
            doc_status = "selected_main"
            reason = ""
            selection = "最新年度报告"
        elif doc.get("file_type") in ALLOWED_FILE_TYPES:
            doc_status = "selected_supplement"
            reason = ""
            selection = "补充文件"
        else:
            doc_status = "unsupported_file_type"
            reason = "unsupported_file_type"
            selection = ""
        source_documents.append(_standard_doc(doc, enterprise_name, idx, doc_status, pdf_dir, selection, reason))

    result = _build_standard_output(
        "ok",
        enterprise_name,
        task_id,
        source_documents,
        clean_log,
        freshness_gate,
        data_availability,
    )
    if not result["pdf_handoff"]["documents_needing_pdf_parse"] and any(
        doc.get("pdf_download_status") == "failed" for doc in source_documents
    ):
        result["status"] = "failed"
        result["data_availability"]["data_level"] = "download_failed"
        result["pdf_handoff"]["no_latest_public_data"] = False
        result["pdf_handoff"]["message"] = "已发现公开披露候选文件，但 PDF 下载或主体校验失败。"
        result.setdefault("errors", []).append("download_failed_or_subject_unconfirmed")
    _write_skill1_debug_logs(task_id, clean_log, source_documents, result["pdf_handoff"])

    # Write output
    import hashlib
    name_hash = hashlib.md5(enterprise_name.encode()).hexdigest()[:8]
    output_file = output_path / f"post_loan_{name_hash}_{today}.json"
    output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    result["output_file"] = output_file.resolve().as_posix()
    return result


def _build_no_data_result(
    enterprise_name: str,
    reason: str,
    task_id: str = "",
    search_log: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a no-data result when no valid disclosures are found."""
    freshness_gate = {
        "enabled": True,
        "cutoff_publish_date": "2025-01-01",
        "minimum_report_period": "2025年及之后公开披露",
        "latest_document_publish_date": "",
        "latest_report_period": "",
        "is_fresh_enough_for_analysis": False,
        "stop_reason": reason,
    }
    data_availability = {
        "has_financial_report": False,
        "has_prospectus": False,
        "has_rating_report": False,
        "has_financial_data": False,
        "has_public_opinion": False,
        "data_level": "no_data",
        "data_limitation_note": reason,
    }
    return _build_standard_output(
        "empty",
        enterprise_name,
        task_id,
        [],
        search_log or [],
        freshness_gate,
        data_availability,
        reason,
    )
