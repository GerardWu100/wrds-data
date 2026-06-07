#!/usr/bin/env python3
"""Small ClickHouse connection check script.

Reads clickhouse credentials from clickhouse/config.toml and runs SELECT 1.
"""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

CONFIG_PATH = Path(__file__).resolve().parent / "config.toml"


def _load_clickhouse_config(config_path: Path) -> dict[str, Any]:
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    return raw["clickhouse"]


def _validate_config(clickhouse_cfg: dict[str, Any]) -> None:
    required_keys = ["host", "port", "username", "password", "secure"]
    missing = [key for key in required_keys if key not in clickhouse_cfg]
    if missing:
        raise ValueError(f"Missing clickhouse config keys: {', '.join(missing)}")

    for key in ["username", "password"]:
        value = str(clickhouse_cfg[key]).strip()
        if not value or value.upper().startswith("YOUR_CLICKHOUSE_"):
            raise ValueError(f"Invalid clickhouse.{key}: set a real value in {CONFIG_PATH}")


def _resolve_host_and_secure(raw_host: str, secure: bool) -> tuple[str, bool]:
    stripped = raw_host.strip()
    if stripped.startswith("http://") or stripped.startswith("https://"):
        parsed = urlparse(stripped)
        if not parsed.hostname:
            raise ValueError(f"Invalid clickhouse.host URL: {raw_host!r}")
        return parsed.hostname, secure

    return stripped, secure


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
    port = int(clickhouse_cfg["port"])

    return clickhouse_connect.get_client(
        host=host,
        port=port,
        username=str(clickhouse_cfg["username"]),
        password=str(clickhouse_cfg["password"]),
        secure=secure,
    )


def main() -> None:
    try:
        clickhouse_cfg = _load_clickhouse_config(CONFIG_PATH)
        _validate_config(clickhouse_cfg)
        client = _build_client(clickhouse_cfg)
        result = client.command("SELECT 1")
        print(f"Connection successful. SELECT 1 -> {result}")
    except Exception as exc:
        raise SystemExit(f"Connection test failed: {exc}") from exc


if __name__ == "__main__":
    main()
