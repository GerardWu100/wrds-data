#!/usr/bin/env python3
"""Drop the configured ClickHouse table if it exists."""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path
from urllib.parse import urlparse


def _resolve_host_and_secure(raw_host: str, secure: bool) -> tuple[str, bool]:
    stripped = raw_host.strip()
    if stripped.startswith("http://") or stripped.startswith("https://"):
        parsed = urlparse(stripped)
        if not parsed.hostname:
            raise ValueError(f"Invalid clickhouse.host URL: {raw_host!r}")
        return parsed.hostname, secure
    return stripped, secure


def main() -> None:
    config_path = Path(__file__).resolve().parent / "config.toml"
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)

    clickhouse_cfg = raw["clickhouse"]

    clickhouse_connect = importlib.import_module("clickhouse_connect")
    host, secure = _resolve_host_and_secure(
        str(clickhouse_cfg["host"]),
        bool(clickhouse_cfg["secure"]),
    )
    client = clickhouse_connect.get_client(
        host=host,
        port=int(clickhouse_cfg["port"]),
        username=str(clickhouse_cfg["username"]),
        password=str(clickhouse_cfg["password"]),
        secure=secure,
    )

    database = str(clickhouse_cfg["database"])
    table = str(clickhouse_cfg["table"])
    client.command(f"DROP TABLE IF EXISTS {database}.{table}")
    print(f"Dropped table if it existed: {database}.{table}")


if __name__ == "__main__":
    main()
