# GUIDE_non-crypto

## Part 1 -- Conceptual Explanation

### Purpose

Loads FirstRateData 1-minute OHLCV data for equities, futures, and FX from CSV text files into a ClickHouse table (`firstrate.futures`). This is the most flexible loader, supporting three filename patterns and timezone-aware timestamp conversion.

### Input Format

Three filename patterns are accepted, all with 6 CSV columns (no header):

```
YYYY-MM-DD HH:MM:SS,open,high,low,close,volume
```

| Pattern | Example | Symbol extracted |
|---|---|---|
| `*_full_1min.txt` | `SPY_full_1min.txt` | `SPY` |
| `*_full_1min_*.txt` | `SPY_full_1min_adjsplitdiv.txt` | `SPY` |
| `*_1min.txt` | `EU_U24_1min.txt` | `EU_U24` |

Symbol extraction uses regex: the `_full_1min` or `_1min` suffix is stripped, and everything before it becomes the symbol.

### Timezone Handling

Same as `indices/`: timestamps are interpreted as market-local (default `America/New_York`), converted to UTC, and stored in `DateTime64(3, 'America/New_York')`. Symbols listed in `utc_symbols` config are treated as already-UTC.

### ClickHouse Schema

```sql
CREATE TABLE firstrate.futures (
    symbol LowCardinality(String),
    ts DateTime64(3, 'America/New_York') CODEC(DoubleDelta, ZSTD(3)),
    open Float64 CODEC(ZSTD(3)),
    high Float64 CODEC(ZSTD(3)),
    low Float64 CODEC(ZSTD(3)),
    close Float64 CODEC(ZSTD(3)),
    volume Float64 CODEC(ZSTD(3))
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts)
```

Volume is `Float64` (not integer) because split/dividend-adjusted stock data can produce fractional volume values.

### Error Handling

Malformed rows are **skipped** (not fail-fast) and logged to `outputs/import_errors.log`. Negative price/volume values trigger a warning but are still inserted.

### Volume Parsing

The `_parse_volume_to_float()` function explicitly checks for finite values. Non-numeric or infinite values raise a `ValueError` and skip the row.

### Data Validation Utilities

- `check_data.py` -- runs sanity checks on loaded data.
- `data/check_max_last_col.py` -- inspects the last column of data files for anomalies.

---

## Part 2 -- Code Reference

### `load_ohlcv_to_clickhouse.py`

- `_FULL_1MIN_PATTERN`, `_GENERIC_1MIN_PATTERN` -- compiled regexes for the three supported filename patterns.
- `extract_symbol(file_path)` -- tries full pattern first, then generic. Raises `ValueError` if neither matches.
- `_parse_volume_to_float(raw_volume, file_path, line_number)` -- parses volume as float with finiteness check.
- `_is_supported_ohlcv_file(file_path)` -- predicate used by `load_directory()` to filter files.
- `read_rows()` -- skips malformed rows (logs + continues), warns on negative values.
- `parse_timestamp_to_utc()` -- `ZoneInfo`-based timezone conversion.

### `schema_non_crypto.py`

- Same structure as other schema files. Creates 7-column OHLCV table with volume.

### How to Run

```bash
cd non-crypto
uv run python schema_non_crypto.py    # Create table
uv run python cli.py                   # Load data
uv run python check_data.py           # Validate loaded data
uv run python drop_table.py           # Drop table
```
