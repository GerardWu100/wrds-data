# Contrib General — Quantitative Financial Data

9 tables of time-series numerical data: international factor returns, stock
beta estimates, firm-level value creation measures, corporate tax rates, and
shale drilling counts. These tables are the raw inputs for asset pricing
regressions, corporate finance studies, and real-economy research.

See [GUIDE_contrib_general.md](GUIDE_contrib_general.md) for the full table
index.

---

## Part 1: Table Descriptions

### Asset Pricing Factor Returns (5 tables)

These tables provide the raw ingredients for factor-model regressions. A
**factor return** is the monthly or daily profit from a long-short portfolio
strategy. For example:
- **HML** (High Minus Low) earns the return of cheap value stocks minus
  expensive growth stocks
- **SMB** (Small Minus Big) earns the return of small-cap stocks minus
  large-cap stocks
- **WML** (Winners Minus Losers, i.e. momentum) earns the return of last
  year's winners minus last year's losers

By regressing a portfolio's returns against these factors you can decompose
performance, estimate risk exposures, and compute alpha (return not explained
by the factors).

All five tables share the same column layout — they differ only in frequency
(monthly vs. daily) and currency convention. All return figures are in
**percent per period** (e.g., 3.93 means +3.93%).

**Shared column glossary:**

| Column | Meaning |
|---|---|
| `year`, `month` | Calendar period (monthly tables only) |
| `country` | Country the factors are constructed for |
| `mkt_rf` | Market excess return: total market return minus the risk-free rate |
| `rf` | Risk-free rate for that period (local short-term interest rate) |
| `smb` | Small Minus Big — return of small-cap portfolio minus large-cap |
| `hml` | High Minus Low — return of value (high book-to-market) minus growth |
| `wml` | Winners Minus Losers — momentum factor (prior 12-month return) |
| `smb5`, `rmw`, `cma` | Fama-French 5-factor extensions: size, profitability (Robust Minus Weak operating profit), investment (Conservative Minus Aggressive capex) |
| `smb4`, `roe` | Alternative 4-factor model: size and return-on-equity factors |

---

**`factors.csv` — Monthly returns, per country**

One row per country-month. Covers major developed markets (USA, Japan, UK,
France, Germany, Canada, Australia, and several others) starting July 1991.

```
year   month  country    mkt_rf   rf      smb      hml     wml
1991   7      Australia   3.93    0.84    1.11     0.65   -5.42
1991   7      Canada      0.77    0.69   -1.14    -3.25    4.66
1991   7      Japan       0.75    0.65   -3.60     2.22    1.36
1991   7      USA         4.33    0.46   -0.05    -1.00    4.03
```

In July 1991 the US market rose 4.33% above the risk-free rate. Small caps
barely underperformed large caps (SMB ≈ 0). Momentum stocks gained +4%. Japan
had a similar market return but much larger small-cap underperformance (SMB =
-3.60).

---

**`factors_daily.csv` — Daily returns, per country**

Same columns as `factors.csv` but at daily frequency, and with wider country
coverage: includes Austria, Belgium, Finland, Germany, Greece, Ireland, Spain,
Sweden, plus an aggregate "Europe" row that combines all European countries
into one series.

---

**`factors_eq.csv`, `factors_eq_usd.csv`, `factors_usd.csv` — Currency variants**

These three monthly tables provide the same factor returns in different
currency conventions, useful when combining multiple countries in one
regression and needing a common scale:

- **`factors_eq.csv`** — returns expressed in an equal-weighted currency
  basket (no single base currency; each country's currency is weighted
  equally). Good for cross-country comparisons that should not depend on
  whether you choose USD or EUR as base.
- **`factors_eq_usd.csv`** — the equal-weighted basket then converted to USD.
- **`factors_usd.csv`** — local-currency returns converted directly to USD
  using spot FX rates.

The `rf` column differs substantially across the three: local short rates
(e.g., Australia ≈ 0.84%/month in 1991) shift to near-zero when expressed in
USD terms (because US rates were much lower). Always check which `rf` matches
your return series before computing excess returns.

---

### Stock-Level Financial Measures

**`better_beta.csv` — Improved market beta estimates**

A stock's **market beta** (β) measures how much its return moves in response
to a 1% market move. A β = 1.5 means the stock tends to rise 1.5% when the
market rises 1%. The standard approach — regressing monthly returns on market
returns over a 60-month window — produces noisy estimates, especially for
stocks with short histories. This dataset provides more sophisticated
alternatives.

| Column | Meaning |
|---|---|
| `permno` | CRSP stock identifier (CRSP's internal integer ID for each stock listing) |
| `yyyymmdd` | Month-end date |
| `bswa32` | Beta from Scholes-Williams weighted-average method over a rolling 32-month window. Corrects for non-synchronous trading (thinly traded stocks react to market moves with a lag). |
| `sd0111` | Beta from a shrinkage/Bayesian smoothing method. Only available after 12 months of data. |

Example for PERMNO 10001 (a small, thinly traded stock):

```
permno  yyyymmdd    bswa32   sd0111
10001   1986-01-31   0.71      —       ← sd0111 not yet available
10001   1986-12-31   0.10    0.035
10001   1987-10-30   0.12    0.039     ← low beta, moves little with the market
10001   1990-08-31  -0.11    0.027     ← briefly negative during 1990 Gulf War sell-off
```

A negative beta is unusual — it means the stock moved *against* the market
during that window (e.g., a defensive or counter-cyclical business).

---

### Firm-Level Aggregate Measures

**`liva.csv` — Long-term Investor Value Added**

LIVA measures how much wealth a company has created or destroyed for its
shareholders *relative to its industry peers*. It adjusts for the sector
environment: a firm that rose 30% in a year when its industry rose 50% is
treated as a value *destroyer* (it lagged peers by 20%). A firm that fell 10%
when its industry fell 30% is treated as a value *creator* (it outperformed
by 20%).

LIVA is expressed in dollar terms (billions USD), so you can compare it across
different-sized firms.

| Column | Meaning |
|---|---|
| `gvkey` | Compustat firm ID |
| `year` | Fiscal year |
| `conm` | Company name |
| `loc` | Country of incorporation |
| `gsubind` | GICS sub-industry code (8-digit; e.g., 20101010 = Aerospace & Defense) |
| `liva` | Long-term investor value added (billions USD) |
| `ler` | Long-term excess return (annualized fraction; e.g., 0.30 = +30% above peers) |
| `mcbeg`, `mcend` | Market cap at the start and end of the fiscal year (billions USD) |
| `nmo` | Number of months in the fiscal year (usually 12; shorter for partial years) |

Example: AAR Corp (aerospace services) over several years:

```
gvkey   year  conm      liva    ler     mcbeg   mcend
001004  1999  AAR CORP  -0.82  -0.55    0.66    0.49   ← destroyed $0.8B vs peers
001004  2003  AAR CORP   0.67   0.74    0.16    0.48   ← created $0.7B vs peers
001004  2014  AAR CORP  16.27   0.70    5.54   38.47   ← strong year, market cap 7x
```

The 2003 row shows LIVA = +$0.67B from a market cap base of only $0.16B —
the firm grew sharply relative to its industry that year.

**`marginal_tax.csv` — Marginal corporate income tax rates**

The statutory tax rate (e.g., 35% in the USA before 2018) is not what a
company actually pays on its *next dollar* of income. Firms with past losses
(tax-loss carryforwards), aggressive depreciation, or large interest deductions
can face a much lower effective marginal rate. This dataset provides annual
marginal tax rate estimates per firm using the Graham (1996) simulation
approach, which simulates the firm's tax liability under small income changes.

| Column | Meaning |
|---|---|
| `gvkey` | Compustat firm ID |
| `year` | Fiscal year |
| `bcg_mtrnoint` | Marginal tax rate *before* accounting for interest deductions (as if the firm had no debt) |
| `bcg_mtrint` | Marginal tax rate *after* the interest tax shield (the firm's actual marginal rate given its debt load) |

Values are fractions (e.g., 0.35 = 35%). Example:

```
gvkey   year  bcg_mtrnoint  bcg_mtrint
001004  1985     0.46          0.42    ← near statutory max (46% pre-Tax Reform Act)
001004  2002     0.30          0.25    ← lower after losses; interest shield adds more
001004  2016     0.34          0.34    ← close to 35% statutory rate
001010  1980     0.46          0.46    ← at the statutory cap, effectively no deductions
```

The gap between `bcg_mtrnoint` and `bcg_mtrint` widens when a firm carries
more debt — interest payments reduce taxable income, lowering the effective
marginal rate.

---

### Real-Economy Data

**`shale.csv` — Shale gas well counts by US county**

Tracks how many new shale oil and gas wells were drilled per US county per
month. Researchers use this as a proxy for a local economic shock — counties
that experienced the shale boom received a sudden inflow of capital,
employment, and tax revenue, making it possible to study how nearby publicly
traded firms responded.

| Column | Meaning |
|---|---|
| `fips_county` | 5-digit FIPS county code (first 2 digits = state, last 3 = county within state) |
| `year_month` | Year-month of the drilling activity |
| `well_count` | Number of new wells drilled that month in that county |
| `county` | Human-readable county name |
| `state` | State name |

Example — Cleburne County, Arkansas (part of the Fayetteville Shale play):

```
fips_county  year_month  well_count  county           state
05023        2006-04-01       1      Cleburne County  Arkansas  ← shale boom begins
05023        2009-01-01      16      Cleburne County  Arkansas  ← peak activity
05023        2012-07-01       3      Cleburne County  Arkansas  ← bust as gas prices fell
```

The county went from 1 well/month at the start of the boom to 16 at the 2009
peak, then dropped sharply as natural gas prices collapsed.

The companion table `_states_.csv` (documented in the governance guide) maps
the 2-digit state prefix of `fips_county` to state names.

---

## Part 2: Folder Tree and File Map

```
contrib_general/
├── GUIDE_contrib_general_quant.md  -- This guide.
│
├── --- Monthly factor returns ---
├── factors.csv                     -- Monthly factors, local currency, per country.
├── factors_eq.csv                  -- Monthly factors, equal-weighted currency basket.
├── factors_eq_usd.csv              -- Monthly factors, equal-weighted basket → USD.
├── factors_usd.csv                 -- Monthly factors, local currency → USD.
│
├── --- Daily factor returns ---
├── factors_daily.csv               -- Daily factors, local currency, wider country coverage.
│
├── --- Stock-level measures ---
├── better_beta.csv                 -- Improved market beta per stock per month (CRSP permno).
│
├── --- Firm-level measures ---
├── liva.csv                        -- Long-term investor value added vs. industry (annual).
├── marginal_tax.csv                -- Marginal corporate income tax rate (annual, per firm).
│
└── --- Real economy ---
    └── shale.csv                   -- New shale wells drilled per US county per month.
```

---

## Part 3: Code Reference

**Generated by:** `uv run python -m library_samples.export_small_samples`

**Key identifiers in this group:**

| Identifier | What it is | Tables |
|---|---|---|
| `gvkey` | Compustat firm ID (6-digit string like `001004`) | liva, marginal_tax |
| `permno` | CRSP stock ID (integer) | better_beta |
| `country` | Country name string | factors, factors_daily, factors_eq, factors_eq_usd, factors_usd |
| `fips_county` | 5-digit FIPS county code | shale |

**Choosing among the factor tables:**

| Goal | Recommended table |
|---|---|
| Country-level factor regression in local currency | `factors.csv` or `factors_daily.csv` |
| Comparing factor premia across countries without FX effects | `factors_eq.csv` |
| Everything in USD for a US investor perspective | `factors_usd.csv` or `factors_eq_usd.csv` |
| Intraday or event-study work needing daily precision | `factors_daily.csv` |
