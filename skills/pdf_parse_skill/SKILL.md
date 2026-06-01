---
name: pdf-parse-skill
description: Parse post-loan disclosure PDFs into unified parsed_documents JSON using Marker first and Surya OCR fallback. Use when a workflow needs PDF text/table/page extraction for annual reports, semiannual reports, quarterly reports, prospectuses, rating reports, or other source documents, without financial indicator calculation or risk judgement.
---

# PDF Parse Skill

Use this skill to turn source PDF documents into a stable `parsed_documents[]` payload for downstream extraction.

## Contract

Input should be JSON with either:

- `documents_to_parse`: array of source documents.
- `input_path`: single PDF path for quick parsing.

Each source document may include `document_id`, `file_type`, `report_period`, `title`, `local_pdf_path`, `pdf_url`, and `pdf_sha256`.

Output is JSON with:

- `parsed_documents`: one entry per processed document.
- `failed_documents`: parse/download failures with reasons.
- `parse_summary`: total/success/partial/failed counts.

Each `parsed_documents[]` entry must include:

- `document_id`
- `file_type`
- `report_period`
- `parser_used`
- `ocr_used`
- `page_count`
- `page_texts`
- `tables_raw`
- `parse_status`
- `parse_confidence`
- `parse_warnings`
- `json_output_path`

Preserve page numbers, raw table rows/columns, table captions, and each table's page in `tables_raw`.

## Workflow

Run `scripts/run_pdf_parse.py` with a JSON payload.

Marker is attempted first. If Marker fails, produces very little text, or the document looks scanned, run Surya OCR as fallback. If both tools are unavailable or fail, return a failed parsed document with a clear warning and failure reason.

Do not calculate financial metrics, infer risk levels, write credit judgements, or summarize financial performance. This skill only parses documents.

## Dependencies

The script checks these commands in order:

- Marker: `MARKER_BIN` environment variable, then `marker_single`, then `marker`.
- Surya: `SURYA_BIN` environment variable, then `surya_ocr`.

If a command is missing, return a clear error in `parse_warnings` and `failed_documents` instead of silently swallowing it.
