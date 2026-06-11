"""Create empty compressed ClickHouse tables for IvyDB reference/link data."""

from __future__ import annotations

from ivydb.clickhouse_loader.clickhouse_client import create_client
from ivydb.clickhouse_loader.config import AppConfig, default_config


REFERENCE_TABLE_SQL_BY_SOURCE = {
    "securd": """
CREATE TABLE IF NOT EXISTS `{database}`.`{table}` (
    `secid` Nullable(UInt32) CODEC(ZSTD(12)),
    `cusip` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `ticker` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `sic` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `index_flag` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `exchange_d` Nullable(Float64) CODEC(ZSTD(12)),
    `class` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `issue_type` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `industry_group` Nullable(Float64) CODEC(ZSTD(12))
)
ENGINE = MergeTree
ORDER BY (ifNull(`secid`, 0))
""",
    "secnmd": """
CREATE TABLE IF NOT EXISTS `{database}`.`{table}` (
    `secid` Nullable(UInt32) CODEC(ZSTD(12)),
    `effect_date` Nullable(Date32) CODEC(DoubleDelta, ZSTD(12)),
    `cusip` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `ticker` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `class` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `issuer` Nullable(String) CODEC(ZSTD(12)),
    `issue` Nullable(String) CODEC(ZSTD(12)),
    `sic` LowCardinality(Nullable(String)) CODEC(ZSTD(12))
)
ENGINE = MergeTree
ORDER BY (ifNull(`secid`, 0), ifNull(`effect_date`, toDate32('1970-01-01')))
""",
    "exchgd": """
CREATE TABLE IF NOT EXISTS `{database}`.`{table}` (
    `secid` Nullable(UInt32) CODEC(ZSTD(12)),
    `effect_date` Nullable(Date32) CODEC(DoubleDelta, ZSTD(12)),
    `seq_num` Nullable(UInt32) CODEC(ZSTD(12)),
    `status` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `exchange` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `add_del` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `exch_flag` LowCardinality(Nullable(String)) CODEC(ZSTD(12))
)
ENGINE = MergeTree
ORDER BY (
    ifNull(`secid`, 0),
    ifNull(`effect_date`, toDate32('1970-01-01')),
    ifNull(`seq_num`, 0)
)
""",
    "distrd": """
CREATE TABLE IF NOT EXISTS `{database}`.`{table}` (
    `secid` Nullable(UInt32) CODEC(ZSTD(12)),
    `record_date` Nullable(Date32) CODEC(DoubleDelta, ZSTD(12)),
    `seq_num` Nullable(UInt32) CODEC(ZSTD(12)),
    `ex_date` Nullable(Date32) CODEC(DoubleDelta, ZSTD(12)),
    `amount` Nullable(Float64) CODEC(ZSTD(12)),
    `adj_factor` Nullable(Float64) CODEC(ZSTD(12)),
    `declare_date` Nullable(Date32) CODEC(DoubleDelta, ZSTD(12)),
    `payment_date` Nullable(Date32) CODEC(DoubleDelta, ZSTD(12)),
    `link_secid` Nullable(UInt32) CODEC(ZSTD(12)),
    `distr_type` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `frequency` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `currency` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `approx_flag` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `cancel_flag` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `liquid_flag` LowCardinality(Nullable(String)) CODEC(ZSTD(12))
)
ENGINE = MergeTree
ORDER BY (
    ifNull(`secid`, 0),
    ifNull(`record_date`, toDate32('1970-01-01')),
    ifNull(`seq_num`, 0)
)
""",
    "opinfd": """
CREATE TABLE IF NOT EXISTS `{database}`.`{table}` (
    `secid` Nullable(UInt32) CODEC(ZSTD(12)),
    `div_convention` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `exercise_style` LowCardinality(Nullable(String)) CODEC(ZSTD(12)),
    `am_set_flag` LowCardinality(Nullable(String)) CODEC(ZSTD(12))
)
ENGINE = MergeTree
ORDER BY (ifNull(`secid`, 0))
""",
    "opcrsphist": """
CREATE TABLE IF NOT EXISTS `{database}`.`{table}` (
    `secid` Nullable(UInt32) CODEC(ZSTD(12)),
    `sdate` Nullable(Date32) CODEC(DoubleDelta, ZSTD(12)),
    `edate` Nullable(Date32) CODEC(DoubleDelta, ZSTD(12)),
    `permno` Nullable(UInt32) CODEC(ZSTD(12)),
    `score` Nullable(Float64) CODEC(ZSTD(12))
)
ENGINE = MergeTree
ORDER BY (
    ifNull(`secid`, 0),
    ifNull(`sdate`, toDate32('1970-01-01')),
    ifNull(`edate`, toDate32('1970-01-01')),
    ifNull(`permno`, 0),
    ifNull(`score`, 0)
)
""",
}


def create_reference_tables(client: object, config: AppConfig) -> list[str]:
    """Create configured reference and CRSP-link tables in ClickHouse."""

    created_tables: list[str] = []
    database = config.clickhouse.database
    for table_config in config.static_tables:
        create_sql_template = REFERENCE_TABLE_SQL_BY_SOURCE.get(table_config.source_table)
        if create_sql_template is None:
            supported_tables = ", ".join(sorted(REFERENCE_TABLE_SQL_BY_SOURCE))
            raise ValueError(
                f"No built-in schema for {table_config.source_table!r}. "
                f"Add it to REFERENCE_TABLE_SQL_BY_SOURCE. Supported tables: {supported_tables}"
            )

        client.command(
            create_sql_template.format(
                database=database,
                table=table_config.target_table,
            )
        )
        created_tables.append(table_config.target_table)

    return created_tables


def main() -> None:
    """Create configured reference and CRSP-link ClickHouse tables."""

    config = default_config()
    client = create_client(config.clickhouse)
    created_tables = create_reference_tables(client, config)
    if not created_tables:
        print("No reference tables selected in config.toml.")
        return

    for table in created_tables:
        print(f"Created or already exists: {config.clickhouse.database}.{table}")


if __name__ == "__main__":
    main()
