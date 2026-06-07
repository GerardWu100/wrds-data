# BoardEx Parquet Table Selection Reference

This note explains what the `boardex_parquet/` subfolder is currently set up to
do *without running any downloads yet*.

As of **April 18, 2026**, the direct sources of truth for this note are:

- [`boardex_parquet/config.toml`](/Users/gwh/projects/one-time-projects/wrds-data/boardex_parquet/config.toml)
- [`outputs/postgres_tables.csv`](/Users/gwh/projects/one-time-projects/wrds-data/outputs/postgres_tables.csv)
- [`outputs/postgres_columns.csv`](/Users/gwh/projects/one-time-projects/wrds-data/outputs/postgres_columns.csv)
- the local sample folders under `library_samples/`

Definitions used below:

- **Library**: a WRDS PostgreSQL schema such as `boardex_na` or `ciq_pplintel`
- **Table**: one concrete dataset inside a library
- **Current config**: the settings in `boardex_parquet/config.toml` today
- **Would download**: included by the current config if you run the downloader
- **Would not download**: available in the local WRDS catalog snapshot, but
  excluded by the current config

## Current default behavior

The shipped default is a **selected 35-table BoardEx/CapIQ bundle**, not a
full-library export.

That means:

- enabled libraries: `boardex_na`, `ciq_pplintel`,
  `wrdsapps_plink_boardex_ciq`
- selection rule: use the explicit `enabled_tables` allowlist in
  `config.toml`
- side artifacts by default: Parquet only, with sample CSV previews disabled
- disabled optional libraries: `wrdsapps_link_crsp_comp_bdx`,
  `wrdsapps_plink_exec_boardex`, `wrdsapps_plink_exec_ciq`

Operationally, the bundle is trying to keep:

- core person identity
- role and employment history
- education and achievements
- outside activities
- board announcement and committee text
- BoardEx to Capital IQ linking
- Capital IQ biographies, role records, and the wide `wrds_professional` panel

and to avoid:

- compensation tables
- the largest BoardEx person-association panels
- the giant pairwise person-network table
- two BoardEx convenience joins that overlap more normalized source tables

## Current coverage in the local catalog snapshot

The counts below come from
[`outputs/postgres_tables.csv`](/Users/gwh/projects/one-time-projects/wrds-data/outputs/postgres_tables.csv).

| Library | Meaning | Live tables in local catalog | Current config behavior | Tables that would download | Tables that would not download |
|---|---|---:|---|---:|---:|
| `boardex_na` | BoardEx North America | 39 | Enabled, `download_all_tables = false`, explicit 26-table allowlist | 26 | 13 |
| `ciq_pplintel` | Capital IQ People Intelligence | 16 | Enabled, `download_all_tables = false`, explicit 7-table allowlist | 7 | 9 |
| `wrdsapps_plink_boardex_ciq` | BoardEx to Capital IQ links | 2 | Enabled, `download_all_tables = false`, explicit 2-table allowlist | 2 | 0 |
| `wrdsapps_link_crsp_comp_bdx` | BoardEx to CRSP/Compustat link | 1 | Disabled | 0 | 1 |
| `wrdsapps_plink_exec_boardex` | ExecuComp to BoardEx links | 2 | Disabled | 0 | 2 |
| `wrdsapps_plink_exec_ciq` | ExecuComp to Capital IQ links | 2 | Disabled | 0 | 2 |

So, based on the current config and the local metadata export, the default run
would select **35 tables** and skip **27 tables** across these six libraries.

The local catalog snapshot sums the selected tables to about **27.81 GiB** of
WRDS PostgreSQL relation size before Parquet compression. A live WRDS check run
from this workspace on **April 18, 2026** put the same explicit 35-table
selection at about **28.09 GiB**. The exact live size drifts as WRDS refreshes
data, but the shipped table set no longer grows automatically when WRDS adds
tables.

## Rules used to describe what each table contains

The short descriptions below follow the same interpretation rules throughout:

| Rule | How to read it |
|---|---|
| **Grain-first rule** | Start by asking what one row represents: one person, one role spell, one board event, one association edge, or one convenience-join record. |
| **Key-ID rule** | The most important join fields are usually `directorid`, `boardid`, `companyid`, `personid`, `proid`, or `profunctionid`. |
| **Time rule** | Date and year columns such as `datestartrole`, `dateendrole`, `annualreportdate`, `startyear`, and `endyear` mean the table is historical, not one timeless master record. |
| **Convenience-join rule** | Names beginning with `na_wrds_` or `wrds_` are usually wider helper tables that flatten smaller source tables into one row shape. |
| **Association/network rule** | Names ending in `*_assoc` or `*_networks` are relationship tables. Each row describes a link, not a standalone entity. |

## Tables the current config would download

These are the tables the current config would select if you later run
`uv run python -m boardex_parquet`.

The descriptions below tell you both **what you do get** and **why it is kept**.

| Library | Table | Local catalog size | What you get if you download it | Why it stays in the bundle |
|---|---|---:|---|---|
| `boardex_na` | `na_board_characteristics` | 151.98 MiB | One row per board-level governance snapshot with metrics such as attrition, gender ratio, time-to-retirement, qualification counts, and nationality mix. | Compact pre-computed governance summary that is useful enough to keep. |
| `boardex_na` | `na_board_dir_announcements` | 75.65 MiB | One row per director announcement event with company, director, committee, role, announcement date, effective date, and short description text. | This is one of the clearest unique governance-text tables in BoardEx. |
| `boardex_na` | `na_board_dir_committees` | 634.66 MiB | One row per board-committee assignment spell with committee name, committee role, board role, functional experience, dates, and annual report date. | Keeps committee history and role text without forcing you to derive it later. |
| `boardex_na` | `na_board_education_assoc` | 19.56 MiB | One row per board-to-education-organization association edge with overlap years and shared director context. | Small enough to keep and adds education-network context. |
| `boardex_na` | `na_board_listed_assoc` | 234.82 MiB | One row per board-to-listed-company association with overlap years plus role and associated-role labels. | Board-level association tables are moderate in size and still useful. |
| `boardex_na` | `na_board_nfp_assoc` | 73.59 MiB | One row per board-to-nonprofit association with overlap timing and role labels. | Keeps non-profit network context at the board level. |
| `boardex_na` | `na_board_other_assoc` | 291.44 MiB | One row per board-to-other-organization association with overlap timing and role labels. | Adds broader organization linkage without the giant person-level panels. |
| `boardex_na` | `na_board_unlisted_assoc` | 431.71 MiB | One row per board-to-unlisted-company association with overlap timing and role labels. | Keeps board-level association coverage across private companies. |
| `boardex_na` | `na_company_profile_advisors` | 5.88 MiB | One row per advisor relationship, such as registrar, auditor, law firm, or similar external-advisor category. | Small relationship table with obvious organizational context. |
| `boardex_na` | `na_company_profile_details` | 199.52 MiB | One row per company profile with names, addresses, country fields, and other organization identity fields. | Core company master table. |
| `boardex_na` | `na_company_profile_market_cap` | 1.36 MiB | One row per company market-cap snapshot with currency, market capitalization, employee count, and revenue. | Tiny enrichment table worth keeping. |
| `boardex_na` | `na_company_profile_sr_mgrs` | 198.95 MiB | One row per senior-manager role spell with board, director, role name, role description, and dates. | Gives curated below-board manager coverage that is still smaller than many alternatives. |
| `boardex_na` | `na_company_profile_stocks` | 2.09 MiB | One row per stock identifier record with ticker, ISIN, quote country, primary-stock flag, and board identifier. | Tiny identifier bridge. |
| `boardex_na` | `na_dir_characteristics` | 418.99 MiB | One row per director-board characteristic snapshot with NED flag, role status, gender, nationality, and tenure-like metrics. | Keeps compact director-level governance descriptors. |
| `boardex_na` | `na_dir_profile_achievements` | 207.34 MiB | One row per achievement or honors record with date, achievement text, and linked organization. | Core person-text enrichment. |
| `boardex_na` | `na_dir_profile_details` | 229.71 MiB | One row per person identity profile with name components, titles, and other core identity fields. | Core BoardEx person master. |
| `boardex_na` | `na_dir_profile_education` | 341.48 MiB | One row per education record with institution, qualification, award date, and education description. | Core education-history table. |
| `boardex_na` | `na_dir_profile_emp` | 1.76 GiB | One row per employment or board-role spell with company, role name, board position, dates, and full-text description. | Core historical role table for BoardEx. |
| `boardex_na` | `na_dir_profile_other_activ` | 434.42 MiB | One row per outside activity spell with organization, role, and dates. | Captures affiliations beyond direct employment and board seats. |
| `boardex_na` | `na_wrds_company_dir_names` | 397.19 MiB | Wide helper table combining director IDs, company IDs, company names, ticker, quote country, ISIN, CIK, and annual report date. | Convenience bridge that is still useful for quick joins and screening. |
| `boardex_na` | `na_wrds_company_names` | 132.44 MiB | Company crosswalk with `boardid`, `companyid`, ticker, ISIN, CIK, and quote-country fields. | Core identifier bridge for companies. |
| `boardex_na` | `na_wrds_company_networks` | 1.65 GiB | One row per firm-to-firm network edge with association type, overlap years, shared director, and paired role labels. | Retained because you explicitly liked the broader selected bundle, and this table is hard to describe as trivially derivable. |
| `boardex_na` | `na_wrds_company_profile` | 200.91 MiB | Wide WRDS company helper table that combines company profile and address fields in one row shape. | Convenience company profile join kept in the broader bundle. |
| `boardex_na` | `na_wrds_company_region` | 124.72 MiB | One row per company-region mapping with country and region labels. | Compact regional helper table. |
| `boardex_na` | `na_wrds_org_composition` | 407.81 MiB | One row per organization roster spell linking company and director IDs to role names, dates, and seniority. | Useful normalized roster table with direct organization composition history. |
| `boardex_na` | `na_wrds_org_summary` | 672.90 MiB | Wide summary table with row type, NED flag, role, gender, nationality, and many tenure/composition fields. | Broad convenience summary retained in the selected bundle. |
| `wrdsapps_plink_boardex_ciq` | `boardex_ciq` | 410.74 MiB | Rich BoardEx-CIQ bridge with BoardEx person and company fields, CIQ person and company fields, plus score and match style. | Main cross-vendor person/company link table. |
| `wrdsapps_plink_boardex_ciq` | `boardex_ciq_link` | 89.37 MiB | Leaner person-match table with BoardEx and CIQ name fields plus score and match style. | Smaller, simpler BoardEx-to-CIQ link table worth keeping beside the richer one. |
| `ciq_pplintel` | `ciqperson` | 695.80 MiB | One row per Capital IQ person with names, email, phone, prefix, suffix, salutation, and year of birth. | Core Capital IQ person master. |
| `ciq_pplintel` | `ciqpersonbiography` | 3.26 GiB | One row per `personid` with the long free-text biography field. | Main free-text biography table. |
| `ciq_pplintel` | `ciqprofessional` | 3.33 GiB | One row per professional role with `proid`, `personid`, `companyid`, title, address context, and board/current/education flags. | Core Capital IQ role-history table. |
| `ciq_pplintel` | `ciqprofessionalcoverage` | 17.58 MiB | One row per extra company-coverage link for a professional record. | Small relationship table that adds cross-company coverage context. |
| `ciq_pplintel` | `ciqprofunction` | 96.00 KiB | Function dictionary that decodes `profunctionid` into role-function labels and flags such as key-exec or board role. | Tiny lookup table needed to interpret role-function assignments. |
| `ciq_pplintel` | `ciqprotoprofunction` | 2.41 GiB | One row per professional-to-function assignment with start and end components, current flag, and specialty field. | Core role-function assignment history. |
| `ciq_pplintel` | `wrds_professional` | 8.46 GiB | Wide convenience panel joining company, person, function, title, country/state, dates, and role flags in one row shape. | You kept the broader selected bundle, and this table gives a single wide panel for downstream work. |

## Tables the current config would not download

These are the tables you **do not get** with the current default. The reasons
below explain what you are intentionally avoiding.

### Not downloaded from enabled libraries

| Library | Table | Local catalog size | What you would be skipping | Why it is excluded today |
|---|---|---:|---|---|
| `boardex_na` | `na_dir_education_assoc` | 53.69 GiB | Massive person-to-education-organization association edge table with overlap years and shared-director context. | Excluded because the person-level association panel is extremely large. |
| `boardex_na` | `na_dir_listed_assoc` | 67.05 GiB | Massive person-to-listed-company association edge table with overlap years and paired role labels. | Excluded because it is one of the largest relationship panels in the library. |
| `boardex_na` | `na_dir_nfp_assoc` | 9.42 GiB | Person-to-nonprofit association edge table with overlap timing and role labels. | Excluded as part of the giant person-level association family. |
| `boardex_na` | `na_dir_other_assoc` | 53.32 GiB | Person-to-other-organization association edge table with overlap timing and role labels. | Excluded for the same size-and-redundancy reason as the other person panels. |
| `boardex_na` | `na_dir_standard_remun` | 584.24 MiB | Director remuneration summary with compensation-related fields. | Excluded because the bundle intentionally avoids salary and compensation data. |
| `boardex_na` | `na_dir_unlisted_assoc` | 58.49 GiB | Person-to-unlisted-company association edge table with overlap timing and role labels. | Excluded because it is another huge person-level association panel. |
| `boardex_na` | `na_ltip_compensation` | 95.55 MiB | Long-term incentive compensation records. | Compensation family excluded. |
| `boardex_na` | `na_ltip_wealth` | 96.27 MiB | Long-term incentive wealth/holdings records. | Compensation family excluded. |
| `boardex_na` | `na_options_compensation` | 97.66 MiB | Option compensation records. | Compensation family excluded. |
| `boardex_na` | `na_options_wealth` | 125.14 MiB | Option holdings and wealth records. | Compensation family excluded. |
| `boardex_na` | `na_wrds_dir_profile_all` | 4.40 GiB | Very wide BoardEx person convenience table that starts from person identity and expands across multiple domains. | Excluded because it overlaps more normalized source tables and is large. |
| `boardex_na` | `na_wrds_dir_profile_emp` | 2.14 GiB | Wide employment convenience table similar to `na_dir_profile_emp`, but with extra joined identifiers. | Excluded because the narrower source table already covers the core role history. |
| `boardex_na` | `na_wrds_individual_networks` | 370.92 GiB | Giant person-to-person network table with association type, overlap years, shared organization, and paired role labels. | Excluded because it is the single biggest pairwise network table by far. |
| `ciq_pplintel` | `ciqcompensation` | 9.95 GiB | Executive compensation facts by year and type. | Compensation family excluded. |
| `ciq_pplintel` | `ciqcompensationadjustment` | 120.00 KiB | Compensation adjustment records with comments and filing references. | Compensation family excluded. |
| `ciq_pplintel` | `ciqcompensationadjustmenttype` | 32.00 KiB | Lookup table for compensation adjustment types. | Compensation family excluded. |
| `ciq_pplintel` | `ciqcompensationdetail` | 2.60 GiB | Detailed compensation line items keyed by subtype sequence and filing context. | Compensation family excluded. |
| `ciq_pplintel` | `ciqcompensationsubtype` | 24.00 KiB | Lookup table for compensation subtypes. | Compensation family excluded. |
| `ciq_pplintel` | `ciqcompensationtype` | 32.00 KiB | Lookup table for high-level compensation types. | Compensation family excluded. |
| `ciq_pplintel` | `compensation_length` | 1.19 GiB | Compensation metadata table tied to subtype and reporting length. | Compensation family excluded. |
| `ciq_pplintel` | `wrds_compensation` | 3.09 GiB | Wide WRDS compensation join with person, company, function, and totals. | Compensation family excluded. |
| `ciq_pplintel` | `wrds_compensationdetails` | 1.59 GiB | Wide WRDS detailed-compensation join with company, person, year, and subtype sequence fields. | Compensation family excluded. |

### Not downloaded because the whole library is disabled

| Library | Table | Local catalog size | What you would be skipping | Why it is not downloaded today |
|---|---|---:|---|---|
| `wrdsapps_link_crsp_comp_bdx` | `bdxcrspcomplink` | 1.80 MiB | Bridge from BoardEx to CRSP/Compustat identifiers such as `permno` or `gvkey`. | The whole CRSP/Compustat bridge library is disabled by default. |
| `wrdsapps_plink_exec_boardex` | `exec_boardex` | 19.85 MiB | ExecuComp-to-BoardEx bridge with richer context. | ExecuComp link libraries stay disabled in the current default. |
| `wrdsapps_plink_exec_boardex` | `exec_boardex_link` | 8.54 MiB | Lean ExecuComp-to-BoardEx link table. | ExecuComp link libraries stay disabled in the current default. |
| `wrdsapps_plink_exec_ciq` | `exec_ciq` | 17.03 MiB | ExecuComp-to-CIQ bridge with richer context. | ExecuComp link libraries stay disabled in the current default. |
| `wrdsapps_plink_exec_ciq` | `exec_ciq_link` | 9.87 MiB | Lean ExecuComp-to-CIQ link table. | ExecuComp link libraries stay disabled in the current default. |

## Operational meaning

If you run the subfolder later with the current config:

- it will target **three enabled libraries**
- it will attempt to download **35 concrete tables**
- it will write one Zstandard-compressed Parquet file per table to
  `boardex_parquet/outputs/`
- it will not create sidecar sample CSVs unless you turn them back on

The file naming rule remains:

- `<library>__<table>.parquet`

## How to make the bundle larger or smaller later

The Python downloader still follows `config.toml`, so all scope changes remain
config-driven.

To make the bundle smaller:

1. remove some names from `enabled_tables`, or
2. disable one of the currently enabled libraries

To make the bundle larger:

1. add more names to `enabled_tables`, or
2. enable one of the optional link libraries

The downloader logic does not need to change for any of those scope changes.
