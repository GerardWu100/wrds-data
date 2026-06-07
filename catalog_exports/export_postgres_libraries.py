"""Export one row per canonical WRDS library."""

from __future__ import annotations

import pandas as pd
from catalog_exports.wrds_connection import PROJECT_ROOT

TABLE_INPUT = PROJECT_ROOT / "outputs" / "postgres_tables.csv"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "postgres_libraries.csv"
BYTES_PER_KIB = 1024
BYTES_PER_MIB = 1024 * 1024
BYTES_PER_GIB = 1024 * 1024 * 1024
SAMPLE_TABLE_LIMIT = 5


def format_bytes(byte_count: int) -> str:
    """Format a byte count into a compact human-readable string."""

    if byte_count >= BYTES_PER_GIB:
        return f"{byte_count / BYTES_PER_GIB:.2f} GiB"
    if byte_count >= BYTES_PER_MIB:
        return f"{byte_count / BYTES_PER_MIB:.2f} MiB"
    if byte_count >= BYTES_PER_KIB:
        return f"{byte_count / BYTES_PER_KIB:.2f} KiB"
    return f"{byte_count} B"


def summarize_table_names(table_names: pd.Series) -> str:
    """Return a short comma-separated sample of table names."""

    names = sorted(table_names.dropna().astype(str).tolist())
    return ", ".join(names[:SAMPLE_TABLE_LIMIT])


def first_comment(comments: pd.Series) -> str:
    """Return the first non-empty table comment, if any."""

    non_empty = comments.fillna("").astype(str).str.strip()
    non_empty = non_empty[non_empty != ""]
    if non_empty.empty:
        return ""
    return non_empty.iloc[0]


def main() -> None:
    """Write the canonical library catalog to `outputs/postgres_libraries.csv`."""

    tables = pd.read_csv(TABLE_INPUT)

    summary = tables.groupby("library", as_index=False).agg(
        table_count=("table_name", "count"),
        total_estimated_rows=("estimated_rows", "sum"),
        total_table_bytes=("total_table_bytes", "sum"),
        total_column_count=("column_count", "sum"),
        commented_table_count=(
            "table_comment",
            lambda values: int(values.fillna("").astype(str).str.strip().ne("").sum()),
        ),
        sample_table_names=("table_name", summarize_table_names),
        example_table_comment=("table_comment", first_comment),
    )
    summary["size_pretty"] = summary["total_table_bytes"].map(format_bytes)
    summary = summary[
        [
            "library",
            "table_count",
            "total_estimated_rows",
            "total_table_bytes",
            "size_pretty",
            "total_column_count",
            "commented_table_count",
            "sample_table_names",
            "example_table_comment",
        ]
    ].sort_values(["total_table_bytes", "library"], ascending=[False, True])
    summary.to_csv(OUTPUT_PATH, index=False)

    print(f"Wrote {len(summary)} rows to {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
