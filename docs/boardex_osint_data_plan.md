# BoardEx + Capital IQ Selected Parquet Bundle Plan

This note records the **current shipped default** for
[`boardex_parquet/`](/Users/gwh/projects/one-time-projects/wrds-data/boardex_parquet).

As of **April 18, 2026**, the default is a **selected 35-table BoardEx + Capital
IQ Parquet bundle**:

- `boardex_na`: 26 selected tables
- `ciq_pplintel`: 7 selected tables
- `wrdsapps_plink_boardex_ciq`: 2 selected tables

It is not a full-library export.

## Goal

The goal of the shipped default is:

- keep the most useful BoardEx and Capital IQ people-intelligence tables
- avoid compensation tables
- avoid the largest person-level association and network panels
- keep the data local and queryable as compressed Parquet files
- keep reruns safe if a long table write is interrupted

## Current shipped default

Using the local catalog snapshot in
[`outputs/postgres_tables.csv`](/Users/gwh/projects/one-time-projects/wrds-data/outputs/postgres_tables.csv),
the current config selects:

- 35 tables total
- about 27.81 GiB of WRDS PostgreSQL relation size before Parquet compression

A live WRDS check from this workspace on **April 18, 2026** put the same
selection at about **28.09 GiB**.

The bundle keeps:

- BoardEx identity, role-history, education, achievements, outside-activity,
  board-announcement, committee, company, and selected association/network
  tables
- BoardEx-to-CIQ linking tables
- Capital IQ person, biography, role, role-function, coverage, and wide
  professional tables

The bundle skips:

- all BoardEx compensation tables
- all Capital IQ compensation tables
- the huge BoardEx person-level association panels
- the huge BoardEx pairwise person-network table
- the optional CRSP and ExecuComp bridge libraries

## Implementation rules

The downloader now follows these rules:

1. Read `config.toml` for the enabled libraries and explicit table allowlists.
2. Ask WRDS for the live table list in each enabled library.
3. Verify that the named `enabled_tables` still exist in WRDS.
4. Build a deterministic Arrow schema from live PostgreSQL column metadata for
   each table before the first batch is written.
5. Stream one plain `SELECT *` result per table in chunked DataFrames.
6. Write each table to a same-directory temporary Parquet path first.
7. Atomically move the temporary file into place only after success.
8. In `--resume` mode, skip only readable complete Parquet files.

The current code therefore keeps the narrower selected bundle while fixing the
two important write-path issues found in review:

- truncated outputs are no longer trusted by `--resume`
- sparse early batches no longer control the Parquet schema

## Default config stance

The shipped config keeps the three main libraries enabled and pins the bundle
through explicit `enabled_tables` lists.

That means the selection logic is:

- keep the three selected libraries enabled
- list the exact 35 tables in config
- download only those named tables

`sample_csv_rows = 0` stays in place, so the default workflow writes Parquet
only.

## How to change direction later

If you later want a larger or smaller bundle again, the clean place to change
that is still `config.toml`.

To make the bundle smaller:

1. remove some table names from `enabled_tables`, or
2. disable one of the currently enabled libraries

To make the bundle larger:

1. add some table names to `enabled_tables`, or
2. enable one of the optional libraries

The downloader code itself does not need to change for those scope adjustments.
