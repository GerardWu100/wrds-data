# BoardEx NA Sample Reference

This folder contains **small CSV samples for every live table** in the
`boardex_na` WRDS library. It is a schema-inspection aid, not the source of
truth for the current Parquet ingestion defaults.

## What This Folder Is For

Use these CSVs to answer questions such as:

- does a table exist right now?
- what are its columns?
- what do a few real rows look like?

Do **not** use this file to infer the current default BoardEx download set.
That source of truth now lives in:

- [`docs/boardex_osint_data_plan.md`](/Users/gwh/projects/one-time-projects/wrds-data/docs/boardex_osint_data_plan.md)
- [`boardex_parquet/config.toml`](/Users/gwh/projects/one-time-projects/wrds-data/boardex_parquet/config.toml)

## Current Default Ingestion Stance

The current default text-first Parquet workflow keeps a compact subset of
BoardEx tables:

- `na_dir_profile_details`
- `na_dir_profile_emp`
- `na_dir_profile_education`
- `na_dir_profile_achievements`
- `na_dir_profile_other_activ`
- `na_company_profile_details`
- `na_company_profile_advisors`
- `na_wrds_org_composition`
- `na_wrds_company_names`
- `na_board_dir_announcements`

Optional but currently commented out in `boardex_parquet/config.toml`:

- `na_board_dir_committees`
- `na_company_profile_sr_mgrs`
- `na_board_characteristics`
- `na_wrds_company_region`

Not in the default set:

- compensation tables
- the large `na_dir_*_assoc` panels
- the full `na_wrds_individual_networks` table
- the full `na_wrds_company_networks` table
- convenience joins such as `na_wrds_dir_profile_all`

## Why This Matters

This sample folder still includes CSVs for the whole library, including tables
that are no longer in the default download plan. That is intentional. The
samples are for exploration. The Parquet config is for disciplined storage use.

## Useful Table Families In This Folder

### Person and career source tables

- `na_dir_profile_details.csv`
- `na_dir_profile_emp.csv`
- `na_dir_profile_education.csv`
- `na_dir_profile_achievements.csv`
- `na_dir_profile_other_activ.csv`

### Organization and board source tables

- `na_company_profile_details.csv`
- `na_company_profile_advisors.csv`
- `na_wrds_org_composition.csv`
- `na_wrds_company_names.csv`
- `na_board_dir_announcements.csv`

### Optional governance detail

- `na_board_dir_committees.csv`
- `na_company_profile_sr_mgrs.csv`
- `na_board_characteristics.csv`

### Large derived families to inspect before opting in

- `na_board_*_assoc.csv`
- `na_dir_*_assoc.csv`
- `na_wrds_individual_networks.csv`
- `na_wrds_company_networks.csv`
- `na_wrds_dir_profile_all.csv`
- `na_wrds_dir_profile_emp.csv`
- `na_wrds_company_profile.csv`
