# IvyDB Direct Load And Physical Schema Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the append-once IvyDB warehouse stream directly into its curated ClickHouse tables while preserving nullable categorical data and using more appropriate compressed physical types.

**Architecture:** The loader treats each selected IvyDB source table as historical data loaded once into a pre-created final `MergeTree` table. It no longer creates a generic staging table or supports routine replacement; when a direct load fails, a deliberate `clear-failed` command clears only the failed target table or failed `secprd` source-year partition before a rerun. Curated DDL modules become the sole physical-schema contract, including nullable low-cardinality categories, validated semantic integer and enum types, and date-aware compression.

**Tech Stack:** Python 3.13, `uv`, `pandas`, `wrds`, `clickhouse-connect`, ClickHouse `MergeTree`, local JSON-lines audit log.

---

## Scope And Decisions

This plan supersedes the staging-table and metadata-generated-schema portions of
`docs/superpowers/plans/2026-05-12-ivydb-clickhouse-loader.md`.

It addresses the four reviewed defects:

| Finding | Decision |
|---|---|
| 1. Replacement can publish a generic schema instead of the curated compressed schema. | Remove normal replacement and staging. Historical rows load directly into pre-created curated targets. |
| 2. Nullable WRDS text values are changed into empty strings. | Store nullable categories as `LowCardinality(Nullable(String))` or `Nullable(Enum8(...))`; do not fill nulls. |
| 3. Documented identifiers and counts remain broad `Float64` values. | Narrow only semantically clear fields and reject invalid source values before inserting their chunk. |
| 4. Ordered dates use generic Zstandard compression only. | Keep the wide `Date32` date range and use `CODEC(DoubleDelta, ZSTD(6))` on date columns. |

The plan does not add unmeasured codec changes for prices, returns, implied
volatility, or Greeks. Those values remain nullable floating-point data with
`ZSTD(6)` because they are continuous measurements and need a benchmark before
using a specialized encoding.

## Target Physical Types

`Nullable(T)` means a ClickHouse column of type `T` that can still represent a
missing WRDS value. `LowCardinality` means ClickHouse stores repeated string
values through a compact dictionary. `Enum8` means a categorical value is
stored as an eight-bit integer with named allowed values. `DoubleDelta` encodes
changes in successive date values before `ZSTD` (Zstandard) compression.

### `opprcdYYYY`

| Column group | Target ClickHouse type |
|---|---|
| `secid` | `Nullable(UInt32) CODEC(ZSTD(6))` |
| `optionid` | `Nullable(UInt64) CODEC(ZSTD(6))` |
| `volume`, `open_interest` | `Nullable(UInt64) CODEC(ZSTD(6))` |
| `contract_size`, `am_settlement` | `Nullable(UInt32) CODEC(ZSTD(6))` |
| `date`, `exdate`, `last_date` | `Nullable(Date32) CODEC(DoubleDelta, ZSTD(6))` |
| `symbol`, `expiry_indicator`, `root`, `suffix` | `LowCardinality(Nullable(String)) CODEC(ZSTD(6))` |
| `cp_flag` | `Nullable(Enum8('C' = 1, 'P' = 2)) CODEC(ZSTD(6))` |
| `symbol_flag` | `Nullable(Enum8('0' = 1, '1' = 2)) CODEC(ZSTD(6))` |
| `ss_flag` | `Nullable(Enum8('0' = 1, '1' = 2, 'E' = 3)) CODEC(ZSTD(6))` |
| Prices, volatility, Greeks, factors | Existing `Nullable(Float64) CODEC(ZSTD(6))` |

### Supporting Tables

Use `Nullable(UInt32)` for `secid`, `link_secid`, sequence numbers, and
`permno` where present; use `Nullable(UInt64)` for documented count columns
such as security-price volume; retain floating point for prices, returns, share
outstanding values, cash amounts, adjustment factors, and ambiguous numeric
codes. Use `CODEC(DoubleDelta, ZSTD(6))` on all stored date columns. Store
nullable descriptive/categorical strings as `LowCardinality(Nullable(String))`,
except issuer and issue descriptions, which use `Nullable(String)` because
their cardinality is materially higher.

### Boundary Validation

The narrower types are not inferred from PostgreSQL transport types. They are
based on the IvyDB field meaning, then validated per incoming pandas
`DataFrame` chunk:

- unsigned integer columns must contain only nulls or whole numbers in the
  valid range for their target type;
- enum columns must contain only nulls or one of their declared string labels;
- a violation raises `ValueError` before that chunk is inserted and records a
  failed audit event.

Rows inserted from earlier chunks in that same direct load remain incomplete
until the user runs `clear-failed` and reloads.

## File Map

**Modify**

- `ivydb/clickhouse_loader/create_option_price_tables.py`: curated option DDL types and codecs.
- `ivydb/clickhouse_loader/create_security_price_tables.py`: curated security-price DDL types and date codec.
- `ivydb/clickhouse_loader/create_reference_tables.py`: curated reference/link DDL types and date codecs.
- `ivydb/clickhouse_loader/create_tables.py`: stop attempting privileged database creation.
- `ivydb/clickhouse_loader/clickhouse_client.py`: remove the unused database-creation helper.
- `ivydb/clickhouse_loader/load_to_clickhouse.py`: direct inserts, audit status lookup, and failed-load cleanup commands.
- `ivydb/clickhouse_loader/cli.py`: add `clear-failed`; remove replacement assumptions.
- `ivydb/clickhouse_loader/config.py`: remove replacement and automatic database creation settings.
- `ivydb/clickhouse_loader/config.toml`: remove `replace`; document append-once recovery.
- `ivydb/clickhouse_loader/wrds_stream.py`: retain streaming only after metadata-derived DDL is removed.
- `ivydb/ivyd.xml`: grant `TRUNCATE` for explicit failed-load clearing and describe administrator-created database prerequisite in docs.
- `tests/test_ivydb_clickhouse_loader.py`: replace staging/replacement expectations with direct-load, cleanup, schema, and validation tests.
- `README.md`, `GUIDE_ROOT.md`, `ivydb/GUIDE_ivydb.md`, `ivydb/clickhouse_loader/GUIDE_clickhouse_loader.md`, `ivydb/IVYDB_CLICKHOUSE_RUN_MANUAL.md`, `tests/GUIDE_tests.md`: document the implemented workflow.

**Create**

- `ivydb/clickhouse_loader/normalization.py`: chunk-level semantic type and enum validation/casting.

**Delete**

- `ivydb/clickhouse_loader/schema.py`: generic metadata-driven final/staging DDL has no owner after curated direct loads become mandatory.

## Task 1: Lock In The Curated Type And Codec Contract

**Files:**
- Modify: `tests/test_ivydb_clickhouse_loader.py`
- Modify: `ivydb/clickhouse_loader/create_option_price_tables.py`
- Modify: `ivydb/clickhouse_loader/create_security_price_tables.py`
- Modify: `ivydb/clickhouse_loader/create_reference_tables.py`

- [ ] **Step 1: Replace generic-schema tests with curated-schema assertions**

Remove tests whose subject is `schema.create_table_sql()` and extend
`IvydbClickhouseSchemaTests.test_direct_schema_setup_creates_compressed_tables_once_per_target`
with assertions like these:

```python
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
self.assertIn("`volume` Nullable(UInt64) CODEC(ZSTD(6))", fake_client.commands[0])
self.assertIn("`optionid` Nullable(UInt64) CODEC(ZSTD(6))", fake_client.commands[0])
self.assertIn("`date` Nullable(Date32) CODEC(DoubleDelta, ZSTD(6))", fake_client.commands[1])
self.assertIn("`volume` Nullable(UInt64) CODEC(ZSTD(6))", fake_client.commands[1])
self.assertIn(
    "`exercise_style` LowCardinality(Nullable(String)) CODEC(ZSTD(6))",
    fake_client.commands[2],
)
```

Add an explicit reference-date assertion using `secnmd`:

```python
config = replace(
    config,
    static_tables=(StaticTableConfig("optionm_all", "secnmd", "secnmd"),),
)
commands: list[str] = []
create_reference_tables(fake_client, config)
self.assertIn(
    "`effect_date` Nullable(Date32) CODEC(DoubleDelta, ZSTD(6))",
    fake_client.commands[-1],
)
```

- [ ] **Step 2: Run the schema test and verify the new expectations fail**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse_loader.IvydbClickhouseSchemaTests.test_direct_schema_setup_creates_compressed_tables_once_per_target -v
```

Expected: `FAIL`, because current DDL contains `Float64`, non-nullable
`LowCardinality(String)`, and `Date32 CODEC(ZSTD(6))`.

- [ ] **Step 3: Apply the curated DDL changes**

In `OPTION_PRICE_TABLE_SQL`, change the contract-bearing definitions to:

```sql
    `secid` Nullable(UInt32) CODEC(ZSTD(6)),
    `date` Nullable(Date32) CODEC(DoubleDelta, ZSTD(6)),
    `symbol` LowCardinality(Nullable(String)) CODEC(ZSTD(6)),
    `symbol_flag` Nullable(Enum8('0' = 1, '1' = 2)) CODEC(ZSTD(6)),
    `exdate` Nullable(Date32) CODEC(DoubleDelta, ZSTD(6)),
    `last_date` Nullable(Date32) CODEC(DoubleDelta, ZSTD(6)),
    `cp_flag` Nullable(Enum8('C' = 1, 'P' = 2)) CODEC(ZSTD(6)),
    `strike_price` Nullable(Float64) CODEC(ZSTD(6)),
    `best_bid` Nullable(Float64) CODEC(ZSTD(6)),
    `best_offer` Nullable(Float64) CODEC(ZSTD(6)),
    `volume` Nullable(UInt64) CODEC(ZSTD(6)),
    `open_interest` Nullable(UInt64) CODEC(ZSTD(6)),
    `impl_volatility` Nullable(Float64) CODEC(ZSTD(6)),
    `delta` Nullable(Float64) CODEC(ZSTD(6)),
    `gamma` Nullable(Float64) CODEC(ZSTD(6)),
    `vega` Nullable(Float64) CODEC(ZSTD(6)),
    `theta` Nullable(Float64) CODEC(ZSTD(6)),
    `optionid` Nullable(UInt64) CODEC(ZSTD(6)),
    `cfadj` Nullable(Float64) CODEC(ZSTD(6)),
    `am_settlement` Nullable(UInt32) CODEC(ZSTD(6)),
    `contract_size` Nullable(UInt32) CODEC(ZSTD(6)),
    `ss_flag` Nullable(Enum8('0' = 1, '1' = 2, 'E' = 3)) CODEC(ZSTD(6)),
    `forward_price` Nullable(Float64) CODEC(ZSTD(6)),
    `expiry_indicator` LowCardinality(Nullable(String)) CODEC(ZSTD(6)),
    `root` LowCardinality(Nullable(String)) CODEC(ZSTD(6)),
    `suffix` LowCardinality(Nullable(String)) CODEC(ZSTD(6))
```

In `SECURITY_PRICE_TABLE_SQL`, set:

```sql
    `secid` Nullable(UInt32) CODEC(ZSTD(6)),
    `date` Nullable(Date32) CODEC(DoubleDelta, ZSTD(6)),
    `volume` Nullable(UInt64) CODEC(ZSTD(6)),
```

In `REFERENCE_TABLE_SQL_BY_SOURCE`, set all `secid` and `link_secid`
definitions to `Nullable(UInt32)`, `seq_num` and `permno` definitions to
`Nullable(UInt32)`, all date definitions to:

```sql
Nullable(Date32) CODEC(DoubleDelta, ZSTD(6))
```

and replace nullable categorical text declarations such as:

```sql
LowCardinality(String) CODEC(ZSTD(6))
```

with:

```sql
LowCardinality(Nullable(String)) CODEC(ZSTD(6))
```

Change high-cardinality descriptive columns to:

```sql
`issuer` Nullable(String) CODEC(ZSTD(6)),
`issue` Nullable(String) CODEC(ZSTD(6)),
```

- [ ] **Step 4: Run the schema tests and verify they pass**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse_loader.IvydbClickhouseSchemaTests -v
```

Expected: all curated-schema tests pass.

- [ ] **Step 5: Commit the physical-schema contract**

```bash
git add tests/test_ivydb_clickhouse_loader.py ivydb/clickhouse_loader/create_option_price_tables.py ivydb/clickhouse_loader/create_security_price_tables.py ivydb/clickhouse_loader/create_reference_tables.py
git commit -m "Correct IvyDB ClickHouse physical types and date codecs"
```

## Task 2: Preserve Nulls And Validate Narrowed Values At Ingestion

**Files:**
- Create: `ivydb/clickhouse_loader/normalization.py`
- Modify: `tests/test_ivydb_clickhouse_loader.py`

- [ ] **Step 1: Add null-preservation and semantic-validation tests**

Replace `test_normalize_batch_adds_source_year_first_and_fills_string_nulls`
with:

```python
def test_option_normalization_preserves_null_categories_and_casts_counts(self) -> None:
    """Nullable categories remain missing while valid counts use unsigned storage."""

    import pandas as pd

    from ivydb.clickhouse_loader.normalization import normalize_batch_for_clickhouse
    from ivydb.clickhouse_loader.table_plan import TablePlan

    table = TablePlan(
        source_library="optionm_all",
        source_table="opprcd2024",
        target_table="opprcd2024",
        source_prefix="opprcd",
        source_year=2024,
        load_group="option-prices",
        layout="separate_year_table",
        source_year_column=None,
    )
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

    result = normalize_batch_for_clickhouse(batch, table)

    self.assertTrue(pd.isna(result.loc[0, "cp_flag"]))
    self.assertEqual(str(result["secid"].dtype), "UInt32")
    self.assertEqual(str(result["volume"].dtype), "UInt64")
    self.assertEqual(str(result["optionid"].dtype), "UInt64")
```

Add invalid-boundary tests:

```python
def test_option_normalization_rejects_fractional_volume(self) -> None:
    """Count columns cannot silently truncate a fractional WRDS value."""

    import pandas as pd

    from ivydb.clickhouse_loader.normalization import normalize_batch_for_clickhouse

    with self.assertRaisesRegex(ValueError, "volume.*whole non-negative"):
        normalize_batch_for_clickhouse(
            pd.DataFrame({"volume": [3.5]}),
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
```

Add a small `option_price_plan()` method on the test class to return the
`TablePlan` shown in the first test.

- [ ] **Step 2: Run the new normalization tests and verify they fail**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse_loader.IvydbClickhouseLoadTests -v
```

Expected: `ERROR` or `FAIL` because `ivydb.clickhouse_loader.normalization`
does not yet exist and current behavior fills text nulls.

- [ ] **Step 3: Implement focused chunk normalization**

Create `ivydb/clickhouse_loader/normalization.py` with constants and functions
equivalent to:

```python
"""Validate and cast WRDS IvyDB chunks before ClickHouse insertion."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ivydb.clickhouse_loader.table_plan import TablePlan


@dataclass(frozen=True)
class UnsignedColumnRule:
    """Target unsigned-integer type for one semantically integral column."""

    column_name: str
    pandas_dtype: str
    maximum: int


UINT32_MAX = (2**32) - 1
UINT64_MAX = (2**64) - 1
OPTION_UNSIGNED_RULES = (
    UnsignedColumnRule("secid", "UInt32", UINT32_MAX),
    UnsignedColumnRule("volume", "UInt64", UINT64_MAX),
    UnsignedColumnRule("open_interest", "UInt64", UINT64_MAX),
    UnsignedColumnRule("optionid", "UInt64", UINT64_MAX),
    UnsignedColumnRule("am_settlement", "UInt32", UINT32_MAX),
    UnsignedColumnRule("contract_size", "UInt32", UINT32_MAX),
)
SECURITY_PRICE_UNSIGNED_RULES = (
    UnsignedColumnRule("secid", "UInt32", UINT32_MAX),
    UnsignedColumnRule("volume", "UInt64", UINT64_MAX),
)
REFERENCE_UNSIGNED_COLUMNS = {
    "securd": (UnsignedColumnRule("secid", "UInt32", UINT32_MAX),),
    "secnmd": (UnsignedColumnRule("secid", "UInt32", UINT32_MAX),),
    "exchgd": (
        UnsignedColumnRule("secid", "UInt32", UINT32_MAX),
        UnsignedColumnRule("seq_num", "UInt32", UINT32_MAX),
    ),
    "distrd": (
        UnsignedColumnRule("secid", "UInt32", UINT32_MAX),
        UnsignedColumnRule("link_secid", "UInt32", UINT32_MAX),
        UnsignedColumnRule("seq_num", "UInt32", UINT32_MAX),
    ),
    "opinfd": (UnsignedColumnRule("secid", "UInt32", UINT32_MAX),),
    "opcrsphist": (
        UnsignedColumnRule("secid", "UInt32", UINT32_MAX),
        UnsignedColumnRule("permno", "UInt32", UINT32_MAX),
    ),
}
OPTION_ENUM_VALUES = {
    "cp_flag": {"C", "P"},
    "symbol_flag": {"0", "1"},
    "ss_flag": {"0", "1", "E"},
}


def normalize_batch_for_clickhouse(batch: pd.DataFrame, table: TablePlan) -> pd.DataFrame:
    """Return one validated chunk shaped for its curated ClickHouse table."""

    normalized = batch.copy()
    if table.is_consolidated_year_table:
        if table.source_year is None or table.source_year_column is None:
            raise ValueError("consolidated yearly tables need source-year metadata")
        normalized.insert(0, table.source_year_column, table.source_year)

    if table.source_prefix == "opprcd":
        _validate_enum_columns(normalized, OPTION_ENUM_VALUES)
        rules = OPTION_UNSIGNED_RULES
    elif table.source_prefix == "secprd":
        rules = SECURITY_PRICE_UNSIGNED_RULES
    else:
        rules = REFERENCE_UNSIGNED_COLUMNS.get(table.source_table, ())

    for rule in rules:
        _cast_nullable_unsigned(normalized, rule)
    return normalized


def _cast_nullable_unsigned(dataframe: pd.DataFrame, rule: UnsignedColumnRule) -> None:
    """Validate and cast one nullable identifier or count column in place."""

    if rule.column_name not in dataframe.columns:
        return
    observed = dataframe[rule.column_name].dropna()
    invalid = (
        (observed < 0)
        | (observed > rule.maximum)
        | ((observed % 1) != 0)
    )
    if invalid.any():
        raise ValueError(
            f"{rule.column_name} must contain whole non-negative values "
            f"no greater than {rule.maximum}"
        )
    dataframe[rule.column_name] = dataframe[rule.column_name].astype(rule.pandas_dtype)


def _validate_enum_columns(
    dataframe: pd.DataFrame,
    allowed_values_by_column: dict[str, set[str]],
) -> None:
    """Reject categorical values that do not fit curated enum definitions."""

    for column_name, allowed_values in allowed_values_by_column.items():
        if column_name not in dataframe.columns:
            continue
        observed = set(dataframe[column_name].dropna().astype(str))
        unexpected_values = observed - allowed_values
        if unexpected_values:
            raise ValueError(f"{column_name} contains unexpected values: {sorted(unexpected_values)}")
```

Do not add any `fillna("")` operation. Pandas null values must pass through to
nullable ClickHouse columns.

- [ ] **Step 4: Run the normalization tests and verify they pass**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse_loader.IvydbClickhouseLoadTests -v
```

Expected: normalization tests pass; staging-dependent load tests can still fail
until Task 3 updates the loader workflow.

- [ ] **Step 5: Commit boundary validation**

```bash
git add ivydb/clickhouse_loader/normalization.py tests/test_ivydb_clickhouse_loader.py
git commit -m "Validate and preserve IvyDB values during insertion"
```

## Task 3: Replace Staging With Direct Append-Once Loading

**Files:**
- Modify: `tests/test_ivydb_clickhouse_loader.py`
- Modify: `ivydb/clickhouse_loader/load_to_clickhouse.py`
- Delete: `ivydb/clickhouse_loader/schema.py`
- Modify: `ivydb/clickhouse_loader/wrds_stream.py`

- [ ] **Step 1: Replace staging tests with direct-load tests**

Delete tests for `build_replace_commands`, staging promotion, and renaming
`_tmp_...` tables. Add:

```python
def test_load_streams_directly_into_precreated_final_table(self) -> None:
    """Append-once historical data should not create or copy through staging."""

    import pandas as pd

    from ivydb.clickhouse_loader.config import default_config
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
        results = load_tables(config, object(), client, [self.option_price_plan()])

    self.assertEqual(results[0].rows_loaded, 1)
    self.assertEqual(client.inserted_tables, ["opprcd2024"])
    self.assertFalse(any("_tmp_" in command for command in client.commands))

def test_direct_load_requires_precreated_curated_target(self) -> None:
    """The loader must not replace curated DDL with a derived schema."""

    from ivydb.clickhouse_loader.config import default_config
    from ivydb.clickhouse_loader.load_to_clickhouse import load_tables

    client = self.missing_target_client()
    with self.assertRaisesRegex(ValueError, "run create-tables first"):
        load_tables(default_config(), object(), client, [self.option_price_plan()])
```

Refactor existing fake-client and `TablePlan` construction into small class
helpers only when needed to keep each test readable.

- [ ] **Step 2: Run the direct-load tests and verify they fail**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse_loader.IvydbClickhouseLoadTests.test_load_streams_directly_into_precreated_final_table tests.test_ivydb_clickhouse_loader.IvydbClickhouseLoadTests.test_direct_load_requires_precreated_curated_target -v
```

Expected: failures showing insertion into `_tmp_opprcd2024` or derived-schema
creation instead of direct final-table insertion.

- [ ] **Step 3: Simplify `load_to_clickhouse.py` to direct insertion**

Import normalization and retain only streaming/audit/duplicate responsibilities:

```python
from ivydb.clickhouse_loader.normalization import normalize_batch_for_clickhouse
from ivydb.clickhouse_loader.wrds_stream import stream_table
```

Change `load_tables` to require pre-created targets and remove replacement:

```python
def load_tables(
    config: AppConfig,
    wrds_connection: object,
    clickhouse_client: object,
    table_plan: list[TablePlan],
) -> list[LoadResult]:
    """Stream selected historical WRDS sources directly into curated final tables."""

    results: list[LoadResult] = []
    for table in table_plan:
        if _should_skip_completed_source(config, table):
            results.append(LoadResult(table.source_table, table.target_table, 0))
            continue
        _require_empty_load_destination(config, clickhouse_client, table)
        results.append(
            _load_one_table_direct(config, wrds_connection, clickhouse_client, table)
        )
    return results
```

Implement the direct streaming loop:

```python
def _load_one_table_direct(
    config: AppConfig,
    wrds_connection: object,
    clickhouse_client: object,
    table: TablePlan,
) -> LoadResult:
    """Insert source chunks directly into a pre-created curated final table."""

    started_at = datetime.now(UTC)
    rows_loaded = 0
    try:
        for chunk in stream_table(
            wrds_connection=wrds_connection,
            source_library=table.source_library,
            source_table=table.source_table,
            chunksize=config.loader.wrds_batch_size,
        ):
            normalized_chunk = normalize_batch_for_clickhouse(chunk, table)
            for insert_batch in split_dataframe_for_insert(
                normalized_chunk,
                config.loader.clickhouse_insert_size,
            ):
                clickhouse_client.insert_df(
                    table=table.target_table,
                    df=insert_batch,
                    database=config.clickhouse.database,
                )
            rows_loaded += len(normalized_chunk)
        _write_audit_row(config, table, rows_loaded, started_at, "complete", "")
        return LoadResult(table.source_table, table.target_table, rows_loaded)
    except Exception as exc:
        _write_audit_row(config, table, rows_loaded, started_at, "failed", str(exc))
        raise
```

Rename the duplicate guard to express append-once behavior and make it require
the curated table already exists:

```python
def _require_empty_load_destination(
    config: AppConfig,
    clickhouse_client: object,
    table: TablePlan,
) -> None:
    """Refuse direct inserts unless the selected source has no final rows."""

    database = config.clickhouse.database
    if not table_exists(clickhouse_client, database, table.target_table):
        raise ValueError(
            f"{table.target_table} is missing; run create-tables first "
            "to create its curated schema"
        )
    if table.is_consolidated_year_table:
        result = clickhouse_client.query(
            f"SELECT count() FROM `{database}`.`{table.target_table}` "
            f"WHERE `{table.source_year_column}` = {table.source_year}"
        )
        has_existing_rows = int(result.result_rows[0][0]) > 0
    else:
        has_existing_rows = table_row_count(clickhouse_client, database, table.target_table) > 0
    if has_existing_rows:
        raise ValueError(
            f"{table.target_table} already has rows for {table.source_table}; "
            "do not reload append-once historical data"
        )
```

Remove staging, metadata DDL, replacement, `dry_run`, and `schema_only`
functions and arguments from this module. Update `cli.py` calls to use the
simplified `load_tables(...)` signature.

- [ ] **Step 4: Remove orphaned generic schema generation**

Delete `ivydb/clickhouse_loader/schema.py`. In `wrds_stream.py`, remove
`PostgresColumn`, `build_column_metadata_query()`, and
`fetch_postgres_columns()` so the remaining module exposes only full-table
streaming:

```python
def stream_table(
    wrds_connection: object,
    source_library: str,
    source_table: str,
    chunksize: int,
) -> Iterable[object]:
    """Yield pandas DataFrame chunks from one WRDS source table."""

    query = build_select_query(source_library, source_table)
    return wrds_connection.raw_sql(query, chunksize=chunksize, return_iter=True)
```

- [ ] **Step 5: Run loader tests and verify the direct path passes**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse_loader.IvydbClickhouseLoadTests tests.test_ivydb_clickhouse_loader.IvydbClickhouseWrdsSqlTests -v
```

Expected: all retained and new direct-load tests pass.

- [ ] **Step 6: Commit direct loading**

```bash
git add tests/test_ivydb_clickhouse_loader.py ivydb/clickhouse_loader/load_to_clickhouse.py ivydb/clickhouse_loader/cli.py ivydb/clickhouse_loader/wrds_stream.py
git add -u ivydb/clickhouse_loader/schema.py
git commit -m "Stream IvyDB history directly into curated ClickHouse tables"
```

## Task 4: Add Explicit Failed-Load Clearing And Remove Replacement Configuration

**Files:**
- Modify: `tests/test_ivydb_clickhouse_loader.py`
- Modify: `ivydb/clickhouse_loader/load_to_clickhouse.py`
- Modify: `ivydb/clickhouse_loader/cli.py`
- Modify: `ivydb/clickhouse_loader/config.py`
- Modify: `ivydb/clickhouse_loader/config.toml`
- Modify: `ivydb/clickhouse_loader/create_option_price_tables.py`
- Modify: `ivydb/clickhouse_loader/create_security_price_tables.py`
- Modify: `ivydb/clickhouse_loader/create_reference_tables.py`
- Modify: `ivydb/clickhouse_loader/create_tables.py`
- Modify: `ivydb/clickhouse_loader/clickhouse_client.py`
- Modify: `ivydb/ivyd.xml`

- [ ] **Step 1: Write tests for deliberate failure cleanup**

Add:

```python
def test_clear_failed_truncates_failed_separate_target_without_replacing_schema(self) -> None:
    """Failed option loads clear rows while retaining curated DDL."""

    from ivydb.clickhouse_loader.load_to_clickhouse import clear_failed_tables

    client = self.recording_client()
    config = self.config_with_failed_audit(self.option_price_plan())

    cleared = clear_failed_tables(config, client, [self.option_price_plan()])

    self.assertEqual(cleared, ["opprcd2024"])
    self.assertIn("TRUNCATE TABLE `ivydb`.`opprcd2024`", client.commands)
    self.assertFalse(any("DROP TABLE" in command for command in client.commands))

def test_clear_failed_drops_only_failed_secprd_source_year_partition(self) -> None:
    """Clearing one failed consolidated source must retain other loaded years."""

    from ivydb.clickhouse_loader.load_to_clickhouse import clear_failed_tables

    client = self.recording_client()
    table = self.security_price_plan(2024)
    config = self.config_with_failed_audit(table)

    clear_failed_tables(config, client, [table])

    self.assertIn(
        "ALTER TABLE `ivydb`.`secprd` DROP PARTITION IF EXISTS 2024",
        client.commands,
    )

def test_clear_failed_refuses_to_clear_completed_target(self) -> None:
    """Cleanup must not erase a source whose latest audit status is complete."""

    from ivydb.clickhouse_loader.load_to_clickhouse import clear_failed_tables

    config = self.config_with_complete_audit(self.option_price_plan())
    with self.assertRaisesRegex(ValueError, "latest audit status is complete"):
        clear_failed_tables(config, self.recording_client(), [self.option_price_plan()])
```

Add CLI parser expectation:

```python
clear_args = parser.parse_args(["clear-failed"])
self.assertEqual(clear_args.command, "clear-failed")
```

- [ ] **Step 2: Run cleanup and CLI tests and verify they fail**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse_loader.IvydbClickhouseLoadTests tests.test_ivydb_clickhouse_loader.IvydbClickhouseCliTests -v
```

Expected: failure because `clear_failed_tables` and the `clear-failed`
subcommand do not exist, and the old config still exposes replacement.

- [ ] **Step 3: Implement explicit cleanup using latest audit status**

Replace `_local_audit_has_complete()` with a status-returning helper:

```python
def _local_audit_latest_status(audit_path: Path, table: TablePlan) -> str | None:
    """Return the latest recorded status for one exact source-target pair."""

    latest_status: str | None = None
    if not audit_path.exists():
        return None
    for line_number, line in enumerate(
        audit_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid JSON in audit log {audit_path} on line {line_number}"
            ) from exc
        if (
            record.get("source_library") == table.source_library
            and record.get("source_table") == table.source_table
            and record.get("target_table") == table.target_table
        ):
            latest_status = str(record.get("status", ""))
    return latest_status
```

Have resume skip only when this helper returns `"complete"`. Implement cleanup:

```python
def clear_failed_tables(
    config: AppConfig,
    clickhouse_client: object,
    table_plan: list[TablePlan],
) -> list[str]:
    """Clear only direct-load destinations whose latest audit event failed."""

    cleared_tables: list[str] = []
    for table in table_plan:
        status = _local_audit_latest_status(config.loader.audit_log_path, table)
        if status != "failed":
            raise ValueError(
                f"cannot clear {table.source_table}: latest audit status is {status}"
            )
        database = config.clickhouse.database
        if table.is_consolidated_year_table:
            command = (
                f"ALTER TABLE `{database}`.`{table.target_table}` "
                f"DROP PARTITION IF EXISTS {table.source_year}"
            )
        else:
            command = f"TRUNCATE TABLE `{database}`.`{table.target_table}`"
        clickhouse_client.command(command)
        _write_audit_row(config, table, 0, datetime.now(UTC), "cleared", "")
        cleared_tables.append(table.target_table)
    return cleared_tables
```

Expose `clear-failed` in `cli.py` and print each cleared source/target pair.

- [ ] **Step 4: Remove replacement and implicit database-creation configuration**

Delete `DEFAULT_REPLACE`, `DEFAULT_CREATE_DATABASE`, `LoaderConfig.replace`,
and `LoaderConfig.create_database` from `config.py`. Remove `replace = false`
from `config.toml`. Remove normal-path `ensure_database()` calls from
`create_tables.py`, `cli.py`, and the standalone `main()` functions in
`create_option_price_tables.py`, `create_security_price_tables.py`, and
`create_reference_tables.py`. Remove the now-unused `ensure_database()` helper
and imports from `clickhouse_client.py`. The run manual will instruct the user
to create database `ivydb` once with an administrative account before
configuring `ivydb_user`.

Change `ivydb/ivyd.xml` to grant the operation used by explicit cleanup:

```xml
<query>GRANT SELECT, INSERT, CREATE TABLE, ALTER TABLE, TRUNCATE ON ivydb.*</query>
```

- [ ] **Step 5: Run config, CLI, and load tests and verify they pass**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse_loader.IvydbClickhouseConfigTests tests.test_ivydb_clickhouse_loader.IvydbClickhouseCliTests tests.test_ivydb_clickhouse_loader.IvydbClickhouseLoadTests -v
```

Expected: all direct-load, audit-resume, and failed-clear tests pass.

- [ ] **Step 6: Commit recovery workflow**

```bash
git add tests/test_ivydb_clickhouse_loader.py ivydb/clickhouse_loader/load_to_clickhouse.py ivydb/clickhouse_loader/cli.py ivydb/clickhouse_loader/config.py ivydb/clickhouse_loader/config.toml ivydb/clickhouse_loader/create_tables.py ivydb/clickhouse_loader/create_option_price_tables.py ivydb/clickhouse_loader/create_security_price_tables.py ivydb/clickhouse_loader/create_reference_tables.py ivydb/clickhouse_loader/clickhouse_client.py ivydb/ivyd.xml
git commit -m "Add deliberate recovery for failed IvyDB direct loads"
```

## Task 5: Update Documentation For The Implemented Workflow

**Files:**
- Modify: `README.md`
- Modify: `GUIDE_ROOT.md`
- Modify: `ivydb/GUIDE_ivydb.md`
- Modify: `ivydb/clickhouse_loader/GUIDE_clickhouse_loader.md`
- Modify: `ivydb/IVYDB_CLICKHOUSE_RUN_MANUAL.md`
- Modify: `tests/GUIDE_tests.md`

- [ ] **Step 1: Update user instructions and recovery commands**

Update `README.md` and `ivydb/IVYDB_CLICKHOUSE_RUN_MANUAL.md` so the normal
workflow is:

```bash
uv run python -m ivydb.clickhouse_loader create-tables
uv run python -m ivydb.clickhouse_loader load
uv run python -m ivydb.clickhouse_loader validate
```

Document failed direct-load recovery as:

```bash
# Use the same config selection that failed:
uv run python -m ivydb.clickhouse_loader clear-failed
uv run python -m ivydb.clickhouse_loader load
uv run python -m ivydb.clickhouse_loader validate
```

State explicitly:

- the selected IvyDB tables are historical append-once loads;
- `load` writes directly into pre-created curated ClickHouse tables;
- `clear-failed` refuses to erase any source whose latest audit status is not
  `failed`;
- annual option targets are truncated after a failed load, while `secprd`
  recovery drops only the failed `source_year` partition;
- database `ivydb` must be created administratively once before using
  `ivydb_user`.

- [ ] **Step 2: Update developer guides**

In `GUIDE_ROOT.md`, `ivydb/GUIDE_ivydb.md`, and
`ivydb/clickhouse_loader/GUIDE_clickhouse_loader.md`, remove staging and
replacement descriptions. Explain:

- curated DDL, rather than source-metadata DDL, owns physical ClickHouse types;
- categorical nulls remain null;
- identifier/count casts are validated at the incoming-chunk boundary;
- date columns use `DoubleDelta` plus `ZSTD(6)`;
- failed partial direct loads require `clear-failed`.

Add a short journal entry dated `2026-05-25` in the existing IvyDB guides:

```markdown
- 2026-05-25: Switched historical IvyDB ingestion to direct writes into
  curated final tables, preserving nullable categories and adding explicit
  failed-load clearing rather than routine replacement.
```

In `tests/GUIDE_tests.md`, replace the references to string-null normalization,
staging, and replacement with direct-load, nullable-category preservation,
semantic integer validation, date codecs, and `clear-failed` coverage.

- [ ] **Step 3: Check documentation for stale workflow terms**

Run:

```bash
rg -n "staging|temporary ClickHouse|replace =|--replace|promotion|metadata-generated|fills string|nulls become empty" README.md GUIDE_ROOT.md ivydb tests/GUIDE_tests.md
```

Expected: no active workflow instruction describes staging or normal
replacement; historical journal entries may remain only when clearly dated as
superseded history.

- [ ] **Step 4: Commit documentation**

```bash
git add README.md GUIDE_ROOT.md ivydb/GUIDE_ivydb.md ivydb/clickhouse_loader/GUIDE_clickhouse_loader.md ivydb/IVYDB_CLICKHOUSE_RUN_MANUAL.md tests/GUIDE_tests.md
git commit -m "Document append-once IvyDB direct-load workflow"
```

## Task 6: Verify The Full Change Before Completion

**Files:**
- Verify only; do not edit unless a failing check identifies a defect.

- [ ] **Step 1: Run the full IvyDB unit test module**

Run:

```bash
uv run python -m unittest tests.test_ivydb_clickhouse_loader -v
```

Expected: all IvyDB tests pass.

- [ ] **Step 2: Run the repository regression test suite**

Run:

```bash
uv run python -m unittest discover -s tests -v
uv run python -m unittest boardex_parquet.test_clickhouse_loader -v
```

Expected: all local regression tests pass.

- [ ] **Step 3: Execute the touched package without contacting WRDS**

Create a temporary config selecting no source tables, then exercise the CLI
parser/config path without an expensive data request:

```bash
uv run python -m ivydb.clickhouse_loader --help
```

Expected: help output lists `create-tables`, `load`, `validate`, and
`clear-failed`.

If a local ClickHouse instance is available, additionally create a temporary
database and run the direct-load and clear-failed paths with tiny in-memory
data through a local integration script. If ClickHouse is not running, state
that live integration was not available rather than claiming it was tested.

- [ ] **Step 4: Review the implemented diff and working tree**

Run:

```bash
git diff --stat HEAD~4..HEAD
git status --short --branch
```

Expected: commits contain only the IvyDB loader, tests, permissions, and
documentation changes described above; the working tree is clean.

## Implementation Notes

- Do not load real WRDS history while developing these changes. The unit tests
  and a tiny optional local ClickHouse integration are sufficient before a
  deliberate production load.
- Do not silently coerce values that do not fit narrowed types. A type failure
  is evidence that the curated schema needs revisiting.
- Do not reintroduce automatic replacement. `clear-failed` is a narrowly
  scoped recovery operation for a known failed append-once load.
- Do not implement additional price/volatility codecs without measuring them
  against actual ClickHouse compressed bytes.
