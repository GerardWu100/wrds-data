#!/usr/bin/env python3
"""Core functions to load 1-minute OHLCV text files into ClickHouse.

Input files are expected to contain rows in this format (no header):
    YYYY-mm-dd HH:MM:SS,open,high,low,close,volume

The symbol is inferred from the file name prefix in patterns like:
    SNT_full_1min.txt -> SNT
"""

from __future__ import annotations

import csv
import importlib
import math
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from schema_non_crypto import truncate_table


TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S"
_FULL_1MIN_PATTERN = re.compile(r"^(?P<symbol>.+)_full_1min(?:_.+)?$")
_GENERIC_1MIN_PATTERN = re.compile(r"^(?P<symbol>.+)_1min$")


@dataclass(frozen=True)
class LoaderConfig:
    """Runtime configuration for ClickHouse OHLCV ingestion."""

    data_dir: Path
    host: str
    port: int
    username: str
    password: str
    database: str
    table: str
    batch_size: int
    clean_start: bool
    secure: bool
    market_timezone: str
    utc_symbols: frozenset[str]
    error_export_path: Path
    log_path: Path | None = None


@dataclass(frozen=True)
class OhlcvRow:
    symbol: str
    ts: datetime
    open_: float
    high: float
    low: float
    close: float
    volume: float


def _log(message: str, log_path: Path | None) -> None:
    """Write a timestamped message to stdout and optionally to a log file."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {message}"
    print(line)
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def extract_symbol(file_path: Path) -> str:
    """Extract symbol from supported names like SYMBOL_full_1min*.txt or SYMBOL_1min.txt."""

    stem = file_path.stem
    symbol: str | None = None

    full_match = _FULL_1MIN_PATTERN.fullmatch(stem)
    if full_match:
        symbol = full_match.group("symbol")
    else:
        generic_match = _GENERIC_1MIN_PATTERN.fullmatch(stem)
        if generic_match:
            symbol = generic_match.group("symbol")

    if symbol is None:
        raise ValueError(
            "Unexpected file name format for "
            f"{file_path.name}; expected '*_full_1min.txt', "
            "'*_full_1min_*.txt', or '*_1min.txt'"
        )

    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError(f"Could not infer symbol from file name: {file_path.name}")
    return symbol


def _normalize_symbols(raw_symbols: Iterable[str]) -> frozenset[str]:
    return frozenset(symbol.strip().upper() for symbol in raw_symbols if symbol.strip())


def _parse_volume_to_float(raw_volume: str, file_path: Path, line_number: int) -> float:
    value = raw_volume.strip()
    try:
        parsed = float(value)
    except ValueError:
        raise ValueError(
            f"{file_path.name}:{line_number} volume must be a numeric value, got {raw_volume!r}"
        )

    if not math.isfinite(parsed):
        raise ValueError(
            f"{file_path.name}:{line_number} volume must be a finite numeric value, got {raw_volume!r}"
        )
    return parsed


def _export_row_error(
    error_export_path: Path,
    file_path: Path,
    line_number: int,
    row: list[str],
    error_message: str,
) -> None:
    error_export_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp_utc = datetime.now(UTC).isoformat()
    serialized_row = ",".join(row)
    line = (
        f"{timestamp_utc}\tfile={file_path.name}\tline={line_number}"
        f"\terror={error_message}\trow={serialized_row}\n"
    )
    with error_export_path.open("a", encoding="utf-8") as handle:
        handle.write(line)


def parse_timestamp_to_utc(
    raw_ts: str,
    source_timezone: ZoneInfo,
    treat_as_utc: bool,
) -> datetime:
    naive_dt = datetime.strptime(raw_ts, TIMESTAMP_FMT)
    if treat_as_utc:
        return naive_dt.replace(tzinfo=UTC)
    return naive_dt.replace(tzinfo=source_timezone).astimezone(UTC)


def read_rows(
    file_path: Path,
    market_timezone: str,
    utc_symbols: frozenset[str],
    error_export_path: Path,
) -> Iterable[OhlcvRow]:
    symbol = extract_symbol(file_path)
    source_timezone = ZoneInfo(market_timezone)
    treat_as_utc = symbol in utc_symbols
    with file_path.open("r", newline="") as handle:
        reader = csv.reader(handle)
        for line_number, row in enumerate(reader, start=1):
            if not row:
                continue
            if len(row) != 6:
                error_message = f"{file_path.name}:{line_number} expected 6 columns, got {len(row)}"
                _export_row_error(
                    error_export_path=error_export_path,
                    file_path=file_path,
                    line_number=line_number,
                    row=row,
                    error_message=error_message,
                )
                print(f"[WARN] Skipping row: {error_message}")
                continue

            try:
                parsed_row = OhlcvRow(
                    symbol=symbol,
                    ts=parse_timestamp_to_utc(row[0], source_timezone, treat_as_utc),
                    open_=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=_parse_volume_to_float(row[5], file_path, line_number),
                )
                for field_name, value in [
                    ("open", parsed_row.open_),
                    ("high", parsed_row.high),
                    ("low", parsed_row.low),
                    ("close", parsed_row.close),
                    ("volume", parsed_row.volume),
                ]:
                    if value < 0:
                        print(
                            f"[WARN] {file_path.name}:{line_number} "
                            f"negative {field_name}={value}"
                        )
                yield parsed_row
            except ValueError as exc:
                _export_row_error(
                    error_export_path=error_export_path,
                    file_path=file_path,
                    line_number=line_number,
                    row=row,
                    error_message=str(exc),
                )
                print(f"[WARN] Skipping row: {exc}")
                continue


def flush_batch(
    client: Any,
    database: str,
    table: str,
    batch: list[OhlcvRow],
) -> None:
    if not batch:
        return

    payload = [
        [
            row.symbol,
            row.ts,
            row.open_,
            row.high,
            row.low,
            row.close,
            row.volume,
        ]
        for row in batch
    ]
    client.insert(
        f"{database}.{table}",
        payload,
        column_names=[
            "symbol",
            "ts",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ],
        settings={"max_partitions_per_insert_block": 0},
    )


def load_directory(
    client: Any,
    data_dir: Path,
    database: str,
    table: str,
    batch_size: int,
    market_timezone: str,
    utc_symbols: frozenset[str],
    error_export_path: Path,
    log_path: Path | None,
) -> int:
    files = sorted(file_path for file_path in data_dir.glob("*.txt") if _is_supported_ohlcv_file(file_path))
    if not files:
        raise FileNotFoundError(
            f"No supported OHLCV files found in {data_dir}; expected "
            "'*_full_1min.txt', '*_full_1min_*.txt', or '*_1min.txt'"
        )

    _log(f"Found {len(files)} file(s) in {data_dir}", log_path)

    total_rows = 0
    batch: list[OhlcvRow] = []
    batches_flushed = 0

    for file_index, file_path in enumerate(files, start=1):
        file_start = time.monotonic()
        file_rows = 0
        _log(f"[{file_index}/{len(files)}] Loading {file_path.name} ...", log_path)

        for row in read_rows(file_path, market_timezone, utc_symbols, error_export_path):
            batch.append(row)
            file_rows += 1
            total_rows += 1

            if len(batch) >= batch_size:
                flush_batch(client, database, table, batch)
                batch.clear()
                batches_flushed += 1
                _log(
                    f"  Flushed batch #{batches_flushed} "
                    f"({total_rows:,} rows inserted so far)",
                    log_path,
                )

        elapsed = time.monotonic() - file_start
        _log(
            f"[{file_index}/{len(files)}] Done {file_path.name}: "
            f"{file_rows:,} rows in {elapsed:.1f}s",
            log_path,
        )

    flush_batch(client, database, table, batch)
    if batch:
        batches_flushed += 1
        _log(f"  Flushed final batch #{batches_flushed}", log_path)

    return total_rows


def _is_supported_ohlcv_file(file_path: Path) -> bool:
    stem = file_path.stem
    return bool(_FULL_1MIN_PATTERN.fullmatch(stem) or _GENERIC_1MIN_PATTERN.fullmatch(stem))


def build_client(config: LoaderConfig) -> Any:
    """Build a ClickHouse client from loader configuration."""

    try:
        clickhouse_connect = importlib.import_module("clickhouse_connect")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Missing dependency: clickhouse-connect. Install with `uv add clickhouse-connect`."
        ) from exc

    return clickhouse_connect.get_client(
        host=config.host,
        port=config.port,
        username=config.username,
        password=config.password,
        secure=config.secure,
    )


def run_load(config: LoaderConfig) -> int:
    """Load OHLCV files into an existing ClickHouse table."""

    log_path = config.log_path
    run_start = time.monotonic()

    _log("=" * 60, log_path)
    _log("non-crypto loader starting", log_path)
    _log(f"  Target   : {config.database}.{config.table}", log_path)
    _log(f"  Data     : {config.data_dir}", log_path)
    _log(f"  Batch    : {config.batch_size:,} rows", log_path)
    _log(f"  Timezone : {config.market_timezone}", log_path)
    if config.utc_symbols:
        _log(f"  UTC syms : {sorted(config.utc_symbols)}", log_path)
    if config.clean_start:
        _log("  Mode     : clean_start (table will be truncated)", log_path)
    _log("=" * 60, log_path)

    client = build_client(config)
    if config.clean_start:
        _log("Truncating table ...", log_path)
        truncate_table(client, config.database, config.table)
        _log("Table truncated.", log_path)

    total_rows = load_directory(
        client=client,
        data_dir=config.data_dir,
        database=config.database,
        table=config.table,
        batch_size=config.batch_size,
        market_timezone=config.market_timezone,
        utc_symbols=_normalize_symbols(config.utc_symbols),
        error_export_path=config.error_export_path,
        log_path=log_path,
    )

    elapsed = time.monotonic() - run_start
    _log("=" * 60, log_path)
    _log(
        f"Load complete: {total_rows:,} rows into "
        f"{config.database}.{config.table} in {elapsed:.1f}s",
        log_path,
    )
    _log("=" * 60, log_path)

    return total_rows
