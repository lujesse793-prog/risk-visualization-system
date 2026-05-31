# 输出模式

本 skill 的输出是 **公告来源发现（announcement source discovery）** 结果，供后续 PDF 解析 skill 使用。

```json
{
  "task_type": "announcement_source_discovery",
  "enterprise_name": "",
  "run_date": "YYYY-MM-DD",
  "allowed_sources": [
    "中国货币网",
    "上海证券交易所",
    "深圳证券交易所"
  ],
  "source_documents": [],
  "search_log": [],
  "freshness_gate": {},
  "data_availability": {},
  "pdf_handoff": {},
  "sources": {},
  "financial_tables": {},
  "supplemental_financial_tables": {},
  "financial_indicators": [],
  "negative_findings": [],
  "negative_summary_under_200_chars": "",
  "missing_data_note": ""
}
```

> `financial_tables`、`supplemental_financial_tables`、`financial_indicators`、`negative_findings` 仅作为向后兼容字段保留，**必须为空**，由后续 PDF 解析和财务抽取 skill 负责填充。

---

## 核心输出字段

### task_type

固定值 `"announcement_source_discovery"`，标识本输出为第一阶段来源发现结果。

### run_date

本次搜索运行的日期，格式 `YYYY-MM-DD`。**新鲜度门控以 `run_date` 为基准动态计算**。

---

## source_documents[]（核心）

`source_documents` 是所有发现、分类、验证后的文档清单，作为后续 PDF 解析 skill 的输入。每个文档必须包含：

```json
{
  "document_id": "唯一标识符",
  "enterprise_input_name": "输入的企业全名",
  "source_platform": "中国货币网 / 上海证券交易所 / 深圳证券交易所",
  "source_channel": "具体频道或板块名称",
  "title": "公告或文档标题",
  "attachment_title": "附件标题",
  "file_type": "annual_report / semi_annual_report / quarterly_report / prospectus / rating_report / unsupported_file_type",
  "report_period": "如 2025年 / 2025年6月30日 / 2025年一季度",
  "publish_date": "YYYY-MM-DD",
  "source_url": "详情页URL",
  "pdf_url": "PDF直接链接",
  "local_pdf_path": "本地路径",
  "pdf_download_status": "success / failed / skipped",
  "pdf_file_size": null,
  "pdf_sha256": "",
  "light_parse_status": "success / partial / failed / not_attempted",
  "light_parse_failed_reason": "",
  "needs_deep_pdf_parse": true,
  "document_status": "selected_main / selected_supplement / skipped / stale_or_prior_period_document / subject_mismatch / unsupported_file_type / download_failed",
  "selection_reason": "",
  "skipped_reason": "",
  "entity_verification": {
    "input_name": "输入企业名称",
    "matched_name_in_document": "文档中的匹配名称",
    "matched_role": "发行人 / 披露主体 / 受评主体 / 母公司 / 子公司 / 关联方 / 历史名称 / 不确定",
    "is_same_subject": true,
    "relationship_to_target": "",
    "verification_evidence": "",
    "confidence": "high / medium / low"
  },
  "handoff_to_pdf_parser": {
    "enabled": true,
    "parser_hint": "marker_first_surya_ocr_fallback",
    "priority": 1,
    "reason": ""
  }
}
```

### document_status 含义

| 值 | 含义 |
|---|---|
| `selected_main` | 选为主文件（优先年报） |
| `selected_supplement` | 选为补充文件 |
| `skipped` | 被跳过 |
| `stale_or_prior_period_document` | 过期文档 |
| `subject_mismatch` | 主体核验不匹配 |
| `unsupported_file_type` | 不支持的文件类型 |
| `download_failed` | 下载失败 |

---

## search_log[]

固定三个平台，每个一条：

```json
{
  "source_name": "中国货币网 / 上海证券交易所 / 深圳证券交易所",
  "searched": true,
  "search_modes": ["内部检索", "页面检索", "附件检索", "PDF下载/链接提取"],
  "keywords_used": [],
  "total_results": 0,
  "scanned_result_count": 0,
  "matched_documents": 0,
  "selected_documents": [],
  "skipped_documents": [],
  "skipped_reason": [],
  "download_status": "success / partial / failed / not_applicable",
  "light_parse_status": "success / partial / failed / not_applicable",
  "latest_document_publish_date": "",
  "latest_report_period": "",
  "status": "matched / not_found / stale_only / subject_mismatch / error",
  "note": "",
  "query_runs": []
}
```

### query_runs

```json
{
  "keyword": "",
  "search_scope": "按标题 / 按正文 / 全部",
  "search_column": "",
  "total_results": 0,
  "scanned_result_count": 0,
  "matched_documents": 0,
  "annual_report_found": false,
  "matched_titles": [],
  "selected_titles": [],
  "skipped_titles": [],
  "matched_items": [
    {
      "title": "",
      "attachment_title": "",
      "publish_date": "",
      "source_url": "",
      "pdf_url": "",
      "file_type": "",
      "decision": "selected / skipped",
      "reason": ""
    }
  ],
  "note": ""
}
```

### 定向年报搜索

如果主全名搜索前 30 条未找到 `annual_report`，每个平台必须继续搜索以下五条，每条记录为独立 `query_run`：

1. `{企业全名} 年度报告`
2. `{企业全名} 年报`
3. `{企业全名} 审计报告`
4. `{企业全名} 年度财务报表`
5. `{企业全名} 合并及母公司财务报表`

---

## freshness_gate（动态）

以 `run_date` 为基准动态计算：

```json
{
  "run_year": 2026,
  "min_financial_report_year": 2025,
  "min_prospectus_rating_publish": "2025-01-01",
  "is_fresh_enough": true,
  "latest_document_publish_date": "",
  "latest_report_period": "",
  "stop_reason": "",
  "transitional_fallback_used": false,
  "transitional_fallback_note": ""
}
```

**规则**：`run_year` 为 `run_date` 的年份，记为 Y。
- 财务报告最新有效 `report_period` 要求 `>= Y-1` 年
- 募集说明书和评级报告 `publish_date` 要求 `>= Y-1` 年 1 月 1 日
- 如果 `run_date` 处于当年年报披露尚未完成阶段（如 1-4 月），可允许 `Y-2` 年年报作为过渡性主文件，但 `transitional_fallback_used=true` 并注明数据滞后
- **不得长期写死特定年份**

---

## data_availability

```json
{
  "has_financial_report": false,
  "has_prospectus": false,
  "has_rating_report": false,
  "has_any_valid_document": false,
  "data_level": "has_data / no_data",
  "data_limitation_note": ""
}
```

---

## pdf_handoff（必须存在）

交给后续 PDF 解析 skill 的交接对象：

```json
{
  "enterprise_name": "",
  "task_id": "",
  "generated_at": "",
  "selected_main_documents": [],
  "selected_supplement_documents": [],
  "documents_needing_pdf_parse": [],
  "no_latest_public_data": false,
  "message": ""
}
```

### documents_needing_pdf_parse 准入条件

**必须同时满足全部条件：**

1. `document_status` 为 `selected_main` 或 `selected_supplement`
2. `file_type` 属于 `annual_report`、`semi_annual_report`、`quarterly_report`、`prospectus`、`rating_report`
3. `pdf_url` 或 `local_pdf_path` 非空
4. `needs_deep_pdf_parse` = `true`
5. `entity_verification.is_same_subject` = `true`
6. `entity_verification.confidence` 为 `high` 或 `medium`

**禁止进入的文档：**
- `file_type` = `unsupported_file_type`
- `document_status` = `subject_mismatch`
- `document_status` = `stale_or_prior_period_document`
- `document_status` = `download_failed`

如果 `no_latest_public_data` = `true`，`documents_needing_pdf_parse` **必须为空数组**，`message` 必须为固定提示语。

---

## 兼容字段

以下字段保留向后兼容，本 skill 输出时**必须为空**：

| 字段 | 值 |
|---|---|
| `financial_tables` | `{}` |
| `supplemental_financial_tables` | `{}` |
| `financial_indicators` | `[]` |
| `negative_findings` | `[]` |

---

## 验证规则

1. `task_type` 必须为 `"announcement_source_discovery"`
2. `run_date` 必须存在且为有效日期
3. `source_documents[]` 必须存在
4. 每个 `source_document` 的 `source_platform` 只能是三个允许平台
5. `source_url` 和 `pdf_url` 域名必须匹配对应 `source_platform`
6. `search_log` 必须包含三个平台各一条记录
7. 如果第一条 `query_run` 没有 `annual_report` 且平台有结果，必须存在五条定向年报 `query_run`
8. 每个 `selected` 文档必须有 `entity_verification` 和 `handoff_to_pdf_parser`
9. `pdf_handoff` 必须作为顶层字段存在
10. `documents_needing_pdf_parse` 只能包含符合条件的文档
11. `unsupported_file_type`、`subject_mismatch`、`stale_or_prior_period_document`、`download_failed` 不得进入 handoff
12. `rating_result announcement` 不能误判为 `rating_report`
13. `financial_tables`、`financial_indicators`、`negative_findings` 必须为空