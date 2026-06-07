"""BoardEx/CapIQ -> Parquet downloader package.

Downloads the current config-selected BoardEx/CapIQ bundle and writes one
compressed Parquet file per table to ``boardex_parquet/outputs``.

Entry points:
    __main__.py     -- module execution entry point
    cli.py          -- command-line interface
    download_to_parquet.py  -- core download logic, importable as a module
    load_parquet_to_clickhouse.py -- local Parquet -> ClickHouse loader CLI
    clickhouse_loader.py -- importable ClickHouse load/validation helpers
    validate_derivations.py -- live WRDS spot checks for large derived tables
    config.toml     -- table list and settings
    clickhouse_config.toml -- ClickHouse target settings
"""
