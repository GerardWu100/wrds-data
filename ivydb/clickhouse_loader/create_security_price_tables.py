"""Create the empty compressed ClickHouse table for IvyDB security prices."""

from __future__ import annotations

from ivydb.clickhouse_loader.clickhouse_client import create_client
from ivydb.clickhouse_loader.config import AppConfig, default_config


# Security-price floats use Float32: prices, returns, adjustment factors, and
# shares outstanding (stored in thousands) all sit well inside Float32's ~7
# significant digits, so single precision halves their storage with no
# meaningful precision loss. volume keeps UInt64 because daily share volume for
# index/ETF underlyings can exceed the UInt32 range.
SECURITY_PRICE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS `{database}`.`{table}` (
    `source_year` UInt16 CODEC(ZSTD(6)),
    `secid` Nullable(UInt32) CODEC(ZSTD(6)),
    `date` Nullable(Date32) CODEC(DoubleDelta, ZSTD(6)),
    `low` Nullable(Float32) CODEC(ZSTD(6)),
    `high` Nullable(Float32) CODEC(ZSTD(6)),
    `close` Nullable(Float32) CODEC(ZSTD(6)),
    `volume` Nullable(UInt64) CODEC(ZSTD(6)),
    `return` Nullable(Float32) CODEC(ZSTD(6)),
    `cfadj` Nullable(Float32) CODEC(ZSTD(6)),
    `open` Nullable(Float32) CODEC(ZSTD(6)),
    `cfret` Nullable(Float32) CODEC(ZSTD(6)),
    `shrout` Nullable(Float32) CODEC(ZSTD(6))
)
ENGINE = MergeTree
PARTITION BY `source_year`
ORDER BY (
    ifNull(`secid`, 0),
    ifNull(`date`, toDate32('1970-01-01'))
)
"""


def create_security_price_tables(client: object, config: AppConfig) -> list[str]:
    """Create the configured consolidated security-price table in ClickHouse."""

    if not config.underlying_prices.years:
        return []

    database = config.clickhouse.database
    table = config.underlying_prices.target_table
    client.command(SECURITY_PRICE_TABLE_SQL.format(database=database, table=table))
    return [table]


def main() -> None:
    """Create the configured consolidated ``secprd`` ClickHouse table."""

    config = default_config()
    client = create_client(config.clickhouse)
    created_tables = create_security_price_tables(client, config)
    if not created_tables:
        print("No security price years selected in config.toml.")
        return

    for table in created_tables:
        print(f"Created or already exists: {config.clickhouse.database}.{table}")


if __name__ == "__main__":
    main()
