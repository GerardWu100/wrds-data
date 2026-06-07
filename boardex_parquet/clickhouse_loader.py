"""Load local BoardEx Parquet pocket files into ClickHouse.

The loader treats the audited Parquet files in ``boardex_parquet/outputs`` as
the source of truth. It creates one ClickHouse table per Parquet file, streams
Arrow record batches into that table, and can validate ClickHouse row counts
against the local Parquet footers after loading.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse
import re
import tomllib

import clickhouse_connect
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DEFAULT_INSERT_BATCH_ROWS = 100_000


@dataclass(frozen=True)
class ClickHouseConfig:
    """Connection settings for the target ClickHouse database.

    Parameters
    ----------
    host:
        Host name or HTTP(S) URL for the ClickHouse server.
    port:
        HTTP interface port used by ``clickhouse-connect``.
    username:
        ClickHouse user name.
    password:
        ClickHouse password. An empty password is allowed for local servers.
    secure:
        Whether to use HTTPS/TLS when ``host`` is not already a URL.
    database:
        ClickHouse database that receives the BoardEx tables.
    """

    host: str
    port: int
    username: str
    password: str
    secure: bool
    database: str


@dataclass(frozen=True)
class LoaderConfig:
    """Runtime settings for Parquet-to-ClickHouse loading.

    Parameters
    ----------
    parquet_dir:
        Directory containing ``<library>__<table>.parquet`` files.
    insert_batch_rows:
        Maximum Arrow rows inserted into ClickHouse per request.
    create_database:
        Whether the loader should create the target database if missing.
    replace:
        Whether an existing target table should be dropped and rebuilt.
    resume:
        Whether tables already loaded with matching row counts should be skipped.
    """

    parquet_dir: Path
    insert_batch_rows: int
    create_database: bool
    replace: bool
    resume: bool


@dataclass(frozen=True)
class AppConfig:
    """Full configuration for the BoardEx ClickHouse loader."""

    clickhouse: ClickHouseConfig
    loader: LoaderConfig


@dataclass(frozen=True)
class TableLoadPlan:
    """One local Parquet file and its target ClickHouse table."""

    source_path: Path
    target_table: str
    row_count: int


@dataclass(frozen=True)
class LoadResult:
    """Summary for one loaded or skipped table."""

    source_path: Path
    target_table: str
    parquet_rows: int
    clickhouse_rows: int
    status: str


def default_config_path() -> Path:
    """Return the package-local ClickHouse loader configuration path."""

    return Path(__file__).resolve().parent / "clickhouse_config.toml"


def load_config(path: Path) -> AppConfig:
    """Read and validate the TOML configuration file.

    Parameters
    ----------
    path:
        TOML file with ``[clickhouse]`` and ``[loader]`` sections.

    Returns
    -------
    AppConfig
        Typed configuration used by the loader and command-line interface.
    """

    with path.open("rb") as config_file:
        raw_config = tomllib.load(config_file)

    clickhouse = _parse_clickhouse_config(raw_config["clickhouse"])
    loader = _parse_loader_config(raw_config["loader"], path.parent)

    return AppConfig(clickhouse=clickhouse, loader=loader)


def discover_parquet_files(parquet_dir: Path) -> list[TableLoadPlan]:
    """Return sorted load plans for every Parquet pocket file in a directory.

    File names are expected to use the downloader convention
    ``<wrds_library>__<wrds_table>.parquet``. The ClickHouse table name uses
    the same stem, so provenance remains visible after ingestion.
    """

    if not parquet_dir.exists():
        raise FileNotFoundError(f"Parquet directory does not exist: {parquet_dir}")

    plans: list[TableLoadPlan] = []
    for source_path in sorted(parquet_dir.glob("*.parquet")):
        target_table = _validated_identifier(source_path.stem, "target table")
        row_count = pq.ParquetFile(source_path).metadata.num_rows
        plans.append(
            TableLoadPlan(
                source_path=source_path,
                target_table=target_table,
                row_count=row_count,
            )
        )

    if not plans:
        raise FileNotFoundError(f"No .parquet files found in {parquet_dir}")
    return plans


def arrow_schema_to_clickhouse_columns(schema: pa.Schema) -> list[tuple[str, str]]:
    """Convert an Arrow schema from a Parquet footer into ClickHouse columns."""

    columns: list[tuple[str, str]] = []
    for field in schema:
        column_name = _validated_identifier(field.name, "column")
        base_type = arrow_type_to_clickhouse(field.type)
        if field.nullable:
            column_type = f"Nullable({base_type})"
        else:
            column_type = base_type
        columns.append((column_name, column_type))
    return columns


def arrow_type_to_clickhouse(arrow_type: pa.DataType) -> str:
    """Map the Arrow types used by BoardEx Parquet files to ClickHouse types."""

    if pa.types.is_boolean(arrow_type):
        return "Bool"
    if pa.types.is_int8(arrow_type):
        return "Int8"
    if pa.types.is_int16(arrow_type):
        return "Int16"
    if pa.types.is_int32(arrow_type):
        return "Int32"
    if pa.types.is_int64(arrow_type):
        return "Int64"
    if pa.types.is_uint8(arrow_type):
        return "UInt8"
    if pa.types.is_uint16(arrow_type):
        return "UInt16"
    if pa.types.is_uint32(arrow_type):
        return "UInt32"
    if pa.types.is_uint64(arrow_type):
        return "UInt64"
    if pa.types.is_float16(arrow_type) or pa.types.is_float32(arrow_type):
        return "Float32"
    if pa.types.is_float64(arrow_type):
        return "Float64"
    if pa.types.is_date32(arrow_type):
        # BoardEx uses far-future sentinel dates such as 9000-01-01. ClickHouse
        # Date32 cannot store that range safely, so dates load as strings while
        # preserving the original ISO format.
        return "String"
    if pa.types.is_date64(arrow_type):
        return "DateTime64(3)"
    if pa.types.is_timestamp(arrow_type):
        scale = _timestamp_scale(arrow_type.unit)
        return f"DateTime64({scale})"
    if pa.types.is_decimal(arrow_type):
        return f"Decimal({arrow_type.precision}, {arrow_type.scale})"
    if pa.types.is_string(arrow_type) or pa.types.is_large_string(arrow_type):
        return "String"
    if pa.types.is_binary(arrow_type) or pa.types.is_large_binary(arrow_type):
        return "String"
    if pa.types.is_null(arrow_type):
        return "String"

    raise TypeError(f"Unsupported Arrow type for ClickHouse load: {arrow_type}")


def create_table_sql(database: str, table: str, schema: pa.Schema) -> str:
    """Build a ``CREATE TABLE`` statement for one Parquet-backed table."""

    db_name = _validated_identifier(database, "database")
    table_name = _validated_identifier(table, "table")
    column_sql = ",\n  ".join(
        f"{_quote_identifier(name)} {column_type}"
        for name, column_type in arrow_schema_to_clickhouse_columns(schema)
    )
    order_by = _order_by_expression(schema)
    nullable_key_setting = _nullable_key_setting(schema)

    return (
        f"CREATE TABLE IF NOT EXISTS {_quote_identifier(db_name)}.{_quote_identifier(table_name)} (\n"
        f"  {column_sql}\n"
        ")\n"
        "ENGINE = MergeTree\n"
        f"ORDER BY {order_by}"
        f"{nullable_key_setting}"
    )


def create_client(config: ClickHouseConfig) -> object:
    """Create a ``clickhouse-connect`` client from loader configuration."""

    host, secure = _normalize_host_and_secure(config.host, config.secure)
    return clickhouse_connect.get_client(
        host=host,
        port=config.port,
        username=config.username,
        password=config.password,
        secure=secure,
        database=config.database,
    )


def ensure_database(client: object, database: str) -> None:
    """Create the ClickHouse database when it does not already exist."""

    db_name = _validated_identifier(database, "database")
    client.command(f"CREATE DATABASE IF NOT EXISTS {_quote_identifier(db_name)}")


def load_tables(config: AppConfig, client: object, table_filter: str | None = None) -> list[LoadResult]:
    """Load selected local Parquet files into ClickHouse.

    The load is idempotent when ``resume`` is enabled and the target table row
    count already matches the Parquet footer. Existing non-matching tables are
    rejected unless ``replace`` is enabled, which drops and recreates the table.
    """

    plans = _filtered_plans(
        plans=discover_parquet_files(config.loader.parquet_dir),
        table_filter=table_filter,
    )
    results: list[LoadResult] = []

    for plan in plans:
        parquet_file = pq.ParquetFile(plan.source_path)
        schema = parquet_file.schema_arrow
        table_exists_now = table_exists(client, config.clickhouse.database, plan.target_table)

        if table_exists_now and config.loader.resume:
            current_rows = count_rows(client, config.clickhouse.database, plan.target_table)
            if current_rows == plan.row_count:
                results.append(
                    LoadResult(
                        source_path=plan.source_path,
                        target_table=plan.target_table,
                        parquet_rows=plan.row_count,
                        clickhouse_rows=current_rows,
                        status="skipped",
                    )
                )
                continue

        if table_exists_now and not config.loader.replace:
            current_rows = count_rows(client, config.clickhouse.database, plan.target_table)
            if current_rows != 0:
                raise ValueError(
                    f"{config.clickhouse.database}.{plan.target_table} already exists with "
                    f"{current_rows} rows; use --replace to rebuild it"
                )

        if table_exists_now and config.loader.replace:
            drop_table(client, config.clickhouse.database, plan.target_table)

        client.command(create_table_sql(config.clickhouse.database, plan.target_table, schema))
        for record_batch in parquet_file.iter_batches(
            batch_size=config.loader.insert_batch_rows,
        ):
            arrow_table = pa.Table.from_batches([record_batch], schema=schema)
            arrow_table = prepare_arrow_table_for_insert(arrow_table)
            client.insert_arrow(
                table=plan.target_table,
                arrow_table=arrow_table,
                database=config.clickhouse.database,
            )

        clickhouse_rows = count_rows(client, config.clickhouse.database, plan.target_table)
        status = "loaded" if clickhouse_rows == plan.row_count else "row-count-mismatch"
        results.append(
            LoadResult(
                source_path=plan.source_path,
                target_table=plan.target_table,
                parquet_rows=plan.row_count,
                clickhouse_rows=clickhouse_rows,
                status=status,
            )
        )

    return results


def create_empty_tables(
    config: AppConfig,
    client: object,
    table_filter: str | None = None,
) -> list[LoadResult]:
    """Create ClickHouse database tables from Parquet schemas without inserts.

    This is the inspection step before a full data load. Existing empty tables
    are left in place. Existing non-empty tables are refused unless replace mode
    is enabled, because schema creation should not silently overwrite data.
    """

    plans = _filtered_plans(
        plans=discover_parquet_files(config.loader.parquet_dir),
        table_filter=table_filter,
    )
    results: list[LoadResult] = []

    for plan in plans:
        parquet_file = pq.ParquetFile(plan.source_path)
        schema = parquet_file.schema_arrow
        table_exists_now = table_exists(client, config.clickhouse.database, plan.target_table)

        if table_exists_now:
            current_rows = count_rows(client, config.clickhouse.database, plan.target_table)
            if current_rows == 0 and not config.loader.replace:
                results.append(
                    LoadResult(
                        source_path=plan.source_path,
                        target_table=plan.target_table,
                        parquet_rows=plan.row_count,
                        clickhouse_rows=0,
                        status="already-empty",
                    )
                )
                continue
            if current_rows != 0 and not config.loader.replace:
                raise ValueError(
                    f"{config.clickhouse.database}.{plan.target_table} already exists with "
                    f"{current_rows} rows; use --replace to rebuild it"
                )
            drop_table(client, config.clickhouse.database, plan.target_table)

        client.command(create_table_sql(config.clickhouse.database, plan.target_table, schema))
        results.append(
            LoadResult(
                source_path=plan.source_path,
                target_table=plan.target_table,
                parquet_rows=plan.row_count,
                clickhouse_rows=0,
                status="created-empty",
            )
        )

    return results


def validate_loaded_tables(
    config: AppConfig,
    client: object,
    table_filter: str | None = None,
) -> list[LoadResult]:
    """Compare ClickHouse row counts with the local Parquet row counts."""

    plans = _filtered_plans(
        plans=discover_parquet_files(config.loader.parquet_dir),
        table_filter=table_filter,
    )
    results: list[LoadResult] = []

    for plan in plans:
        if not table_exists(client, config.clickhouse.database, plan.target_table):
            results.append(
                LoadResult(
                    source_path=plan.source_path,
                    target_table=plan.target_table,
                    parquet_rows=plan.row_count,
                    clickhouse_rows=0,
                    status="missing",
                )
            )
            continue

        clickhouse_rows = count_rows(client, config.clickhouse.database, plan.target_table)
        status = "ok" if clickhouse_rows == plan.row_count else "row-count-mismatch"
        results.append(
            LoadResult(
                source_path=plan.source_path,
                target_table=plan.target_table,
                parquet_rows=plan.row_count,
                clickhouse_rows=clickhouse_rows,
                status=status,
            )
        )

    return results


def table_exists(client: object, database: str, table: str) -> bool:
    """Return whether a ClickHouse table exists."""

    db_name = _validated_identifier(database, "database")
    table_name = _validated_identifier(table, "table")
    sql = (
        "SELECT count() "
        "FROM system.tables "
        f"WHERE database = '{db_name}' AND name = '{table_name}'"
    )
    result = client.query(sql)
    return bool(result.result_rows[0][0])


def count_rows(client: object, database: str, table: str) -> int:
    """Return the number of rows currently stored in one ClickHouse table."""

    db_name = _validated_identifier(database, "database")
    table_name = _validated_identifier(table, "table")
    result = client.query(
        f"SELECT count() FROM {_quote_identifier(db_name)}.{_quote_identifier(table_name)}"
    )
    return int(result.result_rows[0][0])


def drop_table(client: object, database: str, table: str) -> None:
    """Drop one ClickHouse table before a replace-mode reload."""

    db_name = _validated_identifier(database, "database")
    table_name = _validated_identifier(table, "table")
    client.command(f"DROP TABLE IF EXISTS {_quote_identifier(db_name)}.{_quote_identifier(table_name)}")


def dry_run(config: AppConfig, table_filter: str | None = None) -> list[tuple[TableLoadPlan, str]]:
    """Return load plans and DDL without connecting to ClickHouse."""

    plans = _filtered_plans(
        plans=discover_parquet_files(config.loader.parquet_dir),
        table_filter=table_filter,
    )
    output: list[tuple[TableLoadPlan, str]] = []
    for plan in plans:
        schema = pq.ParquetFile(plan.source_path).schema_arrow
        output.append(
            (
                plan,
                create_table_sql(
                    database=config.clickhouse.database,
                    table=plan.target_table,
                    schema=schema,
                ),
            )
        )
    return output


def prepare_arrow_table_for_insert(arrow_table: pa.Table) -> pa.Table:
    """Convert Arrow columns that need ClickHouse-safe storage types.

    BoardEx date columns can include sentinel values beyond ClickHouse's native
    date range. This function converts Arrow ``date32`` columns to ISO date
    strings before insertion. Other columns keep their original Arrow arrays.
    """

    arrays: list[pa.ChunkedArray] = []
    fields: list[pa.Field] = []

    for field in arrow_table.schema:
        column = arrow_table[field.name]
        if pa.types.is_date32(field.type):
            formatted_chunks = [
                pc.strftime(chunk, format="%F") for chunk in column.chunks
            ]
            arrays.append(pa.chunked_array(formatted_chunks, type=pa.string()))
            fields.append(pa.field(field.name, pa.string(), nullable=field.nullable))
            continue

        arrays.append(column)
        fields.append(field)

    return pa.Table.from_arrays(arrays, schema=pa.schema(fields))


def with_runtime_overrides(
    config: AppConfig,
    replace_existing: bool,
    resume_existing: bool | None,
    parquet_dir: Path | None,
) -> AppConfig:
    """Apply command-line overrides to a loaded ``AppConfig``."""

    loader = config.loader
    if replace_existing:
        # Replace means rebuild even if an existing table already has matching
        # row counts, so this run must not apply resume skipping.
        loader = replace(loader, replace=True, resume=False)
    if resume_existing is not None:
        loader = replace(loader, resume=resume_existing)
    if parquet_dir is not None:
        loader = replace(loader, parquet_dir=parquet_dir.resolve())
    return replace(config, loader=loader)


def _parse_clickhouse_config(raw_config: dict[str, Any]) -> ClickHouseConfig:
    """Parse and validate the ``[clickhouse]`` TOML section."""

    database = _validated_identifier(str(raw_config["database"]), "clickhouse.database")
    return ClickHouseConfig(
        host=str(raw_config["host"]),
        port=int(raw_config["port"]),
        username=str(raw_config["username"]),
        password=str(raw_config.get("password", "")),
        secure=bool(raw_config["secure"]),
        database=database,
    )


def _parse_loader_config(raw_config: dict[str, Any], config_dir: Path) -> LoaderConfig:
    """Parse and validate the ``[loader]`` TOML section."""

    raw_parquet_dir = Path(str(raw_config["parquet_dir"]))
    parquet_dir = raw_parquet_dir if raw_parquet_dir.is_absolute() else config_dir / raw_parquet_dir
    insert_batch_rows = int(raw_config.get("insert_batch_rows", DEFAULT_INSERT_BATCH_ROWS))
    if insert_batch_rows <= 0:
        raise ValueError("loader.insert_batch_rows must be positive")

    return LoaderConfig(
        parquet_dir=parquet_dir.resolve(),
        insert_batch_rows=insert_batch_rows,
        create_database=bool(raw_config["create_database"]),
        replace=bool(raw_config["replace"]),
        resume=bool(raw_config["resume"]),
    )


def _filtered_plans(
    plans: Iterable[TableLoadPlan],
    table_filter: str | None,
) -> list[TableLoadPlan]:
    """Apply an optional exact target-table filter."""

    filtered = list(plans)
    if table_filter is not None:
        table_name = _validated_identifier(table_filter, "table filter")
        filtered = [plan for plan in filtered if plan.target_table == table_name]
    if not filtered:
        raise ValueError("No Parquet files matched the requested table filter")
    return filtered


def _order_by_expression(schema: pa.Schema) -> str:
    """Choose a compact sort key from common BoardEx identifier/date columns."""

    chosen_columns = _order_by_columns(schema)
    if not chosen_columns:
        return "tuple()"

    quoted_columns = ", ".join(_quote_identifier(column_name) for column_name in chosen_columns)
    return f"({quoted_columns})"


def _order_by_columns(schema: pa.Schema) -> list[str]:
    """Return preferred BoardEx sort-key columns that exist in a schema."""

    source_columns = {field.name for field in schema}
    id_candidates = [
        "directorid",
        "companyid",
        "personid",
        "professionalid",
        "proid",
        "objectid",
    ]
    date_candidates = [
        "annualreportdate",
        "startdate",
        "enddate",
        "date",
        "asofdate",
    ]

    chosen_columns: list[str] = []
    for column_name in id_candidates:
        if column_name in source_columns:
            chosen_columns.append(column_name)
            break
    for column_name in date_candidates:
        if column_name in source_columns:
            chosen_columns.append(column_name)
            break

    return chosen_columns


def _nullable_key_setting(schema: pa.Schema) -> str:
    """Return the MergeTree setting needed when sort-key columns are nullable."""

    order_by_columns = _order_by_columns(schema)
    if not order_by_columns:
        return ""

    nullable_sort_key = any(schema.field(column_name).nullable for column_name in order_by_columns)
    if not nullable_sort_key:
        return ""

    return "\nSETTINGS allow_nullable_key = 1"


def _timestamp_scale(unit: str) -> int:
    """Translate Arrow timestamp units into ClickHouse DateTime64 precision."""

    return {
        "s": 0,
        "ms": 3,
        "us": 6,
        "ns": 9,
    }[unit]


def _normalize_host_and_secure(host: str, configured_secure: bool) -> tuple[str, bool]:
    """Accept either a plain host name or an HTTP(S) URL."""

    if "://" not in host:
        return host, configured_secure

    parsed_host = urlparse(host)
    secure = parsed_host.scheme == "https"
    return parsed_host.hostname or host, secure


def _validated_identifier(name: str, label: str) -> str:
    """Validate names that are interpolated into ClickHouse SQL identifiers."""

    if not IDENTIFIER_PATTERN.fullmatch(name):
        raise ValueError(f"Invalid {label}: {name!r}")
    return name


def _quote_identifier(name: str) -> str:
    """Quote a validated ClickHouse identifier."""

    return f"`{name}`"
