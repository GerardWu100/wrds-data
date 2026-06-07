#!/usr/bin/env python3
"""ClickHouse schema management for 1-minute bar tables."""

from __future__ import annotations

import importlib
import re
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(name: str, label: str) -> str:
    if not _IDENTIFIER_PATTERN.fullmatch(name):
        raise ValueError(f"Invalid {label}: {name!r}")
    return name


def create_database(client: Any, database: str) -> None:
    """Create ClickHouse database only when it does not already exist."""

    db_name = _validate_identifier(database, "database")
    client.command(f"CREATE DATABASE IF NOT EXISTS {db_name}")


def create_ohlcv_table(client: Any, database: str, table: str) -> bool:
    """Create a non-crypto 1-minute OHLCV table when missing.

    Returns:
        True if the table was created, False if it already existed.
    """

    db_name = _validate_identifier(database, "database")
    table_name = _validate_identifier(table, "table")
    exists = int(client.command(f"EXISTS TABLE {db_name}.{table_name}"))
    if exists == 1:
        return False

    # client.command(
    #     f"""
    #     CREATE TABLE IF NOT EXISTS {db_name}.{table_name} (
    #         symbol LowCardinality(String),
    #         ts DateTime64(3, 'America/New_York') CODEC(DoubleDelta, ZSTD(1)),
    #         open Float64 CODEC(Gorilla, ZSTD(1)),
    #         high Float64 CODEC(Gorilla, ZSTD(1)),
    #         low Float64 CODEC(Gorilla, ZSTD(1)),
    #         close Float64 CODEC(Gorilla, ZSTD(1)),
    #         volume Float64 CODEC(ZSTD(1))
    #     )
    #     ENGINE = MergeTree
    #     PARTITION BY toYYYYMM(ts)
    #     ORDER BY (symbol, ts)
    #     """
    # )
    client.command(
        f"""
        CREATE TABLE IF NOT EXISTS {db_name}.{table_name} (
            symbol LowCardinality(String),
            ts DateTime64(3, 'America/New_York') CODEC(DoubleDelta, ZSTD(3)),
            open Float64 CODEC(ZSTD(3)),
            high Float64 CODEC(ZSTD(3)),
            low Float64 CODEC(ZSTD(3)),
            close Float64 CODEC(ZSTD(3)),
            volume Float64 CODEC(ZSTD(3))
        )
        ENGINE = MergeTree
        PARTITION BY toYYYYMM(ts)
        ORDER BY (symbol, ts)
        """
    )
    return True


def truncate_table(client: Any, database: str, table: str) -> None:
    """Truncate table contents while keeping schema intact."""

    db_name = _validate_identifier(database, "database")
    table_name = _validate_identifier(table, "table")
    client.command(f"TRUNCATE TABLE {db_name}.{table_name}")


def _default_config_path() -> Path:
    return Path(__file__).resolve().parent / "config.toml"


def _load_clickhouse_config(config_path: Path) -> dict[str, Any]:
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    return raw["clickhouse"]


def _validate_required_clickhouse_settings(clickhouse_cfg: dict[str, Any]) -> None:
    required_keys = ["host", "port", "username", "password", "secure", "database", "table"]
    missing = [key for key in required_keys if key not in clickhouse_cfg]
    if missing:
        raise ValueError(f"Missing clickhouse config keys: {', '.join(missing)}")

    for key in ["host", "username", "password"]:
        value = str(clickhouse_cfg[key]).strip()
        if not value or value.upper().startswith("YOUR_CLICKHOUSE_"):
            raise ValueError(
                f"Invalid clickhouse.{key}: set a real value in {_default_config_path()}"
            )


def _build_client(clickhouse_cfg: dict[str, Any]) -> Any:
    try:
        clickhouse_connect = importlib.import_module("clickhouse_connect")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Missing dependency: clickhouse-connect. Install with `uv add clickhouse-connect`."
        ) from exc

    host, secure = _resolve_host_and_secure(
        str(clickhouse_cfg["host"]),
        bool(clickhouse_cfg["secure"]),
    )

    return clickhouse_connect.get_client(
        host=host,
        port=int(clickhouse_cfg["port"]),
        username=str(clickhouse_cfg["username"]),
        password=str(clickhouse_cfg["password"]),
        secure=secure,
    )


def _resolve_host_and_secure(raw_host: str, secure: bool) -> tuple[str, bool]:
    stripped = raw_host.strip()
    if stripped.startswith("http://") or stripped.startswith("https://"):
        parsed = urlparse(stripped)
        if not parsed.hostname:
            raise ValueError(f"Invalid clickhouse.host URL: {raw_host!r}")
        return parsed.hostname, secure
    return stripped, secure


def main() -> None:
    """Create ClickHouse database and OHLCV table using config.toml."""

    try:
        config_path = _default_config_path()
        clickhouse_cfg = _load_clickhouse_config(config_path)
        _validate_required_clickhouse_settings(clickhouse_cfg)
        client = _build_client(clickhouse_cfg)

        database = str(clickhouse_cfg["database"])
        table = str(clickhouse_cfg["table"])
        create_database(client, database)
        created = create_ohlcv_table(client, database, table)
        if created:
            print(f"Created table: {database}.{table}")
        else:
            print(f"Table already exists, no action: {database}.{table}")
    except Exception as exc:
        raise SystemExit(f"Schema setup failed: {exc}") from exc


if __name__ == "__main__":
    main()
