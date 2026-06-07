"""Create empty ClickHouse tables selected in ``config.toml``.

This module is the first step in the two-step IvyDB workflow:

1. ``create-tables`` creates empty ClickHouse tables from ``config.toml``.
2. ``load`` streams WRDS PostgreSQL rows into those tables.

The create step connects only to ClickHouse. It does not need WRDS credentials
or PostgreSQL metadata. Database ``ivydb`` must exist before running create-tables.
"""

from __future__ import annotations

from pathlib import Path

from ivydb.clickhouse_loader.clickhouse_client import create_client
from ivydb.clickhouse_loader.config import AppConfig, default_config_path, load_config
from ivydb.clickhouse_loader.create_option_price_tables import create_option_price_tables
from ivydb.clickhouse_loader.create_reference_tables import create_reference_tables
from ivydb.clickhouse_loader.create_security_price_tables import create_security_price_tables


def planned_create_table_names(config: AppConfig) -> list[str]:
    """Return ClickHouse table names that one create-tables run would touch."""

    planned_tables: list[str] = []
    if config.static_tables:
        planned_tables.extend(table.target_table for table in config.static_tables)
    if config.underlying_prices.years:
        planned_tables.append(config.underlying_prices.target_table)
    if config.option_prices.years:
        planned_tables.extend(
            config.option_prices.target_template.format(year=year)
            for year in config.option_prices.years
        )

    deduped_tables: list[str] = []
    seen_tables: set[str] = set()
    for table in planned_tables:
        if table in seen_tables:
            continue
        seen_tables.add(table)
        deduped_tables.append(table)
    return deduped_tables


def create_tables_from_config(config: AppConfig) -> list[str]:
    """Create empty ClickHouse tables for every enabled family in config.

    Parameters
    ----------
    config:
        Parsed loader configuration. Table families disabled in ``config.toml``
        are skipped.

    Returns
    -------
    list[str]
        ClickHouse table names that were created or already existed.
    """

    client = create_client(config.clickhouse)

    created_tables: list[str] = []
    if config.static_tables:
        created_tables.extend(create_reference_tables(client, config))
    if config.underlying_prices.years:
        created_tables.extend(create_security_price_tables(client, config))
    if config.option_prices.years:
        created_tables.extend(create_option_price_tables(client, config))

    return created_tables


def main() -> None:
    """CLI entrypoint for ``python -m ivydb.clickhouse_loader.create_tables``."""

    import argparse

    parser = argparse.ArgumentParser(
        description="Create empty IvyDB ClickHouse tables from config.toml.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="Path to the IvyDB ClickHouse loader config.toml.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    created_tables = create_tables_from_config(config)
    if not created_tables:
        print("No tables selected in config.toml.")
        return

    database = config.clickhouse.database
    for table in created_tables:
        print(f"Created or already exists: {database}.{table}")


if __name__ == "__main__":
    main()
