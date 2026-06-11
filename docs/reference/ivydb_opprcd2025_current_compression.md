# IvyDB `opprcd2025` Current ClickHouse Compression

This note records the current live ClickHouse storage layout for
`ivydb.opprcd2025` after the 2025 OptionMetrics IvyDB US option-price table was
re-downloaded with the current compression settings.

Measurement date: 2026-06-11

Source table: `optionm_all.opprcd2025`

Target table: `ivydb.opprcd2025`

## Table Summary

Compression ratio means:

```text
compression ratio = uncompressed bytes / compressed bytes
```

Higher is better for storage.

| Metric | Value |
|---|---:|
| Rows | 264,945,680 |
| Minimum `date` | 2025-01-02 |
| Maximum `date` | 2025-08-29 |
| `system.tables.total_bytes` | 5,217,560,811 bytes |
| Table size | 4,975.85 MiB |
| Sum of column compressed bytes | 5,127,109,737 bytes |
| Sum of column compressed size | 4,889.59 MiB |
| Sum of column uncompressed size | 31,253.03 MiB |
| Sum of marks bytes | 6.55 MiB |
| Overall column compression ratio | 6.39x |

`system.tables.total_bytes` is larger than the sum of column compressed bytes
because it includes table storage overhead beyond the raw compressed column
streams.

The future loader DDL now uses `T64, ZSTD(12)` for `last_date`, `volume`,
`open_interest`, `impl_volatility`, `delta`, `gamma`, `vega`, and `theta`.
For `vega` and `theta`, the future DDL also changes the type from `Float32` to
`Decimal64(6)`. This live table was left on its previously loaded codecs and
types so it can be replaced by an explicit rerun. The byte counts below
describe the existing loaded table at the time of measurement.

## Current Column Compression

| # | Column | Type | Codec | Compressed MiB | Uncompressed MiB | Ratio | B/row | Share |
|---:|---|---|---|---:|---:|---:|---:|---:|
| 1 | `secid` | `Nullable(UInt32)` | `CODEC(ZSTD(12))` | 0.98 | 1261.51 | 1281.40x | 0.0039 | 0.02% |
| 2 | `date` | `Nullable(Date32)` | `CODEC(DoubleDelta, ZSTD(12))` | 3.14 | 1261.51 | 401.64x | 0.0124 | 0.06% |
| 3 | `symbol` | `Nullable(String)` | `CODEC(ZSTD(12))` | 84.83 | 6526.71 | 76.94x | 0.3357 | 1.73% |
| 4 | `symbol_flag` | `Nullable(Enum8('0' = 1, '1' = 2))` | `CODEC(ZSTD(12))` | 0.34 | 504.60 | 1479.10x | 0.0014 | 0.01% |
| 5 | `exdate` | `Nullable(Date32)` | `CODEC(DoubleDelta, ZSTD(12))` | 21.09 | 1261.51 | 59.81x | 0.0835 | 0.43% |
| 6 | `last_date` | `Nullable(Date32)` | `CODEC(DoubleDelta, ZSTD(12))` | 220.78 | 1261.51 | 5.71x | 0.8738 | 4.52% |
| 7 | `cp_flag` | `Nullable(Enum8('C' = 1, 'P' = 2))` | `CODEC(ZSTD(12))` | 3.28 | 504.60 | 153.97x | 0.0130 | 0.07% |
| 8 | `strike_price` | `Nullable(Float32)` | `CODEC(ZSTD(12))` | 16.72 | 1261.51 | 75.43x | 0.0662 | 0.34% |
| 9 | `best_bid` | `Nullable(Float32)` | `CODEC(ZSTD(12))` | 366.10 | 1261.51 | 3.45x | 1.4489 | 7.49% |
| 10 | `best_offer` | `Nullable(Float32)` | `CODEC(ZSTD(12))` | 399.47 | 1261.51 | 3.16x | 1.5810 | 8.17% |
| 11 | `volume` | `Nullable(UInt32)` | `CODEC(ZSTD(12))` | 75.97 | 1261.51 | 16.61x | 0.3007 | 1.55% |
| 12 | `open_interest` | `Nullable(UInt32)` | `CODEC(ZSTD(12))` | 101.13 | 1261.51 | 12.47x | 0.4003 | 2.07% |
| 13 | `impl_volatility` | `Nullable(Decimal(9, 6))` | `CODEC(ZSTD(12))` | 695.23 | 1261.51 | 1.81x | 2.7515 | 14.22% |
| 14 | `delta` | `Nullable(Decimal(9, 6))` | `CODEC(ZSTD(12))` | 723.63 | 1261.51 | 1.74x | 2.8639 | 14.80% |
| 15 | `gamma` | `Nullable(Decimal(9, 6))` | `CODEC(ZSTD(12))` | 555.10 | 1261.51 | 2.27x | 2.1969 | 11.35% |
| 16 | `vega` | `Nullable(Float32)` | `CODEC(ZSTD(12))` | 803.32 | 1261.51 | 1.57x | 3.1793 | 16.43% |
| 17 | `theta` | `Nullable(Float32)` | `CODEC(ZSTD(12))` | 801.43 | 1261.51 | 1.57x | 3.1718 | 16.39% |
| 18 | `optionid` | `Nullable(UInt64)` | `CODEC(Delta(8), ZSTD(12))` | 12.68 | 2270.72 | 179.10x | 0.0502 | 0.26% |
| 19 | `cfadj` | `Nullable(Float32)` | `CODEC(ZSTD(12))` | 0.83 | 1261.51 | 1520.72x | 0.0033 | 0.02% |
| 20 | `am_settlement` | `Nullable(UInt8)` | `CODEC(ZSTD(12))` | 0.38 | 504.60 | 1310.88x | 0.0015 | 0.01% |
| 21 | `contract_size` | `Nullable(Int32)` | `CODEC(ZSTD(12))` | 0.87 | 1261.51 | 1456.91x | 0.0034 | 0.02% |
| 22 | `ss_flag` | `Nullable(Enum8('0' = 1, '1' = 2, 'E' = 3))` | `CODEC(ZSTD(12))` | 0.40 | 504.60 | 1249.79x | 0.0016 | 0.01% |
| 23 | `expiry_indicator` | `LowCardinality(Nullable(String))` | `CODEC(ZSTD(12))` | 1.88 | 253.04 | 134.64x | 0.0074 | 0.04% |

## Storage Drivers

The largest compressed columns are the implied-volatility and Greek model
outputs.

| Column group | Compressed MiB | Share of compressed column bytes |
|---|---:|---:|
| `impl_volatility`, `delta`, `gamma`, `vega`, `theta` | 3,578.71 | 73.19% |
| `best_bid`, `best_offer` | 765.57 | 15.66% |
| `last_date`, `volume`, `open_interest` | 397.88 | 8.14% |
| All other columns | 147.43 | 3.02% |

This concentration means most future storage improvements must target the
model-output columns. Optimizing tiny flag columns cannot materially change the
table size.

## Current Lossless Codec Benchmark Notes

The following notes came from temporary shadow-table tests on the January 2025
slice:

```text
date >= 2025-01-01 and date < 2025-02-01
rows = 31,062,326
```

Temporary benchmark tables were dropped after measurement.

Useful lossless changes found and applied to future DDL:

| Column | Previous Codec | Applied Codec | January Change |
|---|---|---|---:|
| `impl_volatility` | `ZSTD(12)` | `T64, ZSTD(12)` | -14.60% |
| `delta` | `ZSTD(12)` | `T64, ZSTD(12)` | -17.62% |
| `gamma` | `ZSTD(12)` | `T64, ZSTD(12)` | -18.51% |
| `last_date` | `DoubleDelta, ZSTD(12)` | `T64, ZSTD(12)` | -50.12% |
| `volume` | `ZSTD(12)` | `T64, ZSTD(12)` | -21.27% |
| `vega + theta` | `Float32, ZSTD(12)` | `Decimal64(6), T64, ZSTD(12)` | -140.40 MiB full-year |

Changes tested but not recommended:

| Column | Tested Codec | January Change | Reason |
|---|---|---:|---|
| `secid` | `Delta, ZSTD(12)` | +34.64% | Worse than plain `ZSTD(12)` |
| `open_interest` | `T64, ZSTD(12)` | -1.06% | Too small to matter |
| `optionid` | `T64, ZSTD(12)` | +353.14% | Much worse than `Delta(8), ZSTD(12)` |
| `symbol_flag` | `T64, ZSTD(12)` | +32.43% | Worse than plain `ZSTD(12)` |
| `cp_flag` | `T64, ZSTD(12)` | +424.22% | Worse than plain `ZSTD(12)` |
| `ss_flag` | `T64, ZSTD(12)` | +63.66% | Worse than plain `ZSTD(12)` |
| `strike_price` | `Gorilla, ZSTD(12)` | +434.27% | Worse than plain `ZSTD(12)` |
| `best_bid` | `Gorilla, ZSTD(12)` | +60.27% | Worse than plain `ZSTD(12)` |
| `best_offer` | `Gorilla, ZSTD(12)` | +57.17% | Worse than plain `ZSTD(12)` |
| `cfadj` | `Gorilla, ZSTD(12)` | +45.51% | Worse than plain `ZSTD(12)` |

`T64` is lossless. It changes how integer-like values are encoded on disk; it
does not round or alter values. `Decimal` columns are integer-like because
ClickHouse stores them as scaled integers. For example, `0.123456` in
`Decimal32(6)` is stored internally as `123456`.

`Delta` is also lossless. It is better than `T64` for `optionid` because
nearby sorted `optionid` values often differ by small amounts, and storing
differences compresses much better than storing the original identifiers.
