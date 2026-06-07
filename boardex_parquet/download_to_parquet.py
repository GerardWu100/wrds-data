#!/usr/bin/env python3
"""Download WRDS BoardEx/CapIQ tables from PostgreSQL to Parquet files.

One Parquet file is written per table, named ``<library>__<table>.parquet``,
inside the configured output directory.

The module is driven entirely by ``config.toml``. The current default enables
three WRDS libraries and exports one explicit selected 35-table bundle. No data
is inserted into any local database.

Flow
----
1. Read ``config.toml`` for the library-selection rules and output settings.
2. Connect to WRDS using the project-level ``.pgpass`` file.
3. For each library and each selected table in that library:
   a. Open one streaming ``SELECT *`` query against WRDS.
   b. Read the result in chunked ``pandas`` DataFrames.
   c. Build a deterministic Arrow schema from live PostgreSQL metadata.
   d. Write each chunk directly into a temporary ``ParquetWriter``.
   e. Atomically move the temporary file into place after success.
   f. Collect only the first ``sample_csv_rows`` rows for an optional sample CSV.
4. Print a summary of every file written (path, rows, size).

Why this implementation changed
-------------------------------
The previous version paginated with ``LIMIT ... OFFSET ...`` and accumulated the
entire table in memory before writing one Parquet file. That approach is fragile
for multi-gigabyte text tables such as ``ciqpersonbiography`` because memory use
grows with the full table size and ``OFFSET`` gets slower as the offset grows.

The current version streams one SQL result, writes Parquet incrementally, and
uses a metadata-driven schema plus temporary-file promotion. That keeps peak
memory bounded by the chunk size, avoids first-batch schema drift on sparse
wide tables, and prevents ``--resume`` from trusting truncated outputs.

Run via ``cli.py``::

    uv run python boardex_parquet/cli.py                      # download all tables
    uv run python boardex_parquet/cli.py --dry-run            # show row counts only
    uv run python boardex_parquet/cli.py --library boardex_na # one library
    uv run python boardex_parquet/cli.py --table na_dir_profile_emp --library boardex_na
    uv run python boardex_parquet/cli.py --resume             # skip already-written files
"""

from __future__ import annotations

from collections.abc import Iterator
import os
import re
import sys
import time
import tomllib
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from catalog_exports.wrds_connection import connect_wrds

CONFIG_PATH = Path(__file__).resolve().parent / "config.toml"
PGPASS_PATH = PROJECT_ROOT / ".pgpass"

# Parquet compression to use.  "zstd" is a good default: fast decode, good ratio.
PARQUET_COMPRESSION = "zstd"
PARQUET_TEMP_SUFFIX = ".tmp"
LOG_BANNER_WIDTH = 60

DECIMAL_TYPE_PATTERN = re.compile(
    r"^(?:numeric|decimal)\((?P<precision>\d+),(?P<scale>\d+)\)$"
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def load_config(config_path: Path = CONFIG_PATH) -> dict:
    """Read config.toml and return the parsed dict."""
    with config_path.open("rb") as fh:
        return tomllib.load(fh)


def resolve_output_dir(cfg: dict, config_path: Path = CONFIG_PATH) -> Path:
    """Return the absolute path to the output directory, creating it if needed."""
    raw = cfg["loader"]["output_dir"]
    output_dir = (config_path.parent / raw).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def fetch_library_tables(wrds_db, library: str) -> list[str]:
    """Return all live base-table names for one WRDS library."""

    result = wrds_db.raw_sql(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %(library)s
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """,
        params={"library": library},
    )
    return result["table_name"].tolist()


def select_tables_from_library_config(
    available_tables: list[str],
    lib_cfg: dict,
    library_name: str | None = None,
) -> list[str]:
    """Resolve the selected tables for one library config block.

    Parameters
    ----------
    available_tables : list of str
        Live table names available in WRDS for this library.
    lib_cfg : dict
        Parsed config block for one library.
    library_name : str or None
        Library name used only for clearer warning and error messages.

    Returns
    -------
    list of str
        Selected table names in output order.
    """

    download_all_tables = bool(lib_cfg.get("download_all_tables", True))
    enabled_tables = list(lib_cfg.get("enabled_tables", []))
    disabled_tables = set(lib_cfg.get("disabled_tables", []))
    available_table_set = set(available_tables)

    unknown_enabled = sorted(set(enabled_tables) - available_table_set)
    if unknown_enabled:
        message = (
            "Config requested enabled tables that do not exist in the live "
            f"library: {unknown_enabled}"
        )
        raise ValueError(message)

    unknown_disabled = sorted(disabled_tables - available_table_set)
    if unknown_disabled:
        library_label = library_name or "<unknown>"
        _log(
            "  WARNING: ignoring stale disabled_tables entries for "
            f"{library_label}: {unknown_disabled}"
        )
        disabled_tables -= set(unknown_disabled)

    if download_all_tables:
        return [
            table_name
            for table_name in available_tables
            if table_name not in disabled_tables
        ]

    return [
        table_name for table_name in enabled_tables if table_name not in disabled_tables
    ]


def build_table_list(wrds_db, cfg: dict) -> list[tuple[str, str]]:
    """Return ``(library, table)`` pairs for all config-selected live tables."""

    pairs: list[tuple[str, str]] = []

    for library, lib_cfg in cfg.get("libraries", {}).items():
        if not bool(lib_cfg.get("enabled", True)):
            continue

        available_tables = fetch_library_tables(wrds_db, library)
        selected_tables = select_tables_from_library_config(
            available_tables=available_tables,
            lib_cfg=lib_cfg,
            library_name=library,
        )

        for table_name in selected_tables:
            pairs.append((library, table_name))

    return pairs


def parquet_path(output_dir: Path, library: str, table: str) -> Path:
    """Return the output path for a given library+table combination.

    Uses double underscore as separator to avoid clashing with table names
    that contain single underscores.
    """
    return output_dir / f"{library}__{table}.parquet"


def temporary_parquet_path(parquet_output_path: Path) -> Path:
    """Return the temporary output path used during one table write.

    Parameters
    ----------
    parquet_output_path : Path
        Final destination for the completed Parquet file.

    Returns
    -------
    Path
        Temporary path in the same directory so ``Path.replace`` is atomic on
        the same filesystem.
    """

    return parquet_output_path.with_suffix(
        f"{parquet_output_path.suffix}{PARQUET_TEMP_SUFFIX}"
    )


# ---------------------------------------------------------------------------
# WRDS helpers
# ---------------------------------------------------------------------------


def fetch_pg_row_count(wrds_db, library: str, table: str) -> int:
    """Return the fast approximate row count from pg_class (not an exact COUNT(*)).

    pg_class.reltuples is updated by ANALYZE and AUTOVACUUM.  On WRDS it is
    generally reliable for large tables.  Returns -1 if the table is not found.
    """
    result = wrds_db.raw_sql(
        """
        SELECT reltuples::bigint AS n
        FROM pg_class c
        JOIN pg_namespace ns ON ns.oid = c.relnamespace
        WHERE ns.nspname = %(library)s
          AND c.relname = %(table)s
        """,
        params={"library": library, "table": table},
    )
    if result.empty:
        return -1
    return int(result.iloc[0]["n"])


def build_select_query(library: str, table: str) -> str:
    """Return the plain ``SELECT *`` query used for chunked streaming.

    Notes
    -----
    We keep the query intentionally simple. One long-running ``SELECT`` gives a
    more stable snapshot than repeatedly issuing ``LIMIT ... OFFSET ...`` pages.
    """

    return f'SELECT * FROM "{library}"."{table}"'


def fetch_table_columns(wrds_db, library: str, table: str) -> list[dict[str, object]]:
    """Return live PostgreSQL column metadata for one WRDS table.

    The downloader needs the live type metadata so the Parquet schema is fixed
    before the first data batch arrives. That avoids the first-batch inference
    problem on sparse wide tables where an early chunk may contain only nulls.

    Parameters
    ----------
    wrds_db : wrds.Connection
        Open WRDS connection wrapper.
    library : str
        WRDS schema name.
    table : str
        WRDS table name.

    Returns
    -------
    list of dict
        Ordered metadata rows. Each row includes ``column_name``,
        ``data_type``, and ``nullable``.
    """

    result = wrds_db.raw_sql(
        """
        SELECT
            a.attname AS column_name,
            format_type(a.atttypid, a.atttypmod) AS data_type,
            NOT a.attnotnull AS nullable
        FROM pg_attribute a
        JOIN pg_class c
          ON c.oid = a.attrelid
        JOIN pg_namespace ns
          ON ns.oid = c.relnamespace
        WHERE ns.nspname = %(library)s
          AND c.relname = %(table)s
          AND a.attnum > 0
          AND NOT a.attisdropped
        ORDER BY a.attnum
        """,
        params={"library": library, "table": table},
    )
    return result.to_dict("records")


def postgres_type_to_arrow_type(data_type: str) -> pa.DataType:
    """Map one PostgreSQL type string into the corresponding Arrow type.

    Parameters
    ----------
    data_type : str
        PostgreSQL type as returned by ``format_type(...)``.

    Returns
    -------
    pyarrow.DataType
        Concrete Arrow type used for the Parquet schema.

    Raises
    ------
    ValueError
        If the type string is not one of the supported PostgreSQL types.
    """

    normalized_type = data_type.strip().lower()

    # PostgreSQL array types come through as "<element_type>[]".
    # Recursively map the element type, then wrap it as an Arrow list.
    if normalized_type.endswith("[]"):
        element_type = postgres_type_to_arrow_type(normalized_type[:-2])
        return pa.list_(element_type)

    if normalized_type in {"smallint", "int2"}:
        return pa.int16()
    if normalized_type in {"integer", "int", "int4"}:
        return pa.int32()
    if normalized_type in {"bigint", "int8"}:
        return pa.int64()
    if normalized_type in {"real", "float4"}:
        return pa.float32()
    if normalized_type in {"double precision", "float8"}:
        return pa.float64()
    if normalized_type in {"boolean", "bool"}:
        return pa.bool_()
    if normalized_type == "date":
        return pa.date32()
    if normalized_type == "timestamp without time zone":
        return pa.timestamp("ns")
    if normalized_type == "timestamp with time zone":
        return pa.timestamp("ns", tz="UTC")
    if normalized_type == "time without time zone":
        return pa.time64("us")
    if normalized_type == "bytea":
        return pa.binary()

    # Precision/scale numeric columns map directly to Arrow decimal types.
    decimal_match = DECIMAL_TYPE_PATTERN.match(normalized_type)
    if decimal_match:
        precision = int(decimal_match.group("precision"))
        scale = int(decimal_match.group("scale"))
        if precision <= 38:
            return pa.decimal128(precision, scale)
        return pa.decimal256(precision, scale)

    if normalized_type in {"numeric", "decimal"}:
        return pa.decimal256(76, 38)

    string_prefixes = (
        "character varying(",
        "varchar(",
        "character(",
        "char(",
    )
    string_types = {
        "text",
        "character varying",
        "varchar",
        "character",
        "char",
        "bpchar",
        "uuid",
        "xml",
        "json",
        "jsonb",
        "inet",
        "cidr",
        "macaddr",
        "macaddr8",
        "name",
        "time with time zone",
        "interval",
    }
    if normalized_type in string_types or normalized_type.startswith(string_prefixes):
        return pa.string()

    message = f"Unsupported PostgreSQL type for Arrow schema: {data_type}"
    raise ValueError(message)


def build_arrow_schema_from_columns(columns: list[dict[str, object]]) -> pa.Schema:
    """Build a deterministic Arrow schema from live PostgreSQL column metadata.

    Parameters
    ----------
    columns : list of dict
        Ordered column metadata rows from ``fetch_table_columns``.

    Returns
    -------
    pyarrow.Schema
        Fixed Arrow schema used for both the writer and every streamed batch.
    """

    fields: list[pa.Field] = []

    for column in columns:
        column_name = str(column["column_name"])
        data_type = str(column["data_type"])
        nullable = bool(column["nullable"])
        arrow_type = postgres_type_to_arrow_type(data_type)
        fields.append(pa.field(column_name, arrow_type, nullable=nullable))

    return pa.schema(fields)


def fetch_table_schema(wrds_db, library: str, table: str) -> pa.Schema:
    """Return the deterministic Arrow schema for one live WRDS table."""

    columns = fetch_table_columns(wrds_db, library, table)
    return build_arrow_schema_from_columns(columns)


def stream_table_batches(
    wrds_db,
    library: str,
    table: str,
    batch_size: int,
) -> Iterator[pd.DataFrame]:
    """Yield chunked DataFrames from one streaming SQL query.

    Parameters
    ----------
    wrds_db : wrds.Connection
        Open WRDS connection wrapper.
    library : str
        WRDS schema name.
    table : str
        WRDS table name.
    batch_size : int
        Number of rows per chunk requested from ``wrds.Connection.raw_sql``.

    Returns
    -------
    Iterator[pandas.DataFrame]
        Iterator of chunked ``pandas.DataFrame`` batches.
    """

    query = build_select_query(library, table)

    # Use WRDS's public chunked query API instead of reaching into the
    # SQLAlchemy connection internals. This avoids depending on the engine's
    # AUTOCOMMIT transaction behavior for chunk iteration.
    return wrds_db.raw_sql(
        query,
        chunksize=batch_size,
        return_iter=True,
    )


def dataframe_to_arrow_table(batch: pd.DataFrame, schema: pa.Schema) -> pa.Table:
    """Convert one streamed DataFrame batch into an Arrow table with fixed types.

    Parameters
    ----------
    batch : pandas.DataFrame
        One batch returned from the chunked SQL iterator.
    schema : pyarrow.Schema
        Deterministic output schema built from live PostgreSQL metadata.

    Returns
    -------
    pyarrow.Table
        Arrow table with exactly the declared field order and data types.
    """

    arrays: list[pa.Array] = []

    for field in schema:
        series = batch[field.name]
        normalized_series = normalize_series_for_arrow_type(series, field.type)

        try:
            arrays.append(
                pa.array(normalized_series, type=field.type, from_pandas=True)
            )
        except (pa.ArrowInvalid, pa.ArrowTypeError, pa.ArrowException) as exc:
            sample_values = series.dropna().head(5).tolist()
            message = (
                "Could not convert DataFrame column to declared Arrow type. "
                f"column={field.name!r}, arrow_type={field.type}, "
                f"pandas_dtype={series.dtype}, sample_values={sample_values}"
            )
            raise ValueError(message) from exc

    return pa.Table.from_arrays(arrays, schema=schema)


def normalize_series_for_arrow_type(
    series: pd.Series,
    arrow_type: pa.DataType,
) -> pd.Series:
    """Return a pandas Series that PyArrow can cast to the declared type.

    Parameters
    ----------
    series : pandas.Series
        One DataFrame column from WRDS.
    arrow_type : pyarrow.DataType
        The fixed Arrow type declared from live PostgreSQL metadata.

    Returns
    -------
    pandas.Series
        Original or normalized Series ready for ``pyarrow.array``.

    Notes
    -----
    WRDS sometimes returns PostgreSQL ``date`` columns as pandas string
    columns. PyArrow cannot directly cast string scalars into ``date32`` when a
    fixed date schema is supplied, so the downloader parses those values at the
    DataFrame/Arrow boundary.
    """

    if pa.types.is_date(arrow_type):
        parsed_values = [parse_wrds_date_value(value) for value in series]
        return pd.Series(parsed_values, index=series.index, dtype=object)

    return series


def parse_wrds_date_value(value: object) -> date | None:
    """Parse one WRDS date value without pandas timestamp bounds.

    Parameters
    ----------
    value : object
        Scalar value from a pandas Series. WRDS may provide Python date objects,
        pandas timestamps, strings such as ``"2005-12-01"``, or null values.

    Returns
    -------
    datetime.date or None
        Python date object suitable for Arrow ``date32`` conversion. Null-like
        values are returned as ``None`` so Arrow preserves missing data.

    Notes
    -----
    BoardEx uses far-future sentinel dates such as ``9000-01-01``. Those dates
    are valid PostgreSQL and Arrow dates, but they exceed pandas' nanosecond
    timestamp range. Parsing strings with ``date.fromisoformat`` avoids that
    pandas-only limit.
    """

    if pd.isna(value):
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    return date.fromisoformat(str(value))


def empty_table_from_schema(schema: pa.Schema) -> pa.Table:
    """Return an empty Arrow table with the declared output schema."""

    arrays = [pa.array([], type=field.type, from_pandas=True) for field in schema]
    return pa.Table.from_arrays(arrays, schema=schema)


def is_complete_parquet_file(path: Path) -> bool:
    """Return whether a path points to a readable complete Parquet file.

    Parameters
    ----------
    path : Path
        Candidate Parquet output file.

    Returns
    -------
    bool
        ``True`` when the file exists and the Parquet footer can be read.
    """

    if not path.exists() or path.stat().st_size == 0:
        return False

    try:
        pq.ParquetFile(path)
    except (OSError, pa.ArrowInvalid, pa.ArrowException):
        return False

    return True


# ---------------------------------------------------------------------------
# Core download
# ---------------------------------------------------------------------------


def _log(msg: str) -> None:
    ts = datetime.now(UTC).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def download_table(
    wrds_db,
    cfg: dict,
    library: str,
    table: str,
    output_dir: Path,
    *,
    dry_run: bool = False,
    resume: bool = False,
) -> int:
    """Download one WRDS table and write it as a Parquet file.

    Parameters
    ----------
    wrds_db : wrds.Connection
        Open WRDS connection.
    cfg : dict
        Parsed config.toml.
    library : str
        WRDS library name (PostgreSQL schema).
    table : str
        Table name within the library.
    output_dir : Path
        Directory where .parquet (and sample .csv) files are written.
    dry_run : bool
        If True, only print the estimated row count and return 0.
    resume : bool
        If True, skip tables whose Parquet file already exists.

    Returns
    -------
    int
        Number of rows written (0 for dry_run or skipped).
    """
    # Resolve the final and temporary output paths once so every branch uses
    # the same file targets.
    out_path = parquet_path(output_dir, library, table)
    temp_path = temporary_parquet_path(out_path)
    batch_size = cfg["loader"]["batch_size"]
    sample_rows = cfg["loader"]["sample_csv_rows"]

    _log(f"--- {library}.{table} ---")

    # Resume mode should only trust completed Parquet files. A truncated file
    # from an interrupted run must be overwritten instead of silently skipped.
    if resume and out_path.exists():
        if is_complete_parquet_file(out_path):
            size_mb = out_path.stat().st_size / 1024**2
            _log(f"  SKIP (already exists: {out_path.name}, {size_mb:.1f} MiB)")
            return 0

        _log(
            "  WARNING: existing output is not a valid Parquet file and will "
            "be replaced."
        )
        out_path.unlink()

    if temp_path.exists():
        _log(
            "  WARNING: removing stale temporary output left by a prior "
            "interrupted run."
        )
        temp_path.unlink()

    # Show the approximate table size up front so dry runs still report work.
    est_rows = fetch_pg_row_count(wrds_db, library, table)
    _log(f"  Estimated rows : {est_rows:,}")

    if dry_run:
        _log("  [DRY RUN] Skipping download.")
        return 0

    # Stream one SQL result and write each chunk directly into Parquet. This
    # keeps peak memory proportional to ``batch_size`` instead of table size.
    total_rows = 0
    t0 = time.monotonic()
    sample_chunks: list[pd.DataFrame] = []
    remaining_sample_rows = sample_rows
    saw_non_empty_batch = False
    schema = fetch_table_schema(wrds_db, library, table)

    try:
        with pq.ParquetWriter(
            where=temp_path,
            schema=schema,
            compression=PARQUET_COMPRESSION,
        ) as parquet_writer:
            for batch in stream_table_batches(wrds_db, library, table, batch_size):
                if batch.empty:
                    continue

                saw_non_empty_batch = True

                # Keep just enough rows for the optional sample CSV instead of
                # carrying every batch in memory.
                if remaining_sample_rows > 0:
                    sample_batch = batch.head(remaining_sample_rows).copy()
                    sample_chunks.append(sample_batch)
                    remaining_sample_rows -= len(sample_batch)

                arrow_table = dataframe_to_arrow_table(batch, schema)
                parquet_writer.write_table(arrow_table)
                total_rows += len(batch)

                elapsed = time.monotonic() - t0
                rate = total_rows / elapsed if elapsed > 0 else 0
                _log(f"  {total_rows:,} rows so far ({rate:,.0f} rows/s)")

            # Preserve existing behavior: if the query returns no rows, still
            # write an empty Parquet file with the correct schema.
            if not saw_non_empty_batch:
                _log("  WARNING: zero rows returned. Writing empty Parquet file.")
                parquet_writer.write_table(empty_table_from_schema(schema))
    except Exception:
        # Never leave partial files behind after an interrupted write.
        if temp_path.exists():
            temp_path.unlink()
        raise

    temp_path.replace(out_path)

    file_size_mib = out_path.stat().st_size / 1024**2
    elapsed_total = time.monotonic() - t0
    _log(
        f"  Written: {out_path.name}  ({total_rows:,} rows, {file_size_mib:.1f} MiB, {elapsed_total:.1f}s)"
    )

    # Optionally write a sample CSV.
    if sample_rows > 0 and sample_chunks:
        sample_path = output_dir / f"{library}__{table}__sample.csv"
        sample_df = pd.concat(sample_chunks, ignore_index=True)
        sample_df.to_csv(sample_path, index=False)
        _log(f"  Sample CSV: {sample_path.name} ({len(sample_df)} rows)")

    return total_rows


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run(
    config_path: Path = CONFIG_PATH,
    *,
    dry_run: bool = False,
    resume: bool = False,
    filter_library: str | None = None,
    filter_table: str | None = None,
) -> None:
    """Download all configured tables from WRDS to Parquet.

    Parameters
    ----------
    config_path : Path
        Path to config.toml.
    dry_run : bool
        If True, print row counts but do not write any files.
    resume : bool
        If True, skip tables whose Parquet file already exists in output_dir.
    filter_library : str or None
        If provided, only process this library.
    filter_table : str or None
        If provided (with filter_library), only process this one table.
    """
    cfg = load_config(config_path)
    output_dir = resolve_output_dir(cfg, config_path)

    _log("=" * LOG_BANNER_WIDTH)
    _log("BoardEx OSINT -> Parquet downloader")
    _log(f"  Output dir : {output_dir}")
    _log(f"  Batch size : {cfg['loader']['batch_size']:,}")
    _log(f"  Compression: {PARQUET_COMPRESSION}")
    if dry_run:
        _log("  Mode       : DRY RUN (no files written)")
    elif resume:
        _log("  Mode       : RESUME (skip existing files)")
    _log("=" * LOG_BANNER_WIDTH)

    os.environ["PGPASSFILE"] = str(PGPASS_PATH)
    _log("Connecting to WRDS ...")
    wrds_db = connect_wrds()

    total_rows = 0
    t0 = time.monotonic()

    try:
        all_tables = build_table_list(wrds_db, cfg)

        # Apply optional library/table filters after resolving the live,
        # config-selected table set.
        if filter_library:
            filtered_tables: list[tuple[str, str]] = []

            # Filter in explicit steps so the selection logic is easy to read
            # and modify.
            for library_name, table_name in all_tables:
                if library_name != filter_library:
                    continue
                if filter_table is not None and table_name != filter_table:
                    continue
                filtered_tables.append((library_name, table_name))

            all_tables = filtered_tables

            if not all_tables:
                print(
                    "ERROR: No matching tables found for "
                    f"library={filter_library!r}, table={filter_table!r}"
                )
                sys.exit(1)

        _log(f"  Tables     : {len(all_tables)}")

        for library, table in all_tables:
            total_rows += download_table(
                wrds_db=wrds_db,
                cfg=cfg,
                library=library,
                table=table,
                output_dir=output_dir,
                dry_run=dry_run,
                resume=resume,
            )
    finally:
        wrds_db.close()

    _log("=" * LOG_BANNER_WIDTH)
    _log(f"All done: {total_rows:,} rows in {time.monotonic() - t0:.1f}s")
    if not dry_run:
        _log(f"Files in: {output_dir}")
        written = sorted(output_dir.glob("*.parquet"))
        for f in written:
            _log(f"  {f.name}  ({f.stat().st_size / 1024**2:.1f} MiB)")
    _log("=" * LOG_BANNER_WIDTH)


if __name__ == "__main__":
    run()
