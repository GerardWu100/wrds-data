# IvyDB ClickHouse Loader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a direct WRDS PostgreSQL to ClickHouse loader for the selected OptionMetrics IvyDB US bundle, with large option price tables kept as separate yearly ClickHouse tables and yearly underlying stock price tables consolidated into one ClickHouse table.

**Architecture:** Reuse the project WRDS connection helper and the BoardEx downloader's chunked `raw_sql(..., chunksize=..., return_iter=True)` pattern, but replace local Parquet writes with ClickHouse batch inserts. Use generated ClickHouse schemas from live PostgreSQL metadata, explicit table-layout rules from config, and staging tables so interrupted loads do not masquerade as complete final tables.

**Tech Stack:** Python 3.13, `uv`, `wrds`, `pandas`, `clickhouse-connect`, ClickHouse `MergeTree`, project-local `.pgpass`.

---

## Design Summary

The loader must not read WRDS text files or write local data files as an ingestion stage. Data flow is:

```text
WRDS PostgreSQL table
  -> chunked pandas DataFrame
  -> normalized pandas DataFrame
  -> ClickHouse insert batch
  -> final MergeTree table
```

Default table layout:

| WRDS source | ClickHouse target | Layout rule |
|---|---|---|
| `optionm_all.opprcd1996` through `optionm_all.opprcd2025` | `ivydb.opprcd1996` through `ivydb.opprcd2025` | Keep one physical ClickHouse table per source year because these are the largest selected tables. |
| `optionm_all.secprd1996` through `optionm_all.secprd2025` | `ivydb.secprd` | Consolidate all years into one table with an added `source_year UInt16` column. |
| `optionm_all.securd`, `secnmd`, `exchgd`, `distrd`, `opinfd` | same target table names | One ClickHouse table per static reference table. |
| `wrdsapps_link_crsp_optionm.opcrsphist` | `ivydb.opcrsphist` | One ClickHouse table; load full table, then validation reports null links and `score = 1` coverage. |

Do not include `fwdprdYYYY`, `borrateYYYY`, `distrprojdYYYY`, `idxdvd`, `zerocd`, `vsurfdYYYY`, `stdopdYYYY`, `hvoldYYYY`, `stdbrteYYYY`, `opvold`, `optionmnames`, `secprd`, or `indexd` in the default config.

## File Structure

- Create `ivydb_clickhouse/__init__.py`: package marker.
- Create `ivydb_clickhouse/__main__.py`: module entrypoint for `uv run python -m ivydb_clickhouse`.
- Create `ivydb_clickhouse/config.toml`: commented default loader config, ClickHouse connection settings, selected table rules, and operational settings.
- Create `ivydb_clickhouse/config.py`: typed config dataclasses, TOML parsing, identifier validation, and CLI override resolution.
- Create `ivydb_clickhouse/clickhouse_client.py`: ClickHouse client construction, host URL normalization, database creation, command helpers.
- Create `ivydb_clickhouse/table_plan.py`: selected WRDS-to-ClickHouse table plan construction from config and live WRDS metadata.
- Create `ivydb_clickhouse/schema.py`: PostgreSQL-to-ClickHouse type mapping and `CREATE TABLE` statement generation.
- Create `ivydb_clickhouse/wrds_stream.py`: WRDS metadata fetches, `SELECT` query construction, and chunked source streaming.
- Create `ivydb_clickhouse/load_to_clickhouse.py`: staging-table load orchestration, batch insert, audit writes, resume and replace behavior.
- Create `ivydb_clickhouse/validation.py`: post-load row count, date range, key null, duplicate key, and `opcrsphist` match-quality checks.
- Create `ivydb_clickhouse/cli.py`: CLI entrypoint for dry run, schema creation, loading, resume, replace, filtering, and validation.
- Create `ivydb_clickhouse/GUIDE_ivydb_clickhouse.md`: developer guide for this folder.
- Create `ivydb_clickhouse/TABLE_SELECTION_REFERENCE.md`: short reference tying the config to `ivydb/optionmetrics_ivydb_download_plan.md`.
- Create `tests/test_ivydb_clickhouse.py`: unit tests for config, table planning, schema mapping, DDL, query construction, DataFrame normalization, and load orchestration with mocked WRDS and ClickHouse clients.
- Modify `pyproject.toml`: add `clickhouse-connect`.
- Modify `README.md` and `GUIDE_ROOT.md`: add user commands and folder navigation.

## Task 1: Add Dependency And Package Skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `ivydb_clickhouse/__init__.py`
- Create: `ivydb_clickhouse/__main__.py`
- Create: `ivydb_clickhouse/cli.py`
- Test: `tests/test_ivydb_clickhouse.py`

- [ ] **Step 1: Add the ClickHouse dependency**

Run:

```bash
uv add clickhouse-connect
```

Expected: `pyproject.toml` contains `clickhouse-connect`, and `uv.lock` updates.

- [ ] **Step 2: Write the first import test**

Add to `tests/test_ivydb_clickhouse.py`:

```python
"""Tests for the IvyDB WRDS-to-ClickHouse loader."""

from __future__ import annotations

import unittest


class IvydbClickhouseImportTests(unittest.TestCase):
    """Verify that the package entrypoints import cleanly."""

    def test_cli_module_imports(self) -> None:
        """The CLI module should be importable before any database connection."""

        from ivydb_clickhouse import cli

        self.assertTrue(hasattr(cli, "main"))
```

- [ ] **Step 3: Run the import test and verify it fails**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse.IvydbClickhouseImportTests.test_cli_module_imports
```

Expected: failure with `ModuleNotFoundError: No module named 'ivydb_clickhouse'`.

- [ ] **Step 4: Create the package marker and CLI entrypoints**

Create `ivydb_clickhouse/__init__.py`:

```python
"""Direct WRDS PostgreSQL to ClickHouse loader for OptionMetrics IvyDB US."""
```

Create `ivydb_clickhouse/cli.py`:

```python
"""Command-line interface for loading IvyDB data from WRDS into ClickHouse."""

from __future__ import annotations


def main() -> None:
    """Run the IvyDB ClickHouse loader command-line interface."""

    print("IvyDB ClickHouse loader CLI is installed.")
```

Create `ivydb_clickhouse/__main__.py`:

```python
"""Module entrypoint for ``python -m ivydb_clickhouse``."""

from __future__ import annotations

from ivydb_clickhouse.cli import main


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the import test and verify it passes**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse.IvydbClickhouseImportTests.test_cli_module_imports
```

Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock ivydb_clickhouse tests/test_ivydb_clickhouse.py
git commit -m "Add IvyDB ClickHouse loader package"
```

## Task 2: Config Parsing And CLI Shape

**Files:**
- Create: `ivydb_clickhouse/config.toml`
- Create: `ivydb_clickhouse/config.py`
- Modify: `ivydb_clickhouse/cli.py`
- Test: `tests/test_ivydb_clickhouse.py`

- [ ] **Step 1: Add config tests**

Append:

```python
from pathlib import Path
import tempfile
import textwrap


class IvydbClickhouseConfigTests(unittest.TestCase):
    """Check TOML parsing and CLI override behavior."""

    def test_load_config_reads_clickhouse_and_loader_sections(self) -> None:
        """Config parsing should expose validated ClickHouse and loader settings."""

        from ivydb_clickhouse.config import load_config

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.toml"
            path.write_text(
                textwrap.dedent(
                    """
                    [clickhouse]
                    host = "https://clickhouse.example.com"
                    port = 443
                    username = "user"
                    password = "pass"
                    secure = true
                    database = "ivydb"

                    [loader]
                    wrds_batch_size = 1000
                    clickhouse_insert_size = 500
                    create_database = true
                    resume = true
                    replace = false

                    [tables.option_prices]
                    enabled = true
                    source_library = "optionm_all"
                    source_prefix = "opprcd"
                    years = [2024, 2025]
                    layout = "separate_year_tables"
                    target_template = "opprcd{year}"

                    [tables.underlying_prices]
                    enabled = true
                    source_library = "optionm_all"
                    source_prefix = "secprd"
                    years = [2024, 2025]
                    layout = "consolidated_year_table"
                    target_table = "secprd"
                    source_year_column = "source_year"

                    [tables.static_reference]
                    enabled = true
                    tables = [
                        { source_library = "optionm_all", source_table = "securd", target_table = "securd" },
                        { source_library = "wrdsapps_link_crsp_optionm", source_table = "opcrsphist", target_table = "opcrsphist" },
                    ]
                    """
                ),
                encoding="utf-8",
            )

            config = load_config(path)

        self.assertEqual(config.clickhouse.database, "ivydb")
        self.assertEqual(config.loader.wrds_batch_size, 1000)
        self.assertEqual(config.option_price_years, [2024, 2025])
        self.assertEqual(config.underlying_price_years, [2024, 2025])
        self.assertEqual(len(config.static_tables), 2)
```

- [ ] **Step 2: Run the config test and verify it fails**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse.IvydbClickhouseConfigTests.test_load_config_reads_clickhouse_and_loader_sections
```

Expected: failure because `ivydb_clickhouse.config` does not exist.

- [ ] **Step 3: Implement `config.py`**

Create dataclasses:

```python
@dataclass(frozen=True)
class ClickHouseConfig:
    """ClickHouse connection and target database settings."""

    host: str
    port: int
    username: str
    password: str
    secure: bool
    database: str


@dataclass(frozen=True)
class LoaderConfig:
    """Runtime settings that control chunk sizes and load safety."""

    wrds_batch_size: int
    clickhouse_insert_size: int
    create_database: bool
    resume: bool
    replace: bool


@dataclass(frozen=True)
class StaticTableConfig:
    """One static WRDS source table and its ClickHouse target table."""

    source_library: str
    source_table: str
    target_table: str


@dataclass(frozen=True)
class AppConfig:
    """Fully parsed IvyDB ClickHouse loader configuration."""

    clickhouse: ClickHouseConfig
    loader: LoaderConfig
    option_price_years: list[int]
    underlying_price_years: list[int]
    static_tables: list[StaticTableConfig]
```

Implement `load_config(config_path: Path) -> AppConfig` using `tomllib`, validate identifiers with `^[A-Za-z_][A-Za-z0-9_]*$`, validate years are integers between 1996 and 2025, and reject unknown layouts.

- [ ] **Step 4: Add the default config**

Create `ivydb_clickhouse/config.toml` with comments for every option. Include:

```toml
[clickhouse]
# ClickHouse host. URL form such as "https://clickhouse.example.com" is accepted.
host = "https://clickhouse.example.com"
# ClickHouse HTTPS port.
port = 443
# ClickHouse username.
username = "YOUR_CLICKHOUSE_USERNAME"
# ClickHouse password.
password = "YOUR_CLICKHOUSE_PASSWORD"
# Whether clickhouse-connect should use a secure HTTPS connection.
secure = true
# Target ClickHouse database for IvyDB tables.
database = "ivydb"

[loader]
# Rows fetched from WRDS PostgreSQL per chunk.
wrds_batch_size = 100000
# Rows inserted into ClickHouse per insert call.
clickhouse_insert_size = 100000
# Create the target ClickHouse database if it does not exist.
create_database = true
# Skip sources marked complete in the audit table.
resume = true
# Replace target tables or source-year partitions before loading.
replace = false

[tables.option_prices]
# Keep annual option price sources as separate ClickHouse tables.
enabled = true
source_library = "optionm_all"
source_prefix = "opprcd"
years = [1996, 1997, 1998, 1999, 2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
layout = "separate_year_tables"
target_template = "opprcd{year}"

[tables.underlying_prices]
# Consolidate annual underlying security prices into one ClickHouse table.
enabled = true
source_library = "optionm_all"
source_prefix = "secprd"
years = [1996, 1997, 1998, 1999, 2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
layout = "consolidated_year_table"
target_table = "secprd"
source_year_column = "source_year"

[tables.static_reference]
# Small reference and link tables loaded one target table per source table.
enabled = true
tables = [
    { source_library = "optionm_all", source_table = "securd", target_table = "securd" },
    { source_library = "optionm_all", source_table = "secnmd", target_table = "secnmd" },
    { source_library = "optionm_all", source_table = "exchgd", target_table = "exchgd" },
    { source_library = "optionm_all", source_table = "distrd", target_table = "distrd" },
    { source_library = "optionm_all", source_table = "opinfd", target_table = "opinfd" },
    { source_library = "wrdsapps_link_crsp_optionm", source_table = "opcrsphist", target_table = "opcrsphist" },
]
```

- [ ] **Step 5: Wire basic CLI parsing**

Update `ivydb_clickhouse/cli.py` to parse `--config`, `--dry-run`, `--schema-only`, `--validate-only`, `--resume`, `--replace`, `--source-table`, and `--target-table`. For this task, parse and print the resolved config database.

- [ ] **Step 6: Run tests**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse.IvydbClickhouseConfigTests
```

Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
git add ivydb_clickhouse/config.py ivydb_clickhouse/config.toml ivydb_clickhouse/cli.py tests/test_ivydb_clickhouse.py
git commit -m "Add IvyDB ClickHouse config parsing"
```

## Task 3: Build The WRDS Source To ClickHouse Target Plan

**Files:**
- Create: `ivydb_clickhouse/table_plan.py`
- Test: `tests/test_ivydb_clickhouse.py`

- [ ] **Step 1: Add table-plan tests**

Add tests asserting:

```python
class IvydbClickhouseTablePlanTests(unittest.TestCase):
    """Check source-to-target layout rules."""

    def test_option_prices_stay_as_separate_year_tables(self) -> None:
        """Each opprcd year should map to its own ClickHouse table."""

        from ivydb_clickhouse.table_plan import TableLoadPlan, build_table_plan

        plans = build_table_plan(
            option_years=[2024, 2025],
            underlying_years=[],
            static_tables=[],
        )

        self.assertEqual(
            plans,
            [
                TableLoadPlan("optionm_all", "opprcd2024", "opprcd2024", "separate", 2024),
                TableLoadPlan("optionm_all", "opprcd2025", "opprcd2025", "separate", 2025),
            ],
        )

    def test_underlying_prices_consolidate_to_one_table(self) -> None:
        """Each secprd source year should target the same ClickHouse table."""

        from ivydb_clickhouse.table_plan import TableLoadPlan, build_table_plan

        plans = build_table_plan(
            option_years=[],
            underlying_years=[2024, 2025],
            static_tables=[],
        )

        self.assertEqual(
            plans,
            [
                TableLoadPlan("optionm_all", "secprd2024", "secprd", "consolidated", 2024),
                TableLoadPlan("optionm_all", "secprd2025", "secprd", "consolidated", 2025),
            ],
        )
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse.IvydbClickhouseTablePlanTests
```

Expected: failure because `table_plan.py` does not exist.

- [ ] **Step 3: Implement `table_plan.py`**

Define:

```python
@dataclass(frozen=True)
class TableLoadPlan:
    """One WRDS source table mapped to one ClickHouse target table."""

    source_library: str
    source_table: str
    target_table: str
    layout: Literal["separate", "consolidated", "static"]
    source_year: int | None
```

Implement `build_table_plan(...) -> list[TableLoadPlan]` so option years become `opprcd{year}`, underlying years become `secprd{year}` targeting `secprd`, and static tables use their configured target names.

- [ ] **Step 4: Add live table validation helper**

Add `validate_source_tables_exist(wrds_db, plans)` that queries `information_schema.tables` and raises `ValueError` listing every missing `schema.table`.

- [ ] **Step 5: Run tests**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse.IvydbClickhouseTablePlanTests
```

Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add ivydb_clickhouse/table_plan.py tests/test_ivydb_clickhouse.py
git commit -m "Add IvyDB table load planning"
```

## Task 4: Generate ClickHouse Schemas From WRDS Metadata

**Files:**
- Create: `ivydb_clickhouse/schema.py`
- Test: `tests/test_ivydb_clickhouse.py`

- [ ] **Step 1: Add schema mapping tests**

Add tests for these mappings:

```python
class IvydbClickhouseSchemaTests(unittest.TestCase):
    """Check PostgreSQL metadata to ClickHouse DDL conversion."""

    def test_postgres_types_map_to_clickhouse_types(self) -> None:
        """Common WRDS PostgreSQL types should map to stable ClickHouse types."""

        from ivydb_clickhouse.schema import postgres_type_to_clickhouse_type

        self.assertEqual(postgres_type_to_clickhouse_type("date"), "Date32")
        self.assertEqual(postgres_type_to_clickhouse_type("integer"), "Int32")
        self.assertEqual(postgres_type_to_clickhouse_type("double precision"), "Float64")
        self.assertEqual(postgres_type_to_clickhouse_type("character varying"), "String")
        self.assertEqual(postgres_type_to_clickhouse_type("numeric(12,2)"), "Decimal(12, 2)")

    def test_secprd_schema_adds_source_year(self) -> None:
        """Consolidated yearly sources should include source_year in ClickHouse."""

        from ivydb_clickhouse.schema import build_clickhouse_columns

        columns = [
            {"column_name": "secid", "data_type": "double precision", "nullable": True},
            {"column_name": "date", "data_type": "date", "nullable": True},
            {"column_name": "close", "data_type": "double precision", "nullable": True},
        ]

        result = build_clickhouse_columns(columns, add_source_year=True)

        self.assertEqual(result[0].name, "source_year")
        self.assertEqual(result[0].clickhouse_type, "UInt16")
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse.IvydbClickhouseSchemaTests
```

Expected: failure because `schema.py` does not exist.

- [ ] **Step 3: Implement schema types and DDL**

Implement:

```python
@dataclass(frozen=True)
class ClickHouseColumn:
    """One ClickHouse column produced from WRDS PostgreSQL metadata."""

    name: str
    clickhouse_type: str
    nullable: bool
```

Rules:

- PostgreSQL `date` maps to `Date32`.
- PostgreSQL integer types map to `Int16`, `Int32`, or `Int64`.
- PostgreSQL floating types map to `Float32` or `Float64`.
- PostgreSQL `numeric(p,s)` maps to `Decimal(p, s)` when `p <= 76`.
- PostgreSQL text-like, JSON-like, UUID, and interval types map to `String`.
- Nullable columns wrap as `Nullable(<type>)` except `String`, because ClickHouse handles empty strings and null strings less ergonomically; keep WRDS string nulls as empty strings during normalization.

Build DDL with these engines:

```sql
ENGINE = MergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (secid, date, optionid, exdate, cp_flag, strike_price)
```

for `opprcdYYYY`;

```sql
ENGINE = MergeTree
PARTITION BY source_year
ORDER BY (secid, date)
```

for consolidated `secprd`;

```sql
ENGINE = MergeTree
ORDER BY (<configured key columns>)
```

for static reference tables, with default keys:

| Target table | ORDER BY |
|---|---|
| `securd` | `(secid)` |
| `secnmd` | `(secid, effect_date)` |
| `exchgd` | `(secid, effect_date, seq_num)` |
| `distrd` | `(secid, record_date, seq_num)` |
| `opinfd` | `(secid)` |
| `opcrsphist` | `(secid, sdate, edate, permno, score)` |

- [ ] **Step 4: Run tests**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse.IvydbClickhouseSchemaTests
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add ivydb_clickhouse/schema.py tests/test_ivydb_clickhouse.py
git commit -m "Generate ClickHouse schemas from WRDS metadata"
```

## Task 5: Add WRDS Streaming And DataFrame Normalization

**Files:**
- Create: `ivydb_clickhouse/wrds_stream.py`
- Modify: `ivydb_clickhouse/load_to_clickhouse.py`
- Test: `tests/test_ivydb_clickhouse.py`

- [ ] **Step 1: Add WRDS query and normalization tests**

Add:

```python
class IvydbClickhouseWrdsStreamTests(unittest.TestCase):
    """Check direct PostgreSQL source query construction and batch normalization."""

    def test_build_select_query_quotes_identifiers(self) -> None:
        """The WRDS query should stream directly from PostgreSQL."""

        from ivydb_clickhouse.wrds_stream import build_select_query

        self.assertEqual(
            build_select_query("optionm_all", "opprcd2024"),
            'SELECT * FROM "optionm_all"."opprcd2024"',
        )

    def test_add_source_year_for_consolidated_secprd(self) -> None:
        """Consolidated source batches should get a source_year column."""

        import pandas as pd
        from ivydb_clickhouse.load_to_clickhouse import normalize_batch_for_clickhouse

        batch = pd.DataFrame({"secid": [5139.0], "date": ["2024-01-02"], "close": [21.25]})

        result = normalize_batch_for_clickhouse(
            batch=batch,
            source_year=2024,
            add_source_year=True,
            string_columns=[],
        )

        self.assertEqual(result["source_year"].tolist(), [2024])
        self.assertEqual(result.columns.tolist(), ["source_year", "secid", "date", "close"])
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse.IvydbClickhouseWrdsStreamTests
```

Expected: failure because `wrds_stream.py` and `load_to_clickhouse.py` do not exist.

- [ ] **Step 3: Implement `wrds_stream.py`**

Implement `build_select_query(library: str, table: str) -> str`, `fetch_table_columns(wrds_db, library, table)`, `fetch_approx_row_count(wrds_db, library, table)`, and `stream_table_batches(wrds_db, library, table, batch_size)`.

`stream_table_batches` must call:

```python
return wrds_db.raw_sql(
    build_select_query(library, table),
    chunksize=batch_size,
    return_iter=True,
)
```

- [ ] **Step 4: Implement DataFrame normalization**

Create `ivydb_clickhouse/load_to_clickhouse.py` with `normalize_batch_for_clickhouse(...)`. Behavior:

- Insert `source_year` as the first column when `add_source_year` is true.
- Convert configured string columns to empty strings where pandas has nulls.
- Leave numeric nulls as pandas null values so ClickHouse nullable numeric columns receive nulls.
- Do not rescale `strike_price`; keep WRDS's 1/1000 dollar convention exactly as stored.

- [ ] **Step 5: Run tests**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse.IvydbClickhouseWrdsStreamTests
```

Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add ivydb_clickhouse/wrds_stream.py ivydb_clickhouse/load_to_clickhouse.py tests/test_ivydb_clickhouse.py
git commit -m "Add WRDS streaming for IvyDB ClickHouse loads"
```

## Task 6: Build ClickHouse Client And Staging Load Orchestration

**Files:**
- Create: `ivydb_clickhouse/clickhouse_client.py`
- Modify: `ivydb_clickhouse/load_to_clickhouse.py`
- Test: `tests/test_ivydb_clickhouse.py`

- [ ] **Step 1: Add mocked orchestration tests**

Add a fake client with `command()` and `insert_df()` call capture. Test:

```python
class IvydbClickhouseLoadTests(unittest.TestCase):
    """Check load orchestration without touching a real ClickHouse server."""

    def test_consolidated_year_load_drops_only_source_year_partition_when_replacing(self) -> None:
        """Replacing secprd2024 should drop partition 2024, not the whole secprd table."""

        from ivydb_clickhouse.load_to_clickhouse import build_replace_commands
        from ivydb_clickhouse.table_plan import TableLoadPlan

        plan = TableLoadPlan("optionm_all", "secprd2024", "secprd", "consolidated", 2024)

        commands = build_replace_commands(database="ivydb", plan=plan)

        self.assertEqual(commands, ["ALTER TABLE ivydb.secprd DROP PARTITION 2024"])
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse.IvydbClickhouseLoadTests
```

Expected: failure because `build_replace_commands` does not exist.

- [ ] **Step 3: Implement ClickHouse client construction**

In `clickhouse_client.py`, reuse the URL normalization pattern from `clickhouse-example/schema_non_crypto.py`. Implement:

- `resolve_host_and_secure(raw_host: str, secure: bool) -> tuple[str, bool]`
- `build_client(config: ClickHouseConfig) -> Any`
- `create_database(client, database: str) -> None`
- `validate_identifier(name: str, label: str) -> str`

- [ ] **Step 4: Implement staging rules**

In `load_to_clickhouse.py`, implement:

- Separate option table: load to `_tmp_opprcd2024_<run_id>`, then rename to `opprcd2024` after success.
- Consolidated `secprd`: load source year to `_tmp_secprd_2024_<run_id>`, then `ALTER TABLE ivydb.secprd DROP PARTITION 2024` only when `replace = true`, then `INSERT INTO ivydb.secprd SELECT * FROM tmp`, then drop temp.
- Static reference table: load to `_tmp_<target>_<run_id>`, then rename to final when final is absent or `replace = true`.

The loader should refuse to append duplicate final data when `replace = false` and a target table or completed audit row already exists.

- [ ] **Step 5: Add audit table**

Create `_load_audit` with columns:

```sql
source_library String,
source_table String,
target_table String,
layout LowCardinality(String),
source_year Nullable(UInt16),
status LowCardinality(String),
rows_inserted UInt64,
started_at DateTime64(3, 'UTC'),
completed_at Nullable(DateTime64(3, 'UTC')),
error_message String
```

Use `MergeTree ORDER BY (target_table, source_table, started_at)`.

- [ ] **Step 6: Run tests**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse.IvydbClickhouseLoadTests
```

Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
git add ivydb_clickhouse/clickhouse_client.py ivydb_clickhouse/load_to_clickhouse.py tests/test_ivydb_clickhouse.py
git commit -m "Add staged ClickHouse load orchestration"
```

## Task 7: Complete CLI Commands

**Files:**
- Modify: `ivydb_clickhouse/cli.py`
- Test: `tests/test_ivydb_clickhouse.py`

- [ ] **Step 1: Add CLI argument tests**

Test that:

- `--table opprcd2024` without `--library` exits with code 2.
- `--dry-run` calls planning and row-count reporting but does not create tables.
- `--schema-only` creates target schemas but does not stream WRDS rows.
- `--validate-only` runs validation without loading data.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse
```

Expected: CLI tests fail before implementation.

- [ ] **Step 3: Implement CLI flow**

The CLI should support:

```bash
uv run python -m ivydb_clickhouse --dry-run
uv run python -m ivydb_clickhouse --schema-only
uv run python -m ivydb_clickhouse
uv run python -m ivydb_clickhouse --resume
uv run python -m ivydb_clickhouse --replace --target-table secprd
uv run python -m ivydb_clickhouse --source-table opprcd2024
uv run python -m ivydb_clickhouse --validate-only
```

Filter semantics:

- `--source-table opprcd2024` loads only WRDS source `opprcd2024`.
- `--target-table secprd` loads all source years targeting consolidated `secprd` unless `--source-table` narrows it.
- `--replace` permits dropping target tables, temp tables, or consolidated source-year partitions according to layout.

- [ ] **Step 4: Run tests**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add ivydb_clickhouse/cli.py tests/test_ivydb_clickhouse.py
git commit -m "Wire IvyDB ClickHouse CLI"
```

## Task 8: Add Post-Load Validation

**Files:**
- Create: `ivydb_clickhouse/validation.py`
- Modify: `ivydb_clickhouse/cli.py`
- Test: `tests/test_ivydb_clickhouse.py`

- [ ] **Step 1: Add validation SQL tests**

Test generated validation queries for:

- row count by target table
- min and max `date` for annual tables
- null key counts for `secid`, `date`, `optionid`, `exdate`, `cp_flag`, `strike_price`
- duplicate contract-date keys for `opprcdYYYY`
- `opcrsphist` counts for missing `permno`, missing `sdate`, missing `edate`, and `score = 1`

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse
```

Expected: validation tests fail before `validation.py` exists.

- [ ] **Step 3: Implement validation reports**

Implement functions that return DataFrames or printed tables:

- `validate_table_counts(client, database, plans)`
- `validate_date_ranges(client, database, plans)`
- `validate_required_keys(client, database, plans)`
- `validate_opprcd_duplicates(client, database, target_table)`
- `validate_opcrsphist_links(client, database)`

For `opcrsphist`, report full row count, missing `permno`, missing `sdate`, missing `edate`, `score = 1` rows, and non-`score = 1` rows. Do not delete lower-score rows during load.

- [ ] **Step 4: Run tests**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add ivydb_clickhouse/validation.py ivydb_clickhouse/cli.py tests/test_ivydb_clickhouse.py
git commit -m "Add IvyDB ClickHouse validation reports"
```

## Task 9: Live Smoke Tests With Tiny Scope

**Files:**
- Modify only if live testing exposes a bug.

- [ ] **Step 1: Check ClickHouse connection**

Run:

```bash
uv run python -m ivydb_clickhouse --config ivydb_clickhouse/config.toml --dry-run --source-table opinfd
```

Expected: prints one selected source table and approximate WRDS row count; writes no ClickHouse data.

- [ ] **Step 2: Create schema for one tiny table**

Run:

```bash
uv run python -m ivydb_clickhouse --schema-only --source-table opinfd
```

Expected: creates `ivydb.opinfd` and `_load_audit`.

- [ ] **Step 3: Load one tiny table**

Run:

```bash
uv run python -m ivydb_clickhouse --replace --source-table opinfd
```

Expected: inserts `optionm_all.opinfd` into `ivydb.opinfd`, marks audit status `complete`, and prints inserted row count.

- [ ] **Step 4: Validate one tiny table**

Run:

```bash
uv run python -m ivydb_clickhouse --validate-only --source-table opinfd
```

Expected: row count and key-null validation report prints without errors.

- [ ] **Step 5: Commit fixes from live smoke testing**

If code changed:

```bash
git add ivydb_clickhouse tests README.md GUIDE_ROOT.md
git commit -m "Fix IvyDB ClickHouse smoke test issues"
```

## Task 10: Documentation

**Files:**
- Create: `ivydb_clickhouse/GUIDE_ivydb_clickhouse.md`
- Create: `ivydb_clickhouse/TABLE_SELECTION_REFERENCE.md`
- Modify: `README.md`
- Modify: `GUIDE_ROOT.md`
- Test: documentation command scan

- [ ] **Step 1: Write folder guide**

Document:

- direct WRDS PostgreSQL to ClickHouse flow
- why `opprcdYYYY` stays separate by year
- why `secprdYYYY` consolidates into `secprd`
- staging and audit behavior
- validation reports
- commands for dry run, schema-only, one-table smoke test, full load, resume, and replace

- [ ] **Step 2: Write table-selection reference**

Tie the default config back to `ivydb/optionmetrics_ivydb_download_plan.md`. Explicitly list selected and excluded table families.

- [ ] **Step 3: Update root docs**

Update `README.md` and `GUIDE_ROOT.md` to mention `ivydb_clickhouse/` as the direct ClickHouse workflow. Remove or correct any stale reference that says the folder exists before it is created.

- [ ] **Step 4: Verify docs mention all user-facing commands**

Run:

```bash
rg -n "ivydb_clickhouse|--dry-run|--schema-only|--validate-only|--replace" README.md GUIDE_ROOT.md ivydb_clickhouse
```

Expected: every command appears in either README or the folder guide.

- [ ] **Step 5: Commit**

```bash
git add README.md GUIDE_ROOT.md ivydb_clickhouse/GUIDE_ivydb_clickhouse.md ivydb_clickhouse/TABLE_SELECTION_REFERENCE.md
git commit -m "Document IvyDB ClickHouse loader"
```

## Task 11: Full Verification Before Large Download

**Files:**
- No planned edits.

- [ ] **Step 1: Run unit tests**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse
```

Expected: `OK`.

- [ ] **Step 2: Run existing tests**

Run:

```bash
uv run python -m unittest tests.test_boardex_parquet
```

Expected: `OK`.

- [ ] **Step 3: Run dry run for the full default plan**

Run:

```bash
uv run python -m ivydb_clickhouse --dry-run
```

Expected: prints 30 `opprcdYYYY` sources, 30 `secprdYYYY` sources targeting `secprd`, 6 static/link sources, approximate WRDS row counts, and no ClickHouse inserts.

- [ ] **Step 4: Run validation-only before load**

Run:

```bash
uv run python -m ivydb_clickhouse --validate-only
```

Expected: reports missing target tables clearly if the full load has not run.

- [ ] **Step 5: Commit final verification notes if docs changed**

```bash
git status --short
```

Expected: clean working tree after the final commit.

## Self-Review

- Spec coverage: The plan covers direct WRDS PostgreSQL streaming, no text-file ingestion, ClickHouse target schema creation, separate yearly option tables, consolidated underlying stock price table, static reference loads, CRSP link handling, validation, docs, and live smoke tests.
- Placeholder scan: The plan contains no unfinished-work markers or copy-from-earlier-task shortcuts.
- Type consistency: The same names are used throughout: `TableLoadPlan`, `source_year`, `opprcdYYYY`, `secprd`, `opcrsphist`, `wrds_batch_size`, and `clickhouse_insert_size`.
