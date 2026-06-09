"""Validate and cast WRDS IvyDB chunks before ClickHouse insertion."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

import pandas as pd

from ivydb.clickhouse_loader.table_plan import TablePlan


@dataclass(frozen=True)
class UnsignedColumnRule:
    """Target unsigned-integer type for one semantically integral column."""

    column_name: str
    pandas_dtype: str
    maximum: int


@dataclass(frozen=True)
class SignedColumnRule:
    """Target signed-integer type for one semantically integral column."""

    column_name: str
    pandas_dtype: str
    minimum: int
    maximum: int


UINT8_MAX = (2**8) - 1
INT32_MIN = -(2**31)
INT32_MAX = (2**31) - 1
UINT32_MAX = (2**32) - 1
UINT64_MAX = (2**64) - 1
# Widths mirror the curated ClickHouse DDL so out-of-range values are rejected
# at the chunk boundary instead of silently overflowing on insert. opprcd
# volume/open_interest are per-contract daily counts (UInt32), am_settlement is
# a 0/1 flag (UInt8), optionid stays UInt64, and contract_size is signed because
# WRDS uses -99 as an OptionMetrics missing-value sentinel.
OPTION_UNSIGNED_RULES = (
    UnsignedColumnRule("secid", "UInt32", UINT32_MAX),
    UnsignedColumnRule("volume", "UInt32", UINT32_MAX),
    UnsignedColumnRule("open_interest", "UInt32", UINT32_MAX),
    UnsignedColumnRule("optionid", "UInt64", UINT64_MAX),
    UnsignedColumnRule("am_settlement", "UInt8", UINT8_MAX),
)
OPTION_SIGNED_RULES = (
    SignedColumnRule("contract_size", "Int32", INT32_MIN, INT32_MAX),
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
# impl_volatility and the four Greeks carry exactly 6 decimal places at the WRDS
# source. The curated ClickHouse schema stores them as fixed-point Decimal(6)
# (delta/gamma/vega/impl_volatility -> Decimal32(6); theta -> Decimal64(6)) to
# remove Float32 mantissa noise and compress ~10% smaller. We convert the source
# double straight to a 6-place Decimal here so the stored value is bit-exact to
# the source grid, rather than letting it round-trip through Float32 first.
OPTION_DECIMAL_COLUMNS = ("impl_volatility", "delta", "gamma", "vega", "theta")
OPTION_DECIMAL_SCALE = 6


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
        signed_rules = OPTION_SIGNED_RULES
        date_columns = OPTION_DATE_COLUMNS
    elif table.source_prefix == "secprd":
        rules = SECURITY_PRICE_UNSIGNED_RULES
        signed_rules = ()
        date_columns = SECURITY_PRICE_DATE_COLUMNS
    else:
        rules = REFERENCE_UNSIGNED_COLUMNS.get(table.source_table, ())
        signed_rules = ()
        date_columns = REFERENCE_DATE_COLUMNS.get(table.source_table, ())

    for rule in rules:
        _cast_nullable_unsigned(normalized, rule)
    for rule in signed_rules:
        _cast_nullable_signed(normalized, rule)
    if table.source_prefix == "opprcd":
        for column_name in OPTION_BINARY_FLAG_COLUMNS:
            _validate_nullable_binary_flag(normalized, column_name)
        for column_name in OPTION_DECIMAL_COLUMNS:
            _cast_nullable_decimal(normalized, column_name, OPTION_DECIMAL_SCALE)
    for column_name in date_columns:
        _cast_nullable_date(normalized, column_name)
    return normalized


def _cast_nullable_decimal(dataframe: pd.DataFrame, column_name: str, scale: int) -> None:
    """Convert one nullable float column to exact fixed-point ``Decimal`` in place.

    Parameters
    ----------
    dataframe:
        Incoming WRDS chunk. The column is modified in place because the caller
        already owns a copied DataFrame.
    column_name:
        Column whose ClickHouse target type is ``Nullable(Decimal32(scale))`` or
        ``Nullable(Decimal64(scale))``.
    scale:
        Number of decimal places to keep (6 for IvyDB implied volatility/Greeks).

    Notes
    -----
    WRDS exposes these columns as PostgreSQL ``double precision`` (pandas
    ``float64``). The source values live on a 6-decimal grid, but a binary float
    only approximates them. We quantize each value to ``scale`` decimal places so
    the stored ``Decimal`` is exact to that grid, and map missing values to
    ``None`` so ClickHouse treats them as nullable entries. ``clickhouse-connect``
    writes Decimal columns from Python ``decimal.Decimal`` objects, so the
    normalized column is an object column of ``Decimal`` or ``None``.
    """

    if column_name not in dataframe.columns:
        return

    # ``quantum`` is the smallest representable step, e.g. Decimal('0.000001').
    # ROUND_HALF_EVEN (banker's rounding) matches IEEE float rounding and only
    # ever triggers for the rare source value that is not already on the grid.
    quantum = Decimal(1).scaleb(-scale)

    def to_decimal(value: object) -> Decimal | None:
        if pd.isna(value):
            return None
        return Decimal(float(value)).quantize(quantum, rounding=ROUND_HALF_EVEN)

    dataframe[column_name] = dataframe[column_name].map(to_decimal).astype(object)


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


def _cast_nullable_signed(dataframe: pd.DataFrame, rule: SignedColumnRule) -> None:
    """Validate and cast one nullable signed identifier or count column in place."""

    if rule.column_name not in dataframe.columns:
        return

    observed = dataframe[rule.column_name].dropna()
    invalid = (
        (observed < rule.minimum)
        | (observed > rule.maximum)
        | ((observed % 1) != 0)
    )
    if invalid.any():
        raise ValueError(
            f"{rule.column_name} must contain whole values between "
            f"{rule.minimum} and {rule.maximum}"
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
