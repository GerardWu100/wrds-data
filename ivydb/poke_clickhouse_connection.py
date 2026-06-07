"""Standalone ClickHouse connection smoke test for the IvyDB loader.

Run this before the full WRDS load to verify that the Docker ClickHouse server,
user credentials, HTTP port, and target database are reachable from Python.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ivydb.clickhouse_loader.clickhouse_client import create_client
from ivydb.clickhouse_loader.config import ClickHouseConfig, default_config_path, load_config


def main(argv: Sequence[str] | None = None) -> None:
    """Load IvyDB ClickHouse settings and run a minimal live database check."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)
    clickhouse_config = config.clickhouse

    print(_connection_summary(clickhouse_config))
    client = create_client(clickhouse_config)

    ping_result = client.query("SELECT 1")
    ping_value = ping_result.result_rows[0][0]
    if ping_value != 1:
        raise RuntimeError(f"ClickHouse SELECT 1 returned unexpected value: {ping_value!r}")

    database_sql = (
        "SELECT count() "
        "FROM system.databases "
        f"WHERE name = '{clickhouse_config.database}'"
    )
    database_result = client.query(database_sql)
    database_count = int(database_result.result_rows[0][0])
    if database_count != 1:
        raise RuntimeError(
            f"ClickHouse database {clickhouse_config.database!r} is not visible. "
            "Create it once with an admin account before running the loader."
        )

    print(f"OK: connected and found database {clickhouse_config.database!r}.")


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""

    parser = argparse.ArgumentParser(
        description="Poke the IvyDB ClickHouse connection before running the loader.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="Path to the IvyDB ClickHouse loader config.toml.",
    )
    return parser


def _connection_summary(config: ClickHouseConfig) -> str:
    """Return a password-safe summary of the ClickHouse connection target."""

    protocol = "https" if config.secure else "http"
    return (
        "Poking ClickHouse "
        f"{protocol}://{config.host}:{config.port} "
        f"as user {config.username!r} "
        f"for database {config.database!r}."
    )


if __name__ == "__main__":
    main()
