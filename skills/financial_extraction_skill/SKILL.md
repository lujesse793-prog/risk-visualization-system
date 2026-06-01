---
name: financial_extraction_skill
description: Use when post-loan analysis needs to extract standardized financial statement fields and evidence from Skill2 parsed_documents JSON for downstream financial_analysis_skill inputs, without searching disclosures, parsing PDFs, computing ratios, or making risk judgements.
---

# Financial Extraction Skill

Use this skill as Skill3 in the post-loan pipeline. It converts Skill2 PDF parse output into standardized financial statement fields and traceable evidence for `financial_analysis_skill`.

## Boundary

Only do these tasks:

1. Read `source_documents[]` and `parsed_documents[]`.
2. Identify balance sheet, income statement, and cash flow statement data.
3. Map Chinese financial line items to `standard_field_name`.
4. Output `structured_financial_data`, `field_evidence`, `missing_fields`, `extraction_warnings`, `document_usage`, and `validation_result`.

Never search announcements, download PDFs, parse raw PDFs, OCR, calculate financial ratios, generate risk conclusions, invent values, fill by experience, or let prospectus/rating-report summary data overwrite newer annual/semiannual/quarterly report statement data.

## Quick Run

```bash
python scripts/run_analysis.py --input input.json --output output.json
```

The script must always write structured JSON. On extraction failure, it writes a failed result instead of raising an uncaught exception. It automatically runs `scripts/validate_output.py` before finishing and stores validation errors in `validation_result.errors`.

## References

Load only what is needed:

- `references/input-schema.md` for accepted Skill2 input shape.
- `references/output-schema.md` for required Skill3 output shape.
- `references/field-mapping.md` for Chinese-to-standard financial fields.
- `references/field-aliases.md` for accepted aliases that should map before declaring missing fields.
- `references/period-rules.md` for period and period_type rules.
- `references/extraction-rules.md` for document/table/source priority and conflict handling.
- `references/evidence-rules.md` for field evidence requirements.
- `references/validation-rules.md` for pre-delivery self-checks and status logic.

## Implementation Notes

Prefer consolidated primary statements from structured `tables_raw`. Exclude tables whose title contains note/detail words such as `附注`, `明细`, `构成`, `账龄`, `分类`, or `补充资料` from primary extraction. Use page text only as lower-confidence fallback. Use prospectus or rating-report financial summaries only when no formal report statement is available, lower confidence, and warn.

When units are not explicit, keep `unit = "unknown"`, lower confidence, and emit `unit_uncertain`; never silently assume yuan.
