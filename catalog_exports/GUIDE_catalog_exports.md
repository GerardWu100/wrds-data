# Catalog Exports Guide

## Part 1: Conceptual Explanation

This folder owns the WRDS metadata export workflow. Its job is to turn WRDS
PostgreSQL metadata into three durable CSV catalogs and then enrich the
library-level catalog with WRDS product descriptions.

The flow is:

1. Resolve the project root from the module location.
2. Read the WRDS username from the project-local `.pgpass`.
3. Set `PGPASSFILE` so all WRDS connections use that local password file.
4. Ask WRDS which libraries are visible.
5. Use PostgreSQL system catalogs to keep only schemas that contain real tables.
6. Export table-level metadata.
7. Export column-level metadata.
8. Aggregate table-level metadata into a library summary.
9. Merge WRDS product descriptions and data-dictionary URLs from the CSV files
   in `docs/`.

The key design decision is the shared helper module. `wrds_connection.py`
centralizes root discovery, `.pgpass` parsing, WRDS connection setup, canonical
library discovery, and safe identifier quoting for tiny sample queries. That
prevents the moved scripts from drifting apart after the reorganization.

Inputs:

- `.pgpass` in the project root
- `docs/Wharton Research Data Services.csv`
- `docs/wrds_accessible_datasets_with_doc_urls_and_simple_descriptions.csv`
- PostgreSQL metadata visible through WRDS

Outputs:

- `outputs/postgres_tables.csv`
- `outputs/postgres_columns.csv`
- `outputs/postgres_libraries.csv`

## Part 2: Folder Tree And File Map

```text
catalog_exports/
├── GUIDE_catalog_exports.md          -- This folder guide.
├── __init__.py                       -- Marks the folder as a package.
├── wrds_connection.py                -- Shared WRDS login and metadata helpers.
├── export_postgres_tables.py         -- Exports one row per canonical table.
├── export_postgres_columns.py        -- Exports one row per canonical column.
├── export_postgres_libraries.py      -- Aggregates table metadata to libraries.
└── merge_postgres_library_descriptions.py -- Merges WRDS catalog descriptions.
```

## Part 3: Code Reference

`wrds_connection.py`

- `PROJECT_ROOT`: path anchor for all file I/O.
- `read_wrds_username()`: parses the username from `.pgpass`.
- `connect_wrds()`: sets `PGPASSFILE` and opens the WRDS connection.
- `fetch_canonical_libraries()`: filters visible schemas down to real-table
  schemas.
- `fetch_small_table_sample()`: small helper used by `library_samples/`.

`export_postgres_tables.py`

- `fetch_table_catalog()`: pulls table metadata from PostgreSQL system catalogs.
- `format_bytes()`: human-readable size formatter.
- `main()`: writes `outputs/postgres_tables.csv`.

`export_postgres_columns.py`

- `fetch_column_catalog()`: pulls column metadata from PostgreSQL system
  catalogs.
- `main()`: writes `outputs/postgres_columns.csv`.

`export_postgres_libraries.py`

- Reads the table catalog and aggregates counts, sizes, comments, and sample
  table names.
- `main()`: writes `outputs/postgres_libraries.csv`.

`merge_postgres_library_descriptions.py`

- Loads the two WRDS source CSVs.
- Joins descriptive fields into `outputs/postgres_libraries.csv`.

Common commands:

```bash
uv run python -m catalog_exports.export_postgres_tables
uv run python -m catalog_exports.export_postgres_columns
uv run python -m catalog_exports.export_postgres_libraries
uv run python -m catalog_exports.merge_postgres_library_descriptions
```
