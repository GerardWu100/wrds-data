"""Shared WRDS sample exporter for full-library table discovery."""

from __future__ import annotations

from pathlib import Path
import sys
import tomllib
from typing import Any, Iterable

import wrds

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    # Support direct script execution via `uv run library_samples/export_small_samples.py`.
    sys.path.insert(0, str(PROJECT_ROOT))

from catalog_exports.wrds_connection import (
    connect_wrds,
    fetch_small_table_sample,
)

CONFIG_PATH = PROJECT_ROOT / "library_samples" / "config.toml"
CONFIG_LIBRARY_KEY = "libraries"
CONFIG_ROW_LIMIT_KEY = "row_limit"
DEFAULT_ROW_LIMIT = 10


def load_export_config(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Return the sample export configuration loaded from TOML."""

    with config_path.open("rb") as config_file:
        return tomllib.load(config_file)


def parse_row_limit(config: dict[str, Any]) -> int:
    """Return the configured row limit with basic validation."""

    row_limit = config.get(CONFIG_ROW_LIMIT_KEY, DEFAULT_ROW_LIMIT)
    if not isinstance(row_limit, int) or row_limit <= 0:
        message = "Config key `row_limit` must be a positive integer."
        raise ValueError(message)
    return row_limit


def normalize_library_names(libraries: Iterable[str]) -> list[str]:
    """Return stripped unique library names in stable order."""

    normalized_libraries: list[str] = []
    seen_libraries: set[str] = set()

    for library in libraries:
        normalized_library = library.strip()
        if not normalized_library:
            continue
        if normalized_library in seen_libraries:
            continue
        seen_libraries.add(normalized_library)
        normalized_libraries.append(normalized_library)

    return normalized_libraries


def parse_libraries(config: dict[str, Any]) -> list[str]:
    """Return the configured library names with validation."""

    libraries = config.get(CONFIG_LIBRARY_KEY)
    if not isinstance(libraries, list):
        message = "Config key `libraries` must be a TOML array of strings."
        raise ValueError(message)
    if not all(isinstance(library, str) for library in libraries):
        message = "Every item in config key `libraries` must be a string."
        raise ValueError(message)

    normalized_libraries = normalize_library_names(libraries=libraries)
    if not normalized_libraries:
        message = "Config key `libraries` must contain at least one library name."
        raise ValueError(message)
    return normalized_libraries


def build_output_path(library: str, table_name: str) -> Path:
    """Return the CSV path for one sampled WRDS table."""

    return PROJECT_ROOT / "library_samples" / library / f"{table_name}.csv"


def fetch_table_names(db: wrds.Connection, library: str) -> list[str]:
    """Return all live PostgreSQL table names for one WRDS library."""

    return sorted(db.list_tables(library=library))


def export_table_sample(
    db: wrds.Connection,
    library: str,
    table_name: str,
    row_limit: int,
) -> Path:
    """Export one tiny table sample into the library's subfolder."""

    output_path = build_output_path(library=library, table_name=table_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sample = fetch_small_table_sample(
        db=db,
        library=library,
        table_name=table_name,
        row_limit=row_limit,
    )
    sample.to_csv(output_path, index=False)
    return output_path


def export_library_samples(
    db: wrds.Connection,
    library: str,
    row_limit: int,
) -> list[Path]:
    """Export one tiny CSV per live table for one WRDS library."""

    output_paths: list[Path] = []
    table_names = fetch_table_names(db=db, library=library)
    print(f"Exporting {len(table_names)} tables from {library}")

    for table_name in table_names:
        output_path = export_table_sample(
            db=db,
            library=library,
            table_name=table_name,
            row_limit=row_limit,
        )
        output_paths.append(output_path)

    return output_paths


def export_samples_for_libraries(
    libraries: Iterable[str],
    row_limit: int = DEFAULT_ROW_LIMIT,
) -> list[Path]:
    """Export tiny CSV samples for every live table in each requested library."""

    normalized_libraries = normalize_library_names(libraries=libraries)
    output_paths: list[Path] = []

    db = connect_wrds()
    try:
        for library in normalized_libraries:
            output_paths.extend(
                export_library_samples(
                    db=db,
                    library=library,
                    row_limit=row_limit,
                )
            )
    finally:
        db.close()

    return output_paths


def export_samples_from_config(config_path: Path = CONFIG_PATH) -> list[Path]:
    """Export tiny CSV samples using the TOML config file."""

    config = load_export_config(config_path=config_path)
    libraries = parse_libraries(config=config)
    row_limit = parse_row_limit(config=config)
    return export_samples_for_libraries(
        libraries=libraries,
        row_limit=row_limit,
    )


def main() -> None:
    """Export tiny CSV samples using `library_samples/config.toml`."""

    output_paths = export_samples_from_config()
    for output_path in output_paths:
        relative_output = output_path.relative_to(PROJECT_ROOT)
        print(f"Wrote {relative_output}")


if __name__ == "__main__":
    main()
