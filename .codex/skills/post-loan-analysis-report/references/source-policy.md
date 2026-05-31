# 来源策略与新鲜度门控

## 允许检索渠道

本 skill 仅从以下 3 个公开渠道检索文件：

1. 中国货币网
   - `https://www.chinamoney.com.cn`
   - 使用内部站点检索或等效 ChinaMoney 页面/API 检索债券信息披露、财务报告、募集说明书和评级报告
   - 不依赖外部搜索引擎 `site:` 查询作为唯一方式
2. 上海证券交易所 / 上交所债券信息网
   - `https://www.sse.com.cn`
   - `https://bond.sse.com.cn`
   - 使用上交所债券信息网、公司债券项目信息平台、债券公告和信息披露页面
3. 深圳证券交易所 / 深交所固定收益信息平台
   - `https://www.szse.cn`
   - 使用深交所固定收益信息平台、债券公告、信息披露页面

不得搜索或使用任何其他网站。不得搜索新闻、工商信息、招聘、招标、第三方聚合器、发行人官网等来源。

如果三渠道没有提供有效最新公开披露，停止并在 `pdf_handoff` 中设置 `no_latest_public_data=true`。

## 允许文件类型

仅检索、下载、处理以下 5 类文件：

1. `annual_report`：年度报告、年报、年度财务报表、年度审计报告、经审计财务报告、合并及母公司财务报表、合并财务报表、母公司财务报表、审计报告、财务报表及附注、年度财务报表及附注
2. `semi_annual_report`：半年度报告、半年报、半年度财务报表
3. `quarterly_report`：第一季度报告、一季度报告、第一季度财务报表、一季度财务报表、第三季度报告、三季度报告、季度财务报表
4. `prospectus`：募集说明书、更新募集说明书、债券募集说明书、中期票据募集说明书、超短期融资券募集说明书
5. `rating_report`：主体评级报告、债项评级报告、跟踪评级报告、信用评级报告、评级报告

独立的「评级结果公告」不得分类为 `rating_report`。如果评级结果公告有附件标题含完整评级报告术语的附件，可分类并使用附件。如果无完整评级报告附件，将包装页分类为 `unsupported_file_type` 并记录 `skipped_reason`。

以下默认排除：付息公告、兑付公告、发行结果公告、持有人会议公告、法律意见书、受托管理事务报告、临时公告、发行方案、承诺函、说明公告、一般更正公告、工商信息、新闻报道、舆情信息。

例外：如果标题或附件含「年度报告」「半年度报告」「季度报告」「财务报表」「审计报告」「募集说明书」「评级报告」或「更正后文件」，不因包装页标题就过滤。打开详情页和附件列表，下载更正后的正式 PDF。

## 文件类型优先级

```
annual_report > semi_annual_report > quarterly_report > prospectus > rating_report
```

1. 年度报告是主数据来源。如最新年报存在，必须下载、验证并选为 `selected_main`
2. 半年度报告补充年报
3. 季度报告仅作补充
4. 募集说明书和评级报告补充企业信息，不作为主文件
5. 绝不使用募集说明书或评级报告替换已有年报

## 新鲜度门控（动态）

以 `run_date` 为基准动态计算。记 `run_date` 所在年份为 Y。

### 对财务报告

1. 使用文件前先识别 `report_period`
2. 最新有效 `report_period` 原则上要求 `>= Y-1` 年
3. 如 `publish_date >= Y-1 年 1 月 1 日` 但 `report_period < Y-1` 年，记录为 `stale_or_prior_period_document`
4. 如果 `run_date` 处于当年年报披露尚未完成阶段（通常 1-4 月），可允许 `Y-2` 年年报作为过渡性主文件：
   - `transitional_fallback_used=true`
   - `data_limitation_note` 必须注明「数据滞后，基于 Y-2 年年报」

### 对募集说明书和评级报告

1. 使用 `publish_date >= Y-1 年 1 月 1 日` 作为新鲜度测试
2. 记录文档内财务数据的实际截止日期 `disclosed_financial_data_cutoff`

### 门控触发条件

全部满足时触发：

1. 未找到 `report_period >= Y-1` 年的财务报告
2. 未找到 `publish_date >= Y-1 年 1 月 1 日` 的募集说明书或评级报告
3. 且无符合条件的过渡性文件

触发后：停止搜索，`pdf_handoff.no_latest_public_data=true`，`documents_needing_pdf_parse=[]`。

## URL 域名白名单

仅以下域名及子域名允许：

- 中国货币网：`chinamoney.com.cn`
- 上海证券交易所：`sse.com.cn`, `bond.sse.com.cn`
- 深圳证券交易所：`szse.cn`

每个 `source_url` 和 `pdf_url` 必须匹配以上域名。`source_platform` 必须与域名匹配。