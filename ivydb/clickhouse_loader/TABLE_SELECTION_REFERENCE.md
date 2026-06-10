# IvyDB ClickHouse Table Selection Reference

This loader implements the default table selection from
`ivydb/optionmetrics_ivydb_download_plan.md`.

## Default ClickHouse Tables

| Source group | WRDS source tables | ClickHouse target tables |
|---|---:|---:|
| Option prices | 30 yearly `opprcdYYYY` tables, 1996-2025 | 30 yearly tables, `opprcd1996` through `opprcd2025` |
| Underlying stock/security prices | 30 yearly `secprdYYYY` tables, 1996-2025 | 1 consolidated table, `secprd` |
| Static reference tables | 5 tables | 5 tables |
| CRSP link table | 1 table, `opcrsphist` | 1 table, `opcrsphist` |

Default count: 66 WRDS source tables become 37 ClickHouse data tables. The
loader does not create operational audit tables in ClickHouse. Resume state is
stored locally in `logs/ivydb_load_audit.jsonl`.

## Column Selection

The loader downloads explicit columns (see `source_columns.py`), not `SELECT *`.
Every source table keeps its full WRDS column set except `opprcd`, which drops
three columns (23 of 26):

- `forward_price`: moved to the `fwdprd` file in manual version 5.0 and 0%
  populated in the live `opprcd` tables.
- `root` and `suffix`: the 2010 OptionMetrics OSI revision replaced these legacy
  fields with `symbol` + `symbol_flag`. For 1996-2010 rows they are exactly
  `symbol` split on `.` (100% reconstructable); from 2011 on they are empty. So
  they carry nothing beyond `symbol` and are recoverable via
  `splitByChar('.', symbol)` if a legacy tool needs them.

The implied volatility and Greek columns are kept by default but are the
dominant storage cost (~73% of the compressed `opprcd` footprint). They are
stored as fixed-point decimals with exactly six digits after the decimal point:
implied volatility, delta, gamma, and vega use `Decimal32(6)`. Theta uses
`Float32` because recent rows exceed the narrower `Decimal32(6)` range and
`Decimal64(6)` doubles raw width for a model output. The loader validates each
decimal column's target range before insertion. Drop them only as a deliberate
research decision.

## Excluded By Default

The default config does not load `fwdprdYYYY`, `borrateYYYY`,
`distrprojdYYYY`, `idxdvd`, `zerocd`, `vsurfdYYYY`, `stdopdYYYY`, `hvoldYYYY`,
`stdbrteYYYY`, `opvold`, `optionmnames`, WRDS consolidated `secprd`, or
`indexd`.

Those tables are useful for specific research designs, especially exact
OptionMetrics pricing replication, index-option work, standardized option
panels, or vendor volatility-surface research. Add them deliberately in the
loader table-plan code only when the research question needs them.
