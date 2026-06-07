# OptionMetrics IvyDB US Download Plan

This note records the working download decision for WRDS OptionMetrics IvyDB US
data. It reconciles three sources:

- WRDS live PostgreSQL metadata queried on 2026-04-26 and rechecked on
  2026-05-12.
- Local catalog exports in `outputs/postgres_libraries.csv`,
  `outputs/postgres_tables.csv`, and `outputs/postgres_columns.csv`.
- IvyDB US File and Data Reference Manual version 5.4, revised 2023-03-29.

`WRDS` means Wharton Research Data Services. `IvyDB US` is the OptionMetrics
United States listed equity and index option database. `SECID` is the
OptionMetrics security identifier. `CRSP` means Center for Research in Security
Prices. `PERMNO` is the CRSP permanent security identifier.

## Verification

The live WRDS metadata query found 280 physical tables in `optionm_all`. The
local catalog also has 280 `optionm_all` tables. No live tables were missing
from the local catalog, and no local tables were absent from live WRDS.

The full `optionm_all` library is about 2.89 TiB in the local catalog snapshot.
Most of that size comes from raw option prices and the derived volatility
surface.

The live WRDS check on 2026-05-12 also confirmed that
`wrdsapps_link_crsp_optionm.opcrsphist` has one physical table and 121,773 rows.
That table contains imperfect link candidates as well as high-quality links:
86,892 rows have missing `permno`, `sdate`, and `edate`, and 28,336 rows have
`score = 1`. Download the full link table because it is small, but filter or
score links explicitly before joining to CRSP data.

## Download Summary

Use this as the default first-pass download set for single-name empirical
equity-option research:

```text
optionm_all.opprcd1996-2025
optionm_all.secprd1996-2025
optionm_all.securd
optionm_all.secnmd
optionm_all.exchgd
optionm_all.distrd
optionm_all.opinfd
wrdsapps_link_crsp_optionm.opcrsphist
```

This set gives the observed option quotes, underlying security prices, core
reference data, and CRSP link table. `CRSP` means Center for Research in
Security Prices. The CRSP link is needed when joining IvyDB `secid`
identifiers to CRSP `permno` identifiers.

This is not a complete bundle for every OptionMetrics use case. Add specialized
tables when the research object is exact OptionMetrics pricing-model
replication, index options, vendor volatility surfaces, standardized options,
or standardized borrow-rate surfaces.

The selection rule is to keep raw or broadly portable data, and skip fields or
tables that are vendor-specific calculations, secondary model inputs, or
rebuildable from more basic data. A portable dataset means a dataset whose core
economic object could plausibly come from another source later, such as option
quotes, underlying prices, distributions, security identifiers, exchange
listings, or CRSP links. It does not mean every value is perfectly identical
across vendors.

Do not include a default second-pass bundle. Add excluded pricing-input tables
only for a specific research question that cannot use rebuilt or external
inputs.

Skip vendor-specific or rebuildable pricing-input tables:

```text
optionm_all.fwdprd1996-2025
optionm_all.borrate1996-2025
optionm_all.distrprojd1996-2023
optionm_all.idxdvd
optionm_all.zerocd
```

Skip large derived, standardized, redundant, or aggregate tables:

```text
optionm_all.vsurfd1996-2025
optionm_all.stdopd1996-2025
optionm_all.hvold1996-2025
optionm_all.stdbrte1996-2025
optionm_all.opvold
optionm_all.optionmnames
optionm_all.secprd
optionm_all.indexd
```

`indexd` can be added later if the project explicitly studies index options.
It is not needed for a first single-name equity-option panel.

### Download Tiers

| Tier | Tables | Decision | Approximate size | Reason |
|---|---|---:|---:|---|
| Core observed option panel | `optionm_all.opprcd1996-2025` | Get first | 1.10 TiB | This is the main contract-day option quote panel. It contains bid, offer, volume, open interest, implied volatility, Greeks, strike, expiration, option identifier, contract size, and settlement fields. |
| Core underlying panel | `optionm_all.secprd1996-2025` | Get first | 10.92 GiB | Underlying prices, returns, adjustment factors, opening prices, volume, and shares outstanding are needed for moneyness, returns, filters, and validation. Use the annual tables instead of the consolidated `secprd` table so downloads can be partitioned and resumed by year. |
| Core reference tables | `securd`, `secnmd`, `exchgd`, `distrd`, `opinfd` | Get first | 199.84 MiB | These small tables identify securities, historical names, exchange status, distributions, and option conventions. They are small relative to option prices and prevent ambiguous joins. |
| CRSP link | `wrdsapps_link_crsp_optionm.opcrsphist` | Get first | 9.62 MiB | This tiny table maps IvyDB `secid` to CRSP `permno` over date ranges. It is essential for joining options to CRSP returns, delisting returns, market equity, and other CRSP fields. |
| Vendor pricing inputs | `fwdprd1996-2025`, `borrate1996-2025`, `distrprojd1996-2023`, `idxdvd`, `zerocd` | Do not get first | 49.91 GiB | These are pricing inputs or projected quantities rather than raw option-market observations. Forward prices can be approximated or rebuilt under a chosen model from spot, rates, dividends, borrow assumptions, and contract conventions; exact OptionMetrics replication may require the vendor input tables. Projected dividends are an IvyDB forecast; zero curves can be sourced from public Treasury or FRED data; index dividend yields are specialized index-option inputs; and borrow rates should come from a securities-lending source only if the research question needs them. |
| Large derived surfaces and standardized panels | `vsurfd1996-2025`, `stdopd1996-2025`, `hvold1996-2025`, `stdbrte1996-2025` | Do not get first | 1.65 TiB | These are derived or standardized products. They are useful when the vendor's smoothed surface, standardized option panel, realized volatility convention, or standardized borrow surface is the research object, but they are too large to download by default. |
| Redundant or rebuildable helpers | `secprd`, `opvold`, `optionmnames`, `indexd` | Do not get first | 25.81 GiB | `secprd` duplicates the annual `secprdYYYY` family, `opvold` can be rebuilt from `opprcdYYYY` by aggregating volume and open interest, `optionmnames` is usually unnecessary because `opprcdYYYY` already carries option symbols and identifiers, and `indexd` is only needed for index-option work. |
| Sample and non-IvyDB option libraries | `optionmsamp_us`, `optionmsamp_europe`, `cboe_sample`, `phlx_all` | Do not get for IvyDB US | 144.27 MiB | These are samples or separate option datasets, not the main IvyDB US panel. Use only for toy tests, European samples, Cboe samples, or currency-option work. |
| Cboe VIX index library | `cboe_all` | Maybe later | 1.52 MiB | This can be useful as a market volatility control, but it is not required for contract-level IvyDB US research. |

### Timing and Lookahead Notes

`opprcdYYYY` contains both raw market fields and OptionMetrics-calculated
fields. The portable raw-data fields are bid, offer, volume, open interest,
strike, expiration, call/put flag, contract identifiers, settlement fields, and
contract size. Implied volatility and Greeks are useful diagnostics, but they
are secondary calculations. Do not make them part of the canonical raw panel
unless the research design explicitly chooses to use OptionMetrics' calculated
values.

Open interest is available in `opprcdYYYY`, but the IvyDB manual states that
`Option_Price.Open Interest` is lagged by one day after November 28, 2000.
Before that date, open interest is not lagged. A trading signal that uses
same-date open interest therefore has a structural break around November 28,
2000. After that date, same-date open interest usually represents information
from the prior trading day, which is less likely to introduce lookahead bias.
Before that date, same-date open interest may represent same-day information
and should be handled more conservatively in signal timing.

The manual also says version 5.0 added the separate `Forward_Price` file and
removed forward price from `Option_Price`. The local WRDS catalog still shows a
`forward_price` column in `opprcdYYYY`, but sample rows can be blank. Under the
portable raw-data rule, skip `fwdprdYYYY` by default and approximate or rebuild
forward prices later under the research design's chosen model. Exact
OptionMetrics forward-price replication may require their zero curve, dividend
projection, borrow-rate, and contract-convention inputs.

## Option-Related WRDS Libraries

| Library | Download decision | Table count | Approximate size | What it contains | Reason |
|---|---:|---:|---:|---|---|
| `optionm_all` | Get selected tables | 280 | 2.89 TiB | Main IvyDB US database: option prices, underlying prices, reference tables, pricing inputs, volatility surfaces, standardized options, and realized volatility. | This is the required database for United States listed equity and index option research. Do not download all 280 tables blindly because the full library is terabyte-scale. |
| `wrdsapps_link_crsp_optionm` | Get | 1 | 9.62 MiB | Link table from OptionMetrics `secid` to CRSP `permno`. | Tiny and important when joining options to CRSP returns, delisting returns, market equity, or other CRSP data. |
| `optionmsamp_us` | Do not get | 12 | 6.74 MiB | Sample or trial version of IvyDB US. | Redundant once using `optionm_all`. Useful only for toy tests when full WRDS access is unavailable. |
| `optionmsamp_europe` | Do not get | 12 | 5.82 MiB | Sample or trial version of IvyDB Europe. | Not needed for United States option data. |
| `cboe_sample` | Do not get | 7 | 24.62 MiB | CBOE end-of-day option sample tables. | Sample dataset, not the main OptionMetrics historical database. |
| `cboe_all` | Maybe later | 1 | 1.52 MiB | Cboe VIX index pricing. | Useful as a market volatility control, but not required for contract-level option data. |
| `phlx_all` | Do not get unless studying currency options | 2 | 107.09 MiB | Philadelphia Stock Exchange currency options and implied volatility. | Separate currency-option dataset, not the IvyDB US equity/index option panel. |

## Complete `optionm_all` Table-Family Decision Table

This table covers all 280 live WRDS tables in `optionm_all`. Year-suffixed
families are written as ranges, for example `opprcd1996-2025`.

| Manual file or concept | WRDS table or family | Exact table coverage | Download decision | Approximate size | Description | Reason |
|---|---|---|---:|---:|---|---|
| Option_Price file | `opprcdYYYY` | `opprcd1996` through `opprcd2025`, 30 tables | Get | 1.10 TiB | Main contract-level option panel. One row is one option contract on one date, with `secid`, date, symbol, expiration, call/put flag, strike, bid, offer, volume, open interest, implied volatility, Greeks, option identifier, adjustment factor, settlement fields, contract size, and expiry type. | This is the core market dataset. Almost every options project needs raw option quotes, implied volatility, Greeks, strikes, expirations, volume, and open interest. Open interest is lagged by one day after November 28, 2000, but not before that date, so trading signals must handle the timing break explicitly. |
| Security_Price file | `secprdYYYY` | `secprd1996` through `secprd2025`, 30 tables | Get | 10.92 GiB | Annual underlying security price and return panels keyed by `secid` and date. Includes low, high, close, volume, total return, adjustment factor, open price, total-return adjustment factor, and shares outstanding. | Needed to attach underlying prices, calculate moneyness, compute returns, validate option prices, and rebuild realized volatility. |
| Security_Price file, consolidated | `secprd` | `secprd`, 1 table | Do not get | 9.54 GiB | Consolidated security price file. It has the same conceptual content as the annual `secprdYYYY` family. | Redundant if annual `secprdYYYY` tables are downloaded. Annual tables are easier to partition, resume, and validate by year. |
| Security file | `securd` | `securd`, 1 table | Get | 18.28 MiB | Security master for all equity and index securities known to IvyDB. Includes `secid`, CUSIP, ticker, SIC, index flag, exchange flags, class, issue type, and industry group. | Small and important. It identifies whether a `secid` is a stock or index and provides stable security attributes. |
| Security file with issuer name | `securd1` | `securd1`, 1 table | Do not get | 12.34 MiB | Security file plus issuer-name information. | Mostly redundant with `securd` plus `secnmd`. Small, but not necessary for a clean first-pass dataset. |
| Security_Name file | `secnmd` | `secnmd`, 1 table | Get | 42.34 MiB | Historical record of ticker, CUSIP, issuer description, issue description, class, and SIC changes for each `secid`. | Small and important because tickers and CUSIPs change through time. Use this for historical names and human-readable labels. |
| Exchange file | `exchgd` | `exchgd`, 1 table | Get | 23.47 MiB | Historical exchange listing and delisting records. Includes status, exchange, add/delete indicator, and exchange flags. | Small and useful for listing-status filters, delisting checks, and exchange interpretation. |
| Distribution file | `distrd` | `distrd`, 1 table | Get | 114.81 MiB | Cash dividends, splits, stock dividends, special dividends, spin-offs, rights offerings, warrants, projected regular dividends, and related flags. | Download it because dividends, splits, and adjustment factors affect returns, strikes, prices, and option valuation. The manual makes this central enough to keep. |
| Option_Info file | `opinfd` | `opinfd`, 1 table | Get | 944 KiB | Option-level convention table by underlying `secid`: dividend convention, exercise style, and settlement flag in the WRDS schema. | Tiny and important. It tells whether options are American or European and how dividends are handled in pricing. |
| Zero_Curve file | `zerocd` | `zerocd`, 1 table | Do not get first | 23.86 MiB | Zero-coupon interest-rate curve by date and maturity in days. Rates are continuously compounded. | Skip under the portable raw-data rule. Risk-free curves are broadly available from public Treasury or FRED sources and do not need to be stored from IvyDB unless exact OptionMetrics pricing replication matters. |
| Forward_Price file | `fwdprdYYYY` | `fwdprd1996` through `fwdprd2025`, 30 tables | Do not get first | 14.21 GiB | Forward price by `secid`, date, expiration, and AM settlement indicator. The manual defines forward price as spot plus interest less projected dividends. | Skip because this is a secondary pricing input. Forward price can be approximated or rebuilt under a stated model from spot price, interest rates, dividends, borrow assumptions, and conventions. Exact OptionMetrics replication may require the vendor input tables. The manual says version 5.0 moved forward prices out of `Option_Price` into this separate file, so do not rely on any `opprcdYYYY.forward_price` column either. |
| Borrow Rate file | `borrateYYYY` | `borrate1996` through `borrate2025`, 30 tables | Do not get first | 14.20 GiB | Borrow rate by `secid`, date, expiration date, and days to expiration. | Skip because it is not a raw exchange option quote and is not a universal web-style dataset. If short-sale constraints become central, use a dedicated securities-lending or borrow-rate source rather than making IvyDB's borrow-rate input part of the default panel. |
| Standard Borrow Rate file | `stdbrteYYYY` | `stdbrte1996` through `stdbrte2025`, 30 tables | Do not get first | 31.66 GiB | Standardized borrow-rate panel by `secid`, date, and standardized days to maturity. | Skip unless the project uses standardized option panels or needs a standardized borrow-rate surface. |
| Distribution_Projection file | `distrprojdYYYY` | `distrprojd1996` through `distrprojd2023`, 28 tables | Do not get first | 21.27 GiB | Daily projected future dividends by `secid`, projection date, ex-date, and projected yield. The manual says projections are made up to five years out using only information known on the projection date. | Skip because this is an IvyDB forecast, not raw realized data. Use realized distributions from `distrd`, and build any forecast model explicitly if needed. |
| Index_Dividend file | `idxdvd` | `idxdvd`, 1 table | Do not get first | 211.53 MiB | Dividend yield used for implied volatility calculations on index options. | Skip for the first universal raw-data panel because this is a specialized pricing input for index options. Add only if the project explicitly studies index options. |
| Index information | `indexd` | `indexd`, 1 table | Do not get first | 10.79 MiB | Index metadata including ticker, CUSIP, exchange, issue type, class, index name, issue, dividend convention, exercise style, and settlement flag. | Skip for single-name equity-option work. Add only if index options are part of the research universe. |
| Std_Option_Price file | `stdopdYYYY` | `stdopd1996` through `stdopd2025`, 30 tables | Do not get first | 100.39 GiB | Standardized at-the-money-forward option prices and implied volatilities at fixed calendar-day maturities: 10, 30, 60, 91, 122, 152, 182, 273, 365, 547, and 730 days. | Derived from the volatility surface by interpolation. Useful, but not needed for raw option research. Download only if standardized OptionMetrics contracts are the target object. |
| Volatility_Surface file | `vsurfdYYYY` | `vsurfd1996` through `vsurfd2025`, 30 tables | Do not get first | 1.48 TiB | Smoothed implied volatility surface by `secid`, date, days to expiration, delta, call/put flag, implied volatility, implied strike, implied premium, and dispersion. | Very large. The manual says it is kernel-smoothed with OptionMetrics methodology. Download only for projects that require the vendor's exact surface. |
| Historical_Volatility file | `hvoldYYYY` | `hvold1996` through `hvold2025`, 30 tables | Do not get first | 37.27 GiB | Realized volatility by `secid`, date, and calendar-day window. The manual lists windows of 10, 14, 30, 60, 91, 122, 152, 182, 273, 365, 547, 730, and 1825 calendar days. | Rebuild from `secprdYYYY` using log close-to-close daily total returns when possible. Download only if exact OptionMetrics values are required. |
| Option_Volume file | `opvold` | `opvold`, 1 table | Do not get first | 6.77 GiB | Daily aggregate option volume and open interest by `secid`, date, and call/put flag, including call, put, and total rows. | Can be rebuilt from `opprcdYYYY` by aggregation if needed. Skip unless aggregate volume is the only required option measure. |
| Option names lookup | `optionmnames` | `optionmnames`, 1 table | Do not get first | 9.49 GiB | Large lookup table with `secid`, option symbol, `optionid`, root, suffix, effective date, CUSIP, ticker, class, issuer, and issue. | Useful for auditing option symbols and contract identifiers. Not necessary for most research because `opprcdYYYY` already carries contract fields. |
| Open_Interest file | No live WRDS `optionm_all` table found | Not present in the 280 live tables | Not applicable | Not applicable | The manual describes a morning open-interest file and states it is not provided as part of the release files. | No corresponding physical `optionm_all` table was found in the live WRDS metadata query. Open interest is already present in `opprcdYYYY`, and aggregate open interest is in `opvold`. |

## CRSP Link Table

| Library | Table | Download decision | Approximate size | Description | Reason |
|---|---|---:|---:|---|---|
| `wrdsapps_link_crsp_optionm` | `opcrsphist` | Get | 9.62 MiB | Date-ranged link from OptionMetrics `secid` to CRSP `permno`, with start date, end date, and match score. | Essential for joining IvyDB to CRSP. Join using `secid` and require the option date to fall between `sdate` and `edate`. |

`opcrsphist` should not be joined blindly. A live check on 2026-05-12 found
many rows with missing `permno`, `sdate`, and `edate`, plus many rows with
scores other than 1. For a clean first pass, keep only rows with non-null
`permno`, non-null date bounds, and option dates between `sdate` and `edate`.
Then decide whether the research design requires only `score = 1` links or can
use lower-quality matches with documented sensitivity checks.

## Derived-Table Notes

`hvoldYYYY` is reproducible in principle, but the exact convention matters. The
manual says historical volatility uses the logarithm of close-to-close daily
total returns over calendar-day windows.

`vsurfdYYYY` is methodology-sensitive. The manual says OptionMetrics computes
the volatility surface using a kernel smoothing method with vega weights,
call-equivalent delta, fixed bandwidth parameters, and a vega cutoff. A local
surface can be built, but exact replication should not be assumed.

`stdopdYYYY` is downstream of `vsurfdYYYY`. The manual says standardized option
prices and implied volatilities are interpolated from the volatility surface.
Therefore, skipping `vsurfdYYYY` also means skipping the source object for exact
OptionMetrics standardized option prices.

## Practical Rule

For first-pass single-name equity-option research, start with observed quotes,
underlying prices, realized distributions, small reference tables, and the CRSP
link. Do not download IvyDB-specific pricing inputs or secondary calculations
by default. For OptionMetrics pricing-model replication only, add forward
prices, borrow rates, dividend projections, zero curves, and index dividend
data.

## Download Validation Checklist

After downloading the first-pass bundle, validate these points before building
research panels:

- Row counts by table and year match WRDS query counts captured at download
  time.
- Minimum and maximum dates by annual table match the expected year coverage.
- Key columns are non-null where required: `secid`, `date`, `optionid`,
  `exdate`, `cp_flag`, `strike_price`, and CRSP-link `permno` after filtering.
- Contract-level rows in `opprcdYYYY` are unique at the intended contract-date
  key, including `secid`, `date`, `optionid`, and the contract descriptors used
  by the research code.
- `opcrsphist` match rates are summarized by year before using CRSP returns,
  market equity, or delisting returns.
- Open interest is lagged or otherwise treated according to the
  November 28, 2000 timing break before it is used in trading signals.
