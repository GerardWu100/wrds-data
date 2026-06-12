# IvyDB `opprcd2025` ClickHouse Compression Snapshot: 2026-06-12

This note records the live ClickHouse storage layout for `ivydb.opprcd2025` on
June 12, 2026 after the 2025 OptionMetrics IvyDB US option-price table was
reloaded with the newer fixed-point and `T64, ZSTD(12)` settings.

Measurement date: 2026-06-12

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
| Trading dates | 165 |
| Active parts | 65 |
| `system.tables.total_bytes` | 4,597,377,161 bytes |
| Table size | 4,384.40 MiB |
| Sum of column compressed bytes | 4,498,860,138 bytes |
| Sum of column compressed size | 4,290.45 MiB |
| Sum of column uncompressed size | 33,297.19 MiB |
| Sum of marks bytes | 6.51 MiB |
| Overall column compression ratio | 7.76x |

`system.tables.total_bytes` is larger than the sum of column compressed bytes
because it includes table storage overhead beyond the raw compressed column
streams.

The live table definition has `open_interest` on plain `ZSTD(12)` again after
the full 2025 reload showed `T64, ZSTD(12)` was slightly larger. The displayed
column bytes can still reflect existing physical parts until ClickHouse merges
or rewrites those parts.

## Ranking / Sorting Key

In ClickHouse, the table ranking is the `ORDER BY` sorting key. This controls
the physical row order inside each monthly `date` partition and therefore can
affect compression.

Current live `ivydb.opprcd2025` ranking:

| Rank | Column or expression | Meaning |
|---:|---|---|
| 1 | `secid` | OptionMetrics security identifier |
| 2 | `date` | Quote or observation date |
| 3 | `optionid` | Option contract identifier |
| 4 | `exdate` | Option expiration date |
| 5 | `cp_flag` | Call or put flag |
| 6 | `strike_price` | Strike price multiplied by 1,000 in the WRDS source |

Current live sorting key:

```text
secid, date, optionid, exdate, cp_flag, strike_price
```

Future recreated `opprcdYYYY` tables use the compression-oriented sort key:

```text
secid, date, exdate, cp_flag, strike_price, optionid
```

That future order keeps one security's daily option surface together by
expiration, call/put side, and strike before the high-cardinality option
identifier. It is the strongest current candidate for compression, but it still
needs a shadow-table benchmark before treating it as proven best.

### January 2025 Sort-Key Benchmark

After this snapshot was written, four temporary January 2025 shadow tables were
created from the same `ivydb.opprcd2025` rows to test sort-key compression. Each
table used the same columns, codecs, and 31,062,326 January rows. The temporary
tables were dropped after measurement.

| Rank | Tested sort key | Column compressed size | B/row | Ratio | Change vs current |
|---:|---|---:|---:|---:|---:|
| 1 | `secid, date, exdate, cp_flag, strike_price, optionid` | 489.12 MiB | 16.5114 | 7.9874x | -2.65% |
| 2 | `secid, date, cp_flag, exdate, strike_price, optionid` | 491.77 MiB | 16.6009 | 7.9443x | -2.12% |
| 3 | `secid, date, optionid, exdate, cp_flag, strike_price` | 502.44 MiB | 16.9608 | 7.7757x | baseline |
| 4 | `secid, date, strike_price, exdate, cp_flag, optionid` | 525.33 MiB | 17.7336 | 7.4369x | +4.56% |

The result supports the future sort-key change: putting `exdate`, `cp_flag`,
and `strike_price` before `optionid` improved January compressed column storage
by 13.32 MiB versus the current live order. This is a slice-level benchmark,
not a full-year proof, but it directly tests the table's real data.

## Column Compression

| # | Column | Type | Codec | Compressed MiB | Uncompressed MiB | Ratio | B/row | Share |
|---:|---|---|---|---:|---:|---:|---:|---:|
| 1 | `theta` | `Nullable(Decimal(18, 6))` | `CODEC(T64, ZSTD(12))` | 754.61 | 2,272.47 | 3.01x | 2.9865 | 17.59% |
| 2 | `vega` | `Nullable(Decimal(18, 6))` | `CODEC(T64, ZSTD(12))` | 715.62 | 2,272.47 | 3.18x | 2.8322 | 16.68% |
| 3 | `delta` | `Nullable(Decimal(9, 6))` | `CODEC(T64, ZSTD(12))` | 592.66 | 1,262.48 | 2.13x | 2.3456 | 13.81% |
| 4 | `impl_volatility` | `Nullable(Decimal(9, 6))` | `CODEC(T64, ZSTD(12))` | 591.54 | 1,262.48 | 2.13x | 2.3412 | 13.79% |
| 5 | `gamma` | `Nullable(Decimal(9, 6))` | `CODEC(T64, ZSTD(12))` | 450.15 | 1,262.48 | 2.80x | 1.7816 | 10.49% |
| 6 | `best_offer` | `Nullable(Float32)` | `CODEC(ZSTD(12))` | 399.92 | 1,262.48 | 3.16x | 1.5828 | 9.32% |
| 7 | `best_bid` | `Nullable(Float32)` | `CODEC(ZSTD(12))` | 366.52 | 1,262.48 | 3.44x | 1.4506 | 8.54% |
| 8 | `last_date` | `Nullable(Date32)` | `CODEC(T64, ZSTD(12))` | 110.26 | 1,262.48 | 11.45x | 0.4364 | 2.57% |
| 9 | `open_interest` | `Nullable(UInt32)` | `CODEC(ZSTD(12))` | 101.56 | 1,262.48 | 12.43x | 0.4020 | 2.37% |
| 10 | `symbol` | `Nullable(String)` | `CODEC(ZSTD(12))` | 84.86 | 6,531.82 | 76.97x | 0.3359 | 1.98% |
| 11 | `volume` | `Nullable(UInt32)` | `CODEC(T64, ZSTD(12))` | 59.90 | 1,262.48 | 21.08x | 0.2371 | 1.40% |
| 12 | `exdate` | `Nullable(Date32)` | `CODEC(DoubleDelta, ZSTD(12))` | 21.21 | 1,262.48 | 59.53x | 0.0839 | 0.49% |
| 13 | `strike_price` | `Nullable(Float32)` | `CODEC(ZSTD(12))` | 16.78 | 1,262.48 | 75.24x | 0.0664 | 0.39% |
| 14 | `optionid` | `Nullable(UInt64)` | `CODEC(Delta(8), ZSTD(12))` | 12.72 | 2,272.47 | 178.62x | 0.0504 | 0.30% |
| 15 | `cp_flag` | `Nullable(Enum8('C' = 1, 'P' = 2))` | `CODEC(ZSTD(12))` | 3.28 | 504.99 | 153.77x | 0.0130 | 0.08% |
| 16 | `date` | `Nullable(Date32)` | `CODEC(DoubleDelta, ZSTD(12))` | 3.15 | 1,262.48 | 400.74x | 0.0125 | 0.07% |
| 17 | `expiry_indicator` | `LowCardinality(Nullable(String))` | `CODEC(ZSTD(12))` | 1.88 | 253.22 | 134.95x | 0.0074 | 0.04% |
| 18 | `secid` | `Nullable(UInt32)` | `CODEC(ZSTD(12))` | 0.99 | 1,262.48 | 1,277.38x | 0.0039 | 0.02% |
| 19 | `contract_size` | `Nullable(Int32)` | `CODEC(ZSTD(12))` | 0.87 | 1,262.48 | 1,451.63x | 0.0034 | 0.02% |
| 20 | `cfadj` | `Nullable(Float32)` | `CODEC(ZSTD(12))` | 0.83 | 1,262.48 | 1,515.45x | 0.0033 | 0.02% |
| 21 | `ss_flag` | `Nullable(Enum8('0' = 1, '1' = 2, 'E' = 3))` | `CODEC(ZSTD(12))` | 0.40 | 504.99 | 1,248.49x | 0.0016 | 0.01% |
| 22 | `am_settlement` | `Nullable(UInt8)` | `CODEC(ZSTD(12))` | 0.39 | 504.99 | 1,309.73x | 0.0015 | 0.01% |
| 23 | `symbol_flag` | `Nullable(Enum8('0' = 1, '1' = 2))` | `CODEC(ZSTD(12))` | 0.34 | 504.99 | 1,477.95x | 0.0014 | 0.01% |

## Storage Drivers

The largest compressed columns remain the implied-volatility and Greek model
outputs.

| Column group | Compressed MiB | Share of compressed column bytes |
|---|---:|---:|
| `impl_volatility`, `delta`, `gamma`, `vega`, `theta` | 3,104.58 | 72.36% |
| `best_bid`, `best_offer` | 766.44 | 17.86% |
| `last_date`, `volume`, `open_interest` | 271.72 | 6.33% |
| All other columns | 147.70 | 3.44% |

This concentration means most future storage improvements must target the model
output columns or the physical row order that clusters option surfaces.

## Change From June 11 Snapshot

| Metric | June 11 | June 12 | Change |
|---|---:|---:|---:|
| Table size | 4,975.85 MiB | 4,384.40 MiB | -591.45 MiB |
| Column compressed size | 4,889.59 MiB | 4,290.45 MiB | -599.14 MiB |
| Column compression ratio | 6.39x | 7.76x | +1.37x |
| Column compressed bytes per row | 19.35 | 16.98 | -2.37 |

The June 12 snapshot is smaller because the live table was reloaded with
`T64, ZSTD(12)` for `last_date`, `volume`, implied volatility, and Greeks, and
with `Decimal64(6), T64, ZSTD(12)` for `vega` and `theta`.
