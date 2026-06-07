# Outputs Guide

## Part 1: Conceptual Explanation

This folder keeps the final three metadata catalogs requested by the user plus
one interpretation guide that explains how to read the sampled libraries at a
practical level. The library catalog is enriched after export by merging WRDS
product descriptions, simple descriptions, and data-dictionary URLs from the
two CSV files in `docs/`.

- `postgres_libraries.csv`: one row per canonical WRDS library, with a
  `Description`, `Simple dataset description`, and `Data dictionary URL`
  merged from the WRDS product catalogs when a library code matches
- `postgres_tables.csv`: one row per canonical WRDS table
- `postgres_columns.csv`: one row per canonical WRDS column
- `postgres_table_role_guide.md`: the original synthesized classification guide
  (still valid as a reference). Superseded for data-description purposes by the
  two split guides below.
- `guide_numeric_libraries.md`: enriched guide for numeric/quantitative
  libraries (prices, spreads, returns, estimates, holdings). Each library section
  includes plain-English data descriptions, key column definitions, and inline
  row examples drawn from the `library_samples/` CSVs. Use this to decide which
  numeric dataset to download next.
- `guide_text_libraries.md`: enriched guide for text/people libraries
  (governance, compensation, news/sentiment, identifier spines). Same format.
  Use this to decide which people or event dataset to download next.

Canonical means table-backed PostgreSQL schemas only. View-only alias schemas
are excluded.

## Part 2: Folder Tree And File Map

```text
outputs/
├── GUIDE_outputs.md            -- This guide.
├── postgres_columns.csv        -- Final one-row-per-column metadata catalog.
├── postgres_libraries.csv      -- Final one-row-per-library metadata catalog, enriched with WRDS descriptions.
├── postgres_tables.csv         -- Final one-row-per-table metadata catalog.
├── postgres_table_role_guide.md -- Original classification guide (main/helper/bridge/staging roles).
├── guide_numeric_libraries.md  -- Enriched guide: numeric libraries with column glossaries + row examples.
└── guide_text_libraries.md     -- Enriched guide: text/people libraries with column glossaries + row examples.
```

## Part 3: Code Reference

These files are produced by:

- `export_postgres_tables.py`
- `export_postgres_columns.py`
- `export_postgres_libraries.py`
- `merge_postgres_library_descriptions.py` updates
  `postgres_libraries.csv` in place to add the enrichment columns
- `postgres_table_role_guide.md` is a documentation artifact written from the
  exported catalogs plus the existing `library_samples/` CSV snapshots and, when
  useful, live WRDS catalog checks
