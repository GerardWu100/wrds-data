"""Create empty compressed ClickHouse tables for IvyDB option prices."""

from __future__ import annotations

from ivydb.clickhouse_loader.clickhouse_client import create_client
from ivydb.clickhouse_loader.config import AppConfig, default_config


# Codec / width rationale (benchmarked on a 2.23M-row 2023 sample):
# - The compressed footprint is dominated (~81%) by impl_volatility and the four
#   Greeks. Those are high-entropy floats that barely respond to codec changes
#   (ZSTD(12) ~2% gain, Gorilla ~30% worse). The chosen lever is precision:
#   storing prices, implied vol, Greeks, and cfadj as Float32 cut the whole
#   opprcd table to ~64% of the all-Float64 size (73.5 -> 46.9 MB on-disk for the
#   2.23M-row sample) while keeping ~7 significant digits, which is ample for
#   option prices and Greeks. (Sizes use system.tables.total_bytes; the
#   per-column system.columns view under-reports for the loader's ClickHouse
#   user, which lacks the system.parts grant.)
#   A further ~12% is available by storing the heavy columns as fixed-point
#   Decimal (source IV/Greeks carry 6 decimals, prices 2), which is not applied
#   here because it needs per-column width care (theta can overflow Decimal32).
# - volume / open_interest are per-contract daily counts (observed max ~52k);
#   UInt32 is the correct width and UInt64 only wasted space.
# - am_settlement is a 0/1 flag, so UInt8 is sufficient.
# - optionid increases within the (secid, date) sort runs, so Delta before ZSTD
#   shrinks it markedly (~0.44 -> ~0.13 MB on the sample) with no precision loss.
# - forward_price is intentionally absent: it moved to the fwdprd file in manual
#   version 5.0 and the live opprcd column is 0% populated.
OPTION_PRICE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS `{database}`.`{table}` (
    `secid` Nullable(UInt32) CODEC(ZSTD(6)),
    `date` Nullable(Date32) CODEC(DoubleDelta, ZSTD(6)),
    `symbol` LowCardinality(Nullable(String)) CODEC(ZSTD(6)),
    `symbol_flag` Nullable(Enum8('0' = 1, '1' = 2)) CODEC(ZSTD(6)),
    `exdate` Nullable(Date32) CODEC(DoubleDelta, ZSTD(6)),
    `last_date` Nullable(Date32) CODEC(DoubleDelta, ZSTD(6)),
    `cp_flag` Nullable(Enum8('C' = 1, 'P' = 2)) CODEC(ZSTD(6)),
    `strike_price` Nullable(Float32) CODEC(ZSTD(6)),
    `best_bid` Nullable(Float32) CODEC(ZSTD(6)),
    `best_offer` Nullable(Float32) CODEC(ZSTD(6)),
    `volume` Nullable(UInt32) CODEC(ZSTD(6)),
    `open_interest` Nullable(UInt32) CODEC(ZSTD(6)),
    `impl_volatility` Nullable(Float32) CODEC(ZSTD(6)),
    `delta` Nullable(Float32) CODEC(ZSTD(6)),
    `gamma` Nullable(Float32) CODEC(ZSTD(6)),
    `vega` Nullable(Float32) CODEC(ZSTD(6)),
    `theta` Nullable(Float32) CODEC(ZSTD(6)),
    `optionid` Nullable(UInt64) CODEC(Delta, ZSTD(6)),
    `cfadj` Nullable(Float32) CODEC(ZSTD(6)),
    `am_settlement` Nullable(UInt8) CODEC(ZSTD(6)),
    `contract_size` Nullable(UInt32) CODEC(ZSTD(6)),
    `ss_flag` Nullable(Enum8('0' = 1, '1' = 2, 'E' = 3)) CODEC(ZSTD(6)),
    `expiry_indicator` LowCardinality(Nullable(String)) CODEC(ZSTD(6)),
    `root` LowCardinality(Nullable(String)) CODEC(ZSTD(6)),
    `suffix` LowCardinality(Nullable(String)) CODEC(ZSTD(6))
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(ifNull(`date`, toDate32('1970-01-01')))
ORDER BY (
    ifNull(`secid`, 0),
    ifNull(`date`, toDate32('1970-01-01')),
    ifNull(`optionid`, 0),
    ifNull(`exdate`, toDate32('1970-01-01')),
    ifNull(CAST(`cp_flag`, 'Nullable(Int8)'), toInt8(0)),
    ifNull(`strike_price`, 0)
)
"""


def create_option_price_tables(
    client: object,
    config: AppConfig,
    years: list[int] | None = None,
) -> list[str]:
    """Create configured yearly option-price tables in ClickHouse.

    Parameters
    ----------
    client:
        ClickHouse client with a ``command`` method.
    config:
        Parsed IvyDB loader configuration. The selected years and target table
        template come from ``config.toml``.
    years:
        Optional explicit year list. When omitted, all configured
        ``config.option_prices.years`` are created.

    Returns
    -------
    list[str]
        Created-or-existing ClickHouse table names.
    """

    created_tables: list[str] = []
    database = config.clickhouse.database
    selected_years = list(config.option_prices.years) if years is None else years
    for year in selected_years:
        table = config.option_prices.target_template.format(year=year)
        client.command(OPTION_PRICE_TABLE_SQL.format(database=database, table=table))
        created_tables.append(table)

    return created_tables


def main() -> None:
    """Create configured ``opprcdYYYY`` ClickHouse tables."""

    config = default_config()
    client = create_client(config.clickhouse)
    created_tables = create_option_price_tables(client, config)
    if not created_tables:
        print("No option price tables selected in config.toml.")
        return

    for table in created_tables:
        print(f"Created or already exists: {config.clickhouse.database}.{table}")


if __name__ == "__main__":
    main()
