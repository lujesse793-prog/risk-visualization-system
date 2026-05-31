# Negative Signals

Only surface negative facts from downloaded and parsed documents on the 3 allowed channels. Do not output positive evaluation, risk grades, credit advice, investment advice, or unsupported judgement.

## Financial Negative Signals

Examples include:

- 营业收入同比下降.
- 净利润同比下降.
- 净利润为负.
- 经营性净现金流为负.
- 资产负债率较高.
- 现金短债比较低.
- 流动比率较低.
- 短期债务占比较高.
- 财务费用较高.
- 应收类款项、其他应收款、存货占比较高.
- 主营业务收入结构高度依赖单一板块.
- 毛利率下滑.
- 投资性现金流持续大额流出.
- 筹资性现金流显示对外部融资依赖较强.

Use annual reports and semiannual reports as the normal basis for these signals. If `quarterly_report_used_for_analysis=false`, do not use quarterly data as the main basis for financial negative judgements.

## Prospectus And Rating Negative Signals

Examples include:

- 评级下调.
- 评级展望调整为负面.
- Rating report mentions repayment pressure, refinancing pressure, regional fiscal pressure, weakening profitability, or weak asset liquidity.
- Prospectus discloses major litigation, external guarantees, restricted assets, or concentrated debt maturity.
- Audit report contains emphasis of matter, qualified opinion, or other modified opinions.

Prospectus and rating report signals are supplements. Do not let them replace available annual-report financial analysis.

## Summary Constraints

Generate `negative_summary_under_200_chars` as one concise Chinese paragraph:

1. Base every sentence on retrieved data from the 3 allowed channels.
2. Keep it under 200 Chinese characters.
3. Mention only negative information.
4. Do not use phrases such as `总体来看`, `建议关注`, `风险等级`, or `投资价值`.
5. Do not include positive facts.
6. Do not make investment or credit advice.
7. Do not use quarterly reports as the main negative-analysis basis unless explicitly requested.
8. Ensure each negative judgement maps to a financial indicator, annual/semiannual report, prospectus, or rating report.

## No Latest Data Summary

If no latest public financial disclosure is found on 中国货币网, 上海证券交易所, or 深圳证券交易所, output only:

```text
未有最新公开财务数据披露，无法基于公开资料生成有效贷后分析。
```

If valid financial data is found but no negative matter is directly supported by the downloaded public disclosure files, output:

```text
未识别到可由公开披露文件直接支持的重大负面事项。
```

Keep `negative_findings` as an empty array in that case. Do not force a negative judgement merely to fill the summary.
