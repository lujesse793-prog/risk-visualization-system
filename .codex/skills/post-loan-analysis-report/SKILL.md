---
name: post-loan-analysis-report
description: 公告搜索与PDF来源发现 skill。输入企业名称，仅在中国货币网、上海证券交易所、深圳证券交易所三个平台搜索五类公开文件（年度报告、半年度报告、季度报告、募集说明书、评级报告），提取PDF链接并下载，进行轻量主体核验和报告期识别，输出 source_documents[]、search_log 和 pdf_handoff 给后续 PDF 解析 skill。不做PDF表格解析、财务字段抽取、指标计算和风险判断。
---

# 公告搜索与PDF来源发现

## 职责边界

本 skill 是贷后分析流程的**第一个 skill**，只负责搜索和发现公开披露文件的 PDF 来源：

1. 接收企业名称
2. 在三个指定平台搜索
3. 识别并分类五类文件
4. 提取/下载 PDF 链接，记录下载状态
5. 轻量主体核验（封面页、发行人、受评主体）
6. 报告期识别
7. 新鲜度门控（基于 `run_date` 动态计算）
8. 输出标准化 `source_documents[]` 和 `search_log`
9. 生成 `pdf_handoff` 交给后续 PDF 解析 skill（Marker/Surya）

本 skill **严格不做**：
- PDF 表格解析（资产负债表、利润表、现金流量表）
- 财务字段抽取
- 财务指标计算
- 负面风险判断
- 最终贷后分析报告生成

## 输入

```json
{
  "enterprise_name": "企业全名",
  "run_date": "YYYY-MM-DD",
  "max_results_per_channel": 30
}
```

`enterprise_name` 必填。`run_date` 默认当天日期。`max_results_per_channel` 默认 `30`。

## 工作流程

### 第一步：构造候选名称

读 `references/search-and-verification.md`，构造 `candidate_names`：

1. 输入企业全名
2. 简称
3. 可能的债券发行人名称
4. 搜索结果中出现的高度相似名称
5. 历史名称或曾用名

历史名称、相似名称必须经过 `entity_verification` 核验后才能采用。

### 第二步：三平台检索

仅从以下三个平台搜索：
- 中国货币网 (`chinamoney.com.cn`)
- 上海证券交易所 / 上交所债券信息网 (`sse.com.cn`, `bond.sse.com.cn`)
- 深圳证券交易所 / 深交所固定收益信息平台 (`szse.cn`)

每个平台至少扫描前 30 条结果（如有）。不因找到最新季度报告就停止搜索。不得搜索新闻、工商信息、招聘、招标、第三方聚合器、发行人官网等来源。

### 第三步：文件分类

识别以下五类文件：

- `annual_report`：年度报告、年报、年度审计报告、年度财务报表、合并及母公司财务报表、财务报表及附注
- `semi_annual_report`：半年度报告、半年报、半年度财务报表
- `quarterly_report`：一季度报告、三季度报告、季度报告、季度财务报表
- `prospectus`：募集说明书、更新募集说明书、中期票据募集说明书、公司债券募集说明书、超短期融资券募集说明书
- `rating_report`：评级报告、跟踪评级报告、信用评级报告、主体评级报告、债项评级报告

不支持的公告类型标记为 `unsupported_file_type`。

### 第四步：PDF 链接提取与下载

打开详情页或附件列表，找到真实 PDF 地址。下载 PDF 或记录可下载 PDF 链接。

### 第五步：轻量主体核验

读 `references/search-and-verification.md`。每个 selected 文件必须生成 `entity_verification`：

- 读取 PDF 封面页或前 3 页
- 验证企业名称、披露主体、发行人、受评主体是否与输入企业一致
- 通过 PDF 封面、发行人字段、统一社会信用代码或历史名称关系确认

如果只是标题相似但无法确认为同一主体，`document_status=subject_mismatch`。

### 第六步：报告期识别与新鲜度门控

识别每个文件的 `report_period` 和 `file_type`。

以 `run_date` 为基准动态计算新鲜度（见 `references/source-policy.md`）：
- 记 `run_date` 的年份为 Y
- 财务报告有效 `report_period >= Y-1` 年
- 募集说明书和评级报告有效 `publish_date >= Y-1-01-01`
- 如 `run_date` 在年报披露窗口期前，可允许 `Y-2` 年年报过渡，但必须标注数据滞后
- **不写死特定年份**

### 第七步：主文件选择

严格按照优先级选择：

```
annual_report > semi_annual_report > quarterly_report > prospectus > rating_report
```

1. 最新有效年报必须选为 `selected_main`
2. 更新季度报告可保留为 `selected_supplement`
3. 不得因季报更新就跳过年报
4. 无财务报告但有募集说明书/评级报告，可作 `selected_supplement`
5. 三平台都无有效文件，`no_latest_public_data=true`

### 第八步：生成输出

1. 输出标准化 `source_documents[]`
2. 输出完整 `search_log`（含三个平台、query_runs）
3. 输出 `pdf_handoff` 对象交给后续 PDF 解析 skill
4. `financial_tables`、`financial_indicators`、`negative_findings` 必须为空

## 定向年报搜索规则

如果主全名搜索前 30 条未找到 `annual_report`，**每个平台**必须继续搜索以下五条，每次记录为独立 `query_run`：

1. `{企业全名} 年度报告`
2. `{企业全名} 年报`
3. `{企业全名} 审计报告`
4. `{企业全名} 年度财务报表`
5. `{企业全名} 合并及母公司财务报表`

**不得因为找到季度报告就提前停止。**

## 输出结构

详见 `references/output-schema.md`。核心：

- `task_type`: `"announcement_source_discovery"`
- `run_date`: 运行日期
- `source_documents[]`: 所有发现、分类、验证后的文档
- `search_log[]`: 三个平台的搜索记录（含 query_runs）
- `freshness_gate`: 动态新鲜度判断
- `data_availability`: 简化数据可用性
- `pdf_handoff`: 交给后续 PDF 解析 skill 的交接对象
- `financial_tables` / `financial_indicators` / `negative_findings`: 必须为空

## pdf_handoff

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

`documents_needing_pdf_parse` 准入条件：
- `document_status` 为 `selected_main` 或 `selected_supplement`
- `file_type` 属于五类允许文件
- `pdf_url` 或 `local_pdf_path` 存在
- `needs_deep_pdf_parse=true`
- `entity_verification.is_same_subject=true`
- `entity_verification.confidence` 为 `high` 或 `medium`

禁止进入：`unsupported_file_type`、`subject_mismatch`、`stale_or_prior_period_document`、`download_failed`。

## 数据规则

- 所有数据必须有来源
- 来源仅限中国货币网、上海证券交易所、深圳证券交易所
- 每份 source 必须包含 `entity_verification` 和 `handoff_to_pdf_parser`
- URL 域名必须匹配对应平台

## 参考文献

- `references/search-and-verification.md`：三平台检索逻辑、候选名称、文件分类、轻量 PDF 验证、主体核验、query_runs
- `references/source-policy.md`：三平台白名单、允许文件类型、动态新鲜度门控
- `references/period-and-source-rules.md`：年报优先级、主文件选择
- `references/data-availability.md`：数据可用性判定
- `references/output-schema.md`：最终 JSON 结构

## 已废弃文件

以下文件标记为废弃，由后续 PDF 解析和财务抽取 skill 负责：
- `references/financial-fields.md`
- `references/negative-signals.md`
- `references/negative-thresholds.md`

## 验证

生成 JSON 后运行 `python scripts/validate_output.py <output.json>` 校验。