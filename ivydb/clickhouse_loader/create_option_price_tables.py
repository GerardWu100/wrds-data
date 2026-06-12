"""Create empty compressed ClickHouse tables for IvyDB option prices."""

from __future__ import annotations

from ivydb.clickhouse_loader.clickhouse_client import create_client
from ivydb.clickhouse_loader.config import AppConfig, default_config


# Codec / width rationale (benchmarked on a 2.23M-row 2023 sample):
# - The compressed footprint is dominated by impl_volatility and the four
#   Greeks. Those source values carry six decimal places, so IV, delta, and
#   gamma are stored as Decimal32(6): fixed-point 4-byte integers scaled by
#   1,000,000. Vega and theta use Decimal64(6) because recent years contain
#   values outside Decimal32(6)'s +/-2147.483647 range, while a full-2025
#   shadow-table benchmark showed Decimal64(6) with T64 still compressed about
#   140 MiB smaller than Float32 with ZSTD for those two columns. The loader
#   validates each decimal column's target range at the chunk boundary before
#   insertion. IV, delta, and gamma use T64 before ZSTD because a 31.1M-row
#   January 2025 shadow-table benchmark cut their compressed bytes by roughly
#   15-19% without changing values.
#   Prices and cfadj remain Float32. Historical bid/offer prices often sit on
#   binary-exact tick grids and compressed worse as Decimal in local tests, while
#   cfadj is a low-footprint adjustment factor where Decimal friction is not
#   worth the negligible savings.
# - volume / open_interest are per-contract daily counts (observed max ~52k);
#   UInt32 is the correct width and UInt64 only wasted space. volume uses T64
#   before ZSTD because the January 2025 benchmark showed a meaningful storage
#   gain. open_interest stays on plain ZSTD because the full 2025 reload showed
#   T64 was effectively flat and slightly larger.
# - last_date uses T64 before ZSTD because it halved compressed bytes versus
#   DoubleDelta in the same January 2025 shadow-table benchmark.
# - am_settlement is a 0/1 flag, so UInt8 is sufficient.
# - contract_size is Int32 rather than UInt32 because WRDS uses -99 as an
#   OptionMetrics missing-value sentinel in historical opprcd rows.
# - optionid keeps Delta before ZSTD because recent dense years often assign IDs
#   sequentially within sorted runs, which compresses very well. Sparse early
#   years can lose slightly from Delta, so this is an all-history tradeoff rather
#   than a universal per-year win.
# - forward_price is intentionally absent: it moved to the fwdprd file in manual
#   version 5.0 and the live opprcd column is 0% populated.
# - root / suffix are intentionally absent: the 2010 OptionMetrics OSI revision
#   replaced them with symbol + symbol_flag. For 1996-2010 rows they are exactly
#   symbol split on '.' (verified 100% reconstructable across sampled years), and
#   from 2011 on they are empty. symbol + symbol_flag is the canonical contract
#   identifier; legacy root/suffix are recoverable as splitByChar('.', symbol).
OPTION_PRICE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS `{database}`.`{table}` (
    `secid` Nullable(UInt32) CODEC(ZSTD(12)),
    `date` Nullable(Date32) CODEC(DoubleDelta, ZSTD(12)),
    `symbol` Nullable(String) CODEC(ZSTD(12)),
    `symbol_flag` Nullable(Enum8('0' = 1, '1' = 2)) CODEC(ZSTD(12)),
    `exdate` Nullable(Date32) CODEC(DoubleDelta, ZSTD(12)),
    `last_date` Nullable(Date32) CODEC(T64, ZSTD(12)),
    `cp_flag` Nullable(Enum8('C' = 1, 'P' = 2)) CODEC(ZSTD(12)),
    `strike_price` Nullable(Float32) CODEC(ZSTD(12)),
    `best_bid` Nullable(Float32) CODEC(ZSTD(12)),
    `best_offer` Nullable(Float32) CODEC(ZSTD(12)),
    `volume` Nullable(UInt32) CODEC(T64, ZSTD(12)),
    `open_interest` Nullable(UInt32) CODEC(ZSTD(12)),
    `impl_volatility` Nullable(Decimal32(6)) CODEC(T64, ZSTD(12)),
    `delta` Nullable(Decimal32(6)) CODEC(T64, ZSTD(12)),
    `gamma` Nullable(Decimal32(6)) CODEC(T64, ZSTD(12)),
    `vega` Nullable(Decimal64(6)) CODEC(T64, ZSTD(12)),
    `theta` Nullable(Decimal64(6)) CODEC(T64, ZSTD(12)),
    `optionid` Nullable(UInt64) CODEC(Delta, ZSTD(12)),
    `cfadj` Nullable(Float32) CODEC(ZSTD(12)),
    `am_settlement` Nullable(UInt8) CODEC(ZSTD(12)),
    `contract_size` Nullable(Int32) CODEC(ZSTD(12)),
    `ss_flag` Nullable(Enum8('0' = 1, '1' = 2, 'E' = 3)) CODEC(ZSTD(12)),
    `expiry_indicator` LowCardinality(Nullable(String)) CODEC(ZSTD(12))
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(ifNull(`date`, toDate32('1970-01-01')))
ORDER BY (
    ifNull(`secid`, 0),
    ifNull(`date`, toDate32('1970-01-01')),
    ifNull(`exdate`, toDate32('1970-01-01')),
    ifNull(CAST(`cp_flag`, 'Nullable(Int8)'), toInt8(0)),
    ifNull(`strike_price`, 0),
    ifNull(`optionid`, 0)
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
