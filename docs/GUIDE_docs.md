# Docs Guide

## Purpose

`docs/` stores source metadata, project planning notes, and reference documents
that explain how to use WRDS datasets in this repository.

## Important Files

- `Wharton Research Data Services.csv`: Source WRDS product metadata used to
  enrich library descriptions.
- `wrds_accessible_datasets_with_doc_urls_and_simple_descriptions.csv`: Source
  WRDS dataset descriptions and data dictionary URLs.
- `boardex_osint_data_plan.md`: Planning note for BoardEx and public-source
  data work.
- `reference/ivydb_opprcd2025_compression_2026-06-11.md`: June 11 ClickHouse
  size, codec, and per-column compression snapshot for `ivydb.opprcd2025`.
- `reference/ivydb_opprcd2025_compression_2026-06-12.md`: June 12 ClickHouse
  size, codec, and per-column compression snapshot for `ivydb.opprcd2025`,
  including the current live codec state and future sort-key note.

## Connections

The catalog export modules read the CSV metadata files in this folder and write
merged outputs under `outputs/`. IvyDB implementation plans live under
`ivydb/`; measured database-reference snapshots live under `docs/reference/`
when they are useful for later comparison.
