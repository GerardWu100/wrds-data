"""Explicit WRDS source-column lists for each IvyDB target family.

Why this module exists
----------------------
The loader previously issued ``SELECT *`` against each WRDS table. That made the
download an implicit copy of whatever columns WRDS happens to expose, and it
would break the ClickHouse insert if WRDS ever added a column. This module makes
the downloaded column set an explicit, reviewed contract that mirrors the
curated ClickHouse DDL.

Each list is the exact set of WRDS PostgreSQL columns the loader pulls, in the
same order as the curated ClickHouse table. The ClickHouse insert matches by
column name, so order is not load-critical, but keeping the lists aligned with
the DDL keeps the two contracts readable side by side.

Notable selection decisions
---------------------------
``opprcd`` deliberately omits three WRDS columns:

- ``forward_price``: OptionMetrics moved forward price into the separate
  ``fwdprd`` file in manual version 5.0, and a live 2023 sample showed the
  ``opprcd`` ``forward_price`` column is 0% populated.
- ``root`` and ``suffix``: the 2010 OptionMetrics OSI (Options Symbology
  Initiative) revision replaced these legacy fields with ``symbol`` +
  ``symbol_flag``. For 1996-2010 rows ``symbol`` equals ``root || '.' || suffix``
  exactly (verified 100% reconstructable across sampled years), and from 2011 on
  ``root``/``suffix`` are empty while ``symbol`` is always populated. So they
  carry no information beyond ``symbol`` and are dropped from both the download
  query and the ClickHouse schema; if ever needed for a legacy tool they are
  recoverable as ``splitByChar('.', symbol)``.

Storing any of the three only adds always-null or fully redundant columns.
"""

from __future__ import annotations

# opprcd: 26 WRDS columns minus forward_price (always null) and the legacy
# root/suffix pair (redundant with symbol/symbol_flag) -> 23 columns.
OPTION_PRICE_SOURCE_COLUMNS: tuple[str, ...] = (
    "secid", "date", "symbol", "symbol_flag", "exdate", "last_date", "cp_flag",
    "strike_price", "best_bid", "best_offer", "volume", "open_interest",
    "impl_volatility", "delta", "gamma", "vega", "theta", "optionid", "cfadj",
    "am_settlement", "contract_size", "ss_flag", "expiry_indicator",
)

# secprd: the 11 WRDS columns. The ClickHouse source_year column is added during
# normalization, so it is intentionally absent from the download list.
SECURITY_PRICE_SOURCE_COLUMNS: tuple[str, ...] = (
    "secid", "date", "low", "high", "close", "volume", "return", "cfadj",
    "open", "cfret", "shrout",
)

# One full-column list for each static reference / CRSP-link source table.
REFERENCE_SOURCE_COLUMNS: dict[str, tuple[str, ...]] = {
    "securd": (
        "secid", "cusip", "ticker", "sic", "index_flag", "exchange_d", "class",
        "issue_type", "industry_group",
    ),
    "secnmd": (
        "secid", "effect_date", "cusip", "ticker", "class", "issuer", "issue",
        "sic",
    ),
    "exchgd": (
        "secid", "effect_date", "seq_num", "status", "exchange", "add_del",
        "exch_flag",
    ),
    "distrd": (
        "secid", "record_date", "seq_num", "ex_date", "amount", "adj_factor",
        "declare_date", "payment_date", "link_secid", "distr_type", "frequency",
        "currency", "approx_flag", "cancel_flag", "liquid_flag",
    ),
    "opinfd": ("secid", "div_convention", "exercise_style", "am_set_flag"),
    "opcrsphist": ("secid", "sdate", "edate", "permno", "score"),
}


def source_columns_for(source_prefix: str, source_table: str) -> tuple[str, ...]:
    """Return the explicit WRDS columns to download for one source table.

    Parameters
    ----------
    source_prefix:
        Yearly family prefix (``opprcd`` or ``secprd``) or, for static tables,
        the table name itself.
    source_table:
        Concrete WRDS table name. Used to look up static reference tables.

    Returns
    -------
    tuple[str, ...]
        Ordered WRDS column names for the ``SELECT`` list.

    Raises
    ------
    ValueError
        If the source table has no registered column contract.
    """

    if source_prefix == "opprcd":
        return OPTION_PRICE_SOURCE_COLUMNS
    if source_prefix == "secprd":
        return SECURITY_PRICE_SOURCE_COLUMNS
    if source_table in REFERENCE_SOURCE_COLUMNS:
        return REFERENCE_SOURCE_COLUMNS[source_table]
    supported = ", ".join(["opprcd", "secprd", *sorted(REFERENCE_SOURCE_COLUMNS)])
    raise ValueError(
        f"no source-column contract for {source_table!r} (prefix {source_prefix!r}); "
        f"supported: {supported}"
    )
