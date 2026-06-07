# BoardEx Parquet Pocket-File Audit

Audit date: 2026-05-12.

Local pocket-file snapshot: the Parquet file modification times show the bundle was written on 2026-04-26 between 13:18 and 13:36 local machine time.

## Scope

- Expected bundle from `boardex_parquet/config.toml`: 35 selected tables.
- Actual local Parquet files in `boardex_parquet/outputs/`: 35 files.
- Missing selected files: 0.
- Extra Parquet files: 0.
- Stale `.tmp` files: 0.

## Checks Performed

1. Synced dependencies with `uv sync`.
2. Read every Parquet footer.
3. Scanned every Parquet data page and verified scanned rows equal Parquet metadata rows.
4. Compared every local Parquet schema against the current live WRDS PostgreSQL schema.
5. Ran exact live `COUNT(*)` for each selected WRDS table.
6. Sampled 25 deterministic row positions per file and queried WRDS by table-specific key columns.
7. For sampled rows, compared every column after normalizing WRDS date strings to date objects.
8. Fully compared `ciq_pplintel.ciqprofessionalcoverage`, the only table where current WRDS has fewer rows than the local file.

## Overall Result

- Local total rows: 110,154,028.
- Current live WRDS total rows for the same 35 tables: 110,582,757.
- Live minus local total rows: 428,729.
- Parquet structural corruption found: 0 files.
- Schema mismatches found: 0 files.
- Sampled rows checked: 875.
- Sampled rows matching current WRDS exactly: 845.
- Sampled rows with changed values in current WRDS: 29.
- Sampled rows whose sampled key is absent from current WRDS: 1.

| Status | Count | Meaning |
|---|---:|---|
| `GOOD_MATCH` | 3 | Current WRDS count, schema, and sampled values match local file. |
| `GOOD_OLDER_SNAPSHOT` | 24 | File is structurally sound; current WRDS has more rows, which is consistent with post-download growth. |
| `DRIFT_REVIEW` | 8 | File is structurally sound, but current WRDS differs in sampled values, missing sampled keys, or lower live row count. |

## Per-File Classification

| Table | Status | Local rows | Live rows | Live-local | Sample exact matches | Sample issues | Interpretation |
|---|---|---:|---:|---:|---:|---:|---|
| `boardex_na__na_board_characteristics` | `DRIFT_REVIEW` | 512,077 | 512,943 | 866 | 23/25 | 2 | sampled keys exist but some current WRDS values differ from local snapshot |
| `boardex_na__na_board_dir_announcements` | `GOOD_OLDER_SNAPSHOT` | 315,057 | 315,857 | 800 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_board_dir_committees` | `GOOD_OLDER_SNAPSHOT` | 2,382,957 | 2,383,953 | 996 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_board_education_assoc` | `GOOD_OLDER_SNAPSHOT` | 104,746 | 104,795 | 49 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_board_listed_assoc` | `GOOD_OLDER_SNAPSHOT` | 905,331 | 907,395 | 2,064 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_board_nfp_assoc` | `DRIFT_REVIEW` | 331,372 | 332,108 | 736 | 24/25 | 1 | sampled keys exist but some current WRDS values differ from local snapshot |
| `boardex_na__na_board_other_assoc` | `GOOD_OLDER_SNAPSHOT` | 1,320,717 | 1,322,181 | 1,464 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_board_unlisted_assoc` | `GOOD_OLDER_SNAPSHOT` | 1,868,647 | 1,874,281 | 5,634 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_company_profile_advisors` | `GOOD_OLDER_SNAPSHOT` | 39,041 | 39,433 | 392 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_company_profile_details` | `GOOD_OLDER_SNAPSHOT` | 1,222,609 | 1,225,620 | 3,011 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_company_profile_market_cap` | `DRIFT_REVIEW` | 11,639 | 11,794 | 155 | 16/25 | 9 | sampled keys exist but some current WRDS values differ from local snapshot |
| `boardex_na__na_company_profile_sr_mgrs` | `GOOD_OLDER_SNAPSHOT` | 961,019 | 964,225 | 3,206 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_company_profile_stocks` | `GOOD_OLDER_SNAPSHOT` | 15,128 | 15,170 | 42 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_dir_characteristics` | `DRIFT_REVIEW` | 1,391,680 | 1,392,842 | 1,162 | 23/25 | 2 | sampled keys exist but some current WRDS values differ from local snapshot |
| `boardex_na__na_dir_profile_achievements` | `GOOD_OLDER_SNAPSHOT` | 1,212,011 | 1,213,408 | 1,397 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_dir_profile_details` | `DRIFT_REVIEW` | 1,250,445 | 1,262,008 | 11,563 | 24/25 | 1 | sampled local keys are absent from current WRDS |
| `boardex_na__na_dir_profile_education` | `GOOD_OLDER_SNAPSHOT` | 2,063,316 | 2,070,512 | 7,196 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_dir_profile_emp` | `GOOD_OLDER_SNAPSHOT` | 8,491,547 | 8,527,616 | 36,069 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_dir_profile_other_activ` | `GOOD_OLDER_SNAPSHOT` | 2,451,812 | 2,457,386 | 5,574 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_wrds_company_dir_names` | `GOOD_OLDER_SNAPSHOT` | 2,748,772 | 2,754,708 | 5,936 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_wrds_company_names` | `GOOD_OLDER_SNAPSHOT` | 1,235,257 | 1,238,595 | 3,338 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_wrds_company_networks` | `GOOD_OLDER_SNAPSHOT` | 4,953,766 | 4,965,152 | 11,386 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_wrds_company_profile` | `GOOD_OLDER_SNAPSHOT` | 1,224,606 | 1,227,652 | 3,046 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_wrds_company_region` | `GOOD_OLDER_SNAPSHOT` | 1,222,689 | 1,225,699 | 3,010 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_wrds_org_composition` | `GOOD_OLDER_SNAPSHOT` | 2,308,671 | 2,316,848 | 8,177 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `boardex_na__na_wrds_org_summary` | `DRIFT_REVIEW` | 1,353,508 | 1,354,642 | 1,134 | 11/25 | 14 | sampled keys exist but some current WRDS values differ from local snapshot |
| `ciq_pplintel__ciqperson` | `GOOD_OLDER_SNAPSHOT` | 7,088,542 | 7,126,469 | 37,927 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `ciq_pplintel__ciqpersonbiography` | `GOOD_OLDER_SNAPSHOT` | 6,305,312 | 6,343,352 | 38,040 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `ciq_pplintel__ciqprofessional` | `GOOD_OLDER_SNAPSHOT` | 12,349,049 | 12,411,450 | 62,401 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `ciq_pplintel__ciqprofessionalcoverage` | `DRIFT_REVIEW` | 190,436 | 190,133 | -303 | 25/25 | 0 | local has more rows than current WRDS; vendor appears to have removed/revised rows after download |
| `ciq_pplintel__ciqprofunction` | `GOOD_MATCH` | 306 | 306 | 0 | 25/25 | 0 | current WRDS count, schema, and sampled values match local file |
| `ciq_pplintel__ciqprotoprofunction` | `GOOD_OLDER_SNAPSHOT` | 20,107,856 | 20,193,728 | 85,872 | 25/25 | 0 | current WRDS has additional rows, consistent with post-download growth |
| `ciq_pplintel__wrds_professional` | `DRIFT_REVIEW` | 20,320,982 | 20,407,371 | 86,389 | 24/25 | 1 | sampled keys exist but some current WRDS values differ from local snapshot |
| `wrdsapps_plink_boardex_ciq__boardex_ciq` | `GOOD_MATCH` | 1,382,849 | 1,382,849 | 0 | 25/25 | 0 | current WRDS count, schema, and sampled values match local file |
| `wrdsapps_plink_boardex_ciq__boardex_ciq_link` | `GOOD_MATCH` | 510,276 | 510,276 | 0 | 25/25 | 0 | current WRDS count, schema, and sampled values match local file |

## Drift-Review Notes

- `boardex_na__na_board_characteristics`: Two sampled rows still exist by key but current WRDS has changed calculated board attributes such as gender ratio and tenure/time fields. This looks like vendor recalculation of derived BoardEx metrics, not file corruption.
- `boardex_na__na_board_nfp_assoc`: One sampled row differs only in `boardname`. This looks like a company or board name refresh.
- `boardex_na__na_company_profile_market_cap`: Nine sampled rows differ in `mktcapitalisation`. Market capitalization is naturally time-sensitive, so this is expected live-data drift.
- `boardex_na__na_dir_characteristics`: Two sampled rows differ in tenure/time fields. This is consistent with recalculated director characteristics after the April 26 snapshot.
- `boardex_na__na_dir_profile_details`: One sampled `directorid` from the local file was not present in current WRDS. That suggests a profile deletion, merge, or identifier retirement in the vendor refresh.
- `boardex_na__na_wrds_org_summary`: Fourteen sampled rows differ, mostly `networksize`, with one row also changing `ticker` and `isin`. This is a derived summary table, so network-size recomputation is plausible after source refreshes.
- `ciq_pplintel__ciqprofessionalcoverage`: Current WRDS has 303 fewer rows than local. Full-table comparison found 916 local-only rows and 613 live-only rows, with no duplicate full rows in either side. This is a vendor relationship-table revision, not a Parquet read error.
- `ciq_pplintel__wrds_professional`: One sampled row differs in `prorank`. This is a small rank refresh in a derived/wide professional panel.

## Artifacts

- `outputs/boardex_audit/boardex_parquet_audit_summary_2026-05-12.csv`: one row per pocket file.
- `outputs/boardex_audit/boardex_parquet_audit_samples_2026-05-12.csv`: one row per sampled local row.
- `outputs/boardex_audit/ciqprofessionalcoverage_full_diff_2026-05-12.csv`: full local-only and live-only row diff for the anomalous `ciqprofessionalcoverage` table.

## Conclusion

The local BoardEx/Capital IQ Parquet bundle matches the configured 35-table downloader scope and shows no evidence of Parquet corruption, partial files, schema drift, or downloader schema-writing errors. The differences found against live WRDS on 2026-05-12 are concentrated in eight tables and are best explained as post-download vendor refresh drift from the 2026-04-26 local snapshot. Re-download the eight drift-review files only if the research needs the latest WRDS state rather than the April 26 snapshot.

For the next download, add a manifest at write time containing exact live row count, WRDS query timestamp, schema fingerprint, file hash, and stored sample row hashes. That would let you distinguish “bad download” from “WRDS changed later” without relying on today-versus-snapshot inference.
