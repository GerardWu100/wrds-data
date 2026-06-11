# IvyDB ClickHouse Loader — Instruction Manual

This manual explains how to download OptionMetrics IvyDB US data from WRDS
PostgreSQL into ClickHouse.

**WRDS** = Wharton Research Data Services.
**ClickHouse** = your local analytical database.

---

## How It Works

1. Create database `ivydb` once with an administrative ClickHouse account.
2. Edit `ivydb/clickhouse_loader/config.toml` for the batch you want.
3. Run **one command** to create empty ClickHouse tables with curated schemas.
4. Inspect the tables manually.
5. Run **one command** to stream data from WRDS directly into those tables.

That is the entire workflow. There are no `--run-group`, year-range, or other
CLI flags on the normal path. Everything is controlled in `config.toml`.

```bash
cd /path/to/wrds-data

uv run python -m ivydb.clickhouse_loader create-tables
uv run python -m ivydb.clickhouse_loader load
```

Optional third command after a load:

```bash
uv run python -m ivydb.clickhouse_loader validate
```

Dangerous manual reset command:

```bash
uv run python -m ivydb.clickhouse_loader drop-tables
```

`drop-tables` permanently removes the ClickHouse tables selected in
`config.toml`. It is deliberately excluded from the normal path. It must be run
from an interactive terminal and requires two exact confirmations before it
executes: first the target database name, then the exact comma-separated table
list shown by the command.

Selected IvyDB tables are historical append-once loads. The loader writes
directly into pre-created curated ClickHouse tables and refuses to reload a
source whose destination already has rows.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| `.pgpass` | WRDS PostgreSQL credentials |
| `config.toml` | Table selection plus non-secret ClickHouse defaults |
| `ivydb/.env` | Local ClickHouse Docker connection values |
| ClickHouse running | Test with `curl http://localhost:8123/ping` |
| Database `ivydb` | Create once with an admin account before using `ivydb_user` |
| WRDS IvyDB access | Duo MFA may prompt on first `load` |

Create the database once before the first `create-tables` run:

```sql
CREATE DATABASE IF NOT EXISTS ivydb;
```

Create a local environment file from the checked-in example:

```bash
cp ivydb/.env.example ivydb/.env
```

Edit `ivydb/.env` so `IVYDB_CLICKHOUSE_PASSWORD` matches the password in your
ClickHouse user XML. The Python loader reads process environment variables first,
then `ivydb/.env`, then non-secret defaults from `config.toml`.

See `ivydb/ivydb.xml.example` for a sample `ivydb_user` grant set that includes
`TRUNCATE` for failed-load recovery and `DROP TABLE` for the dangerous manual
`drop-tables` reset command.

Before running the main loader, poke the Docker ClickHouse connection:

```bash
uv run python ivydb/poke_clickhouse_connection.py
```

---

## config.toml Controls Table Selection

Three table families. Enable **one at a time** for each batch.

| Section | What it loads | ClickHouse result |
|---|---|---|
| `[tables.static_reference]` | Security master, names, exchange history, distributions, option flags, CRSP link | One table each (`securd`, `secnmd`, …) |
| `[tables.underlying_prices]` | Underlying stock prices `secprdYYYY` | All years → **one** `secprd` table |
| `[tables.option_prices]` | Option prices `opprcdYYYY` | One table per year |

Each section has an `enabled` flag. When `enabled = false`, that family is
skipped entirely.

For option prices, put the exact years you want in the `years = [...]` list.
For a 5-year slice, list only those five years.

Loader behaviour (resume and log paths) lives in `[loader]`:

```toml
[loader]
resume = true
audit_log_path = "logs/ivydb_load_audit.jsonl"
run_log_path = "logs/ivydb_loader.log"
year_summary_log_path = "logs/ivydb_year_summary.log"
```

`audit_log_path` is the machine-readable JSON-lines file used for resume and
cleanup decisions. `run_log_path` is the detailed progress log. The separate
`year_summary_log_path` receives one compact human-readable line after each
yearly source table finishes, including the source year, inserted rows, target
row count when available, and elapsed seconds.

---

## Failed-Load Recovery

If a direct load fails partway through, the command stops at that source and
does not try later selected sources. Inspect the error first, then use the same
config selection that failed:

```bash
uv run python -m ivydb.clickhouse_loader clear-failed
uv run python -m ivydb.clickhouse_loader load
uv run python -m ivydb.clickhouse_loader validate
```

The loader writes a `started` audit event before insertion, so this recovery
also handles a process interrupted before it could write an error. `clear-failed`
clears sources whose latest audit status is `started` or `failed`; it ignores
completed and never-started sources in the same selected batch. Annual option
targets are truncated after an incomplete load, while `secprd` recovery drops
only the incomplete `source_year` partition.

Do **not** use `drop-tables` for ordinary failed-load recovery. `clear-failed`
is the safer recovery command because it only clears incomplete work recorded in
the audit log. Use `drop-tables` only when you intentionally want to destroy the
selected ClickHouse tables and rebuild them from scratch.

---

## Dangerous Manual Table Drop

`drop-tables` uses the same `config.toml` table selection as `create-tables`.
For example, if only `[tables.option_prices]` is enabled with
`years = [1996, 1997]`, the command targets only `opprcd1996` and `opprcd1997`.
For underlying prices, multiple `secprdYYYY` source years still map to the one
consolidated ClickHouse table `secprd`, so the drop target is `secprd`.

Run it only from a real terminal:

```bash
uv run python -m ivydb.clickhouse_loader drop-tables
```

The command then prints the target database and selected tables. It will ask for
two exact confirmations:

1. Type the database name, for example `ivydb`.
2. Type the exact comma-separated table list shown by the command, for example
   `opprcd1996,opprcd1997`.

If either answer differs by even one character, the command aborts before
connecting to ClickHouse. There is no `--force` flag.

The ClickHouse user must have `DROP TABLE` on the selected `ivydb.*` tables. If
ClickHouse returns `ACCESS_DENIED`, update the local ClickHouse user grant from
`ivydb/ivydb.xml.example` or run the drop with an administrative ClickHouse
account.

---

## Three-Batch Load Order

Run batches in this order. For each batch: edit config → `create-tables` →
inspect → `load` → `validate`.

### Batch 1 — reference and link tables (small)

```toml
[tables.option_prices]
enabled = false

[tables.underlying_prices]
enabled = false

[tables.static_reference]
enabled = true
tables = [
  "securd",
  "secnmd",
  "exchgd",
  "distrd",
  "opinfd",
  "opcrsphist",
]
```

```bash
uv run python -m ivydb.clickhouse_loader create-tables
uv run python -m ivydb.clickhouse_loader load
uv run python -m ivydb.clickhouse_loader validate
```

### Batch 2 — underlying stock prices (medium)

All `secprdYYYY` years consolidate into one ClickHouse table with a
`source_year` column.

```toml
[tables.option_prices]
enabled = false

[tables.static_reference]
enabled = false

[tables.underlying_prices]
enabled = true
years = [
  1996, 1997, 1998, 1999, 2000,
  2001, 2002, 2003, 2004, 2005,
  2006, 2007, 2008, 2009, 2010,
  2011, 2012, 2013, 2014, 2015,
  2016, 2017, 2018, 2019, 2020,
  2021, 2022, 2023, 2024, 2025,
]
```

```bash
uv run python -m ivydb.clickhouse_loader create-tables
uv run python -m ivydb.clickhouse_loader load
uv run python -m ivydb.clickhouse_loader validate
```

### Batch 3 — option prices (large, ~5 years at a time)

Edit `years` for each slice. Example for 1996–2000:

```toml
[tables.static_reference]
enabled = false

[tables.underlying_prices]
enabled = false

[tables.option_prices]
enabled = true
years = [1996, 1997, 1998, 1999, 2000]
```

```bash
uv run python -m ivydb.clickhouse_loader create-tables
uv run python -m ivydb.clickhouse_loader load
uv run python -m ivydb.clickhouse_loader validate
```

Then change `years` to the next slice and repeat:

| Slice | `years` |
|---|---|
| 1996–2000 | `[1996, 1997, 1998, 1999, 2000]` |
| 2001–2005 | `[2001, 2002, 2003, 2004, 2005]` |
| 2006–2010 | `[2006, 2007, 2008, 2009, 2010]` |
| 2011–2015 | `[2011, 2012, 2013, 2014, 2015]` |
| 2016–2020 | `[2016, 2017, 2018, 2019, 2020]` |
| 2021–2025 | `[2021, 2022, 2023, 2024, 2025]` |

If a slice fails halfway, the current command stops. After checking the error,
run `clear-failed`, then rerun `load` with the same config. Completed years are
left untouched and skipped automatically when `resume = true`.

---

## Inspecting Tables After create-tables

```sql
SHOW TABLES FROM ivydb;
DESCRIBE TABLE ivydb.securd;
SELECT count() FROM ivydb.securd;   -- should be 0 before load
SHOW CREATE TABLE ivydb.opprcd1996;
```

---

## Smoke Test First

Test the pipeline on the smallest reference table before a full batch.

```toml
[tables.option_prices]
enabled = false

[tables.underlying_prices]
enabled = false

[tables.static_reference]
enabled = true
tables = ["opinfd"]
```

```bash
uv run python -m ivydb.clickhouse_loader create-tables
uv run python -m ivydb.clickhouse_loader load
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `create-tables` fails immediately | Check ClickHouse host, port, password in `config.toml`; confirm database `ivydb` exists |
| WRDS auth fails | Verify `.pgpass`; approve Duo MFA |
| Batch stops halfway | Inspect the error, run `clear-failed`, then rerun `load` with the same config |
| Process interrupted during a load | Run `clear-failed`; a latest `started` audit event identifies the incomplete source |
| "already has rows" error | Do not reload completed append-once historical data; use `clear-failed` only for a source whose latest audit status is `started` or `failed` |
| Wrong tables run | Re-check `enabled` flags and `years` / `tables` lists |

Logs:

| File | Purpose |
|---|---|
| `logs/ivydb_loader.log` | Human-readable progress |
| `logs/ivydb_load_audit.jsonl` | Per-source-table completion state |

---

## Quick Reference

```bash
# Every batch follows the same commands:
uv run python -m ivydb.clickhouse_loader create-tables
uv run python -m ivydb.clickhouse_loader load

# Optional check after load:
uv run python -m ivydb.clickhouse_loader validate

# Recovery after a failed direct load:
uv run python -m ivydb.clickhouse_loader clear-failed
uv run python -m ivydb.clickhouse_loader load

# Dangerous manual reset for selected config tables:
uv run python -m ivydb.clickhouse_loader drop-tables

# Use a different config file (only optional CLI flag):
uv run python -m ivydb.clickhouse_loader --config /path/to/config.toml load
```

---

## Related Files

| File | Purpose |
|---|---|
| `ivydb/clickhouse_loader/config.toml` | Connection, table selection, loader settings |
| `ivydb/clickhouse_loader/GUIDE_clickhouse_loader.md` | Developer/code reference |
| `ivydb/optionmetrics_ivydb_download_plan.md` | Which WRDS tables to include |
