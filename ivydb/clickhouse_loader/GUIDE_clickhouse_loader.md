# IvyDB ClickHouse Loader Guide

## Part 1: Conceptual Explanation

`ivydb/clickhouse_loader/` downloads selected OptionMetrics IvyDB US tables
directly from WRDS PostgreSQL into ClickHouse. It does not read WRDS text files
and it does not stage the dataset as local CSV, TXT, or Parquet files.

The loader is config-driven. Edit `config.toml` to enable one table family at a
time, then run two commands:

1. `create-tables` — create empty ClickHouse tables with curated physical schemas.
2. `load` — stream WRDS rows directly into those tables.

Optional commands:

- `validate` runs row-count and quality checks in ClickHouse.
- `clear-failed` clears only incomplete direct-load destinations recorded as
  started or failed in the local audit log so they can be reloaded.
- `drop-tables` is a dangerous manual reset that drops the ClickHouse tables
  selected in config after two exact confirmations.

| Table family in config | What it loads | ClickHouse layout |
|---|---|---|
| `[tables.static_reference]` | `securd`, `secnmd`, `exchgd`, `distrd`, `opinfd`, `opcrsphist` | One table each |
| `[tables.underlying_prices]` | `secprdYYYY` stock/security prices | All years → one `secprd` table with `source_year` |
| `[tables.option_prices]` | `opprcdYYYY` option prices | One table per year |

The default physical ClickHouse layout follows the table-selection plan in
`ivydb/optionmetrics_ivydb_download_plan.md`:

- `opprcd1996` through `opprcd2025` stay as 30 separate ClickHouse tables.
- `secprd1996` through `secprd2025` consolidate into one ClickHouse table named
  `secprd`, with an added `source_year` column.
- `securd`, `secnmd`, `exchgd`, `distrd`, `opinfd`, and `opcrsphist` load as
  one ClickHouse table each.

Curated DDL modules, not PostgreSQL metadata, own the physical ClickHouse types.
Nullable categorical strings stay null in ClickHouse. Identifier and count
columns are validated and cast at the incoming-chunk boundary. WRDS date strings
for curated `Date32` columns are converted to Python `date` objects before
insertion because the ClickHouse client subtracts a date epoch while encoding
date columns. Date columns use `DoubleDelta` plus `ZSTD(6)`.

The loader downloads an explicit, reviewed column list per source table from
`source_columns.py` instead of `SELECT *`. This keeps the downloaded set a
contract and avoids breaking the insert if WRDS adds an unrelated column. For
`opprcd` the list deliberately omits `forward_price`: OptionMetrics moved
forward price to the `fwdprd` file in manual version 5.0, and the live `opprcd`
column is 0% populated.

`opprcd` codec and width choices are benchmarked, not guessed. On a 2.23M-row
2023 sample the compressed footprint is ~81% implied volatility plus the four
Greeks (high-entropy floats that barely respond to codecs: `ZSTD(12)` saved
~2%, `Gorilla` was ~30% worse). Because codec tuning is a dead end there, the
price/IV/Greek/`cfadj` columns are stored as `Float32`, which cut the whole
table to ~64% of the all-Float64 size (73.5 -> 46.9 MB on-disk for the sample)
while keeping ~7 significant digits. Size figures use
`system.tables.total_bytes`; the per-column `system.columns` view under-reports
for the loader user, which lacks the `system.parts` grant. Integer choices:
`volume` and `open_interest`
are `UInt32` (per-contract daily counts, not `UInt64`), `am_settlement` is
`UInt8` with an explicit 0/1 boundary check, and `optionid` adds a `Delta`
codec because it increases within the sort runs. `secprd` floats use `Float32`
for the same reason.
Dropping the IV/Greeks columns entirely (≈ 19% of current) remains an
available research decision but is not done by default.

Operational resume state is not stored in ClickHouse. The loader writes
started, completed, failed, and cleared source-table events to the local
JSON-lines file `logs/ivydb_load_audit.jsonl`. Set `resume = true` in
`[loader]` to skip source tables whose latest matching audit event is complete.
A newer started or failed event for the same source and target keeps the source
eligible for deliberate cleanup and repair.

Historical IvyDB tables are append-once loads. The loader refuses to insert
into a destination that already has rows for the selected source. If one source
fails, `load` stops and does not attempt later sources from the selected batch.
After inspecting the failure, run `clear-failed` before reloading with the same
config. The cleanup command skips completed and never-started selections,
truncates incomplete annual option targets, and drops only the incomplete
`source_year` partition from `secprd`.

`drop-tables` is intentionally separate from failed-load cleanup. It targets
the same deduplicated ClickHouse table list as `create-tables`, refuses
non-interactive standard input, asks the operator to type the database name,
then asks for the exact comma-separated table list. Only after both answers
match does it submit `DROP TABLE IF EXISTS` commands. The configured
ClickHouse user must have `DROP TABLE` on the selected `ivydb.*` targets.

Database `ivydb` must be created administratively once before using
`ivydb_user`. The loader does not create the database automatically.

For consolidated yearly targets such as `secprd`, validation reports row counts
and date ranges for each configured `source_year`, not just the full combined
table.

## Part 2: Code Reference

`config.toml`

- The normal control surface for table families, year lists, static table lists,
  loader settings (`resume`, log paths), and non-secret ClickHouse defaults.
- ClickHouse connection values can be overridden by process environment
  variables or `ivydb/.env`: `IVYDB_CLICKHOUSE_HOST`,
  `IVYDB_CLICKHOUSE_PORT`, `IVYDB_CLICKHOUSE_USERNAME`,
  `IVYDB_CLICKHOUSE_PASSWORD`, `IVYDB_CLICKHOUSE_SECURE`, and
  `IVYDB_CLICKHOUSE_DATABASE`.

`cli.py`

- Five subcommands: `create-tables`, `drop-tables`, `load`, `validate`,
  `clear-failed`.
- Reads `config.toml` and acts on every enabled table family.
- Optional `--config` path override only.

`create_tables.py`

- Creates empty ClickHouse tables for all enabled families in config.
- Does not connect to WRDS.

`drop_tables.py`

- Plans the dangerous reset target list from the same selected config tables as
  `create-tables`.
- Requires callers to collect two exact confirmations before dropping tables.

`create_option_price_tables.py`, `create_security_price_tables.py`,
`create_reference_tables.py`

- Curated physical-schema contract for each IvyDB target family.

`source_columns.py`

- Explicit WRDS column contract per source family. `opprcd` omits the
  always-null `forward_price`; other tables list their full column set.

`normalization.py`

- Validates and casts WRDS chunks before direct insertion.
- Unsigned-column rules mirror the curated DDL widths (`UInt32` counts,
  `UInt8` `am_settlement`) so out-of-range values fail at the chunk boundary.
- Converts the curated IvyDB `Date32` columns from WRDS strings or date-like
  values into nullable Python `date` objects for `clickhouse-connect`.

`table_plan.py`

- `build_table_plan_from_config(config)` builds the WRDS source → ClickHouse
  target list from enabled families.

`config.py`

- Parses TOML plus ClickHouse environment overrides into typed dataclasses.
- `enabled = false` on a table family yields empty years or static tables.

`../poke_clickhouse_connection.py`

- Standalone preflight script that runs `SELECT 1` and confirms the configured
  ClickHouse database is visible before WRDS loading begins.

`load_to_clickhouse.py`

- Streams WRDS chunks directly into pre-created final tables, writes local audit
  events, and uses the latest matching audit event for resume and cleanup
  decisions.

`validation.py`

- Runs ClickHouse row-count, date-range, key-null, duplicate-key, CRSP-link,
  and per-source-year checks for the configured table plan.

Run examples:

```bash
uv run python -m ivydb.clickhouse_loader create-tables
uv run python -m ivydb.clickhouse_loader drop-tables
uv run python -m ivydb.clickhouse_loader load
uv run python -m ivydb.clickhouse_loader validate
uv run python -m ivydb.clickhouse_loader clear-failed
```

See `ivydb/IVYDB_CLICKHOUSE_RUN_MANUAL.md` for batch-by-batch config examples.

## Part 3: Short Journal

- 2026-05-12: Implemented the first direct WRDS PostgreSQL to ClickHouse IvyDB
  loader under `ivydb/`, with separate non-option and option-price run groups
  and resume skips.
- 2026-05-18: Simplified the user-facing config so `config.toml` selects the
  IvyDB source tables for the next run while batch sizes remain code defaults.
- 2026-05-19: Added compressed direct-to-ClickHouse schema setup modules for
  option prices, security prices, and reference/link tables.
- 2026-05-22: Added unified `create-tables` command and split run groups for
  reference, underlying prices, and option prices.
- 2026-05-22: Removed CLI run-group and year-range flags; config.toml is now
  the sole control surface for normal runs.
- 2026-05-22: Made resume depend on the latest matching audit row and added
  per-source-year validation for consolidated yearly tables.
- 2026-05-25: Switched historical IvyDB ingestion to direct writes into
  curated final tables, preserving nullable categories and adding explicit
  failed-load clearing rather than routine replacement.
- 2026-05-25: Recorded started direct loads and made cleanup batch-aware so
  stopped loads can be inspected, cleared manually, and resumed safely.
- 2026-06-05: Added date-string normalization for curated IvyDB `Date32`
  columns before ClickHouse insertion.
- 2026-06-05: Added manually gated `drop-tables` support for selected
  ClickHouse tables, with two confirmations and no force flag.
- 2026-06-05: Documented the required ClickHouse `DROP TABLE` grant and made
  rejected drop attempts print a clean operator message.
- 2026-06-06: Benchmarked codecs on a real 2.23M-row opprcd sample and applied
  lossless changes: explicit per-table download columns (`source_columns.py`),
  dropped the always-null `opprcd.forward_price`, narrowed `volume`/
  `open_interest` to `UInt32` and `am_settlement` to `UInt8`, and added a
  `Delta` codec to `optionid`. Found IV+Greeks are ~81% of the footprint, so
  precision or column selection (not codec tuning) are the real size levers.
- 2026-06-06: Switched `opprcd` and `secprd` float columns to `Float32`. On-disk
  (`system.tables.total_bytes`) the opprcd sample went 73.5 -> 46.9 MB (~64% of
  all-Float64) with ~7 significant digits retained. Note: `system.columns`
  under-reports for the loader user, so size claims use `total_bytes`. A further
  ~12% is available via fixed-point Decimal on the heavy columns (deferred:
  needs per-column width care for theta).
- 2026-06-07: Tightened `opprcd.am_settlement` normalization so the loader
  rejects values outside the documented 0/1 flag domain before ClickHouse
  insertion.
