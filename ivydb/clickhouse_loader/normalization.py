"""Validate and cast WRDS IvyDB chunks before ClickHouse insertion."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

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


@dataclass(frozen=True)
class DecimalColumnRule:
    """Target fixed-point decimal type for one six-decimal model column."""

    column_name: str
    type_name: str
    scale: int
    quantum: Decimal
    minimum: Decimal
    maximum: Decimal


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
OPTION_DECIMAL_SCALE = 6
OPTION_DECIMAL_QUANTUM = Decimal("0.000001")
OPTION_DECIMAL32_MAX = Decimal("2147.483647")
OPTION_DECIMAL32_MIN = Decimal("-2147.483648")
OPTION_DECIMAL64_MAX = Decimal("9223372036854.775807")
OPTION_DECIMAL64_MIN = Decimal("-9223372036854.775808")
OPTION_DECIMAL_RULES = (
    DecimalColumnRule(
        "impl_volatility",
        "Decimal32",
        OPTION_DECIMAL_SCALE,
        OPTION_DECIMAL_QUANTUM,
        OPTION_DECIMAL32_MIN,
        OPTION_DECIMAL32_MAX,
    ),
    DecimalColumnRule(
        "delta",
        "Decimal32",
        OPTION_DECIMAL_SCALE,
        OPTION_DECIMAL_QUANTUM,
        OPTION_DECIMAL32_MIN,
        OPTION_DECIMAL32_MAX,
    ),
    DecimalColumnRule(
        "gamma",
        "Decimal32",
        OPTION_DECIMAL_SCALE,
        OPTION_DECIMAL_QUANTUM,
        OPTION_DECIMAL32_MIN,
        OPTION_DECIMAL32_MAX,
    ),
    DecimalColumnRule(
        "vega",
        "Decimal64",
        OPTION_DECIMAL_SCALE,
        OPTION_DECIMAL_QUANTUM,
        OPTION_DECIMAL64_MIN,
        OPTION_DECIMAL64_MAX,
    ),
    DecimalColumnRule(
        "theta",
        "Decimal64",
        OPTION_DECIMAL_SCALE,
        OPTION_DECIMAL_QUANTUM,
        OPTION_DECIMAL64_MIN,
        OPTION_DECIMAL64_MAX,
    ),
)


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
        for rule in OPTION_DECIMAL_RULES:
            _cast_nullable_decimal_scaled(normalized, rule)
    for column_name in date_columns:
        _cast_nullable_date(normalized, column_name)
    return normalized


def _cast_nullable_decimal_scaled(dataframe: pd.DataFrame, rule: DecimalColumnRule) -> None:
    """Convert one nullable six-decimal option model column to fixed point.

    Parameters
    ----------
    dataframe:
        Incoming WRDS chunk. The column is modified in place because the caller
        already owns a copied DataFrame.
    rule:
        Decimal type, scale, and range expected by the curated ClickHouse DDL.

    Notes
    -----
    The WRDS source exposes these columns as PostgreSQL ``double precision``,
    but the values are six-decimal model outputs. Converting through
    ``str(value)`` avoids carrying binary floating-point artifacts such as
    ``0.12345600128173828`` into the fixed-point representation. Vega and theta
    use ``Decimal64(6)`` instead of ``Decimal32(6)`` because recent years exceed
    the narrower Decimal32 range.
    """

    column_name = rule.column_name
    if column_name not in dataframe.columns:
        return

    converted_values: list[Decimal | None] = []
    for raw_value in dataframe[column_name]:
        if pd.isna(raw_value):
            converted_values.append(None)
            continue

        try:
            decimal_value = Decimal(str(raw_value)).quantize(rule.quantum)
        except (InvalidOperation, ValueError) as error:
            raise ValueError(
                f"{column_name} must contain values convertible to "
                f"{rule.type_name}({rule.scale})"
            ) from error

        if decimal_value < rule.minimum or decimal_value > rule.maximum:
            raise ValueError(
                f"{column_name} must fit {rule.type_name}({rule.scale}) range "
                f"{rule.minimum} to {rule.maximum}"
            )

        converted_values.append(decimal_value)

    dataframe[column_name] = pd.Series(converted_values, index=dataframe.index, dtype="object")

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
