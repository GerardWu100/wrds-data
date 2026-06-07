# GUIDE: boardex_parquet

## Part 1: Conceptual Explanation

This folder downloads a **selected BoardEx + Capital IQ WRDS bundle** and
writes one Zstandard-compressed Parquet file per table into
`boardex_parquet/outputs/`.

It can also load those local Parquet pocket files into ClickHouse. That path
does **not** re-query WRDS. It treats the audited local files as the source of
truth and creates one ClickHouse table per file.

The important point is that the shipped default is **not** “download every live
table.” It is a narrower 35-table selection that keeps the user-facing
research tables and skips the biggest or least relevant families.

The current default keeps:

- BoardEx person identity, employment, education, achievements, and outside
  activities
- BoardEx board announcements, committee history, governance summaries, and
  selected board/company association tables
- BoardEx-to-CIQ linking tables
- Capital IQ person, biography, role, role-function, and wide professional
  panel tables

The current default skips:

- BoardEx compensation tables
- Capital IQ compensation tables
- the giant BoardEx person-level association panels
- the giant BoardEx pairwise person-network table
- two broader BoardEx convenience joins that overlap more normalized tables
- the optional CRSP and ExecuComp bridge libraries

Using the local catalog snapshot in
[`outputs/postgres_tables.csv`](/Users/gwh/projects/one-time-projects/wrds-data/outputs/postgres_tables.csv),
the current default targets:

- 26 tables from `boardex_na`
- 7 tables from `ciq_pplintel`
- 2 tables from `wrdsapps_plink_boardex_ciq`
- 35 tables total
- about 27.81 GiB of WRDS PostgreSQL relation size in the local snapshot

A live WRDS check from this workspace on **April 18, 2026** put the same
selection at about **28.09 GiB**. That source size estimate can drift over
time as WRDS refreshes data.

### Why the downloader works this way

The current implementation is trying to solve two separate problems at once:

1. keep the selected table list disciplined
2. make the actual write path safe on large tables

For each selected table, the downloader:

1. reads the selection rules from `config.toml`
2. asks WRDS for the live table list in each enabled library
3. streams one plain `SELECT *` result in chunked `pandas` DataFrames
4. builds the Parquet schema from live PostgreSQL column metadata before the
   first batch is written
5. normalizes WRDS date values that arrive as strings, including far-future
   BoardEx sentinel dates such as `9000-01-01`, into real Arrow date columns
6. writes the table to a temporary Parquet path in the output directory
7. atomically promotes the finished file into place after success
8. in `--resume` mode, skips only files that are readable complete Parquet
   files

That combination matters because older versions had two real risks:

- a truncated Parquet file could be mistaken for a finished output in
  `--resume`
- a sparse early batch could lock the Parquet schema into the wrong inferred
  types
- WRDS date columns could arrive as strings that PyArrow could not cast
  directly into the declared Arrow date type

The current implementation keeps the narrower selected bundle while fixing the
write-path bugs above and preserving BoardEx sentinel dates.

### Loading the pocket files into ClickHouse

For the local BoardEx pocket files, ClickHouse is the recommended target over
PostgreSQL. ClickHouse is a columnar analytical database, which means it stores
data by column and is optimized for scans, filters, aggregations, and large
read-heavy joins. That fits a 35-file BoardEx bundle with about 110 million
local rows. PostgreSQL is still a good database, but it is a better fit for
transactional updates, strict relational constraints, and smaller normalized
workflows.

The loader in this folder:

1. discovers `*.parquet` files under `boardex_parquet/outputs/`
2. maps each file stem to a ClickHouse table name
3. builds the ClickHouse schema from the Parquet footer
4. can create the target database and empty tables as a separate inspection step
5. streams Arrow batches from Parquet into ClickHouse
6. validates loaded row counts against Parquet footer row counts

The schema-only step is useful when you want to inspect the empty database
before inserting about 110 million local rows. `create-schema` creates empty
tables from the Parquet footers. A later `load` run accepts those empty tables
and inserts the Parquet data. The loader still refuses non-empty existing tables
with mismatched row counts unless replace mode is enabled.

BoardEx date columns need one special rule. BoardEx uses far-future sentinel
dates such as `9000-01-01`; a sentinel date is a placeholder value, often used
for unknown or open-ended date ranges. ClickHouse native date types cannot
represent that range safely, so the loader stores Parquet `date32` columns as
nullable `String` values in `YYYY-MM-DD` format. Analysts can cast valid dates
inside queries with ClickHouse parsing functions when needed.

The generated ClickHouse tables use compact `MergeTree` sort keys when common
identifier or date columns are present. Because the source Parquet schema marks
many of those columns nullable, the generated DDL adds
`SETTINGS allow_nullable_key = 1` only when a nullable column appears in the
sort key. Without that table setting, ClickHouse can reject otherwise valid
BoardEx table creation statements.

### Key configuration parameters

`batch_size`

- Meaning: number of rows requested per chunk from one streaming SQL query
- Current default: `100000`
- Increase: fewer round trips, higher peak memory
- Decrease: safer on very wide text tables and weaker machines

`output_dir`

- Meaning: directory where Parquet files are written
- Current default: `outputs`

`sample_csv_rows`

- Meaning: how many rows to keep as a sidecar CSV preview beside each Parquet
  file
- Current default: `0`
- Set to a positive integer only if you explicitly want preview CSVs

### Table-selection model

The code does not hard-code the selected list in Python. Instead, it uses
library-level rules from `config.toml`.

Each enabled library block uses:

- `download_all_tables = false`
- an `enabled_tables` list for the exact tables you **do** want

So the current default is:

- keep the three selected libraries enabled
- list the exact 35 tables in config
- download only those named tables

That model keeps the narrower bundle pinned even if WRDS adds more live tables
later.

## Part 2: Code Reference

`config.toml`

- Declares the enabled libraries and loader settings.
- Keeps the 35-table default through explicit `enabled_tables` lists.
- Disables sample CSV previews by default.

`cli.py`

- Parses `--config`, `--library`, `--table`, `--dry-run`, and `--resume`.
- Delegates the actual work to `download_to_parquet.run()`.

`__main__.py`

- Lets you run the package directly with `uv run python -m boardex_parquet`.
- Calls `boardex_parquet.cli.main()`.

`download_to_parquet.py`

- Loads `config.toml`.
- Resolves the output directory.
- Fetches the live table list for each enabled library.
- Builds an Arrow schema from live PostgreSQL column metadata before writing.
- Converts WRDS date strings to Python date objects before Arrow conversion, so
  date columns stay typed as dates even when pandas reads them as strings.
- Streams each selected table in chunked DataFrames.
- Writes to a temporary Parquet file and atomically promotes it on success.
- Validates existing Parquet files before `--resume` skips them.

`validate_derivations.py`

- Runs live WRDS spot checks for several large BoardEx derived tables.
- Helps document which large derived tables were or were not convincingly
  recoverable from smaller source tables.

`clickhouse_config.toml`

- Holds the ClickHouse connection settings and Parquet load options.
- Defaults to database `myclickhouse`, local host `localhost`, and
  `boardex_parquet/outputs/` as the Parquet source directory.

`clickhouse_loader.py`

- Discovers local Parquet files.
- Converts Arrow schemas into ClickHouse table schemas.
- Creates empty ClickHouse tables without inserting rows when requested.
- Stores BoardEx date columns as strings to preserve far-future sentinel dates.
- Adds ClickHouse's nullable-key table setting when generated sort keys use
  nullable Parquet fields.
- Loads Arrow batches with `clickhouse-connect`.
- Validates ClickHouse row counts against local Parquet row counts.

`load_parquet_to_clickhouse.py`

- Command-line interface for `dry-run`, `create-schema`, `load`, and
  `validate`.
- Supports `--table` to process one pocket file and `--replace` to rebuild
  existing target tables.

`CLICKHOUSE_LOAD_INSTRUCTIONS.md`

- User-facing runbook for configuring ClickHouse, dry-running, loading,
  replacing, and validating the local pocket files.

`TABLE_SELECTION_REFERENCE.md`

- The detailed “what I download and what I do not” reference for the current
  bundle.
- Cross-checks the current config against the local metadata export and local
  sample files.

### Common commands

Dry run:

```bash
uv run python boardex_parquet/cli.py --dry-run
```

Full default download:

```bash
uv run python boardex_parquet/cli.py
```

Equivalent module form:

```bash
uv run python -m boardex_parquet
```

Resume an interrupted run:

```bash
uv run python boardex_parquet/cli.py --resume
```

One library only:

```bash
uv run python boardex_parquet/cli.py --library ciq_pplintel
```

One table only:

```bash
uv run python boardex_parquet/cli.py --library boardex_na --table na_dir_profile_emp
```

Dry-run ClickHouse load DDL:

```bash
uv run python boardex_parquet/load_parquet_to_clickhouse.py dry-run
```

Create empty ClickHouse tables:

```bash
uv run python boardex_parquet/load_parquet_to_clickhouse.py create-schema
```

Load local Parquet pocket files into ClickHouse:

```bash
uv run python boardex_parquet/load_parquet_to_clickhouse.py load
```

Validate ClickHouse row counts against Parquet:

```bash
uv run python boardex_parquet/load_parquet_to_clickhouse.py validate
```

## Part 3: Short Journal

- 2026-05-12: Added a local Parquet-to-ClickHouse loader for the BoardEx pocket
  files and kept BoardEx date columns as strings in ClickHouse so far-future
  sentinel dates are preserved.
- 2026-05-12: Fixed generated BoardEx ClickHouse DDL so nullable Parquet
  columns can be used as `MergeTree` sort keys without table creation failing.
- 2026-05-12: Split BoardEx ClickHouse schema creation from row insertion so
  empty tables can be inspected before loading the Parquet data.
- 2026-04-26: Fixed live WRDS Parquet conversion for BoardEx date columns that
  arrive as strings, including far-future sentinel dates beyond pandas'
  nanosecond timestamp range.
- 2026-04-19: Simplified the internal write/filter flow in
  `download_to_parquet.py` for easier tracing without changing external CLI
  behavior. The writer lifecycle now uses a context manager, sample-row capture
  uses a decrementing counter, and filter logic is expanded into explicit
  steps with added inline comments and clearer type hints.
- 2026-04-18: Pinned the shipped default to an explicit 35-table allowlist so
  WRDS catalog growth cannot silently widen the download scope.
- 2026-04-18: Restored the narrower 35-table default after a mistaken shift to
  full-library export, while keeping the safer temporary-file write path,
  Parquet validation in `--resume`, and metadata-driven schema construction.
