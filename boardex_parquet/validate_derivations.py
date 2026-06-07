#!/usr/bin/env python3
"""Run live WRDS spot checks for large BoardEx derived tables.

This script does not try to prove full table equivalence. That would require
re-implementing BoardEx's internal formatting and filtering rules.

Instead, it answers the operational question that matters for this repo:

1. Which large BoardEx tables are recoverable at the relationship level from
   smaller source tables?
2. Which tables are still not safe to call "trivially derivable"?

The checks use the current live WRDS tables, not only local CSV samples.
Each check intentionally uses a very small sample so the script stays fast and
re-runnable.
"""

from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from catalog_exports.wrds_connection import connect_wrds


@dataclass
class ValidationResult:
    """Container for one validation outcome."""

    table_name: str
    matched_rows: int
    checked_rows: int
    interpretation: str


def build_interpretation(
    *,
    matched_rows: int,
    checked_rows: int,
    ordered_sample: bool,
) -> str:
    """Summarize a derivation spot check from the measured match counts.

    Parameters
    ----------
    matched_rows : int
        Number of sampled rows that were recoverable from the proposed source
        tables.
    checked_rows : int
        Number of sampled rows inspected by the spot check.
    ordered_sample : bool
        Whether the sample query uses a deterministic ordering. Unordered LIMIT
        queries can inspect different rows on reruns, so the summary should say
        that explicitly.

    Returns
    -------
    str
        Interpretation text that matches the measured result instead of making
        a hard-coded universal claim.
    """

    if checked_rows <= 0:
        summary = "No rows were checked."
    elif matched_rows == checked_rows:
        summary = (
            f"All {checked_rows} checked rows were recoverable from smaller "
            "source tables."
        )
    elif matched_rows == 0:
        summary = (
            f"None of the {checked_rows} checked rows were recoverable from "
            "smaller source tables."
        )
    else:
        summary = (
            f"Only {matched_rows} of {checked_rows} checked rows were "
            "recoverable from smaller source tables."
        )

    if ordered_sample:
        return summary

    return (
        f"{summary} The sample uses an unordered LIMIT query, so reruns may "
        "inspect different rows."
    )


def _run_exists_query(wrds_db, query: str) -> bool:
    """Return the boolean result of a one-row ``select exists (...)`` query."""

    result = wrds_db.raw_sql(query)
    return bool(result.iloc[0, 0])


def validate_individual_networks(wrds_db) -> ValidationResult:
    """Validate two sampled rows of ``na_wrds_individual_networks``.

    The sample uses an unordered ``LIMIT 2`` query. On the current live WRDS
    data, the sampled rows are employment-based relationships, so this check
    uses ``na_dir_profile_emp`` as the source table.
    """

    sample = wrds_db.raw_sql(
        """
        select dirbrdid, directorid, companyid, overlapyearstart_int, overlapyearend_int
        from boardex_na.na_wrds_individual_networks
        limit 2
        """
    )

    matched_rows = 0

    for row in sample.itertuples(index=False):
        query = f"""
            select exists (
                select 1
                from boardex_na.na_dir_profile_emp a
                join boardex_na.na_dir_profile_emp b
                  on a.companyid = b.companyid
                 and a.directorid <> b.directorid
                where a.directorid = {int(row.dirbrdid)}
                  and b.directorid = {int(row.directorid)}
                  and a.companyid = {int(row.companyid)}
                  and extract(year from greatest(a.datestartrole, b.datestartrole))
                        <= {int(row.overlapyearend_int)}
                  and extract(year from least(
                        coalesce(a.dateendrole, current_date),
                        coalesce(b.dateendrole, current_date)
                      )) >= {int(row.overlapyearstart_int)}
            )
        """
        matched_rows += int(_run_exists_query(wrds_db, query))

    return ValidationResult(
        table_name="na_wrds_individual_networks",
        matched_rows=matched_rows,
        checked_rows=len(sample),
        interpretation=build_interpretation(
            matched_rows=matched_rows,
            checked_rows=len(sample),
            ordered_sample=False,
        ),
    )


def validate_board_assoc_tables(wrds_db) -> list[ValidationResult]:
    """Validate one sampled row from each ``na_board_*_assoc`` table."""

    checks: list[tuple[str, str]] = [
        (
            "na_board_listed_assoc",
            """
            select exists (
                select 1
                from boardex_na.na_board_listed_assoc s
                join boardex_na.na_dir_profile_emp a
                  on a.companyid = s.boardid and a.directorid = s.directorid
                join boardex_na.na_dir_profile_emp b
                  on b.companyid = s.companyid and b.directorid = s.directorid
                where s.ctid = (select ctid from boardex_na.na_board_listed_assoc limit 1)
                  and extract(year from greatest(a.datestartrole, b.datestartrole))
                        <= cast(s.overlapyearend as integer)
                  and extract(year from least(
                        coalesce(a.dateendrole, current_date),
                        coalesce(b.dateendrole, current_date)
                      )) >= cast(s.overlapyearstart as integer)
            )
            """,
        ),
        (
            "na_board_unlisted_assoc",
            """
            select exists (
                select 1
                from boardex_na.na_board_unlisted_assoc s
                join boardex_na.na_dir_profile_emp a
                  on a.companyid = s.boardid and a.directorid = s.directorid
                join boardex_na.na_dir_profile_emp b
                  on b.companyid = s.companyid and b.directorid = s.directorid
                where s.ctid = (select ctid from boardex_na.na_board_unlisted_assoc limit 1)
                  and extract(year from greatest(a.datestartrole, b.datestartrole))
                        <= cast(s.overlapyearend as integer)
                  and extract(year from least(
                        coalesce(a.dateendrole, current_date),
                        coalesce(b.dateendrole, current_date)
                      )) >= cast(s.overlapyearstart as integer)
            )
            """,
        ),
        (
            "na_board_nfp_assoc",
            """
            select exists (
                select 1
                from boardex_na.na_board_nfp_assoc s
                join boardex_na.na_dir_profile_emp a
                  on a.companyid = s.boardid and a.directorid = s.directorid
                join boardex_na.na_dir_profile_other_activ b
                  on b.companyid = s.companyid and b.directorid = s.directorid
                where s.ctid = (select ctid from boardex_na.na_board_nfp_assoc limit 1)
                  and extract(year from greatest(a.datestartrole, b.startdate))
                        <= cast(s.overlapyearend as integer)
                  and extract(year from least(
                        coalesce(a.dateendrole, current_date),
                        coalesce(b.enddate, current_date)
                      )) >= cast(s.overlapyearstart as integer)
            )
            """,
        ),
        (
            "na_board_other_assoc",
            """
            select exists (
                select 1
                from boardex_na.na_board_other_assoc s
                join boardex_na.na_dir_profile_emp a
                  on a.companyid = s.boardid and a.directorid = s.directorid
                join boardex_na.na_dir_profile_other_activ b
                  on b.companyid = s.companyid and b.directorid = s.directorid
                where s.ctid = (select ctid from boardex_na.na_board_other_assoc limit 1)
                  and extract(year from greatest(a.datestartrole, b.startdate))
                        <= cast(s.overlapyearend as integer)
                  and extract(year from least(
                        coalesce(a.dateendrole, current_date),
                        coalesce(b.enddate, current_date)
                      )) >= cast(s.overlapyearstart as integer)
            )
            """,
        ),
        (
            "na_board_education_assoc",
            """
            select exists (
                select 1
                from boardex_na.na_board_education_assoc s
                join boardex_na.na_dir_profile_emp a
                  on a.companyid = s.boardid and a.directorid = s.directorid
                join boardex_na.na_dir_profile_education b
                  on b.companyid = s.companyid and b.directorid = s.directorid
                where s.ctid = (select ctid from boardex_na.na_board_education_assoc limit 1)
                  and extract(year from a.datestartrole) <= cast(s.overlapyearend as integer)
                  and extract(year from coalesce(a.dateendrole, current_date))
                        >= cast(s.overlapyearstart as integer)
                  and extract(year from b.awarddate)
                        between cast(s.overlapyearstart as integer)
                            and cast(s.overlapyearend as integer)
            )
            """,
        ),
    ]

    results: list[ValidationResult] = []

    for table_name, query in checks:
        matched = int(_run_exists_query(wrds_db, query))
        results.append(
            ValidationResult(
                table_name=table_name,
                matched_rows=matched,
                checked_rows=1,
                interpretation=build_interpretation(
                    matched_rows=matched,
                    checked_rows=1,
                    ordered_sample=False,
                ),
            )
        )

    return results


def validate_senior_managers(wrds_db) -> ValidationResult:
    """Validate that two sampled senior-manager rows exist in emp."""

    sample = wrds_db.raw_sql(
        """
        select boardid, directorid, rolename, datestartrole, dateendrole
        from boardex_na.na_company_profile_sr_mgrs
        limit 2
        """
    )

    matched_rows = 0

    for row in sample.itertuples(index=False):
        role_name = str(row.rolename).replace("'", "''")
        start_date = pd.to_datetime(row.datestartrole).strftime("%Y-%m-%d")

        if pd.notna(row.dateendrole):
            end_date = pd.to_datetime(row.dateendrole).strftime("%Y-%m-%d")
            end_clause = f"e.dateendrole = date '{end_date}'"
        else:
            end_clause = "e.dateendrole is null"

        query = f"""
            select exists (
                select 1
                from boardex_na.na_dir_profile_emp e
                where e.companyid = {int(row.boardid)}
                  and e.directorid = {int(row.directorid)}
                  and e.rolename = '{role_name}'
                  and e.datestartrole = date '{start_date}'
                  and {end_clause}
            )
        """
        matched_rows += int(_run_exists_query(wrds_db, query))

    return ValidationResult(
        table_name="na_company_profile_sr_mgrs",
        matched_rows=matched_rows,
        checked_rows=len(sample),
        interpretation=build_interpretation(
            matched_rows=matched_rows,
            checked_rows=len(sample),
            ordered_sample=False,
        ),
    )


def validate_company_networks(wrds_db) -> ValidationResult:
    """Validate two sampled company-network rows against a broad role union.

    This check intentionally uses a broader normalized role union because the
    company-network table pulls from more than plain employment history. The
    sample also uses an unordered ``LIMIT 2`` query, so reruns may inspect
    different rows.
    """

    query = """
        with sample as (
            select associationtype, boardid, companyid, directorid,
                   overlapyearstart_int, overlapyearend_int
            from boardex_na.na_wrds_company_networks
            limit 2
        ),
        normalized_roles as (
            select directorid, companyid, datestartrole as start_date,
                   coalesce(dateendrole, current_date) as end_date, 'emp' as src
            from boardex_na.na_dir_profile_emp
            union all
            select directorid, companyid, datestartrole as start_date,
                   coalesce(dateendrole, current_date) as end_date, 'org' as src
            from boardex_na.na_wrds_org_composition
            union all
            select directorid, boardid as companyid, datestartrole as start_date,
                   coalesce(dateendrole, current_date) as end_date, 'sr' as src
            from boardex_na.na_company_profile_sr_mgrs
            union all
            select directorid, companyid, startdate as start_date,
                   coalesce(enddate, current_date) as end_date, 'other' as src
            from boardex_na.na_dir_profile_other_activ
            union all
            select directorid, companyid, awarddate as start_date,
                   awarddate as end_date, 'edu' as src
            from boardex_na.na_dir_profile_education
        )
        select
            count(*) as checked_rows,
            sum(case when exists (
                select 1
                from normalized_roles a
                join normalized_roles b
                  on a.directorid = b.directorid
                 and a.companyid <> b.companyid
                where a.companyid = s.boardid
                  and b.companyid = s.companyid
                  and a.directorid = s.directorid
                  and extract(year from greatest(a.start_date, b.start_date))
                        <= s.overlapyearend_int
                  and extract(year from least(a.end_date, b.end_date))
                        >= s.overlapyearstart_int
            ) then 1 else 0 end) as matched_rows
        from sample s
    """

    result = wrds_db.raw_sql(query).iloc[0]

    return ValidationResult(
        table_name="na_wrds_company_networks",
        matched_rows=int(result["matched_rows"]),
        checked_rows=int(result["checked_rows"]),
        interpretation=build_interpretation(
            matched_rows=int(result["matched_rows"]),
            checked_rows=int(result["checked_rows"]),
            ordered_sample=False,
        ),
    )


def main() -> None:
    """Run all live WRDS spot checks and print a compact summary."""

    wrds_db = connect_wrds()

    try:
        results: list[ValidationResult] = []
        results.append(validate_individual_networks(wrds_db))
        results.extend(validate_board_assoc_tables(wrds_db))
        results.append(validate_senior_managers(wrds_db))
        results.append(validate_company_networks(wrds_db))
    finally:
        wrds_db.close()

    print("table_name,matched_rows,checked_rows,interpretation")

    for result in results:
        safe_interpretation = result.interpretation.replace(",", ";")
        print(
            f"{result.table_name},"
            f"{result.matched_rows},"
            f"{result.checked_rows},"
            f"{safe_interpretation}"
        )


if __name__ == "__main__":
    main()
