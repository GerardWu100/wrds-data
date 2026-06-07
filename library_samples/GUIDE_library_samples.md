# Library Samples Guide

## Part 1: Conceptual Explanation

This folder is the lightweight exploration area. Its job is to keep one compact
CSV sample for every live table in each selected WRDS library so the user can
inspect real data quickly without opening the full WRDS tables.

The workflow is intentionally simple and shared:

1. `export_small_samples.py` exposes a shared
   `export_samples_for_libraries()` function.
2. `config.toml` defines the default library list and the row limit.
3. The script opens one WRDS connection through
   `catalog_exports/wrds_connection.py`.
4. For each library, it asks the live WRDS/PostgreSQL database for every table
   in that schema.
5. For each table, it runs `select * ... limit <row_limit>`.
6. It writes the result into the matching library subfolder.

Each library gets its own folder because that is the user's preferred layout for
future exploration. That keeps sample files grouped by source library instead of
mixing everything in one flat output directory. Inside each library folder there
is one CSV per live WRDS table.

The current config in `config.toml` uses `row_limit = 100`. The folder can also
contain older sampled library subfolders that are no longer in the current
default config, because previous exports are kept unless removed manually.

One naming ambiguity mattered here. The requested string
`tr_ownershipfactset_own` is not an actual library code in
`outputs/postgres_libraries.csv`. The first column shows `tr_ownership` and
`factset_own` as separate libraries, so this folder contains both as separate
subfolders.

## Part 2: Folder Tree And File Map

```text
library_samples/
├── GUIDE_library_samples.md          -- This folder guide.
├── __init__.py                       -- Marks the folder as a package.
├── config.toml                       -- Default row limit and target libraries.
├── export_small_samples.py           -- Refreshes all compact sample CSVs.
└── <library_name>/                   -- One subfolder per sampled WRDS library.
    └── <table_name>.csv              -- Tiny `select * ... limit <row_limit>` sample for one live table.
```

## Part 3: Code Reference

`export_small_samples.py`

- `CONFIG_PATH`: default TOML config location.
- `PROJECT_ROOT`: repo root resolved from the script path so the exporter can
  find sibling packages during direct script execution.
- `load_export_config()`: loads TOML settings.
- `parse_libraries()`: validates and normalizes configured libraries.
- `parse_row_limit()`: validates the configured row limit.
- `normalize_library_names()`: strips and de-duplicates a requested library list.
- `build_output_path()`: maps a library/table pair to the CSV path.
- `export_table_sample()`: fetches and writes one small sample CSV.
- `export_library_samples()`: exports all live tables for one library.
- `export_samples_for_libraries()`: shared reusable entry point for arbitrary
  library lists.
- `export_samples_from_config()`: shared entry point for `config.toml`.
- `main()`: refreshes the default library set in one run.

Output layout:

- `library_samples/<library_name>/`: created on demand for each configured
  library
- `library_samples/<library_name>/<table_name>.csv`: one CSV per live WRDS
  table discovered in that library

Run:

```bash
uv run python -m library_samples.export_small_samples
uv run library_samples/export_small_samples.py
```
