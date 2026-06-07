"""WRDS PostgreSQL chunked streaming helpers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def build_select_query(
    source_library: str,
    source_table: str,
    columns: Sequence[str],
) -> str:
    """Build an explicit-column PostgreSQL query for one quoted WRDS table.

    Parameters
    ----------
    source_library:
        WRDS PostgreSQL schema name, for example ``optionm_all``.
    source_table:
        WRDS PostgreSQL table name, for example ``opprcd2024``.
    columns:
        Explicit WRDS column names to download. Selecting named columns instead
        of ``*`` keeps the download set a reviewed contract and avoids breaking
        the ClickHouse insert if WRDS adds an unrelated column later.
    """

    if not columns:
        raise ValueError(f"no columns requested for {source_library}.{source_table}")
    column_list = ", ".join(f'"{column}"' for column in columns)
    return f'SELECT {column_list} FROM "{source_library}"."{source_table}"'


def stream_table(
    wrds_connection: object,
    source_library: str,
    source_table: str,
    columns: Sequence[str],
    chunksize: int,
) -> Iterable[object]:
    """Yield pandas DataFrame chunks from one WRDS source table."""

    query = build_select_query(source_library, source_table, columns)
    return wrds_connection.raw_sql(query, chunksize=chunksize, return_iter=True)
