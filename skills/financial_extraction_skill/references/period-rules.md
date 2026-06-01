# Period Rules

Balance sheet fields are point-in-time values:

- Annual report: `period = "YYYY"`, `period_type = "year_end"`.
- Semiannual report: `period = "YYYYH1"`, `period_type = "half_year_end"`.
- Quarterly report: `period = "YYYYQ1"` or `YYYYQ3`, `period_type = "quarter_end"`.
- `期末余额` maps to the current reporting period.
- `期初余额` maps to the prior year-end for balance sheet values.

Income statement and cash flow statement fields are period values:

- Annual report: `period = "YYYY"`, `period_type = "full_year"`.
- Semiannual report: `period = "YYYYH1"`, `period_type = "ytd"`.
- Quarterly report: `period = "YYYYQ1"` or `YYYYQ3`, `period_type = "ytd"`.
- `本期金额` maps to current reporting period.
- `上期金额` maps to prior comparable period, not prior full year.

When annual report columns show both current year and prior year, keep both, for example `2025` and `2024`.

