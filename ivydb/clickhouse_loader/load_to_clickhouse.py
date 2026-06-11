"""Load IvyDB tables from WRDS PostgreSQL into ClickHouse."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
from typing import Iterator

from ivydb.clickhouse_loader.clickhouse_client import table_exists, table_row_count
from ivydb.clickhouse_loader.config import AppConfig
from ivydb.clickhouse_loader.normalization import normalize_batch_for_clickhouse
from ivydb.clickhouse_loader.table_plan import TablePlan
from ivydb.clickhouse_loader.wrds_stream import stream_table


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoadResult:
    """Summary for one loaded source table."""

    source_table: str
    target_table: str
    rows_loaded: int


def load_tables(
    config: AppConfig,
    wrds_connection: object,
    clickhouse_client: object,
    table_plan: list[TablePlan],
) -> list[LoadResult]:
    """Stream selected historical WRDS sources directly into curated final tables."""

    LOGGER.info(
        "Starting IvyDB load for %s source table(s); local audit file: %s",
        len(table_plan),
        config.loader.audit_log_path,
    )

    results: list[LoadResult] = []
    for table in table_plan:
        if _should_skip_completed_source(config, table):
            LOGGER.info(
                "Skipping %s.%s -> %s because the local audit file marks it complete",
                table.source_library,
                table.source_table,
                table.target_table,
            )
            results.append(LoadResult(table.source_table, table.target_table, 0))
            continue
        _require_empty_load_destination(config, clickhouse_client, table)
        results.append(
            _load_one_table_direct(config, wrds_connection, clickhouse_client, table)
        )
    return results


def clear_failed_tables(
    config: AppConfig,
    clickhouse_client: object,
    table_plan: list[TablePlan],
) -> list[str]:
    """Clear direct-load destinations left incomplete by failed or stopped loads.

    Completed and never-started selections are intentionally ignored so a user
    can run cleanup with the same batch configuration that originally stopped.
    """

    cleared_tables: list[str] = []
    for table in table_plan:
        status = _local_audit_latest_status(config.loader.audit_log_path, table)
        if status not in {"failed", "interrupted", "started"}:
            LOGGER.info(
                "Leaving %s unchanged during cleanup because its latest audit status is %s",
                table.source_table,
                status,
            )
            continue
        database = config.clickhouse.database
        if table.is_consolidated_year_table:
            command = (
                f"ALTER TABLE `{database}`.`{table.target_table}` "
                f"DROP PARTITION IF EXISTS {table.source_year}"
            )
        else:
            command = f"TRUNCATE TABLE `{database}`.`{table.target_table}`"
        clickhouse_client.command(command)
        _write_audit_row(config, table, 0, datetime.now(UTC), "cleared", "")
        cleared_tables.append(table.target_table)
    return cleared_tables


def _load_one_table_direct(
    config: AppConfig,
    wrds_connection: object,
    clickhouse_client: object,
    table: TablePlan,
) -> LoadResult:
    """Insert source chunks directly into a pre-created curated final table."""

    started_at = datetime.now(UTC)
    rows_loaded = 0
    _write_audit_row(config, table, rows_loaded, started_at, "started", "")
    try:
        LOGGER.info(
            "Loading %s.%s -> %s",
            table.source_library,
            table.source_table,
            table.target_table,
        )
        LOGGER.info(
            "Streaming %s.%s from WRDS through a server-side cursor; the first "
            "chunk should arrive promptly and memory stays bounded per chunk",
            table.source_library,
            table.source_table,
        )
        for chunk_number, chunk in enumerate(
            stream_table(
                wrds_connection=wrds_connection,
                source_library=table.source_library,
                source_table=table.source_table,
                columns=table.source_columns,
                chunksize=config.loader.wrds_batch_size,
            ),
            start=1,
        ):
            LOGGER.info(
                "Received WRDS chunk %s from %s.%s with %s row(s)",
                chunk_number,
                table.source_library,
                table.source_table,
                f"{len(chunk):,}",
            )
            normalized_chunk = normalize_batch_for_clickhouse(chunk, table)
            for insert_batch_number, insert_batch in enumerate(
                split_dataframe_for_insert(
                    normalized_chunk,
                    config.loader.clickhouse_insert_size,
                ),
                start=1,
            ):
                LOGGER.info(
                    "Inserting ClickHouse batch %s for %s.%s with %s row(s)",
                    insert_batch_number,
                    table.source_library,
                    table.source_table,
                    f"{len(insert_batch):,}",
                )
                clickhouse_client.insert_df(
                    table=table.target_table,
                    df=insert_batch,
                    database=config.clickhouse.database,
                )
            rows_loaded += len(normalized_chunk)
            LOGGER.info(
                "Loaded %s rows from %s.%s",
                f"{rows_loaded:,}",
                table.source_library,
                table.source_table,
            )
        _write_audit_row(config, table, rows_loaded, started_at, "complete", "")
        _write_year_summary_row(
            config=config,
            clickhouse_client=clickhouse_client,
            table=table,
            rows_loaded=rows_loaded,
            started_at=started_at,
        )
        LOGGER.info(
            "Completed %s.%s -> %s with %s row(s)",
            table.source_library,
            table.source_table,
            table.target_table,
            f"{rows_loaded:,}",
        )
        return LoadResult(table.source_table, table.target_table, rows_loaded)
    except KeyboardInterrupt:
        _write_audit_row(
            config,
            table,
            rows_loaded,
            started_at,
            "interrupted",
            "KeyboardInterrupt",
        )
        LOGGER.warning(
            "Interrupted %s.%s -> %s after %s loaded row(s)",
            table.source_library,
            table.source_table,
            table.target_table,
            f"{rows_loaded:,}",
        )
        raise
    except Exception as exc:
        _write_audit_row(config, table, rows_loaded, started_at, "failed", str(exc))
        LOGGER.exception(
            "Failed %s.%s -> %s after %s loaded row(s)",
            table.source_library,
            table.source_table,
            table.target_table,
            f"{rows_loaded:,}",
        )
        raise


def split_dataframe_for_insert(dataframe: object, insert_size: int) -> Iterator[object]:
    """Yield row slices sized for ClickHouse inserts.

    Parameters
    ----------
    dataframe:
        A pandas DataFrame returned by WRDS.
    insert_size:
        Maximum rows to send in one ClickHouse insert call.
    """

    if insert_size <= 0:
        raise ValueError("insert_size must be positive")

    row_count = len(dataframe)
    for start_index in range(0, row_count, insert_size):
        stop_index = start_index + insert_size
        yield dataframe.iloc[start_index:stop_index]


def _should_skip_completed_source(
    config: AppConfig,
    table: TablePlan,
) -> bool:
    """Return whether resume mode should skip a completed source table."""

    if not config.loader.resume:
        return False

    return _local_audit_latest_status(config.loader.audit_log_path, table) == "complete"


def _require_empty_load_destination(
    config: AppConfig,
    clickhouse_client: object,
    table: TablePlan,
) -> None:
    """Refuse direct inserts unless the selected source has no final rows."""

    database = config.clickhouse.database
    if not table_exists(clickhouse_client, database, table.target_table):
        raise ValueError(
            f"{table.target_table} is missing; run create-tables first "
            "to create its curated schema"
        )
    if table.is_consolidated_year_table:
        if table.source_year is None or table.source_year_column is None:
            raise ValueError("consolidated yearly tables need source-year metadata")
        result = clickhouse_client.query(
            f"SELECT count() FROM `{database}`.`{table.target_table}` "
            f"WHERE `{table.source_year_column}` = {table.source_year}"
        )
        has_existing_rows = int(result.result_rows[0][0]) > 0
    else:
        has_existing_rows = table_row_count(clickhouse_client, database, table.target_table) > 0
    if has_existing_rows:
        raise ValueError(
            f"{table.target_table} already has rows for {table.source_table}; "
            "do not reload append-once historical data"
        )


def _write_audit_row(
    config: AppConfig,
    table: TablePlan,
    rows_loaded: int,
    started_at: datetime,
    status: str,
    error_message: str,
) -> None:
    """Append one source-table load event to the local JSON-lines audit file."""

    audit_path = config.loader.audit_log_path
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    completed_at = datetime.now(UTC)
    record = {
        "source_library": table.source_library,
        "source_table": table.source_table,
        "target_table": table.target_table,
        "layout": table.layout,
        "source_year": table.source_year,
        "status": status,
        "rows_inserted": rows_loaded,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "error_message": error_message,
    }
    with audit_path.open("a", encoding="utf-8") as audit_file:
        audit_file.write(json.dumps(record, sort_keys=True) + "\n")


def _write_year_summary_row(
    config: AppConfig,
    clickhouse_client: object,
    table: TablePlan,
    rows_loaded: int,
    started_at: datetime,
) -> None:
    """Append one human-readable completion line for a yearly source table.

    The JSON-lines audit log remains the resume source of truth. This separate
    summary is for tailing a long run and quickly seeing which source years
    finished, how many rows inserted, and how long each source took.
    """

    if table.source_year is None:
        return

    completed_at = datetime.now(UTC)
    elapsed_seconds = (completed_at - started_at).total_seconds()
    target_row_count = _target_row_count_text(config, clickhouse_client, table)
    summary_path = config.loader.year_summary_log_path
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        f"completed_at={completed_at.isoformat()}",
        "status=complete",
        f"source_library={table.source_library}",
        f"source_table={table.source_table}",
        f"target_table={table.target_table}",
        f"source_year={table.source_year}",
        f"rows_inserted={rows_loaded}",
        f"target_row_count={target_row_count}",
        f"elapsed_seconds={elapsed_seconds:.3f}",
        f"started_at={started_at.isoformat()}",
    ]
    with summary_path.open("a", encoding="utf-8") as summary_file:
        summary_file.write(" ".join(fields) + "\n")


def _target_row_count_text(
    config: AppConfig,
    clickhouse_client: object,
    table: TablePlan,
) -> str:
    """Return a row-count string for the yearly summary log."""

    try:
        if table.is_consolidated_year_table:
            if table.source_year is None or table.source_year_column is None:
                return "unavailable"
            result = clickhouse_client.query(
                f"SELECT count() FROM `{config.clickhouse.database}`.`{table.target_table}` "
                f"WHERE `{table.source_year_column}` = {table.source_year}"
            )
            return str(int(result.result_rows[0][0]))
        row_count = table_row_count(
            clickhouse_client,
            config.clickhouse.database,
            table.target_table,
        )
        return str(row_count)
    except Exception as error:
        return f"unavailable:{type(error).__name__}"


def _local_audit_latest_status(audit_path: Path, table: TablePlan) -> str | None:
    """Return the latest recorded status for one exact source-target pair."""

    latest_status: str | None = None
    if not audit_path.exists():
        return None
    for line_number, line in enumerate(
        audit_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid JSON in audit log {audit_path} on line {line_number}"
            ) from exc
        if (
            record.get("source_library") == table.source_library
            and record.get("source_table") == table.source_table
            and record.get("target_table") == table.target_table
        ):
            latest_status = str(record.get("status", ""))
    return latest_status
