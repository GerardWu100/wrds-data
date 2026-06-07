# Project Overview

## Summary And Purpose

This project is a WRDS metadata and sampling workspace. It does two related
jobs:

1. Export a clean canonical catalog of the WRDS/PostgreSQL data the account can
   access.
2. Keep compact per-library CSV samples for fast manual exploration before
   doing deeper work.

It now also includes two focused side workflows:

- a BoardEx + Capital IQ Parquet downloader for text-first people-intelligence
  research
- a small public-data SEC Form 13F workflow so the user can inspect raw public
  institutional-holdings data before vendor normalization

The catalog side is useful for answering "what libraries, tables, and columns do
I have?" The sample side is useful for answering "what does one real row from
this library look like?"

## Inputs And Outputs

Inputs:

- A project-local `.pgpass` file with WRDS credentials
- `docs/Wharton Research Data Services.csv`
- `docs/wrds_accessible_datasets_with_doc_urls_and_simple_descriptions.csv`

Outputs:

- `outputs/postgres_libraries.csv`
- `outputs/postgres_tables.csv`
- `outputs/postgres_columns.csv`
- `outputs/postgres_table_role_guide.md`
- One compact CSV per live table inside each sampled library folder under
  `library_samples/`
- One Parquet file per configured BoardEx/CapIQ table under
  `boardex_parquet/outputs/`
- One public SEC 13F sample export under `public_13f_samples/outputs/`

## Architecture And Data Flow

The workflow now branches into two paths after WRDS login setup.

Catalog path:

1. Read the WRDS username from the `.pgpass` file in the project root.
2. Set `PGPASSFILE` to that same local file.
3. Connect to WRDS.
4. Keep only canonical schemas with real tables.
5. Export table metadata and column metadata from PostgreSQL catalogs.
6. Aggregate table metadata into the library catalog.
7. Merge WRDS product descriptions and data-dictionary links into the library
   catalog.

Sample path:

1. Reuse the same shared WRDS login helper.
2. Read the default library list and row limit from
   `library_samples/config.toml`.
4. Query WRDS for the live table list in each target library.
5. Fetch `select * ... limit <row_limit>` from each table.
6. Write one CSV per table into each library's own folder under
   `library_samples/`.

The sample area covers whatever libraries are currently listed in
`library_samples/config.toml`. The current config uses `row_limit = 100`. Each
configured library gets its own subfolder, and each live table inside that
library gets one compact CSV sample.

The existing `library_samples/` tree may contain more library folders than the
current default config because prior exports are kept until removed manually.

BoardEx + CapIQ Parquet path:

1. Reuse the same shared WRDS login helper.
2. Read the library-level selection rules from `boardex_parquet/config.toml`.
3. For each configured table, issue one streaming `SELECT *` query to WRDS.
4. Read the SQL result in chunked `pandas` DataFrames.
5. Append each chunk directly into a Parquet writer.
6. Optionally save the first few rows as a sample CSV beside the Parquet file.

This path exists because the user wants a config-controlled BoardEx and Capital
IQ downloader where enabled libraries can default to "all tables on" while
still allowing named exclusions such as compensation or oversized derived
panels.

Public 13F path:

1. Query the SEC submissions JSON endpoint for a fixed sample filer list.
2. Find the latest `13F-HR` or `13F-HR/A` filing for each sample filer.
3. Read the filing directory index from EDGAR.
4. Download the public holdings XML information table.
5. Flatten each holding row into a CSV with issuer, class, CUSIP, value,
   share/principal amount, investment discretion, and voting authority.
6. Save filing metadata, raw holdings XML, and parsed CSV outputs under
   `public_13f_samples/outputs/`.

## Known Limitations And Assumptions

- Alias or view-only schemas are intentionally excluded from the canonical
  catalog.
- `estimated_rows` comes from PostgreSQL statistics, so it is approximate.
- The sample exporter writes only the libraries listed in
  `library_samples/config.toml`. Within those libraries it exports every live
  table.
- The BoardEx Parquet downloader is config-driven. Enabled libraries can
  default to all live tables while `disabled_tables` excludes unwanted tables.
- Some large BoardEx network tables are relationship-derivable from smaller
  source tables, but exact reproduction can still require BoardEx-specific
  text normalization or curation logic.
- The requested token `tr_ownershipfactset_own` does not exist as a single
  library in `outputs/postgres_libraries.csv`; it resolves in practice to the
  separate libraries `tr_ownership` and `factset_own`.
- Public SEC 13F is not a substitute for vendor ownership products. The SEC
  filings are public and useful, but they reflect only the public 13F reporting
  regime, not all of the broader ownership channels included in vendor datasets.

## User Overrides

- Keep current scripts out of the project root by moving them into a subfolder.
- For future WRDS exploration, keep each sampled library in its own subfolder.
