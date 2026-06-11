# Root Guide

## Part 1: Conceptual Explanation

This repository now has several responsibilities that share the same WRDS login
mechanism.

First, it exports a canonical WRDS/PostgreSQL metadata catalog at three levels:

- library level
- table level
- column level

Second, it keeps a compact "look at the shape of the data" sample area under
`library_samples/`, where each requested WRDS library gets its own subfolder and
each live table in that library gets one CSV snapshot.

Third, it includes focused download workflows for selected datasets. BoardEx
and Capital IQ data are written to local Parquet files. IvyDB US data is
streamed directly from WRDS PostgreSQL into ClickHouse.

The project-local `.pgpass` file is still the backbone of both workflows. The
shared WRDS helper in `catalog_exports/wrds_connection.py` does three things:

1. Finds the project root regardless of which module is running.
2. Reads the WRDS username from the local `.pgpass`.
3. Sets `PGPASSFILE` so libpq uses the project-local password file.

The catalog logic is unchanged in spirit: canonical libraries are schemas that
contain real PostgreSQL tables (`relkind = 'r'`). View-only alias schemas stay
excluded.

The sample logic is intentionally simple. The default library list and row limit
live in `library_samples/config.toml`. Running
`library_samples/export_small_samples.py` opens one WRDS connection, asks the
live WRDS/PostgreSQL database for every table in each configured library,
fetches `limit <row_limit>` rows from each table with `select *`, and writes one
CSV per table into that library's folder. The current config uses
`row_limit = 100`, which keeps the snapshots compact while preserving all
columns.

The existing `library_samples/` tree may contain more library folders than the
current default config because prior sample exports are kept until they are
explicitly removed.

One naming issue mattered here: the requested token
`tr_ownershipfactset_own` does not exist as a library in the first column of
`outputs/postgres_libraries.csv`. The actual libraries present are
`tr_ownership` and `factset_own`, so the sample area contains both as separate
subfolders.

## Part 2: Root Tree And Navigation

```text
wrds-data/
├── .pgpass                -- Project-local WRDS login file used through PGPASSFILE.
├── pyproject.toml         -- Python project metadata and dependencies.
├── poke.py                -- Small standalone WRDS connectivity probe.
├── uv.lock                -- Locked dependency set for `uv`.
├── catalog_exports/       -- Metadata export modules plus the shared WRDS helper.
├── docs/                  -- Source CSV files, planning docs, and dataset-selection references.
├── library_samples/       -- Tiny CSV samples, one subfolder per sampled library.
├── boardex_parquet/       -- Downloads the selected BoardEx/CapIQ bundle from WRDS to Parquet.
├── tests/                 -- Regression tests for local Python workflows.
├── public_13f_samples/    -- Public SEC Form 13F sample downloader and outputs.
└── outputs/               -- Final WRDS metadata CSV outputs.
```

Subfolder overview:

`catalog_exports/`

- What it does: Exports canonical WRDS library, table, and column catalogs and
  merges WRDS product descriptions into the library catalog.
- Key files: `wrds_connection.py`, `export_postgres_tables.py`,
  `export_postgres_columns.py`, `export_postgres_libraries.py`,
  `merge_postgres_library_descriptions.py`.
- Where artifacts go: `outputs/`.
- Cross-reference: See `catalog_exports/GUIDE_catalog_exports.md`.

`docs/`

- What it does: Stores the source CSV files used to enrich the library catalog.
- Key files: `Wharton Research Data Services.csv`,
  `wrds_accessible_datasets_with_doc_urls_and_simple_descriptions.csv`.
- Where artifacts go: None.
- Cross-reference: See `docs/GUIDE_docs.md`.

`ivydb/`

- What it does: Stores the canonical IvyDB US planning notes, research timing
  caveats, and direct WRDS-to-ClickHouse loader.
- Key files: `optionmetrics_ivydb_download_plan.md`,
  `open_interest_timing_note.md`, `clickhouse_loader/config.toml`,
  `clickhouse_loader/cli.py`.
- Where artifacts go: ClickHouse database configured in
  `ivydb/clickhouse_loader/config.toml`.
- Notes: The loader writes directly into curated ClickHouse tables created by
  `create-tables`, preserves nullable categories, validates narrowed integer and
  enum values at ingestion, uses `DoubleDelta` plus `ZSTD(12)` on date columns,
  stores `opprcd` implied volatility, delta, and gamma as six-decimal
  `Decimal32` values while keeping vega and theta as compact `Float32` model
  outputs, writes a separate yearly completion summary log, and exposes
  `clear-failed` for deliberate recovery after a failed or interrupted
  append-once load. Loading remains fail-fast: a failed source stops the
  selected batch; cleanup later removes only sources recorded as started,
  interrupted, or failed. Validation reports cover row counts, date ranges, key
  nulls, duplicate option keys, and CRSP link quality.
- Cross-reference: See `ivydb/GUIDE_ivydb.md`.

`library_samples/`

- What it does: Stores one compact CSV per live table for each sampled WRDS
  library and the exporter that refreshes them.
- Key files: `config.toml`, `export_small_samples.py`, plus one subfolder per
  sampled library.
- Where artifacts go: Inside each library-named subfolder.
- Cross-reference: See `library_samples/GUIDE_library_samples.md`.

`outputs/`

- What it does: Stores the final metadata CSVs plus the manual role guide that
  interprets sampled libraries and table families.
- Key files: `postgres_libraries.csv`, `postgres_tables.csv`,
  `postgres_columns.csv`, `postgres_table_role_guide.md`.
- Where artifacts go: This folder is the artifact destination.
- Cross-reference: See `outputs/GUIDE_outputs.md`.

`boardex_parquet/`

- What it does: Downloads the current config-selected BoardEx + CapIQ
  bundle from WRDS and writes one Parquet file per table
  (zstd-compressed) into `boardex_parquet/outputs/`. The current shipped
  default enables `boardex_na`, `ciq_pplintel`, and
  `wrdsapps_plink_boardex_ciq`, then pins the scope with explicit
  `enabled_tables` allowlists to land on a 35-table bundle.
- How it works: Streams one SQL result per table from WRDS and appends chunks
  directly into temporary Parquet files, using a schema built from live
  PostgreSQL column metadata before atomically promoting the completed file into
  place. This avoids both the old full-table in-memory concatenation pattern
  and the first-batch schema drift problem on sparse wide tables.
- ClickHouse path: `load_parquet_to_clickhouse.py` reads every local pocket
  file in `boardex_parquet/outputs/`, creates one ClickHouse table per Parquet
  stem, supports a separate empty-schema creation step before row insertion,
  preserves BoardEx sentinel dates as strings, and allows nullable Parquet
  columns when they appear in `MergeTree` sort keys.
- Selection model: `config.toml` now controls the download through
  library-level `enabled`, `download_all_tables`, `enabled_tables`, and
  optional `disabled_tables` settings. The default user command can therefore
  just run the package and let config decide the exact pinned table set.
- Expected size: ~27.81 GiB in the local metadata snapshot and about 28.09 GiB
  in the live WRDS check run on April 18, 2026, for the current 35-table
  selected bundle.
- Key files: `config.toml`, `cli.py`, `download_to_parquet.py`,
  `clickhouse_config.toml`, `clickhouse_loader.py`,
  `load_parquet_to_clickhouse.py`, `validate_derivations.py`, `__main__.py`.
- Where artifacts go: `boardex_parquet/outputs/`.
- Cross-reference: See `boardex_parquet/GUIDE_boardex_parquet.md`.

`tests/`

- What it does: Stores local regression tests for Python workflows in this
  repository.
- Key files: `test_boardex_parquet.py`, `test_ivydb_clickhouse_loader.py`,
  and `boardex_parquet/test_clickhouse_loader.py`.
- Coverage today: full-export config expectations, metadata-driven schema
  selection expectations, metadata-driven schema construction, result-driven
  derivation summaries, safe resume behavior for Parquet outputs, and
  ClickHouse loader planning/schema behavior.

`public_13f_samples/`

- What it does: Downloads a real public SEC Form 13F filing and flattens the
  holdings XML into CSV so the user can inspect raw public 13F structure
  outside the vendor-normalized WRDS samples.
- Key files: `download_public_13f_samples.py`.
- Where artifacts go: `public_13f_samples/outputs/`.
- Cross-reference: See `public_13f_samples/GUIDE_public_13f_samples.md`.

## Part 3: Code Reference

`catalog_exports/wrds_connection.py`

- Shared WRDS connection setup for both catalog exports and sample exports.
- Provides project-root resolution, local `.pgpass` parsing, canonical-library
  discovery, and a tiny-table sample query helper.

`poke.py`

- Uses the shared WRDS helper instead of re-implementing login logic.
- Opens a WRDS connection and runs one tiny metadata query.
- Prints the configured username, PostgreSQL user, database name, server date,
  and a short canonical-library preview.
- Exists as a root-level sanity check that is independent of the larger export
  and download workflows.

`catalog_exports/export_postgres_tables.py`

- Connects to WRDS through the shared helper.
- Exports one row per canonical PostgreSQL table to `outputs/postgres_tables.csv`.

`catalog_exports/export_postgres_columns.py`

- Connects to WRDS through the shared helper.
- Exports one row per canonical PostgreSQL column to `outputs/postgres_columns.csv`.

`catalog_exports/export_postgres_libraries.py`

- Reads `outputs/postgres_tables.csv`.
- Aggregates one row per canonical library to `outputs/postgres_libraries.csv`.

`catalog_exports/merge_postgres_library_descriptions.py`

- Reads the two CSVs in `docs/`.
- Merges description fields into `outputs/postgres_libraries.csv`.

`library_samples/export_small_samples.py`

- Uses a fixed list of target libraries.
- Reads the default row limit and target libraries from
  `library_samples/config.toml`.
- Reads the live table list from WRDS for each target library.
- Writes one `select * ... limit <row_limit>` CSV per table under
  `library_samples/`, with the current config set to 100 rows.
- Exposes a shared `export_samples_for_libraries()` function so other code can
  reuse the same logic with a different library list.
- Supports both module execution and direct script execution from the project
  root.
