"""Export one row per canonical WRDS PostgreSQL table."""

from __future__ import annotations

import pandas as pd
import wrds

from catalog_exports.wrds_connection import (
    PROJECT_ROOT,
    connect_wrds,
    fetch_canonical_libraries,
)

OUTPUT_PATH = PROJECT_ROOT / "outputs" / "postgres_tables.csv"
BYTES_PER_KIB = 1024
BYTES_PER_MIB = 1024 * 1024
BYTES_PER_GIB = 1024 * 1024 * 1024


def format_bytes(byte_count: int) -> str:
    """Format a byte count into a compact human-readable string."""

    if byte_count >= BYTES_PER_GIB:
        return f"{byte_count / BYTES_PER_GIB:.2f} GiB"
    if byte_count >= BYTES_PER_MIB:
        return f"{byte_count / BYTES_PER_MIB:.2f} MiB"
    if byte_count >= BYTES_PER_KIB:
        return f"{byte_count / BYTES_PER_KIB:.2f} KiB"
    return f"{byte_count} B"


def fetch_table_catalog(db: wrds.Connection, libraries: list[str]) -> pd.DataFrame:
    """Fetch one row per canonical PostgreSQL table."""

    query = """
        select
            n.nspname as library,
            c.relname as table_name,
            coalesce(nullif(c.reltuples, -1), 0)::bigint as estimated_rows,
            pg_total_relation_size(c.oid) as total_table_bytes,
            cols.column_count,
            pk.primary_key_columns,
            obj_description(c.oid, 'pg_class') as table_comment
        from pg_class c
        join pg_namespace n
            on n.oid = c.relnamespace
        left join (
            select
                a.attrelid,
                count(*) as column_count
            from pg_attribute a
            where a.attnum > 0
              and not a.attisdropped
            group by a.attrelid
        ) cols
            on cols.attrelid = c.oid
        left join lateral (
            select string_agg(att.attname, ', ' order by key.ordinality)
                as primary_key_columns
            from pg_constraint con
            join unnest(con.conkey) with ordinality as key(attnum, ordinality)
                on true
            join pg_attribute att
                on att.attrelid = con.conrelid
               and att.attnum = key.attnum
            where con.conrelid = c.oid
              and con.contype = 'p'
        ) pk
            on true
        where n.nspname = any(%(libraries)s)
          and c.relkind = 'r'
        order by n.nspname, c.relname
    """
    return db.raw_sql(query, params={"libraries": libraries})


def main() -> None:
    """Write the canonical table catalog to `outputs/postgres_tables.csv`."""

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = connect_wrds()
    try:
        canonical_libraries = fetch_canonical_libraries(db=db)
        table_catalog = fetch_table_catalog(db=db, libraries=canonical_libraries)
    finally:
        db.close()

    table_catalog["estimated_rows"] = pd.to_numeric(
        table_catalog["estimated_rows"],
        errors="coerce",
    ).fillna(0).astype(int)
    table_catalog["total_table_bytes"] = pd.to_numeric(
        table_catalog["total_table_bytes"],
        errors="coerce",
    ).fillna(0).astype(int)
    table_catalog["column_count"] = pd.to_numeric(
        table_catalog["column_count"],
        errors="coerce",
    ).fillna(0).astype(int)
    table_catalog["size_pretty"] = table_catalog["total_table_bytes"].map(format_bytes)

    table_catalog = table_catalog[
        [
            "library",
            "table_name",
            "estimated_rows",
            "total_table_bytes",
            "column_count",
            "primary_key_columns",
            "table_comment",
            "size_pretty",
        ]
    ]
    table_catalog.to_csv(OUTPUT_PATH, index=False)

    print(f"Wrote {len(table_catalog)} rows to {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
