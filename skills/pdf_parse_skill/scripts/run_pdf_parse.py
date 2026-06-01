import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCANNED_MIN_CHARS_PER_PAGE = 40
OCR_RENDER_ZOOM = 3
OCR_MAX_PAGES = 12
OCR_MIN_CONFIDENCE = 0.35

STATEMENT_TITLE_HINTS = {
    "balance_sheet": "\u8d44\u4ea7\u8d1f\u503a\u8868",
    "income_statement": "\u5229\u6da6\u8868",
    "cash_flow_statement": "\u73b0\u91d1\u6d41\u91cf\u8868",
}


def _parse_query(query: str) -> dict[str, Any]:
    query = (query or "").strip()
    if not query:
        return {}
    if query.startswith("{"):
        return json.loads(query)
    return {"input_path": query}


def _command_from_env_or_path(env_name: str, candidates: list[str]) -> str | None:
    configured = os.environ.get(env_name)
    if configured:
        if Path(configured).exists() or shutil.which(configured):
            return configured
        return None
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def _documents_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    documents = payload.get("documents_to_parse")
    if isinstance(documents, list):
        return documents
    documents = payload.get("documents_needing_pdf_parse")
    if isinstance(documents, list):
        return documents
    input_path = payload.get("input_path") or payload.get("path") or payload.get("file")
    if input_path:
        source = Path(input_path)
        return [
            {
                "document_id": payload.get("document_id") or source.stem,
                "file_type": payload.get("file_type", "unsupported_file_type"),
                "report_period": payload.get("report_period", ""),
                "title": payload.get("title", source.name),
                "local_pdf_path": str(source),
                "pdf_sha256": payload.get("pdf_sha256", ""),
            }
        ]
    return []


def _mark_ocr_candidate_documents(documents: list[dict[str, Any]]) -> None:
    if any(doc.get("is_selected_main") or doc.get("document_status") == "selected_main" for doc in documents):
        return
    for doc in documents:
        if doc.get("file_type") in {"annual_report", "semi_annual_report", "quarterly_report", "prospectus"}:
            doc["_allow_ocr"] = True
            return
    if documents:
        documents[0]["_allow_ocr"] = True


async def run_pdf_parse(query: str, output_dir: str | Path | None = None, **_: Any) -> dict[str, Any]:
    payload = _parse_query(query)
    documents = _documents_from_payload(payload)
    base_output_dir = Path(payload.get("output_dir") or output_dir or Path.cwd() / "pdf_parse_output")
    base_output_dir.mkdir(parents=True, exist_ok=True)

    parsed_documents: list[dict[str, Any]] = []
    failed_documents: list[dict[str, Any]] = []
    _mark_ocr_candidate_documents(documents)

    for doc in documents:
        parsed = await _parse_one_document(doc, base_output_dir)
        parsed_documents.append(parsed)
        if parsed["parse_status"] == "failed":
            failed_documents.append(
                {
                    "document_id": parsed["document_id"],
                    "title": doc.get("title", ""),
                    "failure_stage": "pdf_parse",
                    "failure_reason": "; ".join(parsed.get("parse_warnings", [])) or "parse failed",
                }
            )

    return {
        "status": "success" if not failed_documents else ("failed" if len(failed_documents) == len(parsed_documents) else "partial"),
        "parsed_documents": parsed_documents,
        "failed_documents": failed_documents,
        "parse_summary": {
            "total": len(parsed_documents),
            "success": sum(1 for d in parsed_documents if d["parse_status"] == "success"),
            "partial": sum(1 for d in parsed_documents if d["parse_status"] == "partial"),
            "failed": sum(1 for d in parsed_documents if d["parse_status"] == "failed"),
        },
    }


async def _parse_one_document(doc: dict[str, Any], base_output_dir: Path) -> dict[str, Any]:
    pdf_path = Path(doc.get("local_pdf_path") or "")
    warnings: list[str] = []
    if not pdf_path.exists():
        return _failed_document(doc, [f"PDF file not found: {pdf_path}"])

    doc_id = str(doc.get("document_id") or pdf_path.stem)
    doc_output_dir = base_output_dir / doc_id
    marker_output_dir = doc_output_dir / "marker"
    surya_output_dir = doc_output_dir / "surya"
    marker_output_dir.mkdir(parents=True, exist_ok=True)
    surya_output_dir.mkdir(parents=True, exist_ok=True)

    marker_doc: dict[str, Any] | None = None
    marker_error = ""
    marker_bin = _command_from_env_or_path("MARKER_BIN", ["marker_single", "marker"])
    if marker_bin:
        marker_doc, marker_error = await _run_marker(doc, pdf_path, marker_output_dir, marker_bin)
    else:
        marker_error = "Marker command not found. Set MARKER_BIN or install marker_single/marker."

    if marker_doc and marker_doc["parse_status"] != "failed" and not _looks_scanned(marker_doc):
        return marker_doc

    if marker_doc and _looks_scanned(marker_doc):
        warnings.append("Marker output looks scanned or text-sparse; trying text fallback before OCR.")
    elif marker_error:
        warnings.append(marker_error)

    text_doc, text_error = await _run_text_fallback(doc, pdf_path, doc_output_dir / "text")
    if text_doc and text_doc["parse_status"] != "failed" and not _looks_scanned(text_doc):
        text_doc["parse_warnings"] = warnings + text_doc.get("parse_warnings", [])
        return text_doc
    if text_error:
        warnings.append(text_error)
    elif text_doc:
        warnings.append("Text fallback output is text-sparse; trying Surya OCR fallback.")

    surya_bin = _command_from_env_or_path("SURYA_BIN", ["surya_ocr"])
    if surya_bin:
        surya_doc, surya_error = await _run_surya(doc, pdf_path, surya_output_dir, surya_bin)
        if surya_doc:
            surya_doc["parse_warnings"] = warnings + surya_doc.get("parse_warnings", [])
            return surya_doc
        warnings.append(surya_error or "Surya OCR did not produce parsed output.")
    else:
        warnings.append("Surya OCR command not found. Set SURYA_BIN or install surya_ocr.")

    if marker_doc:
        marker_doc["parse_status"] = "partial" if marker_doc["page_count"] > 0 else "failed"
        marker_doc["parse_confidence"] = "low"
        marker_doc["parse_warnings"] = warnings + marker_doc.get("parse_warnings", [])
        return marker_doc

    return _failed_document(doc, warnings)


async def _run_marker(doc: dict[str, Any], pdf_path: Path, output_dir: Path, marker_bin: str) -> tuple[dict[str, Any] | None, str]:
    cmd = [marker_bin, str(pdf_path), "--output_dir", str(output_dir), "--output_format", "json"]
    proc = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        return None, f"Marker failed: {(proc.stderr or proc.stdout).strip()[-1000:]}"
    data, json_path = _load_first_json(output_dir)
    if data is None:
        return None, "Marker completed but no JSON output was found."
    return _build_parsed_document(doc, "marker", False, data, json_path, []), ""


async def _run_surya(doc: dict[str, Any], pdf_path: Path, output_dir: Path, surya_bin: str) -> tuple[dict[str, Any] | None, str]:
    cmd = [surya_bin, str(pdf_path), "--output_dir", str(output_dir)]
    proc = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        return None, f"Surya OCR failed: {(proc.stderr or proc.stdout).strip()[-1000:]}"
    data, json_path = _load_first_json(output_dir)
    if data is None:
        return None, "Surya OCR completed but no JSON output was found."
    return _build_parsed_document(doc, "surya_ocr", True, data, json_path, []), ""


async def _run_text_fallback(doc: dict[str, Any], pdf_path: Path, output_dir: Path) -> tuple[dict[str, Any] | None, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pypdf_doc, pypdf_error = await asyncio.to_thread(_run_pypdf_fallback_sync, doc, pdf_path, output_dir)

    pymupdf_doc, pymupdf_error = await asyncio.to_thread(_run_pymupdf_fallback_sync, doc, pdf_path, output_dir)
    if pymupdf_doc and pymupdf_doc.get("tables_raw"):
        return pymupdf_doc, ""
    if pymupdf_doc:
        return pymupdf_doc, ""
    if pypdf_doc and not _looks_scanned(pypdf_doc):
        return pypdf_doc, ""

    errors = [msg for msg in [pypdf_error, pymupdf_error] if msg]
    if pypdf_doc:
        return pypdf_doc, "; ".join(errors)
    return None, "; ".join(errors) or "pypdf/pymupdf text fallback unavailable"


def _run_pypdf_fallback_sync(doc: dict[str, Any], pdf_path: Path, output_dir: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        return None, f"pypdf unavailable: {exc}"
    try:
        reader = PdfReader(str(pdf_path))
        page_texts = {
            str(index): page.extract_text() or ""
            for index, page in enumerate(reader.pages, start=1)
        }
        json_path = output_dir / "pypdf.json"
        data = {"page_count": len(reader.pages), "page_texts": page_texts, "tables_raw": []}
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        parsed = _build_parsed_document(doc, "pypdf", False, data, json_path, [])
        if parsed["parse_status"] == "success":
            parsed["parse_status"] = "partial"
            parsed["parse_confidence"] = "medium"
        return parsed, ""
    except Exception as exc:
        return None, f"pypdf failed: {exc}"


def _run_pymupdf_fallback_sync(doc: dict[str, Any], pdf_path: Path, output_dir: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        import fitz
    except Exception as exc:
        return None, f"pymupdf unavailable: {exc}"
    try:
        pdf = fitz.open(str(pdf_path))
        page_texts = {
            str(index + 1): page.get_text("text") or ""
            for index, page in enumerate(pdf)
        }
        ocr_warnings: list[str] = []
        ocr_data = (
            _run_rapidocr_on_sparse_pages_sync(pdf, page_texts, output_dir / "rapidocr_pages", ocr_warnings)
            if _should_ocr_document(doc)
            else {"page_texts": {}, "tables_raw": []}
        )
        for page_num, ocr_text in ocr_data.get("page_texts", {}).items():
            existing = page_texts.get(page_num, "")
            if len(re.sub(r"\s+", "", ocr_text)) > len(re.sub(r"\s+", "", existing)):
                page_texts[page_num] = ocr_text
        tables_raw = ocr_data.get("tables_raw", [])
        json_path = output_dir / "pymupdf.json"
        data = {"page_count": len(pdf), "page_texts": page_texts, "tables_raw": tables_raw}
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        parsed = _build_parsed_document(doc, "pymupdf+rapidocr" if tables_raw else "pymupdf", bool(tables_raw), data, json_path, ocr_warnings)
        if parsed["parse_status"] == "success":
            parsed["parse_status"] = "partial"
            parsed["parse_confidence"] = "medium"
        return parsed, ""
    except Exception as exc:
        return None, f"pymupdf failed: {exc}"


def _should_ocr_document(doc: dict[str, Any]) -> bool:
    if doc.get("_allow_ocr"):
        return True
    if doc.get("is_selected_main") or doc.get("document_status") == "selected_main":
        return True
    return False


def _run_rapidocr_on_sparse_pages_sync(pdf: Any, page_texts: dict[str, str], output_dir: Path, warnings: list[str]) -> dict[str, Any]:
    try:
        import fitz
        from rapidocr_onnxruntime import RapidOCR
    except Exception as exc:
        warnings.append(f"RapidOCR unavailable: {exc}")
        return {"page_texts": {}, "tables_raw": []}

    output_dir.mkdir(parents=True, exist_ok=True)
    ocr = RapidOCR()
    ocr_page_texts: dict[str, str] = {}
    tables_raw: list[dict[str, Any]] = []
    matrix = fitz.Matrix(OCR_RENDER_ZOOM, OCR_RENDER_ZOOM)

    for index, page in enumerate(pdf):
        if index >= OCR_MAX_PAGES:
            break
        page_num = str(index + 1)
        existing_text = page_texts.get(page_num, "")
        existing_len = len(re.sub(r"\s+", "", existing_text))
        image_count = len(page.get_images(full=True))
        if existing_len >= 120 or image_count <= 0:
            continue

        image_path = output_dir / f"page_{page_num}.png"
        try:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            pix.save(str(image_path))
            result, _elapsed = ocr(str(image_path))
        except Exception as exc:
            warnings.append(f"RapidOCR failed on page {page_num}: {exc}")
            continue

        lines = _rapidocr_lines(result or [])
        if not lines:
            continue
        text = "\n".join(line["text"] for line in lines)
        ocr_page_texts[page_num] = text
        table_title = _statement_title_from_ocr_text(text)
        if table_title:
            rows = _ocr_lines_to_table_rows(lines, table_title)
            if rows:
                tables_raw.append(
                    {
                        "page": index + 1,
                        "table_index": len(tables_raw),
                        "table_id": f"rapidocr_page_{page_num}",
                        "table_title": table_title,
                        "caption": table_title,
                        "headers": rows[0],
                        "rows": rows,
                    }
                )

    if ocr_page_texts:
        warnings.append(f"RapidOCR extracted sparse image pages: {', '.join(sorted(ocr_page_texts, key=int))}")
    return {"page_texts": ocr_page_texts, "tables_raw": tables_raw}


def _rapidocr_lines(result: list[Any]) -> list[dict[str, Any]]:
    tokens: list[dict[str, Any]] = []
    for item in result:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        box = item[0]
        text = str(item[1] or "").strip()
        score = float(item[2]) if len(item) > 2 and isinstance(item[2], (int, float)) else 1.0
        if not text or score < OCR_MIN_CONFIDENCE:
            continue
        try:
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
        except Exception:
            continue
        tokens.append({"text": text, "x": min(xs), "y": sum(ys) / len(ys), "height": max(ys) - min(ys)})

    tokens.sort(key=lambda item: (item["y"], item["x"]))
    grouped: list[list[dict[str, Any]]] = []
    for token in tokens:
        if not grouped:
            grouped.append([token])
            continue
        last = grouped[-1]
        avg_y = sum(item["y"] for item in last) / len(last)
        avg_h = max(sum(item["height"] for item in last) / len(last), 10)
        if abs(token["y"] - avg_y) <= max(8, avg_h * 0.7):
            last.append(token)
        else:
            grouped.append([token])

    lines: list[dict[str, Any]] = []
    for group in grouped:
        group.sort(key=lambda item: item["x"])
        parts: list[str] = []
        previous_x: float | None = None
        for token in group:
            sep = "\t" if previous_x is not None and token["x"] - previous_x > 90 else ""
            parts.append(f"{sep}{token['text']}")
            previous_x = token["x"] + max(len(token["text"]) * 18, 28)
        text = "".join(parts).strip()
        if text:
            lines.append({"text": text, "tokens": group, "y": sum(item["y"] for item in group) / len(group)})
    return lines


def _statement_title_from_ocr_text(text: str) -> str:
    compact = re.sub(r"\s+", "", text or "")
    for title in (
        "\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868",
        "\u6bcd\u516c\u53f8\u8d44\u4ea7\u8d1f\u503a\u8868",
        "\u8d44\u4ea7\u8d1f\u503a\u8868",
        "\u5408\u5e76\u5229\u6da6\u8868",
        "\u6bcd\u516c\u53f8\u5229\u6da6\u8868",
        "\u5229\u6da6\u8868",
        "\u5408\u5e76\u73b0\u91d1\u6d41\u91cf\u8868",
        "\u6bcd\u516c\u53f8\u73b0\u91d1\u6d41\u91cf\u8868",
        "\u73b0\u91d1\u6d41\u91cf\u8868",
    ):
        if title in compact:
            return title
    return ""


def _ocr_lines_to_table_rows(lines: list[Any], table_title: str) -> list[list[str]]:
    if STATEMENT_TITLE_HINTS["balance_sheet"] in table_title:
        header = ["\u9879\u76ee", "\u671f\u672b\u4f59\u989d", "\u671f\u521d\u4f59\u989d"]
        rows = [header]
        for line in lines:
            if isinstance(line, dict):
                rows.extend(_balance_sheet_rows_from_ocr_tokens(line.get("tokens", [])))
            else:
                row = _ocr_line_to_table_row(str(line))
                if row:
                    rows.append(row)
        return rows if len(rows) > 1 else []
    else:
        header = ["\u9879\u76ee", "\u672c\u671f\u91d1\u989d", "\u4e0a\u671f\u91d1\u989d"]
    rows: list[list[str]] = [header]
    for line in lines:
        if isinstance(line, dict):
            row = _single_statement_row_from_ocr_tokens(line.get("tokens", []))
        else:
            row = _ocr_line_to_table_row(str(line))
        if row:
            rows.append(row)
    return rows if len(rows) > 1 else []


def _balance_sheet_rows_from_ocr_tokens(tokens: list[dict[str, Any]]) -> list[list[str]]:
    rows: list[list[str]] = []
    rows.extend(_balance_sheet_half_row(tokens, 120, 430, 500, 830))
    rows.extend(_balance_sheet_half_row(tokens, 860, 1135, 1220, 1540))
    return rows


def _balance_sheet_half_row(
    tokens: list[dict[str, Any]],
    label_min_x: int,
    label_max_x: int,
    amount_min_x: int,
    amount_max_x: int,
) -> list[list[str]]:
    label_parts = [
        str(token.get("text", ""))
        for token in tokens
        if label_min_x <= float(token.get("x", 0)) < label_max_x and not _looks_numeric_token(str(token.get("text", "")))
    ]
    amounts = [
        str(token.get("text", ""))
        for token in tokens
        if amount_min_x <= float(token.get("x", 0)) < amount_max_x and _looks_numeric_token(str(token.get("text", "")))
    ]
    label = re.sub(r"[\s,，]+", "", "".join(label_parts)).strip(":：")
    if not label or not amounts:
        return []
    return [[label, *amounts[:2]]]


def _single_statement_row_from_ocr_tokens(tokens: list[dict[str, Any]]) -> list[str] | None:
    label_parts = [
        str(token.get("text", ""))
        for token in tokens
        if float(token.get("x", 0)) < 880 and not _looks_numeric_token(str(token.get("text", "")))
    ]
    amounts = [
        _clean_numeric_token(str(token.get("text", "")))
        for token in tokens
        if float(token.get("x", 0)) >= 1000 and _looks_numeric_token(str(token.get("text", "")))
    ]
    label = re.sub(r"[\s,，]+", "", "".join(label_parts)).strip(":：")
    label = re.sub(r"^[一二三四五六七八九十0-9]+[、.．]?", "", label).strip()
    if not label or not amounts:
        return None
    return [label, *amounts[:2]]


def _looks_numeric_token(text: str) -> bool:
    return bool(re.fullmatch(r"\(?-?[\d,，\s]+(?:\.\s*\d+)?\)?", (text or "").strip()))


def _clean_numeric_token(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").replace("，", ","))


def _ocr_line_to_table_row(line: str) -> list[str] | None:
    normalized = (line or "").replace("\uff0c", ",").strip()
    if not normalized:
        return None
    numbers = re.findall(r"\(?-?\d[\d,]*\.?\d*\)?", normalized)
    if not numbers:
        return None
    label = normalized
    for number in numbers:
        label = label.replace(number, " ")
    label = re.sub(r"[\t ]+", "", label).strip(":：")
    label = re.sub(r"^[一二三四五六七八九十0-9]+[、.．]?", "", label).strip()
    if not label or len(label) > 40:
        return None
    return [label, *numbers[:3]]


def _load_first_json(output_dir: Path) -> tuple[dict[str, Any] | None, Path | None]:
    for path in output_dir.rglob("*.json"):
        try:
            return json.loads(path.read_text(encoding="utf-8")), path
        except Exception:
            continue
    return None, None


def _build_parsed_document(
    source_doc: dict[str, Any],
    parser_used: str,
    ocr_used: bool,
    data: dict[str, Any],
    json_path: Path | None,
    warnings: list[str],
) -> dict[str, Any]:
    page_texts = _extract_page_texts(data)
    tables_raw = _extract_tables(data)
    page_count = _infer_page_count(data, page_texts, tables_raw)
    parse_status = "success" if page_count and (page_texts or tables_raw) else ("partial" if page_count else "failed")
    confidence = "medium" if ocr_used else "high"
    if parse_status == "partial":
        confidence = "medium" if page_texts or tables_raw else "low"
    if parse_status == "failed":
        confidence = "low"

    return {
        "document_id": str(source_doc.get("document_id") or Path(source_doc.get("local_pdf_path", "")).stem),
        "file_type": source_doc.get("file_type", data.get("file_type", "unsupported_file_type")),
        "report_period": source_doc.get("report_period") or data.get("report_period", ""),
        "parser_used": parser_used,
        "ocr_used": ocr_used,
        "page_count": page_count,
        "page_texts": page_texts,
        "tables_raw": tables_raw,
        "parse_status": parse_status,
        "parse_confidence": confidence,
        "parse_warnings": warnings,
        "json_output_path": json_path.resolve().as_posix() if json_path else "",
    }


def _extract_page_texts(data: Any) -> dict[str, str]:
    if not isinstance(data, dict):
        return {}
    if isinstance(data.get("page_texts"), dict):
        return {str(k): str(v or "") for k, v in data["page_texts"].items()}

    pages = data.get("pages")
    page_texts: dict[str, str] = {}
    if isinstance(pages, list):
        for index, page in enumerate(pages, start=1):
            if not isinstance(page, dict):
                continue
            page_num = str(page.get("page") or page.get("page_number") or index)
            text = page.get("text") or page.get("markdown") or page.get("plain_text") or ""
            if not text and isinstance(page.get("blocks"), list):
                text = "\n".join(str(block.get("text", "")) for block in page["blocks"] if isinstance(block, dict))
            page_texts[page_num] = str(text or "")

    markdown = data.get("markdown") or data.get("text")
    if not page_texts and isinstance(markdown, str) and markdown.strip():
        page_texts["1"] = markdown
    return page_texts


def _extract_tables(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    raw_tables = data.get("tables") or data.get("tables_raw") or []
    tables: list[dict[str, Any]] = []
    if not isinstance(raw_tables, list):
        return tables

    for idx, table in enumerate(raw_tables):
        if not isinstance(table, dict):
            continue
        rows = table.get("rows") or table.get("data") or table.get("cells") or []
        rows = _normalize_rows(rows)
        headers = table.get("headers") or (rows[0] if rows else [])
        tables.append(
            {
                "page": int(table.get("page") or table.get("page_number") or 0),
                "table_index": int(table.get("table_index") or idx),
                "table_id": str(table.get("table_id") or f"table_{idx}"),
                "table_title": str(table.get("table_title") or table.get("caption") or table.get("title") or ""),
                "caption": str(table.get("caption") or table.get("title") or ""),
                "headers": [str(h or "") for h in headers] if isinstance(headers, list) else [],
                "rows": rows,
            }
        )
    return tables


def _normalize_rows(rows: Any) -> list[list[str]]:
    if not isinstance(rows, list):
        return []
    normalized: list[list[str]] = []
    for row in rows:
        if isinstance(row, list):
            normalized.append([_cell_text(cell) for cell in row])
        elif isinstance(row, dict):
            cells = row.get("cells") or row.get("row") or list(row.values())
            if isinstance(cells, list):
                normalized.append([_cell_text(cell) for cell in cells])
    return normalized


def _cell_text(cell: Any) -> str:
    if isinstance(cell, dict):
        return str(cell.get("text") or cell.get("value") or "")
    return str(cell or "")


def _infer_page_count(data: dict[str, Any], page_texts: dict[str, str], tables_raw: list[dict[str, Any]]) -> int:
    for key in ["page_count", "pages_count", "num_pages"]:
        if isinstance(data.get(key), int):
            return data[key]
    pages = data.get("pages")
    if isinstance(pages, list):
        return len(pages)
    table_pages = [t.get("page", 0) for t in tables_raw if isinstance(t.get("page"), int)]
    return max([len(page_texts), *table_pages, 0])


def _looks_scanned(parsed_doc: dict[str, Any]) -> bool:
    page_count = parsed_doc.get("page_count") or 0
    if page_count <= 0:
        return True
    text_len = sum(len(re.sub(r"\s+", "", text)) for text in parsed_doc.get("page_texts", {}).values())
    return text_len < page_count * SCANNED_MIN_CHARS_PER_PAGE


def _failed_document(source_doc: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    return {
        "document_id": str(source_doc.get("document_id") or Path(source_doc.get("local_pdf_path", "")).stem or "unknown"),
        "file_type": source_doc.get("file_type", "unsupported_file_type"),
        "report_period": source_doc.get("report_period", ""),
        "parser_used": "none",
        "ocr_used": False,
        "page_count": 0,
        "page_texts": {},
        "tables_raw": [],
        "parse_status": "failed",
        "parse_confidence": "low",
        "parse_warnings": warnings,
        "json_output_path": "",
    }


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    result = await run_pdf_parse(args.query, output_dir=args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
