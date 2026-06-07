# Loading BoardEx Parquet Files Into ClickHouse

## Which Database Should You Use?

Use **ClickHouse** for this BoardEx pocket-file bundle by default.

ClickHouse is a columnar analytical database: it stores each column separately
and is optimized for scans, filters, aggregations, and large table joins. That
matches this folder because the local BoardEx bundle has 35 Parquet files and
about 110 million rows.

Use **PostgreSQL** only if your main goal is transactional editing, strict
relational constraints, or small normalized lookup workflows. For quantitative
research and repeated analytical queries, ClickHouse is the better fit.

## One-Time Setup

Edit:

```bash
boardex_parquet/clickhouse_config.toml
```

Set the target connection:

```toml
[clickhouse]
host = "localhost"
port = 8123
username = "default"
password = ""
secure = false
database = "myclickhouse"
```

The loader creates one ClickHouse table per Parquet file. For example:

```text
boardex_parquet/outputs/boardex_na__na_dir_profile_emp.parquet
```

loads into:

```text
myclickhouse.boardex_na__na_dir_profile_emp
```

## Dry Run

Preview all planned tables and generated ClickHouse table definitions:

```bash
uv run python boardex_parquet/load_parquet_to_clickhouse.py dry-run
```

Preview one table:

```bash
uv run python boardex_parquet/load_parquet_to_clickhouse.py dry-run \
  --table boardex_na__na_dir_profile_emp
```

## Load All Pocket Files

```bash
uv run python boardex_parquet/load_parquet_to_clickhouse.py load
```

This is the one-command load path: it reads every `.parquet` file currently in
`boardex_parquet/outputs/` and writes one ClickHouse table per file.

The default config has `resume = true`, so tables whose ClickHouse row counts
already match the Parquet files are skipped.

## Create Empty Tables First

Use this when you want to create the database and empty tables, inspect them in
ClickHouse, and only then insert the Parquet rows:

```bash
uv run python boardex_parquet/load_parquet_to_clickhouse.py create-schema
```

Then inspect the empty tables in ClickHouse. For example:

```sql
SHOW TABLES FROM myclickhouse;
DESCRIBE TABLE myclickhouse.boardex_na__na_dir_profile_emp;
SELECT count() FROM myclickhouse.boardex_na__na_dir_profile_emp;
```

When the empty schema looks right, load the data:

```bash
uv run python boardex_parquet/load_parquet_to_clickhouse.py load
```

The `load` command accepts empty pre-created tables. It still refuses non-empty
tables whose row counts do not match the Parquet files unless you pass
`--replace`.

## Load One Pocket File

```bash
uv run python boardex_parquet/load_parquet_to_clickhouse.py load \
  --table boardex_na__na_dir_profile_emp
```

## Replace Existing Tables

Use this when you want to rebuild the target table from the local Parquet file:

```bash
uv run python boardex_parquet/load_parquet_to_clickhouse.py load \
  --table boardex_na__na_dir_profile_emp \
  --replace
```

For all tables:

```bash
uv run python boardex_parquet/load_parquet_to_clickhouse.py load --replace
```

## Validate After Loading

Compare each ClickHouse table row count with the Parquet footer row count:

```bash
uv run python boardex_parquet/load_parquet_to_clickhouse.py validate
```

Validate one table:

```bash
uv run python boardex_parquet/load_parquet_to_clickhouse.py validate \
  --table boardex_na__na_dir_profile_emp
```

## Important Date Detail

BoardEx contains far-future sentinel dates such as `9000-01-01`. A sentinel
date is a special placeholder value, often meaning "unknown" or "open-ended."
ClickHouse native date types cannot safely store that range, so this loader
stores Parquet `date32` columns as nullable strings in `YYYY-MM-DD` format.

Most BoardEx Parquet columns are nullable, which means they can contain missing
values. Some of those nullable columns are useful ClickHouse sort keys, such as
`directorid` and `annualreportdate`. The generated `MergeTree` table definitions
therefore include `SETTINGS allow_nullable_key = 1` when needed.

For analysis, cast valid dates inside a query when needed:

```sql
SELECT
    parseDateTimeBestEffortOrNull(datestartrole) AS parsed_start_date,
    count()
FROM myclickhouse.boardex_na__na_dir_profile_emp
GROUP BY parsed_start_date
```
