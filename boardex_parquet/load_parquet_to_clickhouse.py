#!/usr/bin/env python3
"""Command-line interface for loading BoardEx Parquet files into ClickHouse."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from boardex_parquet.clickhouse_loader import (  # noqa: E402
    create_empty_tables,
    create_client,
    default_config_path,
    dry_run,
    ensure_database,
    load_config,
    load_tables,
    validate_loaded_tables,
    with_runtime_overrides,
)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the BoardEx Parquet-to-ClickHouse loader."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config)
    config = with_runtime_overrides(
        config=config,
        replace_existing=args.replace,
        resume_existing=args.resume,
        parquet_dir=args.parquet_dir,
    )

    if args.command == "dry-run":
        for plan, sql in dry_run(config, table_filter=args.table):
            print(f"{plan.source_path.name} -> {config.clickhouse.database}.{plan.target_table}")
            print(f"rows: {plan.row_count}")
            print(sql)
            print()
        return

    client = create_client(config.clickhouse)
    if config.loader.create_database:
        ensure_database(client, config.clickhouse.database)

    if args.command == "create-schema":
        results = create_empty_tables(config, client, table_filter=args.table)
    elif args.command == "load":
        results = load_tables(config, client, table_filter=args.table)
    elif args.command == "validate":
        results = validate_loaded_tables(config, client, table_filter=args.table)
    else:
        raise ValueError(f"Unknown command: {args.command}")

    for result in results:
        print(
            f"{result.target_table}: {result.status}; "
            f"parquet_rows={result.parquet_rows}; "
            f"clickhouse_rows={result.clickhouse_rows}"
        )


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for loading and validating tables."""

    parser = argparse.ArgumentParser(
        description="Load BoardEx Parquet pocket files into ClickHouse.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="Path to boardex_parquet/clickhouse_config.toml.",
    )

    command_options = argparse.ArgumentParser(add_help=False)
    command_options.add_argument(
        "--parquet-dir",
        type=Path,
        default=None,
        help="Override the Parquet input directory from the config file.",
    )
    command_options.add_argument(
        "--table",
        default=None,
        help=(
            "Load or validate one target table, for example "
            "boardex_na__na_dir_profile_emp."
        ),
    )
    command_options.add_argument(
        "--replace",
        action="store_true",
        help="Drop and rebuild existing target tables before loading.",
    )
    command_options.add_argument(
        "--resume",
        action="store_true",
        default=None,
        help="Skip target tables whose ClickHouse row count already matches Parquet.",
    )
    command_options.add_argument(
        "--no-resume",
        action="store_false",
        dest="resume",
        help="Disable row-count resume checks for this run.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "dry-run",
        parents=[command_options],
        help="Print planned tables and DDL without connecting.",
    )
    subparsers.add_parser(
        "load",
        parents=[command_options],
        help="Create tables and insert Parquet rows.",
    )
    subparsers.add_parser(
        "create-schema",
        parents=[command_options],
        help="Create empty ClickHouse tables without inserting Parquet rows.",
    )
    subparsers.add_parser(
        "validate",
        parents=[command_options],
        help="Compare ClickHouse counts with Parquet counts.",
    )
    return parser


if __name__ == "__main__":
    main()
