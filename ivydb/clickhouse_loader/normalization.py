"""Validate and cast WRDS IvyDB chunks before ClickHouse insertion."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ivydb.clickhouse_loader.table_plan import TablePlan


@dataclass(frozen=True)
class UnsignedColumnRule:
    """Target unsigned-integer type for one semantically integral column."""

    column_name: str
    pandas_dtype: str
    maximum: int


UINT8_MAX = (2**8) - 1
UINT32_MAX = (2**32) - 1
UINT64_MAX = (2**64) - 1
# Widths mirror the curated ClickHouse DDL so out-of-range values are rejected
# at the chunk boundary instead of silently overflowing on insert. opprcd
# volume/open_interest are per-contract daily counts (UInt32), am_settlement is
# a 0/1 flag (UInt8), and optionid stays UInt64.
OPTION_UNSIGNED_RULES = (
    UnsignedColumnRule("secid", "UInt32", UINT32_MAX),
    UnsignedColumnRule("volume", "UInt32", UINT32_MAX),
    UnsignedColumnRule("open_interest", "UInt32", UINT32_MAX),
    UnsignedColumnRule("optionid", "UInt64", UINT64_MAX),
    UnsignedColumnRule("am_settlement", "UInt8", UINT8_MAX),
    UnsignedColumnRule("contract_size", "UInt32", UINT32_MAX),
)
SECURITY_PRICE_UNSIGNED_RULES = (
    UnsignedColumnRule("secid", "UInt32", UINT32_MAX),
    UnsignedColumnRule("volume", "UInt64", UINT64_MAX),
)
REFERENCE_UNSIGNED_COLUMNS = {
    "securd": (UnsignedColumnRule("secid", "UInt32", UINT32_MAX),),
    "secnmd": (UnsignedColumnRule("secid", "UInt32", UINT32_MAX),),
    "exchgd": (
        UnsignedColumnRule("secid", "UInt32", UINT32_MAX),
        UnsignedColumnRule("seq_num", "UInt32", UINT32_MAX),
    ),
    "distrd": (
        UnsignedColumnRule("secid", "UInt32", UINT32_MAX),
        UnsignedColumnRule("link_secid", "UInt32", UINT32_MAX),
        UnsignedColumnRule("seq_num", "UInt32", UINT32_MAX),
    ),
    "opinfd": (UnsignedColumnRule("secid", "UInt32", UINT32_MAX),),
    "opcrsphist": (
        UnsignedColumnRule("secid", "UInt32", UINT32_MAX),
        UnsignedColumnRule("permno", "UInt32", UINT32_MAX),
    ),
}
OPTION_DATE_COLUMNS = ("date", "exdate", "last_date")
SECURITY_PRICE_DATE_COLUMNS = ("date",)
REFERENCE_DATE_COLUMNS = {
    "secnmd": ("effect_date",),
    "exchgd": ("effect_date",),
    "distrd": ("record_date", "ex_date", "declare_date", "payment_date"),
    "opcrsphist": ("sdate", "edate"),
}
OPTION_ENUM_VALUES = {
    "cp_flag": {"C", "P"},
    "symbol_flag": {"0", "1"},
    "ss_flag": {"0", "1", "E"},
}
OPTION_BINARY_FLAG_COLUMNS = ("am_settlement",)


def normalize_batch_for_clickhouse(batch: pd.DataFrame, table: TablePlan) -> pd.DataFrame:
    """Return one validated chunk shaped for its curated ClickHouse table."""

    normalized = batch.copy()
    if table.is_consolidated_year_table:
        if table.source_year is None or table.source_year_column is None:
            raise ValueError("consolidated yearly tables need source-year metadata")
        normalized.insert(0, table.source_year_column, table.source_year)

    if table.source_prefix == "opprcd":
        _validate_enum_columns(normalized, OPTION_ENUM_VALUES)
        rules = OPTION_UNSIGNED_RULES
        date_columns = OPTION_DATE_COLUMNS
    elif table.source_prefix == "secprd":
        rules = SECURITY_PRICE_UNSIGNED_RULES
        date_columns = SECURITY_PRICE_DATE_COLUMNS
    else:
        rules = REFERENCE_UNSIGNED_COLUMNS.get(table.source_table, ())
        date_columns = REFERENCE_DATE_COLUMNS.get(table.source_table, ())

    for rule in rules:
        _cast_nullable_unsigned(normalized, rule)
    if table.source_prefix == "opprcd":
        for column_name in OPTION_BINARY_FLAG_COLUMNS:
            _validate_nullable_binary_flag(normalized, column_name)
    for column_name in date_columns:
        _cast_nullable_date(normalized, column_name)
    return normalized


def _cast_nullable_date(dataframe: pd.DataFrame, column_name: str) -> None:
    """Convert one nullable WRDS date column to Python ``date`` objects.

    Parameters
    ----------
    dataframe:
        Incoming WRDS chunk. The column is modified in place because the caller
        already owns a copied DataFrame.
    column_name:
        Column whose ClickHouse target type is ``Nullable(Date32)``.

    Notes
    -----
    WRDS PostgreSQL chunks may expose dates as ISO strings such as
    ``"2024-01-02"``. ``clickhouse-connect`` writes ``Date`` and ``Date32``
    values by subtracting a Python epoch date from each non-null value, so a
    raw string raises ``TypeError`` during insertion. The normalized shape after
    this function is an object column containing either ``datetime.date`` or
    ``None``.
    """

    if column_name not in dataframe.columns:
        return

    # ``to_datetime`` accepts existing date-like values and ISO date strings.
    # It preserves missing values as ``NaT`` so we can convert them back to the
    # explicit ``None`` values that ClickHouse treats as nullable entries.
    parsed_dates = pd.to_datetime(dataframe[column_name], errors="raise")
    python_dates = parsed_dates.dt.date.astype(object)
    dataframe[column_name] = python_dates.where(parsed_dates.notna(), None)


def _cast_nullable_unsigned(dataframe: pd.DataFrame, rule: UnsignedColumnRule) -> None:
    """Validate and cast one nullable identifier or count column in place."""

    if rule.column_name not in dataframe.columns:
        return
    observed = dataframe[rule.column_name].dropna()
    invalid = (
        (observed < 0)
        | (observed > rule.maximum)
        | ((observed % 1) != 0)
    )
    if invalid.any():
        raise ValueError(
            f"{rule.column_name} must contain whole non-negative values "
            f"no greater than {rule.maximum}"
        )
    dataframe[rule.column_name] = dataframe[rule.column_name].astype(rule.pandas_dtype)


def _validate_nullable_binary_flag(dataframe: pd.DataFrame, column_name: str) -> None:
    """Reject nullable flag values outside the documented ``0``/``1`` domain."""

    if column_name not in dataframe.columns:
        return

    observed = dataframe[column_name].dropna()
    invalid = ~observed.isin([0, 1])
    if invalid.any():
        raise ValueError(f"{column_name} must contain only documented 0/1 flag values")


def _validate_enum_columns(
    dataframe: pd.DataFrame,
    allowed_values_by_column: dict[str, set[str]],
) -> None:
    """Reject categorical values that do not fit curated enum definitions."""

    for column_name, allowed_values in allowed_values_by_column.items():
        if column_name not in dataframe.columns:
            continue
        observed = set(dataframe[column_name].dropna().astype(str))
        unexpected_values = observed - allowed_values
        if unexpected_values:
            raise ValueError(f"{column_name} contains unexpected values: {sorted(unexpected_values)}")
