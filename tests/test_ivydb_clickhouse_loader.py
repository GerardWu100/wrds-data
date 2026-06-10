"""Tests for the IvyDB WRDS-to-ClickHouse loader.

The tests use tiny in-memory examples and fake clients instead of live WRDS or
ClickHouse connections. This keeps the loader's planning, curated schema setup,
direct-load orchestration, and SQL construction testable without network
credentials.
"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch


class IvydbClickhouseConfigTests(unittest.TestCase):
    """Check TOML parsing and user-facing run grouping."""

    def test_default_config_starts_with_reference_batch(self) -> None:
        """The shipped config should default to batch 1: reference tables only."""

        from ivydb.clickhouse_loader.config import default_config

        config = default_config()
        static_sources = [table.source_table for table in config.static_tables]

        self.assertEqual(config.option_price_years, [])
        self.assertEqual(config.underlying_price_years, [])
        self.assertEqual(
            static_sources,
            ["securd", "secnmd", "exchgd", "distrd", "opinfd", "opcrsphist"],
        )

    def test_load_config_reads_default_groups_and_years(self) -> None:
        """Config parsing should expose the default split between load runs."""

        from ivydb.clickhouse_loader.config import load_config

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    [clickhouse]
                    host = "localhost"
                    port = 8123
                    username = "default"
                    password = ""
                    secure = false
                    database = "ivydb"

                    [tables.option_prices]
                    enabled = true
                    source_library = "optionm_all"
                    source_prefix = "opprcd"
                    years = [2024, 2025]
                    target_template = "opprcd{year}"

                    [tables.underlying_prices]
                    enabled = true
                    source_library = "optionm_all"
                    source_prefix = "secprd"
                    years = [2023]
                    target_table = "secprd"
                    source_year_column = "source_year"

                    [tables.static_reference]
                    enabled = true
                    tables = [
                        "opinfd",
                        { source_library = "wrdsapps_link_crsp_optionm", source_table = "opcrsphist", target_table = "opcrsphist" },
                    ]
                    """
                ),
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.clickhouse.database, "ivydb")
        self.assertEqual(config.option_price_years, [2024, 2025])
        self.assertEqual(config.underlying_price_years, [2023])
        self.assertEqual(config.static_tables[0].source_table, "opinfd")
        self.assertEqual(config.static_tables[-1].source_table, "opcrsphist")

    def test_clickhouse_connection_settings_can_come_from_environment(self) -> None:
        """Environment variables should override local ClickHouse TOML credentials."""

        from ivydb.clickhouse_loader.config import load_config

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    [clickhouse]
                    host = "toml-host"
                    port = 8123
                    username = "toml_user"
                    password = "toml-password"
                    secure = false
                    database = "toml_db"

                    [tables.option_prices]
                    enabled = false

                    [tables.underlying_prices]
                    enabled = false

                    [tables.static_reference]
                    enabled = false
                    tables = []
                    """
                ),
                encoding="utf-8",
            )

            env = {
                "IVYDB_CLICKHOUSE_HOST": "docker-clickhouse",
                "IVYDB_CLICKHOUSE_PORT": "8124",
                "IVYDB_CLICKHOUSE_USERNAME": "ivydb_user",
                "IVYDB_CLICKHOUSE_PASSWORD": "env-password",
                "IVYDB_CLICKHOUSE_SECURE": "true",
                "IVYDB_CLICKHOUSE_DATABASE": "ivydb",
            }
            with patch.dict("os.environ", env, clear=True):
                config = load_config(config_path)

        self.assertEqual(config.clickhouse.host, "docker-clickhouse")
        self.assertEqual(config.clickhouse.port, 8124)
        self.assertEqual(config.clickhouse.username, "ivydb_user")
        self.assertEqual(config.clickhouse.password, "env-password")
        self.assertTrue(config.clickhouse.secure)
        self.assertEqual(config.clickhouse.database, "ivydb")

    def test_clickhouse_connection_settings_can_come_from_ivydb_env_file(self) -> None:
        """A project-local ivydb/.env file should supply Docker connection secrets."""

        from ivydb.clickhouse_loader.config import load_config

        with tempfile.TemporaryDirectory() as tmpdir:
            ivydb_dir = Path(tmpdir) / "ivydb"
            loader_dir = ivydb_dir / "clickhouse_loader"
            loader_dir.mkdir(parents=True)
            config_path = loader_dir / "config.toml"
            env_path = ivydb_dir / ".env"
            config_path.write_text(
                textwrap.dedent(
                    """
                    [clickhouse]
                    host = "toml-host"
                    port = 8123
                    username = "toml_user"
                    password = ""
                    secure = false
                    database = "toml_db"

                    [tables.option_prices]
                    enabled = false

                    [tables.underlying_prices]
                    enabled = false

                    [tables.static_reference]
                    enabled = false
                    tables = []
                    """
                ),
                encoding="utf-8",
            )
            env_path.write_text(
                textwrap.dedent(
                    """
                    IVYDB_CLICKHOUSE_HOST=localhost
                    IVYDB_CLICKHOUSE_PORT=8123
                    IVYDB_CLICKHOUSE_USERNAME=ivydb_user
                    IVYDB_CLICKHOUSE_PASSWORD=file-password
                    IVYDB_CLICKHOUSE_DATABASE=ivydb
                    IVYDB_CLICKHOUSE_SECURE=false
                    """
                ),
                encoding="utf-8",
            )

            with patch.dict("os.environ", {}, clear=True):
                config = load_config(config_path)

        self.assertEqual(config.clickhouse.host, "localhost")
        self.assertEqual(config.clickhouse.port, 8123)
        self.assertEqual(config.clickhouse.username, "ivydb_user")
        self.assertEqual(config.clickhouse.password, "file-password")
        self.assertFalse(config.clickhouse.secure)
        self.assertEqual(config.clickhouse.database, "ivydb")


class IvydbClickhouseTablePlanTests(unittest.TestCase):
    """Verify WRDS source tables map to the intended ClickHouse targets."""

    def test_config_plan_uses_only_enabled_static_tables(self) -> None:
        """A reference-only config should include only static/link tables."""

        from ivydb.clickhouse_loader.config import default_config
        from ivydb.clickhouse_loader.table_plan import build_table_plan_from_config

        config = default_config()
        plan = build_table_plan_from_config(config)

        source_tables = [table.source_table for table in plan]
        self.assertEqual(
            source_tables,
            ["securd", "secnmd", "exchgd", "distrd", "opinfd", "opcrsphist"],
        )

    def test_config_plan_uses_only_secprd_sources(self) -> None:
        """An underlying-only config should include only consolidated secprd sources."""

        from dataclasses import replace

        from ivydb.clickhouse_loader.config import default_config
        from ivydb.clickhouse_loader.table_plan import build_table_plan_from_config

        config = default_config()
        config = replace(
            config,
            underlying_prices=replace(config.underlying_prices, years=(2023, 2024)),
            static_tables=(),
        )
        plan = build_table_plan_from_config(config)

        source_tables = [table.source_table for table in plan]
        target_tables = {table.target_table for table in plan}

        self.assertEqual(source_tables, ["secprd2023", "secprd2024"])
        self.assertEqual(target_tables, {"secprd"})

    def test_config_plan_combines_enabled_families(self) -> None:
        """Multiple enabled families should appear together in one plan."""

        from dataclasses import replace

        from ivydb.clickhouse_loader.config import (
            StaticTableConfig,
            default_config,
        )
        from ivydb.clickhouse_loader.table_plan import build_table_plan_from_config

        config = default_config()
        config = replace(
            config,
            underlying_prices=replace(config.underlying_prices, years=(2024,)),
            static_tables=(
                StaticTableConfig("optionm_all", "opinfd", "opinfd"),
                StaticTableConfig("wrdsapps_link_crsp_optionm", "opcrsphist", "opcrsphist"),
            ),
        )
        plan = build_table_plan_from_config(config)

        source_tables = [table.source_table for table in plan]
        secprd_targets = {table.target_table for table in plan if table.source_prefix == "secprd"}

        self.assertEqual(source_tables, ["opinfd", "opcrsphist", "secprd2024"])
        self.assertEqual(secprd_targets, {"secprd"})

    def test_config_plan_uses_configured_option_years(self) -> None:
        """Option years in config.toml should define the opprcd load plan."""

        from dataclasses import replace

        from ivydb.clickhouse_loader.config import default_config
        from ivydb.clickhouse_loader.table_plan import build_table_plan_from_config

        config = default_config()
        config = replace(
            config,
            static_tables=(),
            option_prices=replace(
                config.option_prices,
                years=(2006, 2007, 2008, 2009, 2010),
            ),
        )
        plan = build_table_plan_from_config(config)

        source_tables = [table.source_table for table in plan]
        target_tables = [table.target_table for table in plan]

        self.assertEqual(
            source_tables,
            ["opprcd2006", "opprcd2007", "opprcd2008", "opprcd2009", "opprcd2010"],
        )
        self.assertEqual(
            target_tables,
            ["opprcd2006", "opprcd2007", "opprcd2008", "opprcd2009", "opprcd2010"],
        )


class IvydbClickhouseCreateTablesTests(unittest.TestCase):
    """Check create-tables planning for the two-step workflow."""

    def test_planned_create_tables_deduplicates_consolidated_secprd(self) -> None:
        """Underlying-price create planning should list secprd once."""

        from dataclasses import replace

        from ivydb.clickhouse_loader.config import default_config
        from ivydb.clickhouse_loader.create_tables import planned_create_table_names

        config = default_config()
        config = replace(
            config,
            underlying_prices=replace(config.underlying_prices, years=(2023, 2024)),
            static_tables=(),
        )
        table_names = planned_create_table_names(config)

        self.assertEqual(table_names, ["secprd"])

    def test_planned_create_tables_uses_configured_option_years(self) -> None:
        """Option create planning should follow the years list in config.toml."""

        from dataclasses import replace

        from ivydb.clickhouse_loader.config import default_config
        from ivydb.clickhouse_loader.create_tables import planned_create_table_names

        config = default_config()
        config = replace(
            config,
            static_tables=(),
            option_prices=replace(
                config.option_prices,
                years=(2006, 2007, 2008, 2009, 2010),
            ),
        )
        table_names = planned_create_table_names(config)

        self.assertEqual(
            table_names,
            ["opprcd2006", "opprcd2007", "opprcd2008", "opprcd2009", "opprcd2010"],
        )


class IvydbClickhouseSchemaTests(unittest.TestCase):
    """Check curated ClickHouse DDL for IvyDB target tables."""

    def test_direct_schema_setup_creates_compressed_tables_once_per_target(self) -> None:
        """Schema scripts should execute visible compressed DDL directly."""

        from dataclasses import replace

        from ivydb.clickhouse_loader.config import StaticTableConfig
        from ivydb.clickhouse_loader.config import default_config
        from ivydb.clickhouse_loader.create_option_price_tables import create_option_price_tables
        from ivydb.clickhouse_loader.create_reference_tables import create_reference_tables
        from ivydb.clickhouse_loader.create_security_price_tables import create_security_price_tables

        class FakeClickHouseClient:
            """Capture direct ClickHouse commands for schema setup tests."""

            def __init__(self) -> None:
                self.commands: list[str] = []

            def command(self, sql: str) -> None:
                self.commands.append(sql)

        config = default_config()
        config = replace(
            config,
            option_prices=replace(config.option_prices, years=(2024,)),
            underlying_prices=replace(config.underlying_prices, years=(2024, 2025)),
            static_tables=(StaticTableConfig("optionm_all", "opinfd", "opinfd"),),
        )
        fake_client = FakeClickHouseClient()

        option_tables = create_option_price_tables(fake_client, config)
        security_tables = create_security_price_tables(fake_client, config)
        reference_tables = create_reference_tables(fake_client, config)

        self.assertEqual(option_tables, ["opprcd2024"])
        self.assertEqual(security_tables, ["secprd"])
        self.assertEqual(reference_tables, ["opinfd"])
        self.assertEqual(len(fake_client.commands), 3)
        self.assertIn("CREATE TABLE IF NOT EXISTS `ivydb`.`opprcd2024`", fake_client.commands[0])
        self.assertIn("`secid` Nullable(UInt32) CODEC(ZSTD(6))", fake_client.commands[0])
        self.assertIn("`date` Nullable(Date32) CODEC(DoubleDelta, ZSTD(6))", fake_client.commands[0])
        self.assertIn(
            "`symbol` LowCardinality(Nullable(String)) CODEC(ZSTD(6))",
            fake_client.commands[0],
        )
        self.assertIn(
            "`cp_flag` Nullable(Enum8('C' = 1, 'P' = 2)) CODEC(ZSTD(6))",
            fake_client.commands[0],
        )
        self.assertIn(
            "ifNull(CAST(`cp_flag`, 'Nullable(Int8)'), toInt8(0))",
            fake_client.commands[0],
        )
        self.assertIn("`volume` Nullable(UInt32) CODEC(ZSTD(6))", fake_client.commands[0])
        self.assertIn("`open_interest` Nullable(UInt32) CODEC(ZSTD(6))", fake_client.commands[0])
        self.assertIn("`am_settlement` Nullable(UInt8) CODEC(ZSTD(6))", fake_client.commands[0])
        self.assertIn("`contract_size` Nullable(Int32) CODEC(ZSTD(6))", fake_client.commands[0])
        self.assertIn("`optionid` Nullable(UInt64) CODEC(Delta, ZSTD(6))", fake_client.commands[0])
        self.assertIn("`impl_volatility` Nullable(Decimal32(6)) CODEC(ZSTD(6))", fake_client.commands[0])
        self.assertIn("`delta` Nullable(Decimal32(6)) CODEC(ZSTD(6))", fake_client.commands[0])
        self.assertIn("`gamma` Nullable(Decimal32(6)) CODEC(ZSTD(6))", fake_client.commands[0])
        self.assertIn("`vega` Nullable(Decimal32(6)) CODEC(ZSTD(6))", fake_client.commands[0])
        self.assertIn("`theta` Nullable(Decimal32(6)) CODEC(ZSTD(6))", fake_client.commands[0])
        self.assertIn("`strike_price` Nullable(Float32) CODEC(ZSTD(6))", fake_client.commands[0])
        self.assertNotIn("forward_price", fake_client.commands[0])
        self.assertNotIn("`root`", fake_client.commands[0])
        self.assertNotIn("`suffix`", fake_client.commands[0])
        self.assertNotIn("allow_nullable_key", fake_client.commands[0])
        self.assertIn("CREATE TABLE IF NOT EXISTS `ivydb`.`secprd`", fake_client.commands[1])
        self.assertIn("`date` Nullable(Date32) CODEC(DoubleDelta, ZSTD(6))", fake_client.commands[1])
        self.assertIn("`close` Nullable(Float32) CODEC(ZSTD(6))", fake_client.commands[1])
        self.assertIn("`volume` Nullable(UInt64) CODEC(ZSTD(6))", fake_client.commands[1])
        self.assertNotIn("allow_nullable_key", fake_client.commands[1])
        self.assertIn("CREATE TABLE IF NOT EXISTS `ivydb`.`opinfd`", fake_client.commands[2])
        self.assertIn(
            "`exercise_style` LowCardinality(Nullable(String)) CODEC(ZSTD(6))",
            fake_client.commands[2],
        )

    def test_reference_schema_uses_double_delta_date_codec(self) -> None:
        """Reference tables should store dates with DoubleDelta plus ZSTD."""

        from dataclasses import replace

        from ivydb.clickhouse_loader.config import StaticTableConfig, default_config
        from ivydb.clickhouse_loader.create_reference_tables import create_reference_tables

        class FakeClickHouseClient:
            """Capture direct ClickHouse commands for schema setup tests."""

            def __init__(self) -> None:
                self.commands: list[str] = []

            def command(self, sql: str) -> None:
                self.commands.append(sql)

        config = default_config()
        config = replace(
            config,
            static_tables=(StaticTableConfig("optionm_all", "secnmd", "secnmd"),),
        )
        fake_client = FakeClickHouseClient()
        create_reference_tables(fake_client, config)
        self.assertIn(
            "`effect_date` Nullable(Date32) CODEC(DoubleDelta, ZSTD(6))",
            fake_client.commands[-1],
        )


class IvydbClickhouseWrdsSqlTests(unittest.TestCase):
    """Check PostgreSQL query construction."""

    def test_select_query_quotes_schema_table_and_columns(self) -> None:
        """Generated WRDS SQL should select explicit quoted columns."""

        from ivydb.clickhouse_loader.wrds_stream import build_select_query

        sql = build_select_query("optionm_all", "opprcd2024", ("secid", "date", "best_bid"))

        self.assertEqual(
            sql,
            'SELECT "secid", "date", "best_bid" FROM "optionm_all"."opprcd2024"',
        )

    def test_select_query_rejects_empty_column_list(self) -> None:
        """An empty column contract should fail before hitting WRDS."""

        from ivydb.clickhouse_loader.wrds_stream import build_select_query

        with self.assertRaisesRegex(ValueError, "no columns requested"):
            build_select_query("optionm_all", "opprcd2024", ())

    def test_option_source_columns_exclude_forward_price_root_suffix(self) -> None:
        """opprcd drops always-null forward_price and legacy root/suffix."""

        from ivydb.clickhouse_loader.source_columns import OPTION_PRICE_SOURCE_COLUMNS

        self.assertNotIn("forward_price", OPTION_PRICE_SOURCE_COLUMNS)
        self.assertNotIn("root", OPTION_PRICE_SOURCE_COLUMNS)
        self.assertNotIn("suffix", OPTION_PRICE_SOURCE_COLUMNS)
        self.assertEqual(len(OPTION_PRICE_SOURCE_COLUMNS), 23)


class IvydbClickhouseLoadTests(unittest.TestCase):
    """Check local load orchestration behavior with fake clients."""

    def option_price_plan(self) -> object:
        """Return a representative yearly option-price table plan."""

        from ivydb.clickhouse_loader.source_columns import OPTION_PRICE_SOURCE_COLUMNS
        from ivydb.clickhouse_loader.table_plan import TablePlan

        return TablePlan(
            source_library="optionm_all",
            source_table="opprcd2024",
            target_table="opprcd2024",
            source_prefix="opprcd",
            source_year=2024,
            load_group="option-prices",
            layout="separate_year_table",
            source_year_column=None,
            source_columns=OPTION_PRICE_SOURCE_COLUMNS,
        )

    def security_price_plan(self, year: int = 2024) -> object:
        """Return a representative consolidated security-price table plan."""

        from ivydb.clickhouse_loader.source_columns import SECURITY_PRICE_SOURCE_COLUMNS
        from ivydb.clickhouse_loader.table_plan import TablePlan

        return TablePlan(
            source_library="optionm_all",
            source_table=f"secprd{year}",
            target_table="secprd",
            source_prefix="secprd",
            source_year=year,
            load_group="underlying-prices",
            layout="consolidated_year_table",
            source_year_column="source_year",
            source_columns=SECURITY_PRICE_SOURCE_COLUMNS,
        )

    def config_with_audit_path(self, audit_path: Path) -> object:
        """Return loader config pointing at one audit log path."""

        from dataclasses import replace

        from ivydb.clickhouse_loader.config import default_config

        config = default_config()
        return replace(
            config,
            loader=replace(config.loader, audit_log_path=audit_path),
        )

    def config_with_failed_audit(self, table: object) -> object:
        """Return config whose audit log marks one source table as failed."""

        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            audit_path.write_text(
                json.dumps(
                    {
                        "source_library": table.source_library,
                        "source_table": table.source_table,
                        "target_table": table.target_table,
                        "status": "failed",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            return self.config_with_audit_path(audit_path)

    def config_with_complete_audit(self, table: object) -> object:
        """Return config whose audit log marks one source table as complete."""

        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            audit_path.write_text(
                json.dumps(
                    {
                        "source_library": table.source_library,
                        "source_table": table.source_table,
                        "target_table": table.target_table,
                        "status": "complete",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            return self.config_with_audit_path(audit_path)

    class QueryResult:
        """Mimic clickhouse-connect query results."""

        def __init__(self, value: int) -> None:
            self.result_rows = [(value,)]

    class RecordingClient:
        """Fake ClickHouse client that records commands."""

        def __init__(self) -> None:
            self.commands: list[str] = []
            self.inserted_tables: list[str] = []

        def command(self, sql: str) -> None:
            self.commands.append(sql)

        def insert_df(self, table: str, df: object, database: str) -> None:
            self.inserted_tables.append(table)

        def query(self, sql: str) -> object:
            return IvydbClickhouseLoadTests.QueryResult(0)

    def recording_client(self) -> RecordingClient:
        """Return a fresh command-recording fake client."""

        return self.RecordingClient()

    def empty_existing_target_client(self, target_table: str) -> RecordingClient:
        """Return a fake client with an empty pre-created final table."""

        client = self.RecordingClient()

        def query(sql: str) -> object:
            if "system.tables" in sql and target_table in sql:
                return self.QueryResult(1)
            if f"FROM `ivydb`.`{target_table}`" in sql:
                return self.QueryResult(0)
            return self.QueryResult(0)

        client.query = query  # type: ignore[method-assign]
        return client

    def missing_target_client(self) -> RecordingClient:
        """Return a fake client with no pre-created target table."""

        client = self.RecordingClient()

        def query(sql: str) -> object:
            if "system.tables" in sql:
                return self.QueryResult(0)
            return self.QueryResult(0)

        client.query = query  # type: ignore[method-assign]
        return client

    def test_split_dataframe_for_insert_uses_configured_batch_size(self) -> None:
        """ClickHouse insert batching should split large WRDS chunks."""

        import pandas as pd

        from ivydb.clickhouse_loader.load_to_clickhouse import split_dataframe_for_insert

        dataframe = pd.DataFrame({"secid": [1, 2, 3, 4, 5]})
        batches = list(split_dataframe_for_insert(dataframe, insert_size=2))

        self.assertEqual([len(batch) for batch in batches], [2, 2, 1])

    def test_resume_skips_audited_source_table(self) -> None:
        """Resume mode should read the local audit log before reloading."""

        from ivydb.clickhouse_loader.config import default_config
        from ivydb.clickhouse_loader.load_to_clickhouse import load_tables
        from ivydb.clickhouse_loader.source_columns import OPTION_PRICE_SOURCE_COLUMNS
        from ivydb.clickhouse_loader.table_plan import TablePlan

        class FakeClickHouseClient:
            """Minimal fake that reports one audited source table."""

            commands: list[str]
            inserts: list[str]

            def __init__(self) -> None:
                self.commands = []
                self.inserts = []

            def command(self, sql: str) -> None:
                self.commands.append(sql)

            def insert_df(self, table: str, df: object, database: str) -> None:
                self.inserts.append(table)

        table = TablePlan(
            source_library="optionm_all",
            source_table="opprcd2024",
            target_table="opprcd2024",
            source_prefix="opprcd",
            source_year=2024,
            load_group="option-prices",
            layout="separate_year_table",
            source_year_column=None,
            source_columns=OPTION_PRICE_SOURCE_COLUMNS,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "ivydb_load_audit.jsonl"
            audit_record = {
                "source_library": "optionm_all",
                "source_table": "opprcd2024",
                "target_table": "opprcd2024",
                "layout": "separate_year_table",
                "source_year": 2024,
                "status": "complete",
                "rows_inserted": 123,
                "started_at": "2026-05-18T00:00:00+00:00",
                "completed_at": "2026-05-18T00:00:01+00:00",
                "error_message": "",
            }
            audit_path.write_text(json.dumps(audit_record) + "\n", encoding="utf-8")
            config = default_config()
            config = replace(
                config,
                loader=replace(config.loader, audit_log_path=audit_path),
            )

            results = load_tables(
                config=config,
                wrds_connection=object(),
                clickhouse_client=FakeClickHouseClient(),
                table_plan=[table],
            )

        self.assertEqual(results[0].source_table, "opprcd2024")
        self.assertEqual(results[0].rows_loaded, 0)

    def test_resume_uses_latest_matching_audit_status(self) -> None:
        """A later failed load attempt should prevent an old complete row from skipping."""

        from ivydb.clickhouse_loader.load_to_clickhouse import _local_audit_latest_status

        table = self.security_price_plan(2024)

        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            complete_record = {
                "source_library": "optionm_all",
                "source_table": "secprd2024",
                "target_table": "secprd",
                "layout": "consolidated_year_table",
                "source_year": 2024,
                "status": "complete",
            }
            failed_record = {
                "source_library": "optionm_all",
                "source_table": "secprd2024",
                "target_table": "secprd",
                "layout": "consolidated_year_table",
                "source_year": 2024,
                "status": "failed",
            }
            audit_path.write_text(
                json.dumps(complete_record) + "\n" + json.dumps(failed_record) + "\n",
                encoding="utf-8",
            )

            latest_status = _local_audit_latest_status(audit_path, table)

        self.assertEqual(latest_status, "failed")

    def test_successful_load_writes_local_audit_without_clickhouse_audit_table(self) -> None:
        """Load completion should be audited locally without creating a ClickHouse audit table."""

        import pandas as pd

        from ivydb.clickhouse_loader.load_to_clickhouse import load_tables

        table = self.option_price_plan()
        chunk = pd.DataFrame(
            {
                "secid": [101.0, 101.0],
                "date": ["2024-01-02", "2024-01-03"],
                "symbol": ["AAPL240119C00100000", None],
                "volume": [1.0, 2.0],
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "ivydb_load_audit.jsonl"
            config = self.config_with_audit_path(audit_path)
            client = self.empty_existing_target_client("opprcd2024")

            with patch(
                "ivydb.clickhouse_loader.load_to_clickhouse.stream_table",
                return_value=[chunk],
            ):
                results = load_tables(
                    config=config,
                    wrds_connection=object(),
                    clickhouse_client=client,
                    table_plan=[table],
                )

            audit_rows = [
                json.loads(line)
                for line in audit_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(results[0].rows_loaded, 2)
        self.assertEqual(
            [audit_row["status"] for audit_row in audit_rows],
            ["started", "complete"],
        )
        self.assertEqual(audit_rows[1]["rows_inserted"], 2)
        self.assertEqual(client.inserted_tables, ["opprcd2024"])
        self.assertFalse(any("_load_audit" in command for command in client.commands))

    def test_failed_load_records_failure_and_stops_before_later_source(self) -> None:
        """A handled insert failure should abort the batch without loading later sources."""

        import pandas as pd

        from ivydb.clickhouse_loader.load_to_clickhouse import load_tables

        first_table = replace(
            self.option_price_plan(),
            source_table="opprcd2023",
            target_table="opprcd2023",
            source_year=2023,
        )
        later_table = self.option_price_plan()

        class FailingClient(self.RecordingClient):
            """Fail the first attempted insert while keeping query behavior visible."""

            def query(self, sql: str) -> object:
                if "system.tables" in sql:
                    return IvydbClickhouseLoadTests.QueryResult(1)
                return IvydbClickhouseLoadTests.QueryResult(0)

            def insert_df(self, table: str, df: object, database: str) -> None:
                raise RuntimeError("insertion stopped")

        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            config = self.config_with_audit_path(audit_path)
            with patch(
                "ivydb.clickhouse_loader.load_to_clickhouse.stream_table",
                return_value=[pd.DataFrame({"secid": [101.0], "volume": [1.0]})],
            ) as mocked_stream:
                with self.assertRaisesRegex(RuntimeError, "insertion stopped"):
                    load_tables(
                        config=config,
                        wrds_connection=object(),
                        clickhouse_client=FailingClient(),
                        table_plan=[first_table, later_table],
                    )

            statuses = [
                json.loads(line)["status"]
                for line in audit_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(statuses, ["started", "failed"])
        mocked_stream.assert_called_once()

    def test_option_normalization_preserves_null_categories_and_casts_counts(self) -> None:
        """Nullable categories remain missing while integer-like fields are cast."""

        import pandas as pd

        from ivydb.clickhouse_loader.normalization import normalize_batch_for_clickhouse

        batch = pd.DataFrame(
            {
                "secid": [5139.0],
                "cp_flag": [None],
                "symbol_flag": ["1"],
                "ss_flag": ["0"],
                "volume": [21.0],
                "open_interest": [34.0],
                "optionid": [4001001.0],
                "contract_size": [100.0],
                "am_settlement": [0.0],
            }
        )

        result = normalize_batch_for_clickhouse(batch, self.option_price_plan())

        self.assertTrue(pd.isna(result.loc[0, "cp_flag"]))
        self.assertEqual(str(result["secid"].dtype), "UInt32")
        self.assertEqual(str(result["volume"].dtype), "UInt32")
        self.assertEqual(str(result["open_interest"].dtype), "UInt32")
        self.assertEqual(str(result["am_settlement"].dtype), "UInt8")
        self.assertEqual(str(result["optionid"].dtype), "UInt64")
        self.assertEqual(str(result["contract_size"].dtype), "Int32")

    def test_option_normalization_keeps_negative_contract_size_sentinel(self) -> None:
        """WRDS ``-99`` contract-size sentinels should be stored as signed integers."""

        import pandas as pd

        from ivydb.clickhouse_loader.normalization import normalize_batch_for_clickhouse

        result = normalize_batch_for_clickhouse(
            pd.DataFrame({"contract_size": [-99.0, 100.0]}),
            self.option_price_plan(),
        )

        self.assertEqual(str(result["contract_size"].dtype), "Int32")
        self.assertEqual(result["contract_size"].tolist(), [-99, 100])

    def test_option_normalization_still_rejects_negative_volume(self) -> None:
        """The signed ``contract_size`` sentinel rule must not loosen volume checks."""

        import pandas as pd

        from ivydb.clickhouse_loader.normalization import normalize_batch_for_clickhouse

        with self.assertRaisesRegex(ValueError, "volume.*whole non-negative"):
            normalize_batch_for_clickhouse(
                pd.DataFrame({"volume": [-99.0]}),
                self.option_price_plan(),
            )

    def test_option_normalization_converts_date_strings_to_python_dates(self) -> None:
        """ClickHouse Date32 columns should receive Python date objects, not strings."""

        from datetime import date

        import pandas as pd

        from ivydb.clickhouse_loader.normalization import normalize_batch_for_clickhouse

        batch = pd.DataFrame(
            {
                "date": ["2024-01-02", None],
                "exdate": ["2024-03-15", "2024-04-19"],
                "last_date": [None, "2024-01-03"],
            }
        )

        result = normalize_batch_for_clickhouse(batch, self.option_price_plan())

        self.assertEqual(result.loc[0, "date"], date(2024, 1, 2))
        self.assertIsNone(result.loc[1, "date"])
        self.assertEqual(result.loc[0, "exdate"], date(2024, 3, 15))
        self.assertEqual(result.loc[1, "last_date"], date(2024, 1, 3))

    def test_option_normalization_quantizes_greeks_to_decimal32_scale(self) -> None:
        """IV and Greeks should be fixed-point decimals with six decimal places."""

        from decimal import Decimal

        import pandas as pd

        from ivydb.clickhouse_loader.normalization import normalize_batch_for_clickhouse

        batch = pd.DataFrame(
            {
                "impl_volatility": [0.123456],
                "delta": [-0.500000],
                "gamma": [0.001234],
                "vega": [12.345678],
                "theta": [-1477.853027],
            }
        )

        result = normalize_batch_for_clickhouse(batch, self.option_price_plan())

        self.assertEqual(result.loc[0, "impl_volatility"], Decimal("0.123456"))
        self.assertEqual(result.loc[0, "delta"], Decimal("-0.500000"))
        self.assertEqual(result.loc[0, "gamma"], Decimal("0.001234"))
        self.assertEqual(result.loc[0, "vega"], Decimal("12.345678"))
        self.assertEqual(result.loc[0, "theta"], Decimal("-1477.853027"))

    def test_option_normalization_rejects_greeks_outside_decimal32_range(self) -> None:
        """Decimal32(6) cannot store values with magnitude above about 2147."""

        import pandas as pd

        from ivydb.clickhouse_loader.normalization import normalize_batch_for_clickhouse

        with self.assertRaisesRegex(ValueError, "theta.*Decimal32\\(6\\)"):
            normalize_batch_for_clickhouse(
                pd.DataFrame({"theta": [-2147.483649]}),
                self.option_price_plan(),
            )

    def test_option_normalization_rejects_fractional_volume(self) -> None:
        """Count columns cannot silently truncate a fractional WRDS value."""

        import pandas as pd

        from ivydb.clickhouse_loader.normalization import normalize_batch_for_clickhouse

        with self.assertRaisesRegex(ValueError, "volume.*whole non-negative"):
            normalize_batch_for_clickhouse(
                pd.DataFrame({"volume": [3.5]}),
                self.option_price_plan(),
            )

    def test_option_normalization_rejects_non_binary_am_settlement(self) -> None:
        """The AM-settlement flag must remain limited to the documented 0/1 values."""

        import pandas as pd

        from ivydb.clickhouse_loader.normalization import normalize_batch_for_clickhouse

        with self.assertRaisesRegex(ValueError, "am_settlement.*0/1"):
            normalize_batch_for_clickhouse(
                pd.DataFrame({"am_settlement": [2.0]}),
                self.option_price_plan(),
            )

    def test_option_normalization_rejects_unknown_call_put_flag(self) -> None:
        """An unexpected enum label fails before ClickHouse insertion."""

        import pandas as pd

        from ivydb.clickhouse_loader.normalization import normalize_batch_for_clickhouse

        with self.assertRaisesRegex(ValueError, "cp_flag.*unexpected"):
            normalize_batch_for_clickhouse(
                pd.DataFrame({"cp_flag": ["X"]}),
                self.option_price_plan(),
            )

    def test_consolidated_load_refuses_duplicate_source_year(self) -> None:
        """Append-once loads must not duplicate an existing secprd source year."""

        from ivydb.clickhouse_loader.load_to_clickhouse import load_tables

        class FakeClickHouseClient:
            """Fake ClickHouse client with existing source-year data."""

            def command(self, sql: str) -> None:
                """Accept no-op commands."""

            def query(self, sql: str) -> object:
                if "system.tables" in sql:
                    return IvydbClickhouseLoadTests.QueryResult(1)
                if "`source_year` = 2024" in sql:
                    return IvydbClickhouseLoadTests.QueryResult(1)
                return IvydbClickhouseLoadTests.QueryResult(0)

        table = self.security_price_plan(2024)

        with tempfile.TemporaryDirectory() as tmpdir:
            config = self.config_with_audit_path(Path(tmpdir) / "audit.jsonl")

            with self.assertRaisesRegex(ValueError, "already has rows"):
                load_tables(
                    config=config,
                    wrds_connection=object(),
                    clickhouse_client=FakeClickHouseClient(),
                    table_plan=[table],
                )

    def test_load_streams_directly_into_precreated_final_table(self) -> None:
        """Append-once historical data should not create or copy through staging."""

        import pandas as pd

        from ivydb.clickhouse_loader.load_to_clickhouse import load_tables

        client = self.empty_existing_target_client("opprcd2024")
        with (
            patch(
                "ivydb.clickhouse_loader.load_to_clickhouse.stream_table",
                return_value=[pd.DataFrame({"secid": [101.0], "volume": [1.0]})],
            ),
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            config = self.config_with_audit_path(Path(tmpdir) / "audit.jsonl")
            results = load_tables(
                config,
                object(),
                client,
                [self.option_price_plan()],
            )

        self.assertEqual(results[0].rows_loaded, 1)
        self.assertEqual(client.inserted_tables, ["opprcd2024"])
        self.assertFalse(any("_tmp_" in command for command in client.commands))

    def test_direct_load_requires_precreated_curated_target(self) -> None:
        """The loader must not replace curated DDL with a derived schema."""

        from ivydb.clickhouse_loader.config import default_config
        from ivydb.clickhouse_loader.load_to_clickhouse import load_tables

        with self.assertRaisesRegex(ValueError, "run create-tables first"):
            load_tables(
                default_config(),
                object(),
                self.missing_target_client(),
                [self.option_price_plan()],
            )

    def test_clear_failed_truncates_failed_separate_target_without_replacing_schema(self) -> None:
        """Failed option loads clear rows while retaining curated DDL."""

        from ivydb.clickhouse_loader.load_to_clickhouse import clear_failed_tables

        table = self.option_price_plan()
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            audit_path.write_text(
                json.dumps(
                    {
                        "source_library": table.source_library,
                        "source_table": table.source_table,
                        "target_table": table.target_table,
                        "status": "failed",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            config = self.config_with_audit_path(audit_path)
            client = self.recording_client()

            cleared = clear_failed_tables(config, client, [table])

        self.assertEqual(cleared, ["opprcd2024"])
        self.assertIn("TRUNCATE TABLE `ivydb`.`opprcd2024`", client.commands)
        self.assertFalse(any("DROP TABLE" in command for command in client.commands))

    def test_clear_failed_drops_only_failed_secprd_source_year_partition(self) -> None:
        """Clearing one failed consolidated source must retain other loaded years."""

        from ivydb.clickhouse_loader.load_to_clickhouse import clear_failed_tables

        table = self.security_price_plan(2024)
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            audit_path.write_text(
                json.dumps(
                    {
                        "source_library": table.source_library,
                        "source_table": table.source_table,
                        "target_table": table.target_table,
                        "status": "failed",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            config = self.config_with_audit_path(audit_path)
            client = self.recording_client()

            clear_failed_tables(config, client, [table])

        self.assertIn(
            "ALTER TABLE `ivydb`.`secprd` DROP PARTITION IF EXISTS 2024",
            client.commands,
        )

    def test_clear_failed_skips_completed_source_and_clears_failed_source_in_batch(self) -> None:
        """Cleanup should clear only the incomplete year when a prior year completed."""

        from ivydb.clickhouse_loader.load_to_clickhouse import clear_failed_tables

        complete_table = replace(
            self.option_price_plan(),
            source_table="opprcd2023",
            target_table="opprcd2023",
            source_year=2023,
        )
        failed_table = self.option_price_plan()
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            audit_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "source_library": complete_table.source_library,
                                "source_table": complete_table.source_table,
                                "target_table": complete_table.target_table,
                                "status": "complete",
                            }
                        ),
                        json.dumps(
                            {
                                "source_library": failed_table.source_library,
                                "source_table": failed_table.source_table,
                                "target_table": failed_table.target_table,
                                "status": "failed",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            config = self.config_with_audit_path(audit_path)
            client = self.recording_client()

            cleared = clear_failed_tables(config, client, [complete_table, failed_table])

        self.assertEqual(cleared, ["opprcd2024"])
        self.assertNotIn("TRUNCATE TABLE `ivydb`.`opprcd2023`", client.commands)
        self.assertIn("TRUNCATE TABLE `ivydb`.`opprcd2024`", client.commands)

    def test_clear_failed_clears_started_source_after_interrupted_load(self) -> None:
        """Cleanup should remove data left by a process stopped during insertion."""

        from ivydb.clickhouse_loader.load_to_clickhouse import clear_failed_tables

        table = self.option_price_plan()
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            audit_path.write_text(
                json.dumps(
                    {
                        "source_library": table.source_library,
                        "source_table": table.source_table,
                        "target_table": table.target_table,
                        "status": "started",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            config = self.config_with_audit_path(audit_path)
            client = self.recording_client()

            cleared = clear_failed_tables(config, client, [table])

        self.assertEqual(cleared, ["opprcd2024"])
        self.assertIn("TRUNCATE TABLE `ivydb`.`opprcd2024`", client.commands)

    def test_clear_failed_ignores_completed_source_without_removing_data(self) -> None:
        """Cleanup must leave completed historical sources untouched."""

        from ivydb.clickhouse_loader.load_to_clickhouse import clear_failed_tables

        table = self.option_price_plan()
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            audit_path.write_text(
                json.dumps(
                    {
                        "source_library": table.source_library,
                        "source_table": table.source_table,
                        "target_table": table.target_table,
                        "status": "complete",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            config = self.config_with_audit_path(audit_path)
            client = self.recording_client()

            cleared = clear_failed_tables(config, client, [table])

        self.assertEqual(cleared, [])
        self.assertEqual(client.commands, [])


class IvydbClickhouseCliTests(unittest.TestCase):
    """Check the config-driven CLI surface."""

    def test_cli_parses_create_tables_load_and_validate(self) -> None:
        """The CLI should expose only config-driven subcommands."""

        from ivydb.clickhouse_loader.cli import _build_parser

        parser = _build_parser()
        create_args = parser.parse_args(["create-tables"])
        load_args = parser.parse_args(["load"])
        validate_args = parser.parse_args(["validate"])
        clear_args = parser.parse_args(["clear-failed"])

        self.assertEqual(create_args.command, "create-tables")
        self.assertEqual(load_args.command, "load")
        self.assertEqual(validate_args.command, "validate")
        self.assertEqual(clear_args.command, "clear-failed")
        self.assertIn("Clear incomplete direct-load destinations", parser.format_help())

    def test_cli_accepts_custom_config_path(self) -> None:
        """The optional --config flag should override the default config path."""

        from ivydb.clickhouse_loader.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["--config", "/tmp/custom.toml", "load"])

        self.assertEqual(args.config, Path("/tmp/custom.toml"))


class IvydbClickhouseValidationTests(unittest.TestCase):
    """Check validation SQL covers the download-plan checks."""

    def test_opcrsphist_validation_reports_missing_links_and_score_counts(self) -> None:
        """The link validation should summarize null dates, null permno, and scores."""

        from ivydb.clickhouse_loader.validation import opcrsphist_link_quality_sql

        sql = opcrsphist_link_quality_sql("ivydb")

        self.assertIn("permno IS NULL", sql)
        self.assertIn("sdate IS NULL", sql)
        self.assertIn("edate IS NULL", sql)
        self.assertIn("score = 1", sql)
        self.assertIn("score != 1 OR score IS NULL", sql)

    def test_opprcd_duplicate_validation_uses_contract_date_key(self) -> None:
        """Duplicate checks should group by the intended contract-date key."""

        from ivydb.clickhouse_loader.validation import opprcd_duplicate_key_sql

        sql = opprcd_duplicate_key_sql("ivydb", "opprcd2024")

        self.assertIn("GROUP BY `secid`, `date`, `optionid`, `exdate`, `cp_flag`, `strike_price`", sql)
        self.assertIn("HAVING count() > 1", sql)

    def test_consolidated_secprd_validation_reports_each_source_year(self) -> None:
        """A consolidated table should validate row counts and dates by source year."""

        from ivydb.clickhouse_loader.source_columns import SECURITY_PRICE_SOURCE_COLUMNS
        from ivydb.clickhouse_loader.table_plan import TablePlan
        from ivydb.clickhouse_loader.validation import validate_loaded_tables

        class QueryResult:
            """Mimic clickhouse-connect query results."""

            def __init__(self, rows: list[tuple[object, ...]]) -> None:
                self.result_rows = rows

        class FakeClickHouseClient:
            """Return grouped source-year validation rows for secprd."""

            def query(self, sql: str) -> QueryResult:
                if "GROUP BY `source_year`" in sql:
                    return QueryResult(
                        [
                            (2023, 2494685, "2023-01-03", "2023-12-29"),
                            (2024, 2532224, "2024-01-02", "2024-12-31"),
                        ]
                    )
                if "WHERE `secid` IS NULL" in sql or "WHERE `date` IS NULL" in sql:
                    return QueryResult([(0,)])
                return QueryResult([(5026909,)])

        table_plan = [
            TablePlan(
                source_library="optionm_all",
                source_table="secprd2023",
                target_table="secprd",
                source_prefix="secprd",
                source_year=2023,
                load_group="underlying-prices",
                layout="consolidated_year_table",
                source_year_column="source_year",
                source_columns=SECURITY_PRICE_SOURCE_COLUMNS,
            ),
            TablePlan(
                source_library="optionm_all",
                source_table="secprd2024",
                target_table="secprd",
                source_prefix="secprd",
                source_year=2024,
                load_group="underlying-prices",
                layout="consolidated_year_table",
                source_year_column="source_year",
                source_columns=SECURITY_PRICE_SOURCE_COLUMNS,
            ),
        ]

        results = validate_loaded_tables(FakeClickHouseClient(), "ivydb", table_plan)
        checks = {(result.table, result.check_name): result.value for result in results}

        self.assertEqual(checks[("secprd", "source_year_2023_row_count")], 2494685)
        self.assertEqual(checks[("secprd", "source_year_2023_min_date")], "2023-01-03")
        self.assertEqual(checks[("secprd", "source_year_2024_max_date")], "2024-12-31")
