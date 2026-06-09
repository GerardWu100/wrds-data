"""Create empty compressed ClickHouse tables for IvyDB option prices."""

from __future__ import annotations

from ivydb.clickhouse_loader.clickhouse_client import create_client
from ivydb.clickhouse_loader.config import AppConfig, default_config


# Codec / width rationale (benchmarked on the full 15.76M-row 1996 table):
# - The compressed footprint is dominated (~73%) by impl_volatility and the four
#   Greeks. Those carry exactly 6 decimal places at the source, but as Float32
#   their binary mantissa cannot represent 6-decimal values cleanly, so the low
#   bits are noise that ZSTD cannot pack (only ~1.4-1.5x). Storing them as
#   fixed-point Decimal(6) makes each value an exact scaled integer (value * 1e6)
#   that ZSTD compresses ~10% smaller overall (measured: delta -9.8%, gamma
#   -21.4%, impl_volatility -11.1%, vega -4.6%, theta -1.4%) and is bit-exact to
#   the source 6-decimal grid rather than an approximation. Gorilla was ~17%
#   worse and ZSTD(22) gained <1%, so codec tuning alone is a dead end.
#   delta/gamma/vega/impl_volatility fit Decimal32(6) (<=9 significant digits);
#   theta reaches -1477.9 -> 10 digits, so it needs the wider Decimal64(6).
# - prices (strike_price, best_bid, best_offer) and cfadj stay Float32: they sit
#   on a coarse, binary-exact tick grid (e.g. 1/16 dollar) with very few distinct
#   values, so Float32 + ZSTD already compresses well; Decimal made them larger.
# - volume / open_interest are per-contract daily counts (observed max ~52k);
#   UInt32 is the correct width and UInt64 only wasted space.
# - am_settlement is a 0/1 flag, so UInt8 is sufficient.
# - contract_size is Int32 rather than UInt32 because WRDS uses -99 as an
#   OptionMetrics missing-value sentinel in historical opprcd rows.
# - optionid increases within the (secid, date) sort runs, so Delta before ZSTD
#   shrinks it markedly (~26x) with no precision loss.
# - forward_price is intentionally absent: it moved to the fwdprd file in manual
#   version 5.0 and the live opprcd column is 0% populated.
# - root / suffix are intentionally absent: the 2010 OptionMetrics OSI revision
#   replaced them with symbol + symbol_flag. For 1996-2010 rows they are exactly
#   symbol split on '.' (verified 100% reconstructable across sampled years), and
#   from 2011 on they are empty. symbol + symbol_flag is the canonical contract
#   identifier; legacy root/suffix are recoverable as splitByChar('.', symbol).
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
    `impl_volatility` Nullable(Decimal32(6)) CODEC(ZSTD(6)),
    `delta` Nullable(Decimal32(6)) CODEC(ZSTD(6)),
    `gamma` Nullable(Decimal32(6)) CODEC(ZSTD(6)),
    `vega` Nullable(Decimal32(6)) CODEC(ZSTD(6)),
    `theta` Nullable(Decimal64(6)) CODEC(ZSTD(6)),
    `optionid` Nullable(UInt64) CODEC(Delta, ZSTD(6)),
    `cfadj` Nullable(Float32) CODEC(ZSTD(6)),
    `am_settlement` Nullable(UInt8) CODEC(ZSTD(6)),
    `contract_size` Nullable(Int32) CODEC(ZSTD(6)),
    `ss_flag` Nullable(Enum8('0' = 1, '1' = 2, 'E' = 3)) CODEC(ZSTD(6)),
    `expiry_indicator` LowCardinality(Nullable(String)) CODEC(ZSTD(6))
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
