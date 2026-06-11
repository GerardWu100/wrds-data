# GUIDE: tests

## Part 1: Conceptual Explanation

This folder holds local regression tests for the Python workflows in this
repository.

The current test coverage is intentionally narrow and high-signal. It does not
try to exercise full WRDS downloads. Instead, it verifies the logic that can be
checked safely and quickly without pulling real data:

- what the shipped `boardex_parquet` config selects by default
- whether the downloader builds a deterministic Arrow schema from PostgreSQL
  metadata instead of trusting the first data batch
- whether `--resume` skips only valid Parquet outputs and overwrites corrupt
  partial files
- whether the BoardEx Parquet-to-ClickHouse loader discovers all local pocket
  files, maps Arrow schema types into ClickHouse column types, keeps sentinel
  dates as strings, emits valid DDL for nullable sort keys, creates empty
  schema-only tables, and later inserts into those empty tables
- whether the IvyDB ClickHouse loader keeps non-option and option-price runs
  separate, consolidates `secprdYYYY`, honors option-price year ranges, builds
  the planned compressed ClickHouse layout, creates curated schema directly in
  ClickHouse, preserves nullable categories, converts WRDS date strings for
  ClickHouse `Date32` inserts, validates semantic integer and enum values,
  refuses duplicate consolidated reloads, streams directly into final tables,
  stops a batch on insert failure, and exposes cleanup recovery for failed or
  interrupted sources without removing completed history

That split matters because the expensive part of the workflow is the actual WRDS
download, but the most important bugs are often in the local control flow and
file-handling logic around it.

## Part 2: Code Reference

`test_boardex_parquet.py`

- Uses `unittest` so the repo does not need an additional test runner.
- Checks the current pinned 35-table defaults in `boardex_parquet/config.toml`.
- Checks schema construction and fixed-type Arrow conversion.
- Checks that derivation spot-check summaries match the measured match counts.
- Uses mocks and temporary directories to verify safe Parquet overwrite and
  resume behavior without touching WRDS.

`boardex_parquet/test_clickhouse_loader.py`

- Uses tiny temporary Parquet files and in-memory Arrow schemas.
- Checks local Parquet discovery, generated ClickHouse column types, generated
  `MergeTree` DDL, nullable sort-key settings, date-string conversion, and
  runtime override behavior.
- Checks that schema-only creation performs no inserts and that a later load can
  insert into an existing empty table.
- Does not connect to ClickHouse.

`test_ivydb_clickhouse_loader.py`

- Uses tiny in-memory metadata examples and fake clients.
- Checks config parsing, table-plan construction, curated ClickHouse schema
  setup, date codecs, WRDS SQL construction, insert batching, chunk
  normalization including date-string conversion, local-audit resume skips,
  yearly summary logging, duplicate target protection,
  fail-fast direct-load behavior, batch-aware `clear-failed` cleanup,
  interrupted-load recovery, CLI subcommands, and validation SQL.
- Does not connect to WRDS or ClickHouse.

Run the current tests with:

```bash
uv run python -m unittest discover -s tests -v
uv run python -m unittest boardex_parquet.test_clickhouse_loader -v
```

## Part 3: Short Journal

- 2026-04-18: Added the first local regression tests for the safer
  `boardex_parquet` workflow, covering config selection, metadata-driven
  schema construction, and safe resume behavior.
- 2026-04-18: Extended coverage so the shipped config must name the exact
  35-table allowlist and derivation summaries cannot overclaim beyond the
  measured match counts.
- 2026-05-12: Added local tests for the IvyDB ClickHouse loader's table layout,
  option-price year batching, insert batching, and resume behavior.
- 2026-05-12: Added regression tests for the IvyDB loader fixes around
  ClickHouse partitioning, sort keys, type mapping, string-null normalization,
  duplicate-load refusal, CLI filters, and validation SQL.
- 2026-05-19: Added a regression test requiring the shipped IvyDB
  `config.toml` to select the full first-pass core bundle by default.
- 2026-05-19: Added IvyDB schema tests for ClickHouse compression codecs and
  direct curated schema setup without SQL export files.
- 2026-05-25: Updated IvyDB loader tests for direct append-once loading,
  nullable-category preservation, semantic validation, date codecs, and
  `clear-failed` recovery.
- 2026-05-25: Added tests that keep failed loads fail-fast while allowing
  explicit cleanup of failed or interrupted selections in a larger batch.
- 2026-06-05: Added IvyDB loader coverage for converting WRDS date strings to
  Python `date` objects before ClickHouse `Date32` inserts.
- 2026-06-11: Added IvyDB loader coverage for `ZSTD(12)` curated schemas and
  the separate yearly completion summary log.
- 2026-05-12: Added BoardEx ClickHouse loader coverage for nullable sort-key
  DDL so local Parquet tables can be created reliably in ClickHouse.
- 2026-05-12: Added BoardEx ClickHouse tests for separate schema creation and
  loading into pre-created empty tables.
