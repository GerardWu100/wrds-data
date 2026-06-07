#!/usr/bin/env python3
"""Check raw OHLCV .txt files for data quality issues.

Scans every supported file in the given directory and reports:
  - Rows with wrong column count (missing / extra fields)
  - Empty or whitespace-only fields in any column
  - Unparseable timestamps
  - Non-numeric or non-finite OHLCV / volume values
  - Negative values in open, high, low, close, or volume

Usage:
    python check_data.py [data_dir]

    data_dir defaults to ./data if not provided.

Output is printed to stdout AND written to outputs/check_data_<timestamp>.log.
Exit code is 0 if no issues found, 1 otherwise.
"""

from __future__ import annotations

import csv
import math
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S"
COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]

_FULL_1MIN_PATTERN = re.compile(r"^(?P<symbol>.+)_full_1min(?:_.+)?$")
_GENERIC_1MIN_PATTERN = re.compile(r"^(?P<symbol>.+)_1min$")


def _is_supported(file_path: Path) -> bool:
    stem = file_path.stem
    return bool(_FULL_1MIN_PATTERN.fullmatch(stem) or _GENERIC_1MIN_PATTERN.fullmatch(stem))


def _check_file(file_path: Path) -> list[str]:
    """Return a list of issue strings found in the file."""
    issues: list[str] = []

    with file_path.open("r", newline="") as fh:
        reader = csv.reader(fh)
        for line_no, row in enumerate(reader, start=1):
            # blank line
            if not row:
                continue

            prefix = f"  line {line_no}"

            # wrong column count
            if len(row) != 6:
                issues.append(
                    f"{prefix}: wrong column count — expected 6, got {len(row)}  →  {','.join(row)!r}"
                )
                continue  # can't validate individual fields without the right count

            # check for empty fields
            for col_idx, (col_name, value) in enumerate(zip(COLUMNS, row)):
                if not value.strip():
                    issues.append(
                        f"{prefix}: empty '{col_name}' field (column {col_idx + 1})"
                    )

            # timestamp
            raw_ts = row[0].strip()
            if raw_ts:
                try:
                    datetime.strptime(raw_ts, TIMESTAMP_FMT)
                except ValueError:
                    issues.append(
                        f"{prefix}: unparseable timestamp {raw_ts!r} "
                        f"(expected {TIMESTAMP_FMT})"
                    )

            # numeric columns: open, high, low, close, volume
            for col_idx in range(1, 6):
                col_name = COLUMNS[col_idx]
                raw_val = row[col_idx].strip()
                if not raw_val:
                    continue  # already reported as empty above

                try:
                    parsed = float(raw_val)
                except ValueError:
                    issues.append(
                        f"{prefix}: non-numeric '{col_name}' value {raw_val!r}"
                    )
                    continue

                if not math.isfinite(parsed):
                    issues.append(
                        f"{prefix}: non-finite '{col_name}' value {raw_val!r}"
                    )
                    continue

                if parsed < 0:
                    issues.append(
                        f"{prefix}: negative '{col_name}' value {parsed}"
                    )

    return issues


def _emit(message: str, log_fh) -> None:
    """Print to stdout and write to the log file."""
    print(message)
    log_fh.write(message + "\n")


def check_directory(data_dir: Path, log_path: Path) -> int:
    """Check all supported files in data_dir. Returns total number of issues."""
    files = sorted(f for f in data_dir.glob("*.txt") if _is_supported(f))

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log_fh:
        run_ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        log_fh.write(f"check_data run: {run_ts}\n")
        log_fh.write(f"data_dir: {data_dir}\n")
        log_fh.write("=" * 60 + "\n\n")

        if not files:
            msg = f"No supported OHLCV files found in {data_dir}"
            _emit(msg, log_fh)
            return 0

        total_issues = 0
        for file_path in files:
            issues = _check_file(file_path)
            if issues:
                _emit(f"\n{file_path.name}  —  {len(issues)} issue(s) found:", log_fh)
                for issue in issues:
                    _emit(issue, log_fh)
                total_issues += len(issues)
            else:
                _emit(f"{file_path.name}  —  OK", log_fh)

        log_fh.write("\n" + "=" * 60 + "\n")
        summary = (
            f"DONE — {total_issues} issue(s) found across all files."
            if total_issues
            else "DONE — no issues found."
        )
        log_fh.write(summary + "\n")

    return total_issues


def main() -> None:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "data"

    if not data_dir.exists():
        print(f"ERROR: directory not found: {data_dir}", file=sys.stderr)
        sys.exit(1)

    run_ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_path = Path(__file__).parent / "outputs" / f"check_data_{run_ts}.log"

    print(f"Checking files in: {data_dir}")
    print(f"Log file: {log_path}\n")

    total_issues = check_directory(data_dir, log_path)

    print()
    if total_issues:
        print(f"DONE — {total_issues} issue(s) found across all files.")
        print(f"Full report written to: {log_path}")
        sys.exit(1)
    else:
        print("DONE — no issues found.")
        print(f"Log written to: {log_path}")
        sys.exit(0)


if __name__ == "__main__":
    main()
