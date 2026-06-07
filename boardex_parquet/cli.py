#!/usr/bin/env python3
"""CLI for the BoardEx OSINT -> Parquet downloader.

Usage examples
--------------
Download all tables currently selected by config.toml:
    uv run python boardex_parquet/cli.py

Equivalent module form:
    uv run python -m boardex_parquet

Dry-run -- print estimated row counts, write nothing:
    uv run python boardex_parquet/cli.py --dry-run

Resume -- skip tables whose Parquet files already exist:
    uv run python boardex_parquet/cli.py --resume

Download only the boardex_na library:
    uv run python boardex_parquet/cli.py --library boardex_na

Download one specific table:
    uv run python boardex_parquet/cli.py --library boardex_na --table na_dir_profile_emp

Use a non-default config file:
    uv run python boardex_parquet/cli.py --config /path/to/other_config.toml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from boardex_parquet.download_to_parquet import run

CONFIG_PATH = Path(__file__).resolve().parent / "config.toml"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download BoardEx OSINT tables from WRDS to Parquet files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help="Path to config.toml (default: boardex_parquet/config.toml).",
    )
    parser.add_argument(
        "--library",
        help=(
            "Download only tables belonging to this WRDS library "
            "(e.g. 'boardex_na', 'ciq_pplintel')."
        ),
    )
    parser.add_argument(
        "--table",
        help=(
            "Download only this one table. Requires --library to be set. "
            "Example: --library boardex_na --table na_dir_profile_emp"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print estimated row counts for each table but do not write any files.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip tables whose Parquet file already exists in the output directory.",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()

    if args.table and not args.library:
        print("ERROR: --table requires --library to be specified.")
        sys.exit(1)

    run(
        config_path=args.config,
        dry_run=args.dry_run,
        resume=args.resume,
        filter_library=args.library,
        filter_table=args.table,
    )


if __name__ == "__main__":
    main()
