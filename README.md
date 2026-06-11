# WRDS Metadata, Samples, And Selected-Bundle BoardEx/CapIQ Parquet Workflows

This project now has four focused jobs:

1. Export canonical WRDS/PostgreSQL metadata catalogs.
2. Keep compact CSV samples in one subfolder per WRDS library for quick inspection.
3. Download a selected BoardEx + Capital IQ bundle to compressed Parquet files
   for local research.
4. Stream the selected OptionMetrics IvyDB US bundle directly from WRDS
   PostgreSQL into ClickHouse.

It also now includes a small public-data companion under `public_13f_samples/`
that downloads one real SEC Form 13F filing and flattens the public holdings
XML so you can compare raw public 13F data with vendor-normalized ownership
tables.

The catalog exporters and WRDS connection helper live in [`catalog_exports/`](/Users/gwh/projects/one-time-projects/wrds-data/catalog_exports). The sample workflow lives in [`library_samples/`](/Users/gwh/projects/one-time-projects/wrds-data/library_samples). The BoardEx/CapIQ Parquet workflow lives in [`boardex_parquet/`](/Users/gwh/projects/one-time-projects/wrds-data/boardex_parquet). The IvyDB ClickHouse loader lives in [`ivydb/clickhouse_loader/`](/Users/gwh/projects/one-time-projects/wrds-data/ivydb/clickhouse_loader).

## How To Use

Run the catalog exporters as Python modules from the project root:

```bash
uv run python -m catalog_exports.export_postgres_tables
uv run python -m catalog_exports.export_postgres_columns
uv run python -m catalog_exports.export_postgres_libraries
uv run python -m catalog_exports.merge_postgres_library_descriptions
```

Export the current sample snapshots:

```bash
uv run python -m library_samples.export_small_samples
uv run library_samples/export_small_samples.py
```

Download the default BoardEx + Capital IQ Parquet bundle:

```bash
uv run python boardex_parquet/cli.py --dry-run
uv run python boardex_parquet/cli.py
uv run python boardex_parquet/cli.py --resume
uv run python -m boardex_parquet
```

Preview and run the direct IvyDB-to-ClickHouse loader:

```bash
cp ivydb/.env.example ivydb/.env
uv run python ivydb/poke_clickhouse_connection.py
uv run python -m ivydb.clickhouse_loader create-tables
uv run python -m ivydb.clickhouse_loader load
uv run python -m ivydb.clickhouse_loader validate
```

If a direct load fails or is interrupted partway through, it stops before
loading later selected sources. After inspecting the error, clear only
incomplete destinations and reload with the same config:

```bash
uv run python -m ivydb.clickhouse_loader clear-failed
uv run python -m ivydb.clickhouse_loader load
uv run python -m ivydb.clickhouse_loader validate
```

Edit `ivydb/.env` for local Docker ClickHouse credentials and
`ivydb/clickhouse_loader/config.toml` before each batch. See
`ivydb/IVYDB_CLICKHOUSE_RUN_MANUAL.md` for the full instruction manual.

The IvyDB loader is selection-driven. Edit
[`ivydb/clickhouse_loader/config.toml`](/Users/gwh/projects/one-time-projects/wrds-data/ivydb/clickhouse_loader/config.toml)
for non-secret ClickHouse defaults and the exact IvyDB tables to load in the next
run. Put secret or machine-specific ClickHouse settings in `ivydb/.env` or
process environment variables. For example, set `years = [2024]` in
`[tables.option_prices]` to load only `opprcd2024`, or add `"opinfd"` to
`[tables.static_reference].tables` to load only the small Option_Info table.
The full available bundle maps 66 WRDS source tables into 37 ClickHouse data
tables, but the config should usually select a small subset.
Operational audit, run, and yearly completion logs stay local in
`logs/ivydb_load_audit.jsonl`, `logs/ivydb_loader.log`, and
`logs/ivydb_year_summary.log`; the loader does not add an audit table to
ClickHouse.
Historical IvyDB tables are append-once loads: `load` writes directly into
pre-created curated ClickHouse tables and records a `started` audit event
before insertion. `clear-failed` clears only sources whose latest audit status
is `started` or `failed`; it leaves completed history and never-started
selections untouched. Database `ivydb` must be created once by an administrator
before using `ivydb_user`.

The BoardEx downloader is config-driven. Edit
[`boardex_parquet/config.toml`](/Users/gwh/projects/one-time-projects/wrds-data/boardex_parquet/config.toml)
to decide which libraries are enabled and whether each enabled library should
download all live tables by default or only a named subset. The shipped default
now uses explicit `enabled_tables` allowlists for the three selected libraries,
so the bundle stays pinned even if WRDS adds more tables later.

The current shipped default writes Parquet only:

- enabled libraries: `boardex_na`, `ciq_pplintel`, `wrdsapps_plink_boardex_ciq`
- selected tables: an explicit 35-table bundle named in config
- sample CSV previews: off by default
- compression: Zstandard
- safety: temporary-file writes plus Parquet validation before `--resume` skips

Download the latest public SEC 13F sample filing:

```bash
uv run python public_13f_samples/download_public_13f_samples.py
```

Catalog outputs:

- `outputs/postgres_tables.csv`
- `outputs/postgres_columns.csv`
- `outputs/postgres_libraries.csv`

Sample outputs:

- `library_samples/<library_name>/`: one subfolder per configured library
- `library_samples/<library_name>/<table_name>.csv`: one CSV per live table in
  that library
- `boardex_parquet/outputs/<library>__<table>.parquet`: one Parquet file per
  configured BoardEx/CapIQ table
- ClickHouse database `ivydb`: default target for IvyDB tables loaded by
  `ivydb/clickhouse_loader`
- `public_13f_samples/outputs/<sample_filer>/`: filing metadata, raw public
  holdings XML, full flattened holdings CSV, and a preview CSV

Each CSV is `select * ... limit <row_limit>`, where `row_limit` comes from
[`library_samples/config.toml`](/Users/gwh/projects/one-time-projects/wrds-data/library_samples/config.toml).
The current config uses `row_limit = 100`, which keeps the samples compact
while preserving all columns.

The shared exporter is [`library_samples/export_small_samples.py`](/Users/gwh/projects/one-time-projects/wrds-data/library_samples/export_small_samples.py). The default library list and row limit live in [`library_samples/config.toml`](/Users/gwh/projects/one-time-projects/wrds-data/library_samples/config.toml). Change that file to pick a different default library set or a different row count. You can still import `export_samples_for_libraries()` from Python and pass any library list you want.

The existing `library_samples/` tree may contain more library folders than the
current default config because prior sample exports are kept until they are
explicitly removed.

The user requested `tr_ownershipfactset_own`, but the first column of
`outputs/postgres_libraries.csv` contains `tr_ownership` and `factset_own` as
separate libraries, so both are sampled separately.

## Duo Authentication Troubleshooting

WRDS APIs require Duo Push Authentication for every login attempt, including programmatic access via PostgreSQL or Python. If you do not receive a Duo push:

1. **Check Phone Settings**: Ensure your phone is unlocked, not in airplane mode, allows push notifications for Duo, and has no active VPN.
2. **Check Duo App**: Open the Duo app directly to see if the notification is waiting there.
3. **Website Fallback**: Log into the WRDS Website first, then try the WRDS platform or code you need.
4. **IP Consistency**: Ensure your IP address remains identical between website authentication and running your code (do not switch networks or toggle VPNs).

## References

- `docs/Wharton Research Data Services.csv`
- `docs/wrds_accessible_datasets_with_doc_urls_and_simple_descriptions.csv`
- WRDS PostgreSQL access via the project-local `.pgpass`
