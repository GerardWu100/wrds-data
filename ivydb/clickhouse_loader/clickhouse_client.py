"""ClickHouse client construction and small command helpers."""

from __future__ import annotations

from urllib.parse import urlparse

import clickhouse_connect

from ivydb.clickhouse_loader.config import ClickHouseConfig


def create_client(config: ClickHouseConfig) -> object:
    """Create a ``clickhouse-connect`` client from loader configuration."""

    host, secure = _normalize_host_and_secure(config.host, config.secure)
    return clickhouse_connect.get_client(
        host=host,
        port=config.port,
        username=config.username,
        password=config.password,
        secure=secure,
    )


def table_exists(client: object, database: str, table: str) -> bool:
    """Return whether a ClickHouse table already exists."""

    sql = (
        "SELECT count() "
        "FROM system.tables "
        f"WHERE database = '{database}' AND name = '{table}'"
    )
    result = client.query(sql)
    return bool(result.result_rows[0][0])


def table_row_count(client: object, database: str, table: str) -> int:
    """Return the number of rows stored in one ClickHouse table."""

    sql = f"SELECT count() FROM `{database}`.`{table}`"
    result = client.query(sql)
    return int(result.result_rows[0][0])


def _normalize_host_and_secure(host: str, configured_secure: bool) -> tuple[str, bool]:
    """Accept either a host name or an HTTP(S) URL in config."""

    if "://" not in host:
        return host, configured_secure

    parsed_host = urlparse(host)
    secure = parsed_host.scheme == "https"
    return parsed_host.hostname or host, secure
