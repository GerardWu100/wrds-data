"""Shared WRDS connection helpers for catalog and sample exports."""

from __future__ import annotations

import os
from pathlib import Path
import re

import pandas as pd
import wrds

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PGPASS_PATH = PROJECT_ROOT / ".pgpass"
PGPASS_FIELD_COUNT = 5
PGPASS_USERNAME_INDEX = 3
VALID_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def read_wrds_username(pgpass_path: Path = PGPASS_PATH) -> str:
    """Return the WRDS username stored in the project-local `.pgpass` file."""

    pgpass_line = pgpass_path.read_text(encoding="utf-8").strip()
    fields = pgpass_line.split(":")
    if len(fields) != PGPASS_FIELD_COUNT:
        message = (
            "Expected .pgpass to contain 5 colon-separated fields: "
            "host:port:database:user:password"
        )
        raise ValueError(message)
    return fields[PGPASS_USERNAME_INDEX]


def connect_wrds() -> wrds.Connection:
    """Open a WRDS connection using the project-local `.pgpass` file."""

    os.environ["PGPASSFILE"] = str(PGPASS_PATH)
    wrds_username = read_wrds_username()
    print(f"Connecting to WRDS as {wrds_username}")
    return wrds.Connection(wrds_username=wrds_username)


def fetch_canonical_libraries(db: wrds.Connection) -> list[str]:
    """Return table-backed libraries and exclude view-only alias schemas."""

    visible_libraries = db.list_libraries()
    query = """
        select
            n.nspname as library,
            count(*) filter (where c.relkind = 'r') as table_count
        from pg_namespace n
        left join pg_class c
            on c.relnamespace = n.oid
        where n.nspname = any(%(libraries)s)
        group by n.nspname
        having count(*) filter (where c.relkind = 'r') > 0
        order by n.nspname
    """
    result = db.raw_sql(query, params={"libraries": visible_libraries})
    return result["library"].tolist()


def quote_identifier(identifier: str) -> str:
    """Return a safely quoted PostgreSQL identifier for simple WRDS names."""

    if not VALID_IDENTIFIER_PATTERN.fullmatch(identifier):
        message = f"Unsupported SQL identifier: {identifier}"
        raise ValueError(message)
    return f'"{identifier}"'


def fetch_small_table_sample(
    db: wrds.Connection,
    library: str,
    table_name: str,
    row_limit: int,
) -> pd.DataFrame:
    """Fetch a tiny sample from one WRDS table."""

    library_identifier = quote_identifier(library)
    table_identifier = quote_identifier(table_name)
    query = (
        f"select * from {library_identifier}.{table_identifier} "
        f"limit {row_limit}"
    )
    return db.raw_sql(query)
