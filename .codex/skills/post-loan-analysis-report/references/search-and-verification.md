# 搜索与验证规则

先读 `source-policy.md`。本 skill 只能搜索中国货币网、上海证券交易所、深圳证券交易所，不可扩展到其他网站。

## 候选名称

搜索时不要只用输入全名。先构造 `candidate_names`：

1. 输入企业全名
2. 企业简称
3. 可能的债券发行人名称
4. 搜索结果中出现的高度相似名称
5. 历史名称或曾用名

优先使用标题与输入名称完全匹配的文件。如果标题使用历史名称、曾用名或高度相似名称，必须通过以下至少一项验证主体：

- PDF 封面页中的发行人/披露主体
- 募集说明书或报告中的发行人字段
- 统一社会信用代码
- 债券发行人身份
- 明确的历史名称关系

如果无法确认同一主体关系，不使用该文件并记录 `skipped_reason`。

示例：对于「泰州医药城控股集团有限公司」，候选名称可能包括：
- 泰州医药城控股集团有限公司
- 泰州东方中国医药城控股集团有限公司

第二个名称必须经过主体核验后才能采用或排除，不能直接采用或直接排除。

## 文件分类

将标题和附件分类为：

- `annual_report`：包含 年度报告、年报、年度审计报告、年度财务报表、合并及母公司财务报表、财务报表及附注、经审计财务报告、审计报告、年度财务报表及附注
- `semi_annual_report`：包含 半年度报告、半年报、半年度财务报表
- `quarterly_report`：包含 一季度、三季度、季度报告、季度财务报表
- `prospectus`：包含 募集说明书
- `rating_report`：包含 评级报告、跟踪评级报告、信用评级报告、主体评级报告、债项评级报告

不要将独立的「评级结果公告」分类为 `rating_report`，除非详情页或附件列表包含完整评级报告 PDF。如果无完整评级报告附件，分类为 `unsupported_file_type` 并记录 `skipped_reason`。

如果标题含通用「财务报表」同时含「一季度」「三季度」「半年度」等词，归类为对应季度/半年报，而非 `annual_report`。

对于标题为「更正公告」或「说明公告」的包装页面，过滤前检查附件名称。如果附件名含允许文件类型或「更正后文件」，下载并处理更正后的正式 PDF。

## 中国货币网检索

必须使用中国货币网内部检索或等效 ChinaMoney 页面/API 检索。外部搜索引擎 `site:` 查询只能作为补充，不能作为唯一检索方式。

对每个企业：

1. 按候选名称搜索
2. 优先标题搜索
3. 使用全部时间范围或覆盖最近两年
4. 先用全部栏目，再识别财务报告、募集说明书、评级报告
5. 至少扫描前 30 条结果（如有）
6. 不因第一个或最新结果就停止
7. 打开匹配结果的详情页或 PDF 链接
8. 如果页面有附件列表，解析附件列表并下载 PDF

## 定向年报搜索

默认每平台扫描前 30 条结果。**如果前 30 条通用全名结果不含 `annual_report`，每个平台都必须继续搜索：**

1. `{企业全名} 年度报告`
2. `{企业全名} 年报`
3. `{企业全名} 审计报告`
4. `{企业全名} 年度财务报表`
5. `{企业全名} 合并及母公司财务报表`

每次定向搜索至少扫描前 30 条结果（如有）。**不得因为找到季度报告就提前停止。** 每条搜索记录为独立 `query_run`。

## 上交所检索

仅搜索债券相关披露页面和项目平台页面：
- 上交所债券信息网
- 公司债券项目信息平台
- 债券公告和信息披露页面

## 深交所检索

仅搜索固定收益和债券披露区域：
- 固定收益信息平台
- 债券公告
- 信息披露页面

## 不要因季度报告更新就跳过年报

绝不在最新季度报告处停止、不只取第一条结果、不因存在季度报告就停止搜索年报。

## 轻量 PDF 验证（不是完整财务解析）

本 skill 只做轻量 PDF 验证，不做复杂财务报表解析。对每个选中的 PDF：

1. 下载 PDF
2. 尝试读取封面页、前 3 页或元数据
3. 验证企业名称、披露主体、发行人、受评主体是否与输入企业一致
4. 识别 `report_period`
5. 识别 `file_type`
6. 记录 `pdf_download_status`、`light_parse_status`、`light_parse_failed_reason`

如果轻量解析失败，**不代表文件无效**。应将该 PDF 交给后续 PDF 解析 skill（Marker/Surya）处理，记录 `needs_deep_pdf_parse=true`。

对财务报告，记录识别的 `report_period`。新鲜度门控以 `run_date` 为准动态计算（见 `source-policy.md`），`report_period < Y-1` 年的财务报告记录为 `stale_or_prior_period_document`。

对募集说明书和评级报告，记录文档内披露的财务数据截止期 `disclosed_financial_data_cutoff`。

## query_runs 记录

每平台每次搜索都必须记录在 `search_log.query_runs` 中。每条 `query_run` 记录一次特定关键词搜索及其范围和结果。

必填字段：`keyword`、`search_scope`、`search_column`、`total_results`、`scanned_result_count`、`matched_documents`、`annual_report_found`、`matched_titles`、`selected_titles`、`skipped_titles`、`matched_items`、`note`。

`matched_items` 每项含：`title`、`attachment_title`、`publish_date`、`source_url`、`pdf_url`、`file_type`、`decision`、`reason`。

## 主体核验对象

每份被采纳的 source 必须包含：

```json
{
  "entity_verification": {
    "input_name": "",
    "matched_name_in_document": "",
    "matched_role": "发行人 / 披露主体 / 受评主体 / 母公司 / 子公司 / 关联方 / 历史名称 / 不确定",
    "is_same_subject": true,
    "relationship_to_target": "",
    "verification_evidence": "",
    "confidence": "high / medium / low"
  }
}
```

仅 high 或 medium 置信度且 `is_same_subject=true` 的文件进入 handoff。low 置信度和 `is_same_subject=false` 的文件标记为 `subject_mismatch`。