"""Merge WRDS product metadata into the library catalog."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from catalog_exports.wrds_connection import PROJECT_ROOT

WRDS_DESCRIPTION_INPUT = PROJECT_ROOT / "docs" / "Wharton Research Data Services.csv"
WRDS_DOC_INPUT = (
    PROJECT_ROOT
    / "docs"
    / "wrds_accessible_datasets_with_doc_urls_and_simple_descriptions.csv"
)
LIBRARY_INPUT = PROJECT_ROOT / "outputs" / "postgres_libraries.csv"
LIBRARY_KEY_COLUMN = "library"
DESCRIPTION_COLUMN = "Description"
SIMPLE_DESCRIPTION_COLUMN = "Simple dataset description"
DATA_DICTIONARY_URL_COLUMN = "Data dictionary URL"
INSERTED_METADATA_COLUMNS = [
    DESCRIPTION_COLUMN,
    SIMPLE_DESCRIPTION_COLUMN,
    DATA_DICTIONARY_URL_COLUMN,
]
DESCRIPTION_INSERT_INDEX = 1


def normalize_join_key(values: pd.Series) -> pd.Series:
    """Return stripped string join keys with missing values preserved."""

    return values.astype("string").str.strip()


def load_lookup(input_path: Path, columns_to_keep: list[str]) -> pd.DataFrame:
    """Load a de-duplicated lookup table keyed by the first source column."""

    source_frame = pd.read_csv(input_path)
    source_key_column = source_frame.columns[0]

    lookup = source_frame[[source_key_column, *columns_to_keep]].copy()
    lookup[source_key_column] = normalize_join_key(lookup[source_key_column])
    lookup = lookup.drop_duplicates(subset=[source_key_column], keep="first")
    return lookup


def merge_lookup_columns(
    libraries: pd.DataFrame, input_path: Path, columns_to_keep: list[str]
) -> pd.DataFrame:
    """Left-join selected metadata columns into the library catalog."""

    lookup = load_lookup(input_path, columns_to_keep)
    source_key_column = lookup.columns[0]

    merged = libraries.drop(columns=columns_to_keep, errors="ignore").merge(
        lookup,
        left_on=LIBRARY_KEY_COLUMN,
        right_on=source_key_column,
        how="left",
    )
    return merged.drop(columns=[source_key_column])


def merge_descriptions() -> pd.DataFrame:
    """Return the library catalog with merged WRDS metadata columns."""

    libraries = pd.read_csv(LIBRARY_INPUT)
    libraries[LIBRARY_KEY_COLUMN] = normalize_join_key(libraries[LIBRARY_KEY_COLUMN])

    merged = merge_lookup_columns(
        libraries=libraries,
        input_path=WRDS_DESCRIPTION_INPUT,
        columns_to_keep=[DESCRIPTION_COLUMN],
    )
    merged = merge_lookup_columns(
        libraries=merged,
        input_path=WRDS_DOC_INPUT,
        columns_to_keep=[SIMPLE_DESCRIPTION_COLUMN, DATA_DICTIONARY_URL_COLUMN],
    )

    ordered_columns = merged.columns.tolist()
    for column_name in reversed(INSERTED_METADATA_COLUMNS):
        ordered_columns.insert(
            DESCRIPTION_INSERT_INDEX,
            ordered_columns.pop(ordered_columns.index(column_name)),
        )
    return merged[ordered_columns]


def main() -> None:
    """Write the enriched library catalog back to `outputs/postgres_libraries.csv`."""

    merged = merge_descriptions()
    merged.to_csv(LIBRARY_INPUT, index=False)

    relative_output = LIBRARY_INPUT.relative_to(PROJECT_ROOT)

    print(f"Wrote {len(merged)} rows to {relative_output}")
    for column_name in INSERTED_METADATA_COLUMNS:
        matched_count = int(merged[column_name].notna().sum())
        unmatched_count = int(merged[column_name].isna().sum())
        print(f"Matched {column_name}: {matched_count}")
        print(f"Unmatched {column_name}: {unmatched_count}")


if __name__ == "__main__":
    main()
