"""Regression tests for the BoardEx Parquet downloader."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from boardex_parquet import download_to_parquet


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "boardex_parquet" / "config.toml"
POSTGRES_TABLES_PATH = PROJECT_ROOT / "outputs" / "postgres_tables.csv"


class BoardexParquetConfigTests(unittest.TestCase):
    """Check that the shipped config matches the approved selected bundle."""

    def test_default_config_matches_expected_enabled_libraries(self) -> None:
        """The current default should keep the intended three enabled libraries."""

        with CONFIG_PATH.open("rb") as fh:
            config = tomllib.load(fh)

        self.assertEqual(config["loader"]["sample_csv_rows"], 0)

        expected_enabled_libraries = {
            "boardex_na",
            "ciq_pplintel",
            "wrdsapps_plink_boardex_ciq",
        }
        enabled_libraries = {
            library_name
            for library_name, library_config in config["libraries"].items()
            if library_config.get("enabled", True)
        }
        self.assertEqual(enabled_libraries, expected_enabled_libraries)

        for library_name in expected_enabled_libraries:
            library_config = config["libraries"][library_name]
            self.assertFalse(library_config["download_all_tables"])

    def test_default_config_selects_expected_table_counts(self) -> None:
        """The restored default should resolve to the intended 35-table bundle."""

        with CONFIG_PATH.open("rb") as fh:
            config = tomllib.load(fh)

        available_tables_by_library: dict[str, list[str]] = {}
        with POSTGRES_TABLES_PATH.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                available_tables_by_library.setdefault(row["library"], []).append(
                    row["table_name"]
                )

        selected_counts: dict[str, int] = {}

        for library_name, library_config in config["libraries"].items():
            if not library_config.get("enabled", True):
                continue

            selected_tables = download_to_parquet.select_tables_from_library_config(
                available_tables=sorted(available_tables_by_library[library_name]),
                lib_cfg=library_config,
                library_name=library_name,
            )

            selected_counts[library_name] = len(selected_tables)

        self.assertEqual(
            selected_counts,
            {
                "boardex_na": 26,
                "ciq_pplintel": 7,
                "wrdsapps_plink_boardex_ciq": 2,
            },
        )
        self.assertEqual(sum(selected_counts.values()), 35)

    def test_default_config_pins_the_exact_selected_table_bundle(self) -> None:
        """The shipped default should name the exact 35 tables explicitly."""

        with CONFIG_PATH.open("rb") as fh:
            config = tomllib.load(fh)

        expected_tables = {
            "boardex_na": [
                "na_board_characteristics",
                "na_board_dir_announcements",
                "na_board_dir_committees",
                "na_board_education_assoc",
                "na_board_listed_assoc",
                "na_board_nfp_assoc",
                "na_board_other_assoc",
                "na_board_unlisted_assoc",
                "na_company_profile_advisors",
                "na_company_profile_details",
                "na_company_profile_market_cap",
                "na_company_profile_sr_mgrs",
                "na_company_profile_stocks",
                "na_dir_characteristics",
                "na_dir_profile_achievements",
                "na_dir_profile_details",
                "na_dir_profile_education",
                "na_dir_profile_emp",
                "na_dir_profile_other_activ",
                "na_wrds_company_dir_names",
                "na_wrds_company_names",
                "na_wrds_company_networks",
                "na_wrds_company_profile",
                "na_wrds_company_region",
                "na_wrds_org_composition",
                "na_wrds_org_summary",
            ],
            "wrdsapps_plink_boardex_ciq": [
                "boardex_ciq",
                "boardex_ciq_link",
            ],
            "ciq_pplintel": [
                "ciqperson",
                "ciqpersonbiography",
                "ciqprofessional",
                "ciqprofessionalcoverage",
                "ciqprofunction",
                "ciqprotoprofunction",
                "wrds_professional",
            ],
        }

        for library_name, expected_library_tables in expected_tables.items():
            library_config = config["libraries"][library_name]

            self.assertFalse(library_config["download_all_tables"])
            self.assertEqual(library_config.get("disabled_tables", []), [])
            self.assertEqual(
                library_config["enabled_tables"],
                expected_library_tables,
            )


class BoardexParquetSchemaTests(unittest.TestCase):
    """Check that schema construction is stable across sparse chunks."""

    def test_build_arrow_schema_from_postgres_columns(self) -> None:
        """Type mapping should preserve strings, integers, dates, and decimals."""

        columns = [
            {"column_name": "name", "data_type": "text", "nullable": True},
            {"column_name": "directorid", "data_type": "double precision", "nullable": True},
            {"column_name": "event_date", "data_type": "date", "nullable": True},
            {
                "column_name": "amount",
                "data_type": "numeric(12,2)",
                "nullable": True,
            },
        ]

        schema = download_to_parquet.build_arrow_schema_from_columns(columns)

        self.assertEqual(
            schema,
            pa.schema(
                [
                    pa.field("name", pa.string(), nullable=True),
                    pa.field("directorid", pa.float64(), nullable=True),
                    pa.field("event_date", pa.date32(), nullable=True),
                    pa.field("amount", pa.decimal128(12, 2), nullable=True),
                ]
            ),
        )

    def test_dataframe_to_arrow_table_uses_declared_string_schema_for_null_only_batch(
        self,
    ) -> None:
        """A null-only first batch should not lock a column into Arrow null type."""

        schema = pa.schema(
            [
                pa.field("biography", pa.string(), nullable=True),
                pa.field("personid", pa.int64(), nullable=True),
            ]
        )
        null_only_batch = pd.DataFrame(
            {
                "biography": [None, None],
                "personid": [1, 2],
            }
        )
        valued_batch = pd.DataFrame(
            {
                "biography": ["alpha", "beta"],
                "personid": [3, 4],
            }
        )

        first_table = download_to_parquet.dataframe_to_arrow_table(
            null_only_batch,
            schema,
        )
        second_table = download_to_parquet.dataframe_to_arrow_table(
            valued_batch,
            schema,
        )

        self.assertEqual(first_table.schema, schema)
        self.assertEqual(second_table.schema, schema)
        self.assertEqual(first_table.column("biography").type, pa.string())
        self.assertEqual(second_table.column("biography").type, pa.string())

    def test_dataframe_to_arrow_table_parses_string_dates_for_declared_date_schema(
        self,
    ) -> None:
        """WRDS date columns may arrive as strings and should still write as dates."""

        schema = pa.schema(
            [
                pa.field("annualreportdate", pa.date32(), nullable=True),
            ]
        )
        batch = pd.DataFrame(
            {
                "annualreportdate": ["2005-12-01", None],
            }
        )

        arrow_table = download_to_parquet.dataframe_to_arrow_table(batch, schema)

        self.assertEqual(arrow_table.schema, schema)
        self.assertEqual(
            arrow_table.column("annualreportdate").to_pylist(),
            [date(2005, 12, 1), None],
        )

    def test_dataframe_to_arrow_table_preserves_out_of_bounds_sentinel_dates(
        self,
    ) -> None:
        """BoardEx sentinel dates can exceed pandas nanosecond timestamp bounds."""

        schema = pa.schema(
            [
                pa.field("annualreportdate", pa.date32(), nullable=True),
            ]
        )
        batch = pd.DataFrame(
            {
                "annualreportdate": ["9000-01-01"],
            }
        )

        arrow_table = download_to_parquet.dataframe_to_arrow_table(batch, schema)

        self.assertEqual(
            arrow_table.column("annualreportdate").to_pylist(),
            [date(9000, 1, 1)],
        )


class BoardexParquetDownloadTests(unittest.TestCase):
    """Check safe output handling without touching WRDS."""

    def test_resume_overwrites_invalid_existing_parquet_file(self) -> None:
        """Resume mode should replace a corrupt output instead of skipping it."""

        config = {
            "loader": {
                "batch_size": 10,
                "sample_csv_rows": 0,
            }
        }
        batch = pd.DataFrame(
            {
                "personid": [1, 2],
                "biography": ["first", "second"],
            }
        )
        schema = pa.schema(
            [
                pa.field("personid", pa.int64(), nullable=True),
                pa.field("biography", pa.string(), nullable=True),
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            output_path = download_to_parquet.parquet_path(
                output_dir,
                "ciq_pplintel",
                "ciqpersonbiography",
            )
            output_path.write_bytes(b"not-a-real-parquet-file")

            with (
                mock.patch.object(
                    download_to_parquet,
                    "fetch_pg_row_count",
                    return_value=len(batch),
                ),
                mock.patch.object(
                    download_to_parquet,
                    "fetch_table_schema",
                    return_value=schema,
                ),
                mock.patch.object(
                    download_to_parquet,
                    "stream_table_batches",
                    return_value=iter([batch]),
                ),
            ):
                rows_written = download_to_parquet.download_table(
                    wrds_db=object(),
                    cfg=config,
                    library="ciq_pplintel",
                    table="ciqpersonbiography",
                    output_dir=output_dir,
                    resume=True,
                )

            self.assertEqual(rows_written, 2)
            self.assertTrue(download_to_parquet.is_complete_parquet_file(output_path))
            self.assertFalse(
                download_to_parquet.temporary_parquet_path(output_path).exists()
            )
            written_table = pq.read_table(output_path)
            self.assertEqual(written_table.schema, schema)
            self.assertEqual(written_table.num_rows, 2)


class BoardexParquetValidationTests(unittest.TestCase):
    """Check that derivation summaries match the measured results."""

    def test_interpretation_reports_full_match_for_recoverable_rows(self) -> None:
        """A full match should say that all checked rows were recoverable."""

        interpretation = download_to_parquet_validation_interpretation(
            matched_rows=2,
            checked_rows=2,
            ordered_sample=True,
        )

        self.assertEqual(
            interpretation,
            "All 2 checked rows were recoverable from smaller source tables.",
        )

    def test_interpretation_reports_partial_match_and_sampling_risk(self) -> None:
        """A partial match should not claim a universal conclusion."""

        interpretation = download_to_parquet_validation_interpretation(
            matched_rows=1,
            checked_rows=2,
            ordered_sample=False,
        )

        self.assertEqual(
            interpretation,
            "Only 1 of 2 checked rows were recoverable from smaller source "
            "tables. The sample uses an unordered LIMIT query, so reruns may "
            "inspect different rows.",
        )


def download_to_parquet_validation_interpretation(
    *,
    matched_rows: int,
    checked_rows: int,
    ordered_sample: bool,
) -> str:
    """Return the validator interpretation text for assertions in tests."""

    from boardex_parquet.validate_derivations import build_interpretation

    return build_interpretation(
        matched_rows=matched_rows,
        checked_rows=checked_rows,
        ordered_sample=ordered_sample,
    )


if __name__ == "__main__":
    unittest.main()
