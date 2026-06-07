"""Export one row per canonical WRDS PostgreSQL column."""

from __future__ import annotations

import pandas as pd
import wrds

from catalog_exports.wrds_connection import (
    PROJECT_ROOT,
    connect_wrds,
    fetch_canonical_libraries,
)

OUTPUT_PATH = PROJECT_ROOT / "outputs" / "postgres_columns.csv"


def fetch_column_catalog(db: wrds.Connection, libraries: list[str]) -> pd.DataFrame:
    """Fetch one row per canonical PostgreSQL column."""

    query = """
        select
            n.nspname as library,
            c.relname as table_name,
            a.attnum as ordinal_position,
            a.attname as column_name,
            format_type(a.atttypid, a.atttypmod) as data_type,
            not a.attnotnull as nullable,
            pg_get_expr(def.adbin, def.adrelid) as column_default,
            col_description(c.oid, a.attnum) as column_comment
        from pg_attribute a
        join pg_class c
            on c.oid = a.attrelid
        join pg_namespace n
            on n.oid = c.relnamespace
        left join pg_attrdef def
            on def.adrelid = a.attrelid
           and def.adnum = a.attnum
        where n.nspname = any(%(libraries)s)
          and c.relkind = 'r'
          and a.attnum > 0
          and not a.attisdropped
        order by n.nspname, c.relname, a.attnum
    """
    return db.raw_sql(query, params={"libraries": libraries})


def main() -> None:
    """Write the canonical column catalog to `outputs/postgres_columns.csv`."""

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = connect_wrds()
    try:
        canonical_libraries = fetch_canonical_libraries(db=db)
        column_catalog = fetch_column_catalog(db=db, libraries=canonical_libraries)
    finally:
        db.close()

    column_catalog["ordinal_position"] = pd.to_numeric(
        column_catalog["ordinal_position"],
        errors="coerce",
    ).fillna(0).astype(int)
    column_catalog["nullable"] = column_catalog["nullable"].fillna(False).astype(bool)
    column_catalog.to_csv(OUTPUT_PATH, index=False)

    print(f"Wrote {len(column_catalog)} rows to {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
