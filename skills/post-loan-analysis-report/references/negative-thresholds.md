# Negative Indicator Thresholds

Use these default thresholds only for objective negative descriptions. They must not be used for automatic rating, credit approval advice, or investment advice.

All indicators must be calculated from reliable data in annual reports, semiannual reports, prospectuses, or rating reports. If data is missing or the basis is inconsistent, output `无法计算`; do not estimate.

## Solvency

### 资产负债率

Formula:

```text
资产负债率 = 负债合计 / 资产总计
```

Rules:

- `>= 70%`: 资产负债率处于较高水平。
- `>= 80%`: 资产负债率处于高位。
- `>= 85%`: 资产负债率显著偏高，财务杠杆压力较大。
- 连续两年上升: 财务杠杆持续抬升。
- 连续三年上升且超过 `70%`: 债务负担持续加重。

### 流动比率

Formula:

```text
流动比率 = 流动资产合计 / 流动负债合计
```

Rules:

- `< 1.00`: 流动资产对流动负债覆盖不足。
- `< 0.80`: 短期流动性压力较大。
- `< 0.50`: 流动性压力突出。
- 连续两年下降且低于 `1`: 短期偿债保障持续弱化。

### 速动比率

Formula:

```text
速动比率 = (流动资产合计 - 存货) / 流动负债合计
```

Rules:

- `< 1.00`: 速动资产对流动负债覆盖不足。
- `< 0.70`: 短期偿债能力偏弱。
- `< 0.50`: 剔除存货后的流动性压力较大。
- For urban-investment entities whose inventory mainly consists of land consolidation cost, development cost, or land to be developed, mention inventory monetization and asset liquidity.

### 现金短债比

Formula:

```text
现金短债比 = 货币资金 / (短期借款 + 一年内到期的非流动负债)
```

Rules:

- `< 1.00`: 货币资金对短期债务覆盖不足。
- `< 0.50`: 短期偿债压力较大。
- `< 0.30`: 短期偿债压力突出。
- `< 0.10`: 货币资金对短期债务覆盖能力严重不足。
- 连续两期低于 `0.50`: 短期偿债压力持续存在。

### 货币资金 / 流动负债

Formula:

```text
货币资金覆盖流动负债比例 = 货币资金 / 流动负债合计
```

Rules:

- `< 30%`: 货币资金对流动负债覆盖偏弱。
- `< 15%`: 流动负债现金覆盖能力较弱。
- `< 10%`: 即期流动性压力较大。

### 短期有息债务占比

Formula:

```text
短期有息债务占比 = (短期借款 + 一年内到期的非流动负债) /
(短期借款 + 一年内到期的非流动负债 + 长期借款 + 应付债券)
```

Rules:

- `>= 30%`: 有息债务期限结构偏短。
- `>= 40%`: 短期债务占比较高。
- `>= 50%`: 债务集中到期压力较大。
- 连续两期上升且超过 `40%`: 债务期限结构持续短期化。

## Profitability

### 营业收入同比变动

Formula:

```text
营业收入同比变动 = 本期营业收入 / 上期营业收入 - 1
```

Rules:

- `<= -10%`: 营业收入有所下降。
- `<= -30%`: 营业收入明显下降。
- `<= -50%`: 营业收入大幅下降。
- 连续两年下降: 主营业务收入持续承压。
- 连续三年下降: 收入规模持续收缩。
- Compare semiannual reports only with the same period of the previous year.
- Compare annual reports only with the previous full year.
- Do not compare semiannual revenue directly with full-year revenue.

### 净利润同比变动

Formula:

```text
净利润同比变动 = 本期净利润 / 上期净利润 - 1
```

Rules:

- `<= -30%`: 盈利能力明显弱化。
- `<= -50%`: 净利润大幅下降。
- 净利润为负: 公司出现亏损。
- 连续两年净利润下降: 盈利能力持续承压。
- 连续两年亏损: 持续亏损，对自身造血能力形成不利影响。
- 由盈转亏: 盈利表现明显恶化。

### 归母净利润同比变动

Formula:

```text
归母净利润同比变动 = 本期归母净利润 / 上期归母净利润 - 1
```

Rules:

- `<= -30%`: 归母净利润明显下降。
- `<= -50%`: 归母净利润大幅下降。
- 归母净利润为负: 归属于母公司股东的利润为负。
- 净利润为正但归母净利润为负: 少数股东损益对利润贡献较大，母公司股东层面盈利承压。

### 毛利率

Formula:

```text
毛利率 = (营业收入 - 营业成本) / 营业收入
```

Rules:

- `< 10%`: 主营业务毛利率较低。
- `< 5%`: 主营业务盈利空间较弱。
- 同比下降超过 `5` 个百分点: 毛利率明显下滑。
- 连续两年下降: 主营业务盈利能力持续弱化。
- 毛利率为负: 主营业务出现倒挂。

### 净利率

Formula:

```text
净利率 = 净利润 / 营业收入
```

Rules:

- `< 3%`: 净利率较低。
- `< 1%`: 盈利空间较弱。
- `< 0`: 销售收入无法覆盖成本费用，出现亏损。
- 连续两年下降: 盈利质量持续弱化。

### 财务费用率

Formula:

```text
财务费用率 = 财务费用 / 营业收入
```

Rules:

- `> 10%`: 财务费用对利润形成一定侵蚀。
- `> 20%`: 利息负担较重。
- `> 30%`: 财务费用压力突出。
- 财务费用同比增长超过 `30%`: 融资成本或债务规模上升对利润形成压力。

## Cash Flow

- 经营活动现金流量净额 `< 0`: 经营活动现金流为净流出。
- 经营活动现金流量净额连续两期为负: 经营获现能力持续承压。
- 经营活动现金流量净额连续三期为负: 主营业务现金回流能力较弱。
- 净利润为正但经营性净现金流为负: 利润现金含量不足。

Formula:

```text
经营性净现金流收入比 = 经营活动产生的现金流量净额 / 营业收入
净现比 = 经营活动产生的现金流量净额 / 净利润
```

Rules:

- 经营性净现金流收入比 `< 5%`: 经营获现能力偏弱。
- 经营性净现金流收入比 `< 0`: 营业收入未形成有效现金流入。
- 经营性净现金流收入比连续两年低于 `5%`: 主营业务现金回款能力持续偏弱。
- 净现比 `< 1`: 净利润现金保障不足。
- 净现比 `< 0`: 利润与现金流背离。
- 净利润为正但净现比为负: 盈利质量较弱。
- If net profit is negative, do not use net cash/profit as the main judgement; directly mention loss and operating cash flow.
- 投资活动现金流持续大额净流出: 资本开支或项目投入规模较大。
- 连续两年大额投资净流出且经营性现金流不足: 外部融资依赖可能上升。
- 投资性现金流净流出超过营业收入 `50%`: 投资支出规模较大。
- 筹资活动现金流持续大额净流入: 对外部融资依赖较强。
- 筹资活动现金流由正转负: 外部融资支持减弱或偿债支出增加。
- 筹资活动现金流净流出且现金及现金等价物净增加额为负: 资金平衡压力加大。
- 现金及现金等价物净增加额 `< 0`: 现金及现金等价物减少。
- 现金及现金等价物净增加额连续两期为负: 现金储备持续下降。
- 经营、投资、筹资三类现金流合计后现金净减少: 整体现金流平衡承压。

## Debt Structure

Formula:

```text
有息债务 = 短期借款 + 一年内到期的非流动负债 + 长期借款 + 应付债券 + 长期应付款中的有息部分
有息债务资产占比 = 有息债务 / 资产总计
有息债务权益比 = 有息债务 / 所有者权益合计
EBITDA利息保障倍数 = EBITDA / 利息支出
```

Rules:

- 有息债务同比增长超过 `20%`: 债务规模增长较快。
- 有息债务同比增长超过 `50%`: 债务扩张明显。
- 有息债务连续两年增长且现金短债比低于 `0.5`: 债务扩张与现金覆盖不足并存。
- 有息债务资产占比 `> 40%`: 有息债务占资产比重较高。
- 有息债务资产占比 `> 60%`: 资产端对有息债务承压较大。
- 有息债务权益比 `> 1.5`: 有息债务对权益资本依赖较高。
- 有息债务权益比 `> 2.0`: 财务杠杆压力较大。
- 有息债务权益比 `> 3.0`: 权益资本对债务支撑偏弱。
- EBITDA利息保障倍数 `< 2`: EBITDA 对利息支出覆盖偏弱。
- EBITDA利息保障倍数 `< 1`: 经营收益难以覆盖利息支出。
- EBITDA利息保障倍数连续两年下降: 利息偿付保障能力弱化。
- If EBITDA or interest expense is unavailable, do not force calculation.

## Asset Quality

Formula:

```text
应收账款占比 = 应收账款 / 资产总计
其他应收款占比 = 其他应收款 / 资产总计
存货占比 = 存货 / 资产总计
应收类款项合计 = 应收账款 + 其他应收款 + 长期应收款
受限资产占比 = 受限资产 / 资产总计
```

Rules:

- 应收账款占比 `> 10%`: 应收账款占比较高。
- 应收账款占比 `> 20%`: 应收账款对资产形成较大占用。
- 应收账款同比增长超过 `30%` 且营业收入下降: 回款压力可能加大。
- 其他应收款占比 `> 10%`: 其他应收款占比较高。
- 其他应收款占比 `> 20%`: 往来款对资产形成较大占用。
- 其他应收款占比 `> 30%`: 资金占用压力较大。
- 其他应收款连续两年上升且超过 `20%`: 往来款规模持续增加，资产流动性承压。
- For urban-investment entities, if other receivables are mainly due from government departments, related parties, or local SOEs, mention recovery cycle and capital occupation pressure.
- 存货占比 `> 20%`: 存货占比较高。
- 存货占比 `> 30%`: 存货对资产形成较大占用。
- 存货占比 `> 50%`: 资产结构对存货依赖较高。
- 存货连续两年上升且超过 `30%`: 存货规模持续增加，资产流动性承压。
- For urban-investment entities, if inventory mainly consists of land consolidation cost, development cost, or land to be developed, mention long monetization cycle and weak asset liquidity.
- 应收类款项合计占比 `> 20%`: 应收类款项占比较高。
- 应收类款项合计占比 `> 30%`: 应收类款项对资产形成明显占用。
- 应收类款项合计占比 `> 40%`: 资产流动性和回款压力较大。
- 受限资产占比 `> 10%`: 资产受限比例较高。
- 受限资产占比 `> 20%`: 资产抵质押或冻结规模较大。
- 受限资产占比 `> 30%`: 可用于再融资或偿债的资产弹性较弱。
- If a prospectus or rating report discloses restricted assets, prefer its disclosed basis.

## Business Structure

- 单一业务板块收入占比 `> 60%`: 收入结构对单一业务依赖较高。
- 单一业务板块收入占比 `> 80%`: 收入来源高度集中。
- 主要业务收入下降超过 `30%`: 核心业务承压明显。
- 单一主业毛利率 `< 10%`: 该业务盈利能力偏弱。
- 单一主业毛利率同比下降超过 `5` 个百分点: 该业务盈利能力明显弱化。
- 主要业务毛利率为负: 该业务出现亏损。
- For urban-investment entities, government entrusted construction, land consolidation, fiscal subsidies, or government procurement service revenue with high share indicates reliance on local government or regional fiscal support.
- High fiscal subsidy/profit ratio indicates profit reliance on government subsidy.
- Negative net profit after excluding government subsidy indicates weak operating profitability.

## Urban-Investment Entity Focus

These rules apply to urban investment, park development, infrastructure, transportation investment, water, cultural tourism, and state-owned platform entities.

Formula:

```text
政府补助依赖度 = 政府补助 / 利润总额
```

Rules:

- 政府补助依赖度 `> 30%`: 利润对政府补助存在一定依赖。
- 政府补助依赖度 `> 50%`: 利润对政府补助依赖较强。
- 政府补助依赖度 `> 100%`: 扣除政府补助后可能亏损。
- If total profit is negative, do not calculate the subsidy dependency indicator alone; mention loss and subsidy situation.
- Other receivables mainly concentrated in government departments, finance bureaus, management committees, or related SOEs: recovery depends on regional fiscal or related-party arrangements.
- Top five other receivables share over `50%`: concentration is high.
- Aging over `3` years with high share: recovery cycle is long.
- Inventory mainly land consolidation cost, development cost, or land to be developed: asset monetization cycle is long.
- High land asset share in total assets: asset liquidity is weak.
- For urban-investment entities in regions with declining land-transfer revenue, mention land asset monetization pressure.
- If rating reports or prospectuses disclose regional fiscal conditions, focus on declining general public budget revenue, declining government fund revenue, declining land-transfer revenue, high regional debt ratio, and local platform debt pressure.
- External guarantee balance / net assets `> 30%`: external guarantee scale is large.
- External guarantee balance / net assets `> 50%`: contingent liability pressure is large.
- Guaranteed party has enforcement, dishonesty, or debt overdue events: compensation risk rises.
- Large guarantees to private enterprises or weak-credit entities require attention.

## Audit, Announcement, Prospectus, And Rating Signals

List these as negative findings once found:

- Audit opinion is qualified, adverse, or disclaimer.
- Audit report contains emphasis of matter.
- Rating outlook is negative.
- Subject rating or bond rating is downgraded.
- Listed on rating watch.
- Bond extension, replacement, technical default, or substantive default.
- Prospectus discloses major pending litigation.
- Large restricted assets.
- Large external guarantees.
- Large related-party transactions or capital occupation.
- Commercial bill overdue, non-standard debt overdue, or bank loan overdue.
- Controlling shareholder, actual controller, or important subsidiary has major negative events.
- Other negative facts explicitly disclosed in an allowed annual report, semiannual report, prospectus, or rating report.

Do not use public opinion, news, business-registration pages, or third-party pages as negative-signal sources under the current 3-channel policy.

## Deteriorating Trend Rules

Treat these as negative trends only when supported by at least two comparable periods:

1. 营业收入连续两年下降。
2. 净利润连续两年下降。
3. 经营性净现金流连续两期为负。
4. 资产负债率连续两年上升。
5. 现金短债比连续两期下降且低于 `1`。
6. 流动比率连续两期下降且低于 `1`。
7. 其他应收款占比连续两年上升。
8. 存货占比连续两年上升。
9. 有息债务连续两年增长。
10. 财务费用连续两年增长。
11. 受限资产规模连续增加。
12. 对外担保规模连续增加。

Do not make `持续` trend judgements from a single period.

## Basis Limits

1. Do not compare semiannual data directly with full-year data.
2. Do not use quarterly data for formal negative judgements unless the user explicitly asks.
3. Do not use registered capital, paid-in capital, insured employee count, or other business-registration fields for financial judgements.
4. Do not derive financial indicators from news, public-opinion summaries, business-registration pages, or any source outside the 3 allowed channels.
5. Do not directly apply parent, subsidiary, or same-name enterprise data to the target enterprise.
6. Do not output unverifiable judgements such as `资产负债率较高` or `现金短债比较低` when data is missing.
7. Every negative judgement must trace to specific data from an annual report, semiannual report, prospectus, rating report, or other downloaded allowed file from the 3 allowed channels.
