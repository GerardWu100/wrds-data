"""WRDS PostgreSQL chunked streaming helpers.

This module pulls one WRDS source table from PostgreSQL in bounded-memory
batches so even very large yearly option-price tables (hundreds of millions of
rows) can be loaded on a machine with far less RAM than the table size.

Why this matters
----------------
The ``wrds`` package's ``raw_sql(..., chunksize=N)`` runs
``pandas.read_sql_query`` against a SQLAlchemy connection that uses psycopg2's
*default client-side cursor*. A client-side cursor downloads the entire result
set into client memory during ``execute()``, before pandas can hand back the
first chunk. The ``chunksize`` argument then only limits how many rows are
turned into a DataFrame at a time; it does not limit the underlying transfer.

For ``optionm_all.opprcd2025`` (about 265 million rows, ~75 GB on disk) that
full client-side buffer is far larger than typical RAM, so the Linux
out-of-memory killer terminates the process with SIGKILL. Because SIGKILL is
not a Python exception, the loader's ``except`` blocks never run and no
``failed`` audit row is written: the run simply "takes forever and then dies".

The fix is a PostgreSQL *server-side cursor*. The result set stays on the WRDS
server and is streamed to the client in batches, so client memory stays
proportional to one chunk instead of the whole table.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from uuid import uuid4

import pandas as pd


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

    Returns
    -------
    str
        A ``SELECT <columns> FROM "<library>"."<table>"`` statement.
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
) -> Iterator[pd.DataFrame]:
    """Yield pandas DataFrame chunks from one WRDS source table.

    Rows are streamed through a PostgreSQL server-side cursor, so client memory
    stays bounded by ``chunksize`` rather than by the full table size.

    Parameters
    ----------
    wrds_connection:
        A live ``wrds.Connection``. Only its SQLAlchemy ``engine`` attribute is
        used here; a dedicated connection is opened for the streaming read so
        the connection shared by other loader steps is left untouched.
    source_library:
        WRDS PostgreSQL schema name, for example ``optionm_all``.
    source_table:
        WRDS PostgreSQL table name, for example ``opprcd2025``.
    columns:
        Explicit WRDS column names to download, in target-insert order.
    chunksize:
        Number of rows fetched from the server per DataFrame chunk. This bounds
        client memory: each yielded chunk holds at most ``chunksize`` rows.

    Yields
    ------
    pandas.DataFrame
        Successive row batches of the source table, each with ``columns`` as
        its columns and at most ``chunksize`` rows.
    """

    query = build_select_query(source_library, source_table, columns)

    if chunksize <= 0:
        raise ValueError("chunksize must be positive")

    # Use psycopg2's named cursor directly. A named cursor is PostgreSQL's
    # server-side cursor mechanism: ``execute`` declares the cursor on the
    # server, and each ``fetchmany`` pulls only the next bounded batch.
    pooled_connection = wrds_connection.engine.raw_connection()
    driver_connection = _unwrap_driver_connection(pooled_connection)
    original_autocommit = getattr(driver_connection, "autocommit", None)
    if original_autocommit is not None:
        driver_connection.autocommit = False

    cursor_name = f"ivydb_stream_{uuid4().hex}"
    cursor = driver_connection.cursor(name=cursor_name)
    cursor.itersize = chunksize
    try:
        cursor.execute(query)
        result_columns = [description[0] for description in cursor.description]
        while True:
            rows = cursor.fetchmany(chunksize)
            if not rows:
                break
            # Convert only the current DBAPI batch into pandas. Older batches
            # have already been inserted into ClickHouse and released.
            chunk = pd.DataFrame.from_records(rows, columns=result_columns)
            yield chunk
    finally:
        # Close the cursor and roll back the read-only transaction whether the
        # stream finished, raised, or the consumer stopped early.
        cursor.close()
        driver_connection.rollback()
        if original_autocommit is not None:
            driver_connection.autocommit = original_autocommit
        pooled_connection.close()


def _unwrap_driver_connection(pooled_connection: object) -> object:
    """Return the real DBAPI driver connection from SQLAlchemy's pool proxy.

    SQLAlchemy ``Engine.raw_connection()`` returns a pooled proxy object. Reads
    such as ``proxy.autocommit`` delegate to the underlying psycopg2 connection,
    but assignment can land on the proxy itself. Named cursors require the
    underlying psycopg2 connection to have ``autocommit = False``, so the loader
    must mutate the driver connection directly.

    Parameters
    ----------
    pooled_connection:
        Object returned by ``wrds_connection.engine.raw_connection()``.

    Returns
    -------
    object
        The underlying driver connection when SQLAlchemy exposes it, otherwise
        ``pooled_connection`` itself for simple fakes or direct DBAPI objects.
    """

    driver_connection = getattr(pooled_connection, "driver_connection", None)
    if driver_connection is not None:
        return driver_connection

    dbapi_connection = getattr(pooled_connection, "dbapi_connection", None)
    if dbapi_connection is not None:
        return dbapi_connection

    return pooled_connection
