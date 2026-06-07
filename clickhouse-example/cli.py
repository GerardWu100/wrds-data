#!/usr/bin/env python3
"""CLI entrypoint for loading 1-minute OHLCV data into ClickHouse."""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path
from typing import Any

from load_ohlcv_to_clickhouse import LoaderConfig, run_load


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for OHLCV ingestion."""

    parser = argparse.ArgumentParser(
        description="Load 1-minute OHLCV files into ClickHouse."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to TOML config file.",
    )
    parser.add_argument("--data-dir", type=Path, help="Override data directory.")
    parser.add_argument("--host", help="Override ClickHouse host.")
    parser.add_argument("--port", type=int, help="Override ClickHouse port.")
    parser.add_argument("--username", help="Override ClickHouse username.")
    parser.add_argument("--password", help="Override ClickHouse password.")
    parser.add_argument("--database", help="Override ClickHouse database.")
    parser.add_argument("--table", help="Override ClickHouse table.")
    parser.add_argument("--batch-size", type=int, help="Override insert batch size.")
    parser.add_argument(
        "--market-timezone",
        help="Override source market timezone for non-UTC symbols (IANA name, e.g. America/New_York).",
    )
    parser.add_argument(
        "--error-export-path",
        type=Path,
        help="Override path for parse error export log. Import stops at first parse error.",
    )
    parser.add_argument(
        "--clean-start",
        action="store_true",
        help="Override config to truncate table before loading.",
    )
    parser.add_argument(
        "--secure",
        action="store_true",
        help="Override config to use HTTPS for ClickHouse connection.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=Path("outputs/run.log"),
        help="Path to write timestamped run log (default: outputs/run.log). Pass empty string to disable.",
    )
    return parser.parse_args()


def load_config(config_path: Path) -> dict[str, Any]:
    """Load TOML config for ClickHouse ingestion."""

    with config_path.open("rb") as handle:
        return tomllib.load(handle)


def resolve_config(args: Any) -> LoaderConfig:
    """Resolve base config and apply CLI overrides."""

    raw = load_config(args.config)
    clickhouse_cfg = raw["clickhouse"]
    loader_cfg = raw["loader"]

    return LoaderConfig(
        data_dir=args.data_dir if args.data_dir is not None else Path(loader_cfg["data_dir"]),
        host=args.host if args.host is not None else str(clickhouse_cfg["host"]),
        port=args.port if args.port is not None else int(clickhouse_cfg["port"]),
        username=(
            args.username if args.username is not None else str(clickhouse_cfg["username"])
        ),
        password=(
            args.password if args.password is not None else str(clickhouse_cfg["password"])
        ),
        database=(
            args.database if args.database is not None else str(clickhouse_cfg["database"])
        ),
        table=args.table if args.table is not None else str(clickhouse_cfg["table"]),
        batch_size=(
            args.batch_size if args.batch_size is not None else int(loader_cfg["batch_size"])
        ),
        clean_start=bool(loader_cfg["clean_start"]) or bool(args.clean_start),
        secure=bool(clickhouse_cfg["secure"]) or bool(args.secure),
        market_timezone=(
            args.market_timezone
            if args.market_timezone is not None
            else str(loader_cfg.get("market_timezone", "America/New_York"))
        ),
        utc_symbols=frozenset(str(symbol) for symbol in loader_cfg.get("utc_symbols", [])),
        error_export_path=(
            args.error_export_path
            if args.error_export_path is not None
            else Path(loader_cfg.get("error_export_path", "outputs/import_errors.log"))
        ),
        log_path=args.log_path if str(args.log_path) else None,
    )


def main() -> None:
    """Run CLI ingestion flow."""

    args = parse_args()
    config = resolve_config(args)
    run_load(config)


if __name__ == "__main__":
    main()
