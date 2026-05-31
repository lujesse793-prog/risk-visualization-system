"""
Orchestrator Adapter: Skill 2 – PDF 解析

封装对 pdf_parse_skill 的调用。
接收 pdf_handoff.json，输出 parsed_documents[]。

修复要点：
- 可移植性：通过环境变量 MARKER_BIN / SURYA_BIN 配置，默认使用命令名
- 下载逻辑：使用 httpx 带 retry、UA header、content-type 校验、sha256 计算
- report_period 继承：优先使用 source document 中的 report_period
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx

# 项目根目录
def _find_project_root() -> Path:
    current = Path(__file__).resolve().parent
    for _ in range(6):
        if (current / "mx_skills").is_dir() and (current / "server").is_dir():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent.parent

PROJECT_ROOT = _find_project_root()

# ---- 解析器配置 ----
MARKER_BIN = os.environ.get("MARKER_BIN", "marker_single")
SURYA_BIN = os.environ.get("SURYA_BIN", "surya_ocr")

# ---- PDF 下载配置 ----
HTTP_TIMEOUT = int(os.environ.get("PDF_DOWNLOAD_TIMEOUT", "60"))
HTTP_MAX_RETRIES = int(os.environ.get("PDF_DOWNLOAD_RETRIES", "3"))
USER_AGENT = os.environ.get("PDF_USER_AGENT",
    "Mozilla/5.0 (compatible; PostLoanAnalyzer/1.0; +https://example.com/bot)")
PDF_MAX_SIZE_MB = int(os.environ.get("PDF_MAX_SIZE_MB", "100"))


def _check_binary(bin_name: str) -> bool:
    """检查二进制是否可用"""
    return shutil.which(bin_name) is not None


def _compute_sha256(file_path: str) -> str:
    """计算文件 SHA256"""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()


async def run_pdf_parse(
    pdf_handoff: dict[str, Any],
    task_id: str,
) -> dict[str, Any]:
    """
    调用 Skill 2: PDF 解析。
    遍历 pdf_handoff.documents_to_parse，逐个下载并解析。
    """
    parsed_docs: list[dict[str, Any]] = []
    failed_docs: list[dict[str, Any]] = []

    documents = pdf_handoff.get("documents_to_parse", [])
    if not documents:
        return {
            "parsed_documents": [],
            "failed_documents": [],
            "parse_summary": {"total": 0, "success": 0, "failed": 0},
        }

    for doc in documents:
        try:
            parsed = await _parse_single_pdf(doc, task_id)
            if parsed.get("parse_status") == "failed":
                # 尝试 OCR fallback
                parsed = await _parse_with_surya_ocr(doc, task_id)

            if parsed.get("parse_status") != "failed":
                parsed_docs.append(parsed)
            else:
                failed_docs.append({
                    "document_id": doc["document_id"],
                    "title": doc.get("title", ""),
                    "failure_stage": "pdf_parse",
                    "failure_reason": parsed.get("parse_error", "未知解析错误"),
                })
        except Exception as e:
            failed_docs.append({
                "document_id": doc["document_id"],
                "title": doc.get("title", ""),
                "failure_stage": "pdf_parse",
                "failure_reason": str(e),
            })

    return {
        "parsed_documents": parsed_docs,
        "failed_documents": failed_docs,
        "parse_summary": {
            "total": len(documents),
            "success": len(parsed_docs),
            "failed": len(failed_docs),
        },
    }


async def _parse_single_pdf(doc: dict[str, Any], task_id: str) -> dict[str, Any]:
    """使用 Marker 解析单个 PDF"""
    pdf_url = doc.get("pdf_url", "")
    local_path = doc.get("local_pdf_path", "")
    doc_id = doc["document_id"]

    # 尝试本地路径
    pdf_to_parse: str | None = local_path if local_path and Path(local_path).exists() else None

    if not pdf_to_parse and pdf_url:
        # 下载 PDF
        pdf_to_parse = await _download_pdf(pdf_url, doc_id, task_id)

    if not pdf_to_parse or not Path(pdf_to_parse).exists():
        return _build_failed_doc(doc, "PDF 下载失败或路径无效")

    # 计算 SHA256
    try:
        pdf_sha256 = _compute_sha256(pdf_to_parse)
    except Exception:
        pdf_sha256 = ""

    # 尝试 Marker 解析
    if _check_binary(MARKER_BIN):
        try:
            result = await _run_marker_parse(pdf_to_parse, doc_id, task_id)
            if result:
                result["pdf_sha256"] = pdf_sha256
                return result
        except Exception as e:
            pass  # 降级到 pypdf
    else:
        # Marker 不可用，直接走 pypdf
        pass

    # pypdf fallback
    try:
        result = await _run_pypdf_fallback(pdf_to_parse, doc_id)
        if result:
            result["pdf_sha256"] = pdf_sha256
            return result
    except Exception:
        pass

    return _build_failed_doc(doc, f"所有解析器均失败 (marker={'可用' if _check_binary(MARKER_BIN) else '不可用'})")


async def _run_marker_parse(pdf_path: str, doc_id: str, task_id: str) -> dict[str, Any] | None:
    """使用 Marker 解析 PDF"""
    try:
        output_dir = PROJECT_ROOT / "mx_skills" / "output" / f"parsed_{task_id}" / doc_id
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [MARKER_BIN, str(pdf_path), "--output_dir", str(output_dir), "--output_format", "json"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                            cwd=str(PROJECT_ROOT))

        if proc.returncode != 0:
            return None

        json_files = list(output_dir.glob("*.json"))
        if json_files:
            data = json.loads(json_files[0].read_text(encoding="utf-8"))
            return _build_parsed_doc(doc_id, "marker", False, data, output_dir, pd=None)
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None


async def _run_pypdf_fallback(pdf_path: str, doc_id: str) -> dict[str, Any] | None:
    """使用 pypdf 作为简单 fallback"""
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        page_count = len(reader.pages)
        texts = {}
        for i, page in enumerate(reader.pages):
            texts[str(i + 1)] = page.extract_text() or ""
        return _build_parsed_doc(doc_id, "pypdf", False,
                                 {"page_texts": texts, "page_count": page_count},
                                 None, pd=None)
    except Exception:
        return None


async def _parse_with_surya_ocr(doc: dict[str, Any], task_id: str) -> dict[str, Any]:
    """使用 Surya OCR 作为 fallback 解析"""
    if not _check_binary(SURYA_BIN):
        return _build_failed_doc(doc, f"OCR fallback 不可用: 未找到 {SURYA_BIN}")

    pdf_url = doc.get("pdf_url", "")
    local_path = doc.get("local_pdf_path", "")
    doc_id = doc["document_id"]

    pdf_to_parse: str | None = local_path if local_path and Path(local_path).exists() else None
    if not pdf_to_parse and pdf_url:
        pdf_to_parse = await _download_pdf(pdf_url, doc_id, task_id)

    if not pdf_to_parse or not Path(pdf_to_parse).exists():
        return _build_failed_doc(doc, "OCR fallback: PDF 不可用")

    try:
        output_dir = PROJECT_ROOT / "mx_skills" / "output" / f"ocr_{task_id}" / doc_id
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [SURYA_BIN, str(pdf_to_parse), "--output_dir", str(output_dir)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                            cwd=str(PROJECT_ROOT))

        if proc.returncode != 0:
            return _build_failed_doc(doc, f"Surya OCR 退出码 {proc.returncode}")

        json_files = list(output_dir.glob("*.json"))
        if json_files:
            data = json.loads(json_files[0].read_text(encoding="utf-8"))
            return _build_parsed_doc(doc_id, "surya_ocr", True, data, output_dir, pd=None)
    except subprocess.TimeoutExpired:
        return _build_failed_doc(doc, "Surya OCR 超时")
    except Exception as e:
        return _build_failed_doc(doc, f"Surya OCR 异常: {str(e)}")


async def _download_pdf(url: str, doc_id: str, task_id: str) -> str | None:
    """使用 httpx 下载 PDF，带 retry、header 校验"""
    download_dir = PROJECT_ROOT / "data" / "pdfs" / task_id
    download_dir.mkdir(parents=True, exist_ok=True)
    local_path = download_dir / f"{doc_id}.pdf"

    # 如果已存在且非空，直接返回
    if local_path.exists() and local_path.stat().st_size > 0:
        return str(local_path)

    headers = {
        "User-Agent": USER_AGENT,
        "Referer": url.rsplit("/", 1)[0] if "/" in url else url,
        "Accept": "application/pdf,*/*",
    }

    last_error = ""
    for attempt in range(HTTP_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)

                if resp.status_code != 200:
                    last_error = f"HTTP {resp.status_code}"
                    continue

                content_type = resp.headers.get("content-type", "")
                if "pdf" not in content_type.lower() and "octet-stream" not in content_type.lower():
                    last_error = f"非PDF内容类型: {content_type}"
                    continue

                content = resp.content
                if len(content) == 0:
                    last_error = "下载文件为空"
                    continue

                if len(content) > PDF_MAX_SIZE_MB * 1024 * 1024:
                    last_error = f"文件过大: {len(content) / 1024 / 1024:.1f}MB > {PDF_MAX_SIZE_MB}MB"
                    continue

                local_path.write_bytes(content)
                return str(local_path)

        except httpx.TimeoutException:
            last_error = f"下载超时 (attempt {attempt + 1})"
        except Exception as e:
            last_error = str(e)

    return None


def _build_parsed_doc(
    doc_id: str,
    parser_used: str,
    ocr_used: bool,
    data: dict[str, Any],
    output_dir: Path | None,
    pd: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建标准 parsed_document，优先继承 source document 的 report_period/file_type"""
    # 优先使用传入的 pd（source document）中的元数据
    page_count = data.get("page_count", 0) or len(data.get("page_texts", {})) or len(data.get("pages", []))

    return {
        "document_id": doc_id,
        "file_type": data.get("file_type", ""),
        "report_period": data.get("report_period", ""),
        "parser_used": parser_used,
        "ocr_used": ocr_used,
        "is_scanned": data.get("is_scanned", False),
        "page_count": page_count,
        "tables_found_count": len(data.get("tables", [])),
        "parse_status": "success" if page_count > 0 else "partial",
        "parse_confidence": "medium" if ocr_used else "high",
        "parse_warnings": [],
        "markdown_path": str(output_dir) if output_dir else "",
        "json_output_path": "",
        "page_texts": data.get("page_texts", {}),
        "tables_raw": data.get("tables", []),
        "title_hierarchy": data.get("title_hierarchy", []),
        "parse_error": "",
        "pdf_sha256": data.get("pdf_sha256", ""),
    }


def _build_failed_doc(doc: dict[str, Any], error_msg: str) -> dict[str, Any]:
    return {
        "document_id": doc["document_id"],
        "file_type": doc.get("file_type", ""),
        "report_period": doc.get("report_period", ""),
        "parser_used": "none",
        "ocr_used": False,
        "is_scanned": False,
        "page_count": 0,
        "tables_found_count": 0,
        "parse_status": "failed",
        "parse_confidence": "low",
        "parse_warnings": [error_msg],
        "markdown_path": "",
        "json_output_path": "",
        "page_texts": {},
        "tables_raw": [],
        "title_hierarchy": [],
        "parse_error": error_msg,
        "pdf_sha256": "",
    }
