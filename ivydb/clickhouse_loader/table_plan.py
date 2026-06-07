"""Build the WRDS-to-ClickHouse table plan for IvyDB loads."""

from __future__ import annotations

from dataclasses import dataclass

from ivydb.clickhouse_loader.config import AppConfig
from ivydb.clickhouse_loader.source_columns import source_columns_for


RUN_GROUP_REFERENCE = "reference"
RUN_GROUP_UNDERLYING_PRICES = "underlying-prices"
RUN_GROUP_OPTION_PRICES = "option-prices"


@dataclass(frozen=True)
class TablePlan:
    """One WRDS source table and its ClickHouse target table.

    Parameters
    ----------
    source_library:
        WRDS PostgreSQL schema name, for example ``optionm_all``.
    source_table:
        WRDS PostgreSQL table name, for example ``opprcd2024``.
    target_table:
        ClickHouse table name, for example ``opprcd2024`` or consolidated
        ``secprd``.
    source_prefix:
        Yearly table family prefix, such as ``opprcd`` or ``secprd``. Static
        tables use their table name as the prefix.
    source_year:
        Four-digit source table year for yearly tables. Static tables use
        ``None``.
    load_group:
        Table family label used in logs and validation.
    layout:
        Physical layout rule used by ClickHouse.
    source_year_column:
        Added column for consolidated yearly tables. Other layouts use
        ``None``.
    source_columns:
        Explicit WRDS columns to download for this source table, in curated
        order. The loader selects these named columns instead of ``*``.
    """

    source_library: str
    source_table: str
    target_table: str
    source_prefix: str
    source_year: int | None
    load_group: str
    layout: str
    source_year_column: str | None
    source_columns: tuple[str, ...]

    @property
    def is_consolidated_year_table(self) -> bool:
        """Return whether this plan inserts into a multi-year target table."""

        return self.layout == "consolidated_year_table"


def build_table_plan_from_config(config: AppConfig) -> list[TablePlan]:
    """Build table plans for every table family enabled in ``config.toml``.

    Parameters
    ----------
    config:
        Parsed loader configuration. Disabled families have empty ``years`` or
        ``static_tables`` lists and are omitted automatically.

    Returns
    -------
    list[TablePlan]
        Ordered list of WRDS source tables to stream into ClickHouse.
    """

    return (
        _build_reference_plan(config)
        + _build_underlying_price_plan(config)
        + _build_option_price_plan(config)
    )


def _build_reference_plan(config: AppConfig) -> list[TablePlan]:
    """Build the static reference and CRSP-link load plan."""

    plan: list[TablePlan] = []
    for table in config.static_tables:
        plan.append(
            TablePlan(
                source_library=table.source_library,
                source_table=table.source_table,
                target_table=table.target_table,
                source_prefix=table.source_table,
                source_year=None,
                load_group=RUN_GROUP_REFERENCE,
                layout="single_table",
                source_year_column=None,
                source_columns=source_columns_for(table.source_table, table.source_table),
            )
        )
    return plan


def _build_underlying_price_plan(config: AppConfig) -> list[TablePlan]:
    """Build the consolidated underlying security price load plan."""

    plan: list[TablePlan] = []
    for year in config.underlying_prices.years:
        source_table = f"{config.underlying_prices.source_prefix}{year}"
        plan.append(
            TablePlan(
                source_library=config.underlying_prices.source_library,
                source_table=source_table,
                target_table=config.underlying_prices.target_table,
                source_prefix=config.underlying_prices.source_prefix,
                source_year=year,
                load_group=RUN_GROUP_UNDERLYING_PRICES,
                layout="consolidated_year_table",
                source_year_column=config.underlying_prices.source_year_column,
                source_columns=source_columns_for(
                    config.underlying_prices.source_prefix, source_table
                ),
            )
        )
    return plan


def _build_option_price_plan(config: AppConfig) -> list[TablePlan]:
    """Build the option-price load plan from configured years."""

    plan: list[TablePlan] = []
    for year in config.option_prices.years:
        source_table = f"{config.option_prices.source_prefix}{year}"
        target_table = config.option_prices.target_template.format(year=year)
        plan.append(
            TablePlan(
                source_library=config.option_prices.source_library,
                source_table=source_table,
                target_table=target_table,
                source_prefix=config.option_prices.source_prefix,
                source_year=year,
                load_group=RUN_GROUP_OPTION_PRICES,
                layout="separate_year_table",
                source_year_column=None,
                source_columns=source_columns_for(
                    config.option_prices.source_prefix, source_table
                ),
            )
        )
    return plan
