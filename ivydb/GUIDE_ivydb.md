# IvyDB Guide

## Part 1: Conceptual Explanation

`ivydb/` stores the canonical planning notes and the direct ClickHouse loader
for OptionMetrics IvyDB US work. IvyDB US is the OptionMetrics United States
listed equity and index option database.

The main decision is to keep raw or broadly portable data and avoid downloading
IvyDB-specific pricing inputs, derived tables, and rebuildable aggregates by
default. This keeps the future dataset closer to objects that could plausibly
come from another source later: option quotes, underlying prices, realized
distributions, security identifiers, exchange listings, and cross-vendor links.
The default bundle is scoped to first-pass single-name equity-option research;
exact OptionMetrics pricing replication, index-option research, standardized
option panels, and vendor volatility-surface research need extra tables.

The CRSP link table is small enough to download in full, but it contains weak
or incomplete link candidates. Downstream research code should filter for
non-null `permno` and date bounds, apply the date-range join, and decide whether
only `score = 1` links are acceptable.

The folder also records the open-interest timing break from the IvyDB manual.
Open interest is lagged by one day after November 28, 2000, but not before that
date, so signal code should handle this field conservatively.

The executable loader lives in `ivydb/clickhouse_loader/`. It streams selected
WRDS PostgreSQL tables directly into pre-created curated ClickHouse tables.
Edit `config.toml` to enable one table family per batch, then run
`create-tables` and `load`. Option prices can be loaded in slices by changing
the `years` list in config.
The loader supports duplicate-load refusal, post-load validation reports, and
deliberate incomplete-load recovery through `clear-failed`. A failed source
stops the active batch immediately. Before inserting a source, the loader
records `started` locally; after a handled error it records `failed`.
`clear-failed` removes only `started` or `failed` sources, so it can recover a
force-closed load while leaving completed history and unstarted selections
untouched. The audit state lives in `logs/ivydb_load_audit.jsonl` instead of a
ClickHouse audit table.
For full manual resets, the loader exposes a deliberately dangerous
`drop-tables` command that drops the ClickHouse tables selected in
`config.toml`. It is not part of failed-load recovery, refuses non-interactive
execution, and requires two exact confirmations: the target database name and
the exact comma-separated table list.

The loader's resume check is intentionally narrow: it only skips when the
latest matching audit record marks the exact source/target pair complete. A
later failed load attempt therefore prevents an older complete row from hiding
missing data. For consolidated yearly tables, the duplicate guard checks
whether the final ClickHouse table already has rows for the requested source
year before allowing an append.
The user-facing `config.toml` is the manual control surface for deciding which
IvyDB tables enter ClickHouse. ClickHouse Docker connection values can live in
process environment variables or local `ivydb/.env`; the checked-in
`ivydb/.env.example` documents the expected keys. The shipped default starts
with the reference batch enabled and the option-price and underlying-price
batches disabled. For a different run, edit the enabled flags, year lists, or
static table list before launching the loader.
For option-price tables, `contract_size` is intentionally signed because WRDS
uses `-99` as an OptionMetrics missing-value sentinel. Recreate any pre-existing
empty `opprcdYYYY` table after this schema change so ClickHouse uses `Int32`
instead of the older unsigned column.

## Part 2: File Reference

- `optionmetrics_ivydb_download_plan.md`: Canonical table-selection plan for
  which IvyDB and related WRDS tables to download, skip, or add only for a
  specific research design.
- `open_interest_timing_note.md`: Focused note on `opprcdYYYY.open_interest`,
  the November 28, 2000 timing break, and lookahead-bias-safe usage.
- `IVYDB_CLICKHOUSE_RUN_MANUAL.md`: Step-by-step instruction manual for the
  two-step, three-batch workflow (create tables → load data → validate).
- `poke_clickhouse_connection.py`: Standalone Docker ClickHouse preflight check
  that uses the same config/env path as the loader.
- `clickhouse_loader/`: Direct WRDS PostgreSQL to ClickHouse implementation
  for the selected IvyDB bundle. See
  `clickhouse_loader/GUIDE_clickhouse_loader.md`.

## Part 3: Short Journal

- 2026-05-12: Consolidated the duplicate IvyDB download plans into this folder
  so there is one canonical plan.
- 2026-05-12: Clarified that the default IvyDB bundle targets first-pass
  single-name equity-option research and that CRSP links need explicit null,
  date-range, and score handling before joins.
- 2026-05-12: Added the direct ClickHouse loader inside `ivydb/` with separate
  non-option and option-price runs, year-range option-price batches, and
  resume skips.
- 2026-05-12: Simplified the loader implementation by keeping the staging,
  resume, and duplicate checks on one direct path and reusing the shared
  ClickHouse table-existence helper.
- 2026-05-12: Added a run manual for the IvyDB ClickHouse loader so the
  operational steps are separate from code-navigation docs.
- 2026-05-12: Tightened the ClickHouse loader to match the implementation plan:
  planned partitions and sort keys, safer duplicate-load handling, targeted CLI
  controls, and broader validation checks.
- 2026-05-18: Kept loader audit and run logs local rather than storing
  operational state inside the ClickHouse IvyDB database.
- 2026-05-18: Simplified the loader config so it selects IvyDB source tables
  for the next run without exposing low-level batch-size tuning.
- 2026-05-19: Kept manual table selection in `config.toml` so batches can be
  enabled and disabled between runs.
- 2026-05-22: Tightened resume and validation behavior so the latest audit row
  controls resume and consolidated price validation reports each source year.
- 2026-05-25: Switched historical IvyDB ingestion to direct writes into curated
  final tables, preserving nullable categories and adding explicit failed-load
  clearing rather than routine replacement.
- 2026-05-25: Kept direct loads fail-fast while recording started attempts so
  manual cleanup can recover failed or interrupted sources within one batch.
- 2026-06-05: Added a manually gated `drop-tables` reset command for selected
  IvyDB ClickHouse tables, documented as dangerous and separate from
  `clear-failed` recovery.
- 2026-06-06: Benchmarked ClickHouse codecs on a real opprcd sample; switched
  the loader to explicit download columns, dropped the always-null
  `opprcd.forward_price`, and right-sized integer widths. Recorded that
  implied volatility and Greeks dominate option-table storage, so fixed-point
  precision or dropping those columns are the meaningful compression levers.
- 2026-06-09: Dropped legacy `opprcd` `root`/`suffix` columns as redundant with
  `symbol`/`symbol_flag` (lossless for 1996-2010, empty from 2011). Code/schema
  change only; previously loaded ClickHouse tables were left untouched and would
  need a reload to drop the columns.
- 2026-06-10: Changed `opprcd` implied volatility and Greeks from `Float32` to
  `Decimal32(6)`, with normalization converting WRDS values to six-decimal
  fixed-point decimals and rejecting values outside the `Decimal32(6)` range.
- 2026-06-10: Changed `opprcd.vega` back to `Float32` after `opprcd2025`
  exceeded the `Decimal32(6)` range during load. Implied volatility, delta, and
  gamma remain `Decimal32(6)`, while vega and theta are compact `Float32`
  model-output columns.
- 2026-06-11: Changed future `opprcd.vega` and `opprcd.theta` DDL and
  normalization from `Float32` to `Decimal64(6)` with `T64, ZSTD(12)` after a
  full-2025 shadow-table benchmark showed smaller compressed size than
  `Float32, ZSTD(12)`.
- 2026-06-11: Switched new IvyDB ClickHouse tables to `ZSTD(12)` codecs and
  added `logs/ivydb_year_summary.log` for one-line completion summaries after
  each yearly source table finishes.
- 2026-06-11: Changed new `opprcd.symbol` columns to plain nullable strings
  after 2025 sample benchmarks showed better compression than
  `LowCardinality`; `expiry_indicator` remains low-cardinality.
- 2026-06-12: Changed future `opprcd.open_interest` DDL back to plain
  `ZSTD(12)` after the full 2025 reload showed `T64, ZSTD(12)` was slightly
  larger than the old codec.
- 2026-06-12: Changed future `opprcd` sort keys to cluster rows by security,
  quote date, expiration, call/put side, strike, and then option identifier for
  better compression-oriented option-surface locality.
