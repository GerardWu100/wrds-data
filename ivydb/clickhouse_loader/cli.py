"""Command-line interface for loading IvyDB data from WRDS into ClickHouse."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import logging
from pathlib import Path
import sys
import time

from clickhouse_connect.driver.exceptions import ClickHouseError
from catalog_exports.wrds_connection import connect_wrds
from ivydb.clickhouse_loader.clickhouse_client import create_client
from ivydb.clickhouse_loader.config import AppConfig, default_config_path, load_config
from ivydb.clickhouse_loader.create_tables import create_tables_from_config
from ivydb.clickhouse_loader.drop_tables import (
    confirmed_drop_table_names,
    drop_tables_from_config,
    planned_drop_table_names,
)
from ivydb.clickhouse_loader.load_to_clickhouse import clear_failed_tables, load_tables
from ivydb.clickhouse_loader.table_plan import TablePlan, build_table_plan_from_config
from ivydb.clickhouse_loader.validation import validate_loaded_tables


LOGGER = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the IvyDB ClickHouse loader CLI."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config)
    configure_logging(config.loader.run_log_path)
    table_plan = build_table_plan_from_config(config)

    if args.command == "create-tables":
        if not table_plan:
            print("No tables selected in config.toml.")
            return
        _run_create_tables_command(config)
        return

    if args.command == "drop-tables":
        if not planned_drop_table_names(config):
            print("No tables selected in config.toml.")
            return
        _run_drop_tables_command(config)
        return

    if not table_plan:
        print("No source tables selected in config.toml.")
        return

    LOGGER.info(
        "Command=%s target_database=%s tables=%s",
        args.command,
        config.clickhouse.database,
        len(table_plan),
    )
    if args.command == "load":
        _run_load_command(config, table_plan)
    elif args.command == "validate":
        _run_validate_command(config, table_plan)
    elif args.command == "clear-failed":
        _run_clear_failed_command(config, table_plan)
    else:
        raise ValueError(f"unknown command: {args.command}")


def _run_create_tables_command(config: AppConfig) -> None:
    """Create empty ClickHouse tables for the current config selection."""

    created_tables = create_tables_from_config(config)
    database = config.clickhouse.database
    for table in created_tables:
        print(f"Created or already exists: {database}.{table}")


def _run_drop_tables_command(config: AppConfig) -> None:
    """Manually confirm, then drop ClickHouse tables selected in config."""

    if not sys.stdin.isatty():
        raise RuntimeError("drop-tables must be run manually from an interactive terminal")

    database = config.clickhouse.database
    planned_tables = planned_drop_table_names(config)
    try:
        confirmed_drop_table_names(
            database=database,
            tables=planned_tables,
            read_confirmation=input,
            write_output=print,
        )
    except ValueError as error:
        print(f"Aborted: {error}")
        return

    try:
        dropped_tables = drop_tables_from_config(config)
    except ClickHouseError as error:
        print(f"ClickHouse rejected drop-tables: {error}")
        print(
            "Grant DROP TABLE on the selected IvyDB tables, then rerun "
            "drop-tables if you still intend to delete them."
        )
        return

    for table in dropped_tables:
        print(f"Dropped if existed: {database}.{table}")


def _run_load_command(config: AppConfig, table_plan: list[TablePlan]) -> None:
    """Connect to WRDS and ClickHouse, then load the planned source tables."""

    clickhouse_client = create_client(config.clickhouse)
    wrds_connection = connect_wrds()
    try:
        results = load_tables(
            config=config,
            wrds_connection=wrds_connection,
            clickhouse_client=clickhouse_client,
            table_plan=table_plan,
        )
        for result in results:
            print(
                f"{result.source_table} -> {result.target_table}: "
                f"{result.rows_loaded} rows"
            )
    finally:
        wrds_connection.close()


def _run_validate_command(config: AppConfig, table_plan: list[TablePlan]) -> None:
    """Connect to ClickHouse and print validation results for planned targets."""

    clickhouse_client = create_client(config.clickhouse)
    validation_results = validate_loaded_tables(
        clickhouse_client=clickhouse_client,
        database=config.clickhouse.database,
        table_plan=table_plan,
    )
    for result in validation_results:
        print(f"{result.table} {result.check_name}: {result.value}")


def _run_clear_failed_command(config: AppConfig, table_plan: list[TablePlan]) -> None:
    """Clear incomplete direct-load destinations so they can be reloaded."""

    clickhouse_client = create_client(config.clickhouse)
    cleared_tables = clear_failed_tables(
        config=config,
        clickhouse_client=clickhouse_client,
        table_plan=table_plan,
    )
    for table in cleared_tables:
        print(f"Cleared incomplete load destination: {table}")


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Load OptionMetrics IvyDB tables from WRDS PostgreSQL to ClickHouse. "
            "Edit config.toml to choose tables, then run create-tables and load."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="Path to the IvyDB ClickHouse loader config.toml.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "create-tables",
        help="Create empty ClickHouse tables selected in config.toml.",
    )
    subparsers.add_parser(
        "drop-tables",
        help="Manually drop ClickHouse tables selected in config.toml after double confirmation.",
    )
    subparsers.add_parser(
        "load",
        help="Stream WRDS PostgreSQL rows into the selected ClickHouse tables.",
    )
    subparsers.add_parser(
        "validate",
        help="Run ClickHouse validation checks for the selected tables.",
    )
    subparsers.add_parser(
        "clear-failed",
        help="Clear incomplete direct-load destinations recorded in the audit log.",
    )

    return parser


def configure_logging(log_path: Path | None) -> None:
    """Configure timestamped terminal logging and optional local file logging."""

    logging.Formatter.converter = time.gmtime
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s UTC %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )
    LOGGER.info("Writing run log to %s", log_path if log_path is not None else "terminal only")
