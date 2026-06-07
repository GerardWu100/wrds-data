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
`forward_price` (25 of 26 columns). That column moved to the `fwdprd` file in
manual version 5.0 and is 0% populated in the live `opprcd` tables, so it is
excluded from both the download query and the ClickHouse schema. The implied
volatility and Greek columns are kept by default but are the dominant storage
cost (~81% of the compressed `opprcd` footprint); drop or downcast them only as
a deliberate research decision.

## Excluded By Default

The default config does not load `fwdprdYYYY`, `borrateYYYY`,
`distrprojdYYYY`, `idxdvd`, `zerocd`, `vsurfdYYYY`, `stdopdYYYY`, `hvoldYYYY`,
`stdbrteYYYY`, `opvold`, `optionmnames`, WRDS consolidated `secprd`, or
`indexd`.

Those tables are useful for specific research designs, especially exact
OptionMetrics pricing replication, index-option work, standardized option
panels, or vendor volatility-surface research. Add them deliberately in the
loader table-plan code only when the research question needs them.
