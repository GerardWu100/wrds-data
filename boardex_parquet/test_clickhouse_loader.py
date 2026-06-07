"""Tests for loading BoardEx Parquet pocket files into ClickHouse."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from datetime import date

import pyarrow as pa
import pyarrow.parquet as pq

from boardex_parquet import clickhouse_loader


class BoardexClickHouseLoaderTests(unittest.TestCase):
    """Check local planning and schema generation for ClickHouse loads."""

    def test_discover_parquet_files_returns_one_plan_per_pocket_file(self) -> None:
        """File names should map directly to stable ClickHouse table names."""

        schema = pa.schema([pa.field("personid", pa.int64(), nullable=True)])
        table = pa.table({"personid": [1, 2]}, schema=schema)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            pq.write_table(table, output_dir / "ciq_pplintel__ciqperson.parquet")
            pq.write_table(table, output_dir / "boardex_na__na_dir_profile_emp.parquet")
            (output_dir / "ignore.txt").write_text("not parquet", encoding="utf-8")

            plans = clickhouse_loader.discover_parquet_files(output_dir)

        self.assertEqual(
            [(plan.source_path.name, plan.target_table) for plan in plans],
            [
                ("boardex_na__na_dir_profile_emp.parquet", "boardex_na__na_dir_profile_emp"),
                ("ciq_pplintel__ciqperson.parquet", "ciq_pplintel__ciqperson"),
            ],
        )

    def test_arrow_schema_maps_to_nullable_clickhouse_columns(self) -> None:
        """Parquet types should become ClickHouse types that preserve nulls."""

        schema = pa.schema(
            [
                pa.field("personid", pa.int64(), nullable=True),
                pa.field("fullname", pa.string(), nullable=True),
                pa.field("active", pa.bool_(), nullable=True),
                pa.field("annualreportdate", pa.date32(), nullable=True),
                pa.field("mktcapitalisation", pa.decimal128(18, 4), nullable=True),
                pa.field("score", pa.float64(), nullable=False),
            ]
        )

        columns = clickhouse_loader.arrow_schema_to_clickhouse_columns(schema)

        self.assertEqual(
            columns,
            [
                ("personid", "Nullable(Int64)"),
                ("fullname", "Nullable(String)"),
                ("active", "Nullable(Bool)"),
                ("annualreportdate", "Nullable(String)"),
                ("mktcapitalisation", "Nullable(Decimal(18, 4))"),
                ("score", "Float64"),
            ],
        )

    def test_create_table_sql_quotes_names_and_uses_id_date_sort_key(self) -> None:
        """Generated DDL should quote identifiers and choose useful sort columns."""

        schema = pa.schema(
            [
                pa.field("directorid", pa.int64(), nullable=True),
                pa.field("annualreportdate", pa.date32(), nullable=True),
                pa.field("fullname", pa.string(), nullable=True),
            ]
        )

        sql = clickhouse_loader.create_table_sql(
            database="myclickhouse",
            table="boardex_na__na_dir_profile_emp",
            schema=schema,
        )

        self.assertIn("CREATE TABLE IF NOT EXISTS `myclickhouse`.`boardex_na__na_dir_profile_emp`", sql)
        self.assertIn("`directorid` Nullable(Int64)", sql)
        self.assertIn("`annualreportdate` Nullable(String)", sql)
        self.assertIn("ENGINE = MergeTree", sql)
        self.assertIn("ORDER BY (`directorid`, `annualreportdate`)", sql)

    def test_create_table_sql_allows_nullable_sort_key_columns(self) -> None:
        """Nullable Parquet fields should be valid in ClickHouse sort keys."""

        schema = pa.schema(
            [
                pa.field("directorid", pa.int64(), nullable=True),
                pa.field("annualreportdate", pa.date32(), nullable=True),
            ]
        )

        sql = clickhouse_loader.create_table_sql(
            database="myclickhouse",
            table="boardex_na__na_dir_profile_emp",
            schema=schema,
        )

        self.assertIn("ORDER BY (`directorid`, `annualreportdate`)", sql)
        self.assertIn("SETTINGS allow_nullable_key = 1", sql)

    def test_prepare_arrow_table_for_insert_preserves_sentinel_dates_as_strings(self) -> None:
        """BoardEx sentinel dates such as 9000-01-01 should load without truncation."""

        schema = pa.schema(
            [
                pa.field("annualreportdate", pa.date32(), nullable=True),
            ]
        )
        arrow_table = pa.table(
            {"annualreportdate": [date(2020, 1, 1), date(9000, 1, 1), None]},
            schema=schema,
        )

        prepared = clickhouse_loader.prepare_arrow_table_for_insert(arrow_table)

        self.assertEqual(prepared.schema.field("annualreportdate").type, pa.string())
        self.assertEqual(
            prepared.column("annualreportdate").to_pylist(),
            ["2020-01-01", "9000-01-01", None],
        )

    def test_replace_runtime_override_disables_resume(self) -> None:
        """Replace mode should rebuild a table even when config resume is true."""

        config = clickhouse_loader.AppConfig(
            clickhouse=clickhouse_loader.ClickHouseConfig(
                host="localhost",
                port=8123,
                username="default",
                password="",
                secure=False,
                database="myclickhouse",
            ),
            loader=clickhouse_loader.LoaderConfig(
                parquet_dir=Path("/tmp/parquet"),
                insert_batch_rows=100_000,
                create_database=True,
                replace=False,
                resume=True,
            ),
        )

        overridden = clickhouse_loader.with_runtime_overrides(
            config=config,
            replace_existing=True,
            resume_existing=None,
            parquet_dir=None,
        )

        self.assertTrue(overridden.loader.replace)
        self.assertFalse(overridden.loader.resume)

    def test_create_empty_tables_creates_schema_without_inserting_rows(self) -> None:
        """Schema creation should let users inspect empty ClickHouse tables."""

        schema = pa.schema([pa.field("directorid", pa.int64(), nullable=True)])
        arrow_table = pa.table({"directorid": [1, 2]}, schema=schema)

        class FakeClickHouseClient:
            """Record schema commands while reporting no existing tables."""

            def __init__(self) -> None:
                self.commands: list[str] = []
                self.inserted_tables: list[str] = []

            def command(self, sql: str) -> None:
                self.commands.append(sql)

            def query(self, sql: str) -> object:
                class QueryResult:
                    """Mimic the clickhouse-connect query result shape."""

                    result_rows = [(0,)]

                return QueryResult()

            def insert_arrow(self, table: str, arrow_table: pa.Table, database: str) -> None:
                self.inserted_tables.append(table)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            pq.write_table(arrow_table, output_dir / "boardex_na__na_dir_profile_emp.parquet")
            config = _test_app_config(output_dir)
            client = FakeClickHouseClient()

            results = clickhouse_loader.create_empty_tables(config, client)

        self.assertEqual(results[0].status, "created-empty")
        self.assertEqual(results[0].clickhouse_rows, 0)
        self.assertEqual(client.inserted_tables, [])
        self.assertIn("CREATE TABLE IF NOT EXISTS", client.commands[0])

    def test_load_tables_inserts_into_existing_empty_schema_table(self) -> None:
        """A prior schema-only run should not block the later data load."""

        schema = pa.schema([pa.field("directorid", pa.int64(), nullable=True)])
        arrow_table = pa.table({"directorid": [1, 2]}, schema=schema)

        class FakeClickHouseClient:
            """Report an empty existing table and count inserted Arrow rows."""

            def __init__(self) -> None:
                self.rows_inserted = 0
                self.commands: list[str] = []

            def command(self, sql: str) -> None:
                self.commands.append(sql)

            def query(self, sql: str) -> object:
                class QueryResult:
                    """Mimic the clickhouse-connect query result shape."""

                    def __init__(self, value: int) -> None:
                        self.result_rows = [(value,)]

                if "system.tables" in sql:
                    return QueryResult(1)
                return QueryResult(self.rows_inserted)

            def insert_arrow(self, table: str, arrow_table: pa.Table, database: str) -> None:
                self.rows_inserted += arrow_table.num_rows

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            pq.write_table(arrow_table, output_dir / "boardex_na__na_dir_profile_emp.parquet")
            config = _test_app_config(output_dir)
            client = FakeClickHouseClient()

            results = clickhouse_loader.load_tables(config, client)

        self.assertEqual(results[0].status, "loaded")
        self.assertEqual(results[0].parquet_rows, 2)
        self.assertEqual(results[0].clickhouse_rows, 2)
        self.assertEqual(client.rows_inserted, 2)


def _test_app_config(parquet_dir: Path) -> clickhouse_loader.AppConfig:
    """Return a minimal loader config for local ClickHouse loader tests."""

    return clickhouse_loader.AppConfig(
        clickhouse=clickhouse_loader.ClickHouseConfig(
            host="localhost",
            port=8123,
            username="default",
            password="",
            secure=False,
            database="myclickhouse",
        ),
        loader=clickhouse_loader.LoaderConfig(
            parquet_dir=parquet_dir,
            insert_batch_rows=100_000,
            create_database=True,
            replace=False,
            resume=True,
        ),
    )


if __name__ == "__main__":
    unittest.main()
