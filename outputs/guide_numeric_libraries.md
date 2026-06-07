# WRDS Numeric Data Libraries Guide

These libraries are dominated by time-series numeric data: prices, spreads,
returns, volatility, estimates, and similar quantitative panels. Every row is
fundamentally a number attached to an identifier and a date. These are the
libraries to prioritize for backtesting and factor research.

Ownership data (`factset_own`, `tr_ownership`) has been moved to
`guide_text_libraries.md` — holdings are about who owns what, not about
price series.

See `guide_text_libraries.md` for people, governance, news, and text-heavy
libraries.

---

## Quick Triage

| Library | Approx size | What it is | Start here |
| --- | ---: | --- | --- |
| `optionm_all` | 2,894 GB | US equity option prices + vol surfaces | `opprcdYYYY`, `stdopdYYYY`, `vsurfdYYYY`, `secprdYYYY` |
| `comp_global_daily` | 128 GB | Compustat Global prices + fundamentals | `g_secd`, `g_funda`, `g_fundq`; sub-families `g_co_*`, `g_sec_*` |
| `contrib_global_factor` | 76 GB | 400+ pre-built factors, monthly + daily | `global_factor`, `ctff_daily_ret`, `ctff_chars` |
| `markit_cds` | 341 GB | Daily CDS spreads by issuer | `cdsYYYY` |
| `trace_enhanced` | 132 GB | FINRA bond trades (clean) | `trace_enhanced` |
| `trace_standard` | 105 GB | FINRA bond trades (raw) | `trace`, `trade_summary` |
| `wrdsapps_bondret` | 93 GB | Ready-to-use monthly bond returns | `bondret`, `bondret_std` |
| `fisd_fisd` | 71 GB | Bond issue terms + trade history | `fisd_mergedissue`, `fisd_tsales` |
| `msrb_all` | 79 GB | Municipal bond trades | `msrb` |
| `ciq_ratings` | 16 GB | S&P credit ratings history | `wrds_srating`, `wrds_erating`, `ratings_ids` |
| `tr_ibes` | 711 GB | Analyst EPS estimates + consensus + targets + recs | `det_epsus`, `statsum_epsus`, `ptgdet`, `recddet` |

---

## Library Notes

### `optionm_all`

**What is this?** The IvyDB US option market database. Each row in the main
tables is one option contract on one day: its strike, expiry, bid/ask, implied
volatility, and Greeks. A parallel table gives the underlying stock's price and
return on that same day. A third family gives the full implied-volatility surface
as a grid of (days-to-expiry, delta) cells. Coverage starts 1996.

This is the go-to library for anything involving option prices, implied
volatility, realized volatility, the volatility surface, or option-based risk
measures.

**Main tables:**

**`opprcdYYYY`** (~1.1 TB total across 30 annual tables)

One row = one option contract × one trading day.

Key columns:
- `secid` — OptionMetrics security ID for the underlying stock
- `date` — trading date
- `cp_flag` — `C` = call, `P` = put
- `strike_price` — strike price stored on a 1/1000 dollar scale
- `exdate` — expiration date
- `best_bid`, `best_offer` — bid/ask quotes
- `volume`, `open_interest` — trading activity
- `impl_volatility` — Black-Scholes implied volatility (annualized)
- `delta`, `gamma`, `vega`, `theta` — option Greeks
- `forward_price` — forward price of the underlying used in pricing
- `cfadj` — cumulative adjustment factor for splits/dividends

Example (from `opprcd2024`):

| secid | date | cp_flag | strike_price | best_bid | best_offer | impl_volatility | delta |
|---|---|---|---|---|---|---|---|
| 5139 | 2024-01-02 | C | 10000 | 9.70 | 13.60 | 2.6968 | 0.9441 |
| 5139 | 2024-01-02 | C | 12500 | 7.30 | 11.10 | 2.0882 | 0.9205 |

---

**`vsurfdYYYY`** (~1.48 TB total across 30 annual tables)

One row = one (underlying, date, days-to-expiry, delta, option-side) cell on
the standardized volatility surface grid.

Key columns:
- `secid` — underlying security ID
- `date` — date
- `days` — time to expiry in calendar days (10, 30, 60, 91, 122, 152, 182, 273, 365, 547, 730)
- `delta` — option delta (–90 to –10 for puts, 10 to 90 for calls, in integer steps)
- `cp_flag` — `C` or `P`
- `impl_volatility` — interpolated implied vol at this (days, delta) node
- `impl_strike`, `impl_premium` — implied strike and option premium at this node

Example: a row with `days=30, delta=-50` gives the at-the-money 1-month put
implied vol for that security on that date.

---

**`secprdYYYY`** (~10.9 GB total across 30 annual tables)

One row = one underlying stock × one trading day.

Key columns:
- `secid` — OptionMetrics security ID
- `date` — date
- `close` — closing price
- `volume` — shares traded
- `return` — daily total return (including dividends)
- `cfadj` — cumulative adjustment factor
- `shrout` — shares outstanding (thousands)

Use this to attach the underlying stock's daily price and return to option data.

---

**Other main families:**
- `stdopdYYYY` (~100 GB total across 30 annual tables) — standardized option
  price panels. Same security × date × contract structure as `opprcdYYYY` but
  normalized to a consistent pricing convention. Use when you need a clean,
  normalized version of the option pricing history rather than raw bid/ask
  quotes.
- `hvoldYYYY` (~37 GB total) — realized (historical) volatility at various
  lookback windows, keyed by `secid` and `date`
- `borrateYYYY` (~14 GB total) — stock borrow rate by security and expiration
  horizon (useful for put-call parity and short-selling studies)
- `fwdprdYYYY` (~14 GB total) — forward prices at various tenors
- `distrprojdYYYY` (~21 GB total across 28 annual tables) — projected dividend
  distributions used in option valuation and risk decomposition

**Helper tables:** `secnmd`, `optionmnames` (security name/identifier tables),
`exchgd` (exchange codes), `indexd` (index reference data), `idxdvd`
(index-dividend data), `distrd` (distribution reference data), `zerocd`
(zero-curve / risk-free rate reference data used in option pricing)

---

### `comp_global_daily`

**What is this?** Compustat Global: daily and monthly stock prices plus annual
and quarterly company fundamentals for publicly listed companies worldwide. This
covers thousands of companies across most major markets, with gvkey as the
company identifier and iid as the security/issue identifier.

There is no single "main" table — price research and fundamental research use
different starting points.

**Main tables:**

**`g_secd`** (74 GB) — Global security daily panel

One row = one security (gvkey + iid) × one trading day.

Key columns:
- `gvkey` — Compustat company identifier
- `iid` — issue identifier (links to a specific listing/share class)
- `datadate` — trading date
- `prccd` — closing price in local currency
- `prchd`, `prcld` — daily high and low price
- `cshoc` — shares outstanding (thousands)
- `cshtrd` — shares traded
- `curcdd` — price currency code (e.g., `USD`, `EUR`, `GBP`)
- `ajexdi` — adjustment factor for splits and dividends
- `trfd` — total return factor (includes dividends)
- `isin` — ISIN identifier

Example: one row is ASM International NV (Dutch semiconductor company) trading
on Euronext on a given day, with its closing price in EUR and adjustment factors.

---

**`g_funda`** (1.02 GB) — Global annual fundamentals

One row = one company (gvkey) × one fiscal year. Contains 400+ accounting line
items (balance sheet, income statement, cash flow). Key items include:
- `gvkey` — company
- `fyear` — fiscal year
- `datadate` — fiscal year-end date
- `sale` — net revenue
- `at` — total assets
- `ceq` — common equity
- `ni` — net income
- `capx` — capital expenditure
- `curcd` — reporting currency

---

**`g_fundq`** (2.95 GB) — Global quarterly fundamentals

Same structure as `g_funda` but at the quarter level. Key identifier:
`datacqtr` (calendar quarter like `1998Q2`).

---

**`g_sec_dprc`** (34 GB) — Narrower daily price table

Covers price, volume, dividends, and adjustment factors without the full
merged-descriptor payload of `g_secd`. Use when you only need price data.

**`g_secm`** (2.17 GB) — Monthly security panel (same structure as `g_secd`)

---

**Sub-family tables (use when you need a specific data group rather than the
merged files):**

**`g_co_*` family** (~7 GB across 22 tables) — Company-level annual and interim
data grouped by topic: `g_co_afnd1`, `g_co_afnd2` (annual fundamentals split
into two groups), `g_co_ifndq`, `g_co_ifndsa`, `g_co_ifndytd` (quarterly and
interim fundamentals), `g_co_adesind`, `g_co_idesind` (descriptor/industry
fields), `g_co_hgic` (GICS classification), `g_co_gsuppl` (supplemental
data), `g_co_aaudit`/`g_co_iaudit` (audit fields), etc. Use when the merged
`g_funda`/`g_fundq` files include too many columns and you only need one
specific Compustat data group.

**`g_sec_*` family** (~39 GB across 17 tables) — Security-level data beyond
the main price tables: `g_sec_afnd`/`g_sec_ifnd` (per-security fundamentals
and interim fundamentals), `g_sec_afnt`/`g_sec_ifnt` (footnote variants),
`g_sec_divid` (dividend history), `g_sec_adjfact` (adjustment factor history),
`g_sec_split` (split history), `g_sec_dtrt` (total return detail),
`g_sec_history` (security status history), etc.

**`g_idx_daily`** (298 MB) — Daily global index history

One row = one index × one trading day. Use for index-level return and
constituent work. Key columns include index code, date, open, close, volume,
and return fields. Companion tables: `g_idx_index` (index master),
`g_idx_mth` (monthly index panel), `g_idxcst_his`/`g_indexcst_his`
(constituent history).

**`g_company`** — Company master (one row per gvkey)

Contains company name, SIC, GICS, incorporation country, and fiscal year
conventions. The `g_names` and `g_namesq` tables carry security-level name
and identifier history. Use when you need to match a `gvkey` to a company
name or country without loading `g_secd`.

**Helper tables:** `dd_group`, `dd_group_xref`, `dd_item`, `dd_package`
(data-dictionary), `xfl_table`, `xfl_column` (metadata cross-reference),
`r_*` tables (reference/code lookups — country, exchange, GIC, SIC,
currency, accounting standard, and dozens of other decode tables),
`g_currency` (currency master), `g_exrt_dly`/`g_exrt_mth` (daily and
monthly exchange rates), `g_chars` (miscellaneous characteristic helpers)

---

### `contrib_global_factor`

**What is this?** A pre-built academic factor library covering global equity
markets. The centerpiece is a single 400+ column panel table combining security
identifiers, market structure flags, and hundreds of cross-sectional
characteristics. You can use this as a ready-made feature matrix for factor
research without building your own pipeline.

**Main tables:**

**`global_factor`** (67 GB)

One row = one stock × one month-end date, globally.

Key columns (selected from 400+):
- `permno`, `gvkey`, `iid` — security identifiers (CRSP + Compustat)
- `id` — library's own integer security ID
- `date` — month-end date
- `excntry` — country code (e.g., `USA`, `GBR`, `JPN`)
- `me` — market equity (USD millions)
- `ret_exc` — excess return for the month (return minus risk-free rate)
- `ret_12_1` — 12-1 month momentum
- `be_me` — book-to-market ratio
- `at_me` — total assets to market equity (size-adjusted leverage)
- `gp_at` — gross profitability (gross profit / assets)
- `beta_252d` — 252-day market beta
- `ivol_capm_252d` — idiosyncratic volatility (CAPM residual)
- `qmj` — quality-minus-junk composite score

The remaining columns are hundreds of additional accounting ratios, growth
rates, momentum windows, risk measures, liquidity measures, and composite
scores — all pre-computed and ready to use.

Example row: US nano-cap stock in April 2020 with its full characteristic
vector attached. A single join on (id, date) gives you all factors.

---

**`ctff_daily_ret`** (4.26 GB)

One row = one stock × one trading day.

Key columns:
- `id` — library integer security ID
- `date` — date
- `ret_exc` — daily excess return

Use this when you need daily return data from the same universe, without loading
the full monthly panel.

---

**`ctff_chars`** (4.78 GB) — Monthly characteristics panel

Same universe as `global_factor` but a narrower subset of columns. Useful
when you only need cross-sectional characteristics (e.g., price, market
equity, enterprise value, book-to-market) without loading the full 400+
column panel. Keyed by `id` and `date`. Join to `ctff_daily_ret` on `id`
for a daily return series.

**`ctff_features`** — one-column dictionary listing all feature names in the
library. Download this first to know which columns exist in `global_factor`
before pulling the full wide panel.

---

### `markit_cds`

**What is this?** Daily CDS (credit default swap) spread quotes for corporate
and sovereign names, provided by Markit. Each row is one entity × one tenor ×
one contract configuration × one day. Coverage starts 2001. This is the
standard source for CDS spread time series in credit research.

**Main tables:**

**`cdsYYYY`** (~341 GB total across 26 annual tables)

One row = one reference entity × one tenor × one day.

Key columns:
- `date` — trading date
- `ticker` — company ticker used by Markit (e.g., `A` for Agilent)
- `redcode` — Markit RED code (the primary CDS entity identifier, 6 chars)
- `shortname` — company short name
- `sector` — broad sector (e.g., `Healthcare`, `Technology`)
- `region` — geographic region (e.g., `N.Amer`, `Europe`)
- `country` — country name
- `tier` — contract tier (e.g., `SNRFOR` = senior foreign, `SUBLTD` = subordinated)
- `currency` — CDS currency denomination
- `docclause` — restructuring clause (e.g., `MR14` = modified restructuring)
- `tenor` — maturity tenor (e.g., `5Y`, `10Y`, `1Y`)
- `parspread` — par CDS spread in decimal (multiply by 10000 for basis points)
- `convspreard` — conventional spread
- `upfront` — upfront payment for standardized CDS contracts
- `avrating`, `impliedrating` — average and implied credit ratings
- `runningcoupon` — running coupon (0.01 = 100bp, 0.05 = 500bp)
- `primarycurve` — whether this is the primary curve for the entity

Example: Agilent Technologies senior USD 5Y CDS on 2024-01-01 with par spread
~79.6bp (0.00796 × 10000) and implied rating BBB.

---

**Helper tables:**
- `cdslookup` — maps `redcode` and `ticker` to company short names; use to
  look up entity labels without loading the full yearly tables

---

### `trace_enhanced`

**What is this?** The FINRA TRACE bond transaction reporting system —
enhanced (BTDS) version. Every time a bond dealer executes an OTC trade, they
report it to TRACE. The enhanced feed has been through WRDS/academic cleaning
and includes richer fields than the standard feed. This is the main source for
US corporate bond microstructure and liquidity research.

**Main tables:**

**`trace_enhanced`** (98.6 GB)

One row = one reported bond trade.

Key columns:
- `cusip_id` — 9-digit CUSIP of the bond
- `bond_sym_id` — TRACE bond symbol (e.g., `CHRC4086085`)
- `company_symbol` — issuer ticker
- `trd_exctn_dt`, `trd_exctn_tm` — execution date and time
- `trd_rpt_dt`, `trd_rpt_tm` — report date and time (can differ from execution)
- `msg_seq_nb` — message sequence number (unique trade ID within date)
- `trc_st` — trade status: `T` = trade, `C` = cancel, `W` = withdrawal
- `entrd_vol_qt` — par amount traded (face value in dollars)
- `rptd_pr` — reported price (percent of par, e.g., 100.0 = par)
- `yld_pt` — reported yield (if provided)
- `rpt_side_cd` — reporting side: `B` = buy, `S` = sell, `D` = dealer-to-dealer
- `buy_cpcty_cd`, `sell_cpcty_cd` — capacity codes: `A` = agent, `P` = principal
- `asof_cd` — as-of indicator (blank = same-day, `A` = as-of)
- `sub_prdct` — TRACE sub-product code
- `bloomberg_identifier` — Bloomberg bond ticker for joins

Example row: a sell-side dealer reports selling \$9,500 face of `CHRC4086085`
at 100.0 (par) on 2010-01-29.

---

**Other trade tables:** `trace_btds144a_enhanced` (144A private placements),
`trace_agency_enhanced` (agency bonds), `trace_spds_mbs_enhanced` (MBS),
`trace_spds_tba_enhanced` (TBA), `trace_spds_cmo_enhanced` (CMO)

**Helper tables:** `absmasterfile`, `camasterfile`, `cmomasterfile`,
`mbsmasterfile`, `tbamasterfile` — security reference tables with issue
characteristics for each product type

---

### `trace_standard`

**What is this?** The standard (non-enhanced) version of the FINRA TRACE
corporate bond trade feed. Less clean than the enhanced version — includes all
TRACE message types including cancels and corrections — but covers a longer
history and is the original raw feed. The daily trade summary tables derived
from this are useful when you only need aggregate daily statistics.

**Main tables:**

**`trace`** (69.95 GB) — Raw TRACE core tape

One row = one TRACE message (trade, cancel, or correction).

Key columns similar to `trace_enhanced` but with fewer derived/cleaned fields.
- `cusip_id`, `bond_sym_id`, `company_symbol`, `bsym` — bond identifiers
- `trd_exctn_dt`, `trd_exctn_tm` — execution date/time
- `ascii_rptd_vol_tx` — trade size (text field, face value)
- `rptd_pr` — price (percent of par)
- `side` — `B`/`S`/`D`
- `chng_cd` — change code: `N` = new, `C` = cancel, `W` = withdrawal

**`trade_summary`** (7.72 GB) — Daily bond summary rows

One row = one bond × one trading day. The sampled columns are price/yield
summary fields (`high_pr`, `low_pr`, `close_pr`, corresponding yields) plus
issuer/action metadata. Often the right starting point when you don't need
message-level detail.

---

### `wrdsapps_bondret`

**What is this?** WRDS-built monthly bond return panel. Combines TRACE trade
data with FISD bond reference data to produce a clean, ready-to-use return
series. If you want to do bond-level return analysis without building your own
cleaning pipeline, start here.

**Main tables:**

**`bondret`** (1.85 GB)

One row = one bond × one month-end.

Key columns:
- `date` — month-end date
- `issue_id`, `cusip`, `bond_sym_id`, `isin` — bond identifiers
- `company_symbol` — issuer ticker
- `bond_type` — e.g., `CDEB` (corporate debenture)
- `security_level` — `SEN` / `SUB` / etc.
- `coupon` — annual coupon rate
- `maturity` — maturity date
- `rating_num`, `rating_cat`, `rating_class` — numeric and categorical ratings
- `amount_outstanding` — face amount outstanding (thousands)
- `price_eom` — end-of-month clean price (percent of par)
- `ret_eom` — monthly total return (including accrued coupon)
- `yield` — end-of-month yield to maturity
- `t_spread` — yield spread to treasury
- `duration` — modified duration
- `tmt` — time to maturity (years)

Example: AAR Corp 7.25% bond maturing 2003-10-15, observed at month-end July
2002: price 102.79, yield 4.94%, return +0.87%.

---

**`bondret_std`** (84 MB) — Standard-TRACE-based return panel

Smaller counterpart to `bondret`, built from the standard (non-enhanced)
TRACE feed rather than the enhanced feed. Use when you want a narrower,
straight-through construction that avoids the additional cleaning steps in the
enhanced pipeline. Same column structure as `bondret`.

**Staging tables:** `trace_enhanced_clean` (55.7 GB) and
`trace_standard_clean` (35.4 GB) are the cleaned TRACE sources used to build
`bondret` and `bondret_std` respectively. Touch these only if you need to
inspect the construction pipeline.

---

### `fisd_fisd`

**What is this?** The Mergent Fixed Income Securities Database. Two main uses:
(1) look up detailed terms for a bond issue (coupon, maturity, covenants,
call schedule, rating history), and (2) access historical bond transaction
data going back further than TRACE.

**Main tables:**

**`fisd_mergedissue`** (288 MB)

One row = one bond issue (`issue_id` / `complete_cusip`).

Key columns:
- `issue_id` — Mergent issue identifier
- `issuer_id` — issuer identifier (join to `fisd_issuer`)
- `issuer_cusip` — issuer-level 6-character CUSIP stem
- `issue_cusip` — issue-level suffix
- `complete_cusip` — full 9-character CUSIP
- `issue_name` — bond name/series
- `maturity` — maturity date
- `coupon` — annual coupon rate
- `coupon_type` — `F` = fixed, `V` = variable, `Z` = zero
- `bond_type` — e.g., `CDEB`, `USBN`
- `security_level` — `SEN`, `SUB`, etc.
- `convertible`, `putable`, `redeemable` — flags
- `offering_amt` — original offering amount (thousands)
- `offering_date`, `offering_price`, `offering_yield`
- `rule_144a` — 144A private placement flag
- `isin`
- `interest_frequency` — 1=annual, 2=semiannual, etc.
- `day_count_basis` — e.g., `30/360`
- `amount_outstanding` — current amount outstanding (thousands)
- `defaulted` — Y/N default flag

Example: AAR Corp 9.5% senior notes due 2001-11-01, offered at par in 1989,
\$65M face, 30/360 semiannual coupons, not convertible.

---

**`fisd_tsales`** (68 GB)

Historical bond trade data with TRACE-like execution fields. One row = one
trade when the trade columns are populated.

Key columns in the sample schema: `issue_id`, `bond_sym_id`, `company_symbol`,
`ascii_rptd_vol_tx`, `rptd_pr`, `yld_pt`, `trd_exctn_dt`, `trd_exctn_tm`,
`trc_st`

**`fisd_ratings`** (331 MB) — Current rating by issue and rating agency

One row = one issue × one rating type at a point in time.

Key columns:
- `issue_id` — bond identifier
- `rating_type` — agency code (e.g., `DPR` = Duff & Phelps, `FR` = Fitch)
- `rating_date` — date rating was assigned
- `rating` — rating symbol (e.g., `BBB-`, `NR`)
- `investment_grade` — flag

**Helper tables:** `fisd_code` (code decode), `fisd_agent`, `fisd_issuer`,
per-covenant/call/put schedule tables

---

### `msrb_all`

**What is this?** The Municipal Securities Rulemaking Board trade transaction
database. Every OTC trade in a US municipal bond is reported here. Coverage
from the early 2000s. This is the primary source for muni bond liquidity,
pricing, and market microstructure research.

**Main tables:**

**`msrb`** (79 GB, 215M+ rows)

One row = one reported municipal bond trade.

Key columns:
- `rtrs_control_number` — unique trade ID
- `cusip` — 9-digit CUSIP of the muni bond
- `security_description` — bond description (e.g., `ABAG FIN AUTH FOR NONPROFIT COMB FING 3`)
- `trade_type_indicator` — `P` = purchase (dealer bought from customer),
  `S` = sale (dealer sold to customer), `D` = interdealer
- `trade_date` — trade date
- `time_of_trade` — time of trade (HH:MM:SS)
- `settlement_date` — settlement date
- `par_traded` — face amount traded (dollars)
- `dollar_price` — price (percent of par)
- `yield` — yield to maturity
- `coupon` — bond coupon rate
- `maturity_date` — bond maturity date
- `dated_date` — bond dated date
- `brokers_broker_indicator` — whether trade was via inter-dealer broker
- `cusip6` — issuer CUSIP prefix (first 6 digits)

Example: \$5,000 face of ABAG Finance Authority bond (5.6% coupon, maturing
2023-11-01) purchased at par (100.0) on 2005-01-12.

---

**Helper tables:**
- `msrb_lookup` — maps `cusip6` (issuer prefix) to a text description, with
  date range. Use to label issuers without loading the full trade table.
- `msrb_qvards` — query-support only, not for research

---

### `ciq_ratings`

**What is this?** S&P credit ratings history (via Capital IQ). Three rating
levels — security (instrument), instrument, and entity (issuer) — each in a
WRDS-flattened view and the underlying raw S&P normalized tables. Use the
`wrds_*` tables unless you need the raw S&P schema.

**Main tables:**

**`wrds_srating`** (2.9 GB) — Security-level ratings panel

One row = one rating event for one security (CUSIP/ISIN level).

Key columns:
- `ratingdetailid` — unique rating record ID
- `security_id`, `instrument_id` — identifiers
- `cusip`, `isin` — standard identifiers
- `ratingtypecode` — e.g., `STDLONG` (standard long-term), `FCLONG` (foreign
  currency long-term)
- `currentratingsymbol` — current rating (e.g., `BBB+`, `B+`, `NR`)
- `ratingsymbol` — rating assigned at this event
- `priorratingsymbol` — previous rating
- `outlook` — rating outlook (e.g., `Stable`, `Negative`)
- `creditwatch` — CreditWatch status (e.g., `Watch Pos`, `Watch Neg`)
- `ratingactionword` — action description (e.g., `New Rating`, `Upgrade`)
- `ratingdate` — date of rating action
- `iscurrent` — Y if this is the current active rating

Example: Security 1, STDLONG rating, upgraded from B+ to NR (not rated) on
1990-07-26 with prior rating date 1987-09-28.

---

**`ratings_ids`** (4.79 GB) — Identifier spine

One row = one entity-role combination.

Key columns:
- `entity_id` — S&P entity identifier
- `cusip6`, `cusip9` — CUSIP identifiers
- `instrument_id`, `security_id` — S&P sub-entity IDs
- `roletypecode` — role (e.g., `OBLIGOR` = debt issuer, `UNDERWRITR`)
- `gvkey` — Compustat company key (when available)
- `sic`, `naics` — industry classifications
- `sectorcode` — broad sector (e.g., `FI` = Financial Institutions)
- `countrycode`, `region`

Use this to join ratings to Compustat (`gvkey`) or other databases via CUSIP.

---

**`wrds_sassessment`** (33 MB) — Security-level S\&P assessments panel

Same structure as `wrds_srating` but for S\&P assessments (a distinct product
covering recovery ratings and structured-finance assessments). Key columns:
`assessmentdetailid`, `instrument_id`, `security_id`, `assessmenttypecode`,
`currentassessmentsymbol`, `outlook`, `assessmentactionword`, `assessmentdate`,
`iscurrent`, `longtermflag`, `globalornationalscaleind`, `cusip`, `isin`.

**`wrds_eassessment`** (736 KB) — Entity-level assessments (issuer/obligor
parallel to `wrds_erating`).

**Descriptor helpers:**
- `wrds_sec_info` — security-level descriptor: maturity, coupon, amounts
  outstanding, currency, CUSIP, ISIN, and placement type. Join to `wrds_srating`
  on `security_id` to attach bond terms.
- `wrds_inst_info` — instrument-level descriptor: debt type, program type,
  instrument type, sector/subsector, taxable flag, and original/current face
  amounts. Join on `instrument_id`.
- `wrds_entity_info` — entity-level descriptor: entity name, CIQ company ID,
  SIC, NAICS, sector, region, country, and analyst. Join on `entity_id` from
  `ratings_ids`.

**`wrds_erating`** (105 MB) — Entity-level ratings (issuer/obligor)
**`wrds_irating`** (21 MB) — Instrument-level ratings

**Helper tables:** `spratingdata`, `spratingtype`, `spassessmentdata`,
`spassessmenttype` (raw S\&P schemas and decoder tables),
`spratingidentifier`, `spinstrumenttoentity` (identifier and entity-link
helpers), `spentitysector`/`spentitysectorcode`/`spinstrumentsectorcode`
(sector classification tables), plus many specialized narrow decode tables
(`spratingroletype`, `spratingcollateraltype`, `spratingcoupontype`,
`spratingcountry`, `spratingregion`, `spratingdebttype`, etc.)

---

### `tr_ibes`

**What is this?** Thomson Reuters I/B/E/S: the standard database of sell-side
analyst earnings estimates. Contains individual analyst forecasts, consensus
statistics, price targets, and analyst buy/sell/hold recommendations. The US
and international variants are distinct; EPS is the most common measure but
the library covers many other metrics.

**Main tables:**

**`det_epsus`** and related `det_*` family (~299 GB total)

One row = one analyst's estimate for one company, at one forecast horizon, at
one point in time.

Key columns:
- `ticker` — I/B/E/S ticker (6-char, e.g., `TLMR`)
- `cusip` — 8-digit CUSIP
- `cname` — company name
- `oftic` — official ticker
- `estimator` — firm code for the brokerage house
- `analys` — analyst code
- `fpi` — forecast period indicator (6 = next quarter, 1 = next year, etc.)
- `pdf` — periodicity: `A` = annual, `Q` = quarterly
- `measure` — `EPS`, `ROE`, `BPS`, etc.
- `value` — the analyst's estimate
- `curr` — currency
- `fpedats` — fiscal period end date (the period being estimated)
- `actdats` — activation date (when this estimate became active)
- `revdats`, `revtims` — revision date/time
- `anndats`, `anntims` — announcement date/time
- `actual` — realized value (if filled in after the fact)

Example: Analyst 71182 at broker 1267 forecast Q1 2014 EPS for Talmer
Bancorp at \$0.20, activated 2014-03-10. Actual was \$0.12 (reported 2014-05-06).

---

**`statsum_epsus`** and related `statsum_*` family (~180 GB total)

One row = one company × one consensus snapshot date × one forecast period.

Key columns:
- `ticker`, `cusip`, `cname` — identifiers
- `statpers` — statistics period (snapshot date)
- `fpedats` — fiscal period end date
- `fpi` — forecast period indicator
- `numest` — number of estimates in consensus
- `numup`, `numdown` — upgrades and downgrades since last period
- `medest` — median estimate
- `meanest` — mean estimate
- `stdev` — standard deviation across analysts
- `highest`, `lowest` — range of estimates
- `actual` — realized value

Example: Talmer Bancorp consensus on 2014-04-17 for Q1 2014 EPS: 4 analysts,
median \$0.07, mean \$0.08, std \$0.01. Actual was \$0.12.

---

**`recddet`** — Individual analyst recommendations

One row = one analyst's recommendation for one company, at one point in time.

Key columns:
- `ticker`, `cusip`, `cname` — identifiers
- `estimid` — broker/firm identifier
- `analyst` — analyst code
- `ereccd` — encoded recommendation (1=Strong Buy, 2=Buy, 3=Hold, 4=Sell, 5=Strong Sell)
- `etext` — text label for `ereccd` (e.g., `OUTPERFORM`)
- `ireccd` — standardized 1–5 code
- `itext` — standardized label (e.g., `BUY`)
- `revdats` — revision date
- `anndats` — announcement date (when estimate became public)

Example: RBC analyst Arfstrom rated Talmer Bancorp `OUTPERFORM` (code 2=BUY)
starting 2014-03-10.

---

**`ptgdet` / `ptgdetu`** and **`ptgsum` / `ptgsumu`** families (~8.8 GB across
8 tables including normalized variants)

Price-target detail and summary panels.

`ptgdet` — One row = one analyst's price target for one company, at one point
in time. Key columns: `ticker`, `cusip`, `oftic`, `cname`, `actdats`
(activation date), `estimid` (broker), `alysnam` (analyst name), `horizon`
(forecast horizon in months, e.g., 12), `value` (target price), `estcur`,
`curr`, `amaskcd` (anonymous analyst code), `anndats`, `anntims`.

`ptgsum` — One row = one company × one consensus snapshot date. Key columns:
`ticker`, `cusip`, `statpers` (snapshot date), `numest`, `numup4w`,
`numdown4w`, `meanptg`, `medptg`, `stdev`, `ptghigh`, `ptglow`, `curr`.

Paired `nptg*` tables are the normalized (I/B/E/S standardized) variants;
`ptg*u` tables include unadjusted estimates.

Example from `ptgdet`: RBC analyst Arfstrom set a 12-month price target of
\$16.00 for Talmer Bancorp on 2014-03-10.
Example from `ptgsum`: consensus on 2014-03-20 across 4 analysts was a mean
target of \$16.00, std \$0.00.

---

**`surpsum` / `surpsumu`** and **`nsurpsum` / `nsurpsumu`** (~5.8 GB across
4 tables) — Earnings surprise history

One row = one company × one announcement period. Captures the gap between
consensus and the reported actual. Key columns: `ticker`, `cusip`, `cname`,
`pdf` (periodicity), `fpi` (forecast period), `anndats` (announcement date),
`actual`, `meanest`, `medest`, `surprise`, `suescore` (standardized unexpected
earnings). Use for event-study research around earnings announcements.

---

**`newact` / `newactu`** and **`newnact` / `newnactu`** families (~53.3 GB
across 4 tables) — Newer actuals history

A separately maintained actuals history that sits alongside the older `act_*`
family. Contains realized EPS and other measures per fiscal period with
announcement dates and times. Use when the `act_*` tables have gaps or you
need the most current actuals history.

---

**`recdid`** — recommendation identifier spine (maps analyst codes to broker
names); **`recdidsum`** — consensus recommendation counts per company;
**`recdstp`** — stopped recommendations; **`recdsum`** — aggregated
recommendation summary statistics.

Note: `n*` prefixed tables (e.g., `nptgdet`, `nstatsum_epsus`) are the
I/B/E/S normalized variants with currency adjustment and consistency
standardization. Use them for multi-currency or long-horizon cross-country work.

---

**Helper tables:** `id`, `idsum` (I/B/E/S ticker–CUSIP–PERMNO bridge),
`curr`, `currnew`, `ncurr` (currency codes and conversion), `adj`, `adjsum`
(split adjustment factors for estimates), `trbc` (classification helper),
`eurx`, `hsxrat`, `hdxrati` (FX/conversion helpers)

---
