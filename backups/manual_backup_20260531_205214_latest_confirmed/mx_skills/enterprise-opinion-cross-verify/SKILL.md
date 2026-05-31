---
name: enterprise-opinion-cross-verify
description: 企业舆情交叉验证 Skill。用于贷后监控系统的舆情信息归集模块，当用户输入中国境内城投企业、地方国企、央企及下属企业全名时，先把 iFinD MCP 与 mx-finance-search 等已有 Skill 结果作为线索源，再用公开网页搜索和正文抓取进行交叉验证，输出已验证舆情摘要、正文片段、来源链接、发布时间和主体匹配依据。禁止输出贷后分析、风险评级、风险评分、投资建议或未经公开渠道验证的确定性结论。
---

# Enterprise Opinion Cross Verify

Use this Skill only as an information verification component. It does not perform post-loan analysis, risk grading, scoring, recommendations, or interpretive risk conclusions.

## Runtime

Use `scripts/cross_verify.py`.

Primary entry points:

- `run_opinion_batch(companies: list, default_params: dict | None, force: bool = False) -> dict`: scheduled batch entry point. It is the production path that may call MCP, mx Skills, public search, and page fetching.
- `run_cross_verification(params: dict, batch_context: bool = False) -> dict`: internal batch worker. In production, call it only from the batch service.
- `get_cached_opinion_result(company_name: str, batch_id: str | None = None) -> dict | None`: read cached batch output for frontend list pages.
- `get_latest_batch_status() -> dict`: return latest batch status.
- `get_full_text(full_text_id: str) -> dict | None`: return cached full text saved during verification.

Required input:

```json
{
  "company_name": "企业全名",
  "credit_code": "",
  "province": "",
  "city": "",
  "aliases": [],
  "lookback_days": 365,
  "max_results": 20,
  "include_full_text": true
}
```

## Batch-Only Triggering

- Production systems must run verification only through `run_opinion_batch` at the configured batch window: Thursday and Sunday 00:00 by default.
- Batch time is always Beijing time via `ZoneInfo("Asia/Shanghai")`; the intended cron rule is `0 0 * * 0,4`.
- Batch status includes `timezone`, `next_scheduled_run`, `latest_batch_id`, `latest_batch_status`, `latest_success_batch_id`, and `latest_success_finished_at`.
- Ordinary frontend APIs must read cached batch results only; they must not trigger MCP, mx Skill, public search, or page fetching.
- `run_cross_verification` rejects direct live calls unless explicitly invoked with batch context or `OPINION_ALLOW_DIRECT_VERIFY=true` is set for controlled local testing.
- `POST /api/opinion/verify` and legacy `POST /api/opinion/cross-verify` are disabled by default. Enable only for administrators with `OPINION_ENABLE_MANUAL_VERIFY=true` and `OPINION_ADMIN_TOKEN`.
- Scheduler/batch callers should use `POST /api/opinion/batch/run` with `X-Opinion-Batch-Token`; outside the batch window it returns a skipped status unless called with an internal force flag.
- Use `GET /api/opinion/batch/latest` to inspect latest batch status and `GET /api/opinion/company/:company_name` or `GET /api/opinion/verify?company_name=...` to read one company's cached result.
- `run_opinion_batch` uses a status/file lock. If a previous `running` batch is younger than `OPINION_BATCH_TIMEOUT_HOURS` (default `12`), a new batch returns `previous_batch_still_running`. Stale running batches are marked `stale_failed` before a new batch starts.
- Batch progress is updated per company through `asyncio.as_completed`; frontend polling can read `completed_companies`, `failed_companies`, and `total_companies` while the batch is still running.
- Cache reads default to `latest_success_batch_id`, so a new `running`, `failed`, or `skipped` batch does not hide the last successful or partially successful company result.

## Source Roles

- Treat iFinD MCP and mx Skills as clue sources only.
- Never trust MCP or mx Skill text as final facts without public verification.
- Truncate clue text aggressively. Keep only title, publish date, source, snippet, keywords, possible URL, and `raw_source`.
- Use public search and fetched public pages as verification sources.
- If public search fails, return MCP/Skill leads as `pending_verification`; do not promote them.

## Verification Workflow

1. Validate `company_name`; use the full company name as the primary search term.
2. Collect clue leads from enabled MCP sources.
3. Collect clue leads from enabled mx Skill sources.
4. Normalize leads into:

```json
{
  "title": "",
  "publish_date": "",
  "source": "",
  "snippet": "",
  "keywords": [],
  "possible_url": "",
  "raw_source": "mcp"
}
```

5. Deduplicate by normalized title, source, date, and keywords.
6. Generate public search queries for each candidate:
   - company full name + title
   - company full name + keywords
   - company full name + source
   - company full name + date + keywords
   - company full name + 行政处罚 / 被执行人 / 评级下调 / 债券公告 / 违约 / 逾期 / 诉讼
   - company full name + 债券 / 公告 / 评级报告 / 募集说明书 / 重大事项
7. Prefer official announcement sites, exchanges, bond disclosure channels, court enforcement sites, enterprise credit sites, Credit China, government regulators, mainstream finance media, local government, and local media.
8. Fetch public pages, extract title, source, publish date, and body text.
9. Verify target entity:
   - `strong`: the exact input full company name appears, or the input unified social credit code matches.
   - `medium`: a configured alias/name variant appears and at least two auxiliary conditions appear, such as province/city, controlling shareholder or investor, bond code, bond-short-name field, or official source.
   - `weak`: only abbreviation plus generic words such as公告、评级、债券、国资、城投 appears.
10. Put `strong` and `medium` matches into `verified_results`; put weak or unresolved matches into `pending_verification_results`; reject confirmed unrelated, duplicate, advertising, or low-quality pages.

## Verification Enhancements

- Directly search official disclosure channels before general discovery search. Current templates cover SSE, SZSE, ChinaMoney, SH Clearing, and NAFMII; keep them as high-priority verification sources.
- Run public verification concurrently with bounded parallelism. Tune with `OPINION_VERIFY_CONCURRENCY` (default `2`) and cap candidate breadth with `OPINION_MAX_VERIFY_LEADS`.
- Limit official-source query fanout with `OPINION_OFFICIAL_QUERY_LIMIT` (default `8`) and result count with `OPINION_OFFICIAL_MAX_RESULTS` (default `20`).
- Limit company-name variants used for broad discovery search with `OPINION_DISCOVERY_NAME_LIMIT` (default `8`) and total broad-discovery queries with `OPINION_DISCOVERY_QUERY_LIMIT` (default `24`); keep formal names and城投 aliases near the front.
- Deduplicate verified items at event level, preferring official domains and fully verified pages when media reposts and official announcements describe the same event.
- Include discovery aliases for城投名称 variants such as `城市投资` -> `城投`. Add site- or事件-specific discovery terms through `OPINION_EXTRA_DISCOVERY_TERMS`; do not hard-code media names.
- MCP calls share one global limiter, at least `OPINION_MCP_MIN_INTERVAL_SECONDS` between calls (default `0.7`), with two retries after 5 seconds and 15 seconds.
- Public search shares one global limiter via `OPINION_PUBLIC_SEARCH_INTERVAL_SECONDS` (default `1.2`). Page fetching also uses per-domain throttling via `OPINION_DOMAIN_FETCH_INTERVAL_SECONDS` (default `2.0`).
- Batch runs prioritize stability over speed. Use `OPINION_BATCH_COMPANY_CONCURRENCY` default `1` for 300+ company jobs unless operations confirms higher throughput is safe.

## Full Text Rules

- Return only `text_excerpt` in list responses; cap at 800 Chinese characters.
- Store complete fetched text through `FullTextStore`; the default implementation is file-backed JSON and can be replaced with an `opinion_full_texts` database table later.
- Return a `full_text_id` for separate retrieval.
- Do not show `full_text_id` as user-facing text; pass it only as the "view full text" button parameter.
- Set `full_text_available=false` when only a search snippet or partial text is available.
- Never fabricate full text.
- Parse public PDF pages with `pypdf`; when extracted PDF text is too short, optionally try OCR through `pdf2image` and `pytesseract`.
- OCR can be disabled with `OPINION_ENABLE_PDF_OCR=false`. It requires local Poppler (`pdftoppm`) and Tesseract binaries in addition to Python packages; if unavailable, the Skill skips OCR and keeps the page partially verified rather than fabricating text.
- Tune PDF handling with `OPINION_PDF_MAX_PAGES`, `OPINION_PDF_OCR_MAX_PAGES`, `OPINION_PDF_OCR_MIN_CHARS`, and `OPINION_OCR_LANG`.

## Backend API

Read one company's latest cached opinions:

```http
GET /api/opinion/company/济南城市建设集团有限公司
```

or:

```http
GET /api/opinion/verify?company_name=济南城市建设集团有限公司
```

Read latest batch status:

```http
GET /api/opinion/batch/latest
```

Manual verification is disabled by default:

```http
POST /api/opinion/verify
X-Opinion-Admin-Token: <admin token>
```

Scheduled batch run:

```http
POST /api/opinion/batch/run
X-Opinion-Batch-Token: <batch token>
Content-Type: application/json
```

```json
{
  "companies": [
    {
      "company_name": "济南城市建设集团有限公司",
      "credit_code": "",
      "province": "山东省",
      "city": "济南市",
      "aliases": ["济南城建"]
    }
  ],
  "default_params": {
    "lookback_days": 365,
    "max_results": 20,
    "include_full_text": true
  }
}
```

Read cached full text:

```http
GET /api/opinion/full-text/{full_text_id}
```

Frontend list page example:

```js
async function fetchVerifiedOpinions(companyName) {
  const res = await fetch(`/api/opinion/verify?company_name=${encodeURIComponent(companyName)}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

Frontend detail page example:

```js
async function fetchOpinionFullText(fullTextId) {
  const res = await fetch(`/api/opinion/full-text/${encodeURIComponent(fullTextId)}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

Frontend display rules:

- Show only `verified_results` where `verification_status` is `verified` and `entity_match.match_level` is `strong` or `medium`.
- Put `weak` or unknown entity matches into待核验; never show them as verified opinions.
- Do not render "交叉验证已完成" as an opinion event; it is a process status only.
- Hide `rejected_results` from default lists; expose them only in debug pages or logs.
- Use `source_excerpt` as the source text excerpt. Do not label it as an AI-generated summary.

## Packaging

Package with the Skill-bundled helper so zip entries use POSIX `/` paths:

```bash
python mx_skills/enterprise-opinion-cross-verify/scripts/package_enterprise_opinion_skill.py --output "$HOME/Desktop/enterprise-opinion-cross-verify.zip"
```

Validate an existing zip:

```bash
python mx_skills/enterprise-opinion-cross-verify/scripts/package_enterprise_opinion_skill.py --check --output "$HOME/Desktop/enterprise-opinion-cross-verify.zip"
```

Required zip entries:

- `enterprise-opinion-cross-verify/SKILL.md`
- `enterprise-opinion-cross-verify/scripts/cross_verify.py`
- `enterprise-opinion-cross-verify/scripts/package_enterprise_opinion_skill.py`

Reject any zip entry containing `\`.

## Output Guardrails

Do not output:

- Post-loan analysis conclusions.
- Risk grades or scores.
- Investment advice.
- Phrases such as "建议关注", "偿债压力较大", or "再融资压力较大".
- Unverified facts as final conclusions.
- Full text without a public source URL.
- Weak entity matches as verified results.
