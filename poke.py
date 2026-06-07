#!/usr/bin/env python3
"""Small WRDS connection poke script.

This script is intentionally separate from the other workflows in the repo.
Its job is only to answer one question:

    "Can this project open a WRDS connection and run a tiny query right now?"

What it does
------------
1. Uses the shared project helper in ``catalog_exports/wrds_connection.py``.
2. Opens a WRDS connection with the project-local ``.pgpass`` file.
3. Runs one tiny metadata query against PostgreSQL.
4. Prints a short preview of canonical WRDS libraries.

Examples
--------
Run the default poke:

    uv run python poke.py

Show more preview libraries:

    uv run python poke.py --library-preview-count 10
"""

from __future__ import annotations

import argparse

from catalog_exports.wrds_connection import connect_wrds
from catalog_exports.wrds_connection import fetch_canonical_libraries
from catalog_exports.wrds_connection import read_wrds_username

DEFAULT_LIBRARY_PREVIEW_COUNT = 5


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the poke script."""

    parser = argparse.ArgumentParser(
        description="Open a small WRDS connection and run one tiny metadata query.",
    )
    parser.add_argument(
        "--library-preview-count",
        type=int,
        default=DEFAULT_LIBRARY_PREVIEW_COUNT,
        help=(
            "How many canonical WRDS library names to print after the connection "
            "check succeeds."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Connect to WRDS, run a tiny query, and print a small status summary."""

    args = parse_args()
    preview_count = max(args.library_preview_count, 0)
    wrds_username = read_wrds_username()

    print("WRDS connection poke")
    print(f"Configured username: {wrds_username}")

    wrds_db = connect_wrds()

    try:
        # Keep the SQL tiny and metadata-only so the script is safe to use as
        # a quick connectivity probe rather than a real data job.
        metadata_query = """
            select
                current_user as postgres_user,
                current_database() as database_name,
                current_date as server_date
        """
        metadata_result = wrds_db.raw_sql(metadata_query)
        metadata_row = metadata_result.iloc[0]

        canonical_libraries = fetch_canonical_libraries(wrds_db)
        preview_libraries = canonical_libraries[:preview_count]

        print("Connection successful.")
        print(f"PostgreSQL user: {metadata_row['postgres_user']}")
        print(f"Database name: {metadata_row['database_name']}")
        print(f"Server date: {metadata_row['server_date']}")
        print(f"Canonical library count: {len(canonical_libraries)}")

        if preview_libraries:
            preview_text = ", ".join(preview_libraries)
            print(f"Library preview: {preview_text}")
    finally:
        wrds_db.close()


if __name__ == "__main__":
    main()
