"""Post-load validation helpers for IvyDB ClickHouse tables."""

from __future__ import annotations

from dataclasses import dataclass

from ivydb.clickhouse_loader.table_plan import TablePlan


@dataclass(frozen=True)
class ValidationResult:
    """One validation check result."""

    table: str
    check_name: str
    value: int | float | str


def row_count_sql(database: str, table: str) -> str:
    """Build a ClickHouse row-count query."""

    return f"SELECT count() FROM `{database}`.`{table}`"


def date_range_sql(database: str, table: str) -> str:
    """Build a ClickHouse date-range query for tables with a ``date`` column."""

    return f"SELECT min(`date`), max(`date`) FROM `{database}`.`{table}`"


def source_year_summary_sql(database: str, table: str, source_year_column: str, years: list[int]) -> str:
    """Build a ClickHouse summary query for one consolidated yearly target."""

    year_list = ", ".join(str(year) for year in years)
    return (
        f"SELECT `{source_year_column}`, count(), min(`date`), max(`date`) "
        f"FROM `{database}`.`{table}` "
        f"WHERE `{source_year_column}` IN ({year_list}) "
        f"GROUP BY `{source_year_column}` "
        f"ORDER BY `{source_year_column}`"
    )


def required_key_null_count_sql(database: str, table: str, column: str) -> str:
    """Build a query that counts nulls in one required key column."""

    return f"SELECT count() FROM `{database}`.`{table}` WHERE `{column}` IS NULL"


def opprcd_duplicate_key_sql(database: str, table: str) -> str:
    """Build duplicate-key validation SQL for one option-price table."""

    key_columns = "`secid`, `date`, `optionid`, `exdate`, `cp_flag`, `strike_price`"
    return (
        "SELECT count() FROM ("
        f"SELECT {key_columns}, count() AS duplicate_count "
        f"FROM `{database}`.`{table}` "
        f"GROUP BY {key_columns} "
        "HAVING count() > 1"
        ")"
    )


def opcrsphist_link_quality_sql(database: str) -> str:
    """Build link-quality validation SQL for the OptionMetrics-CRSP link table."""

    return (
        "SELECT "
        "count() AS row_count, "
        "countIf(permno IS NULL) AS missing_permno, "
        "countIf(sdate IS NULL) AS missing_sdate, "
        "countIf(edate IS NULL) AS missing_edate, "
        "countIf(score = 1) AS score_1_rows, "
        "countIf(score != 1 OR score IS NULL) AS non_score_1_rows "
        f"FROM `{database}`.`opcrsphist`"
    )


def validate_loaded_tables(
    clickhouse_client: object,
    database: str,
    table_plan: list[TablePlan],
) -> list[ValidationResult]:
    """Run post-load validation checks for loaded target tables.

    The checks are intentionally read-only. They report suspicious counts but do
    not delete rows, filter low-score CRSP links, or rewrite any target table.
    """

    results: list[ValidationResult] = []
    plans_by_target: dict[str, list[TablePlan]] = {}
    for table in table_plan:
        plans_by_target.setdefault(table.target_table, []).append(table)

    for target_plans in plans_by_target.values():
        target_results = _validate_one_target_table(
            clickhouse_client,
            database,
            target_plans[0],
            target_plans,
        )
        results.extend(target_results)

    return results


def _validate_one_target_table(
    clickhouse_client: object,
    database: str,
    table: TablePlan,
    target_plans: list[TablePlan],
) -> list[ValidationResult]:
    """Run all validation checks for one ClickHouse target table."""

    try:
        query_result = clickhouse_client.query(row_count_sql(database, table.target_table))
        row_count = query_result.result_rows[0][0]
    except Exception as error:
        return [
            ValidationResult(
                table=table.target_table,
                check_name="missing_or_unreadable",
                value=str(error),
            )
        ]

    results = [
        ValidationResult(
            table=table.target_table,
            check_name="row_count",
            value=row_count,
        )
    ]
    if table.is_consolidated_year_table:
        results.extend(_validate_source_year_summaries(clickhouse_client, database, table, target_plans))
    else:
        results.extend(_validate_date_range(clickhouse_client, database, table))
    results.extend(_validate_required_keys(clickhouse_client, database, table))

    if table.source_prefix == "opprcd":
        duplicate_result = clickhouse_client.query(
            opprcd_duplicate_key_sql(database, table.target_table)
        )
        results.append(
            ValidationResult(
                table=table.target_table,
                check_name="duplicate_contract_date_keys",
                value=duplicate_result.result_rows[0][0],
            )
        )

    if table.target_table == "opcrsphist":
        results.extend(_opcrsphist_link_quality_results(clickhouse_client, database))

    return results


def _validate_source_year_summaries(
    clickhouse_client: object,
    database: str,
    table: TablePlan,
    target_plans: list[TablePlan],
) -> list[ValidationResult]:
    """Return per-source-year row counts and date ranges for consolidated targets."""

    if table.source_year_column is None:
        raise ValueError("consolidated validation needs a source-year column")

    years = [
        target_plan.source_year
        for target_plan in target_plans
        if target_plan.source_year is not None
    ]
    if not years:
        return []

    query_result = clickhouse_client.query(
        source_year_summary_sql(
            database=database,
            table=table.target_table,
            source_year_column=table.source_year_column,
            years=years,
        )
    )

    results: list[ValidationResult] = []
    observed_years: set[int] = set()
    for source_year, row_count, min_date, max_date in query_result.result_rows:
        year = int(source_year)
        observed_years.add(year)
        results.extend(
            [
                ValidationResult(table.target_table, f"source_year_{year}_row_count", row_count),
                ValidationResult(table.target_table, f"source_year_{year}_min_date", str(min_date)),
                ValidationResult(table.target_table, f"source_year_{year}_max_date", str(max_date)),
            ]
        )

    for year in years:
        if year in observed_years:
            continue
        results.extend(
            [
                ValidationResult(table.target_table, f"source_year_{year}_row_count", 0),
                ValidationResult(table.target_table, f"source_year_{year}_min_date", ""),
                ValidationResult(table.target_table, f"source_year_{year}_max_date", ""),
            ]
        )

    return results


def _opcrsphist_link_quality_results(
    clickhouse_client: object,
    database: str,
) -> list[ValidationResult]:
    """Return link-quality metrics for the OptionMetrics-CRSP mapping table."""

    link_result = clickhouse_client.query(opcrsphist_link_quality_sql(database))
    row = link_result.result_rows[0]
    check_names = [
        "link_quality_row_count",
        "missing_permno",
        "missing_sdate",
        "missing_edate",
        "score_1_rows",
        "non_score_1_rows",
    ]
    return [
        ValidationResult(table="opcrsphist", check_name=check_name, value=value)
        for check_name, value in zip(check_names, row, strict=True)
    ]


def _validate_date_range(
    clickhouse_client: object,
    database: str,
    table: TablePlan,
) -> list[ValidationResult]:
    """Return min and max date checks for annual source tables."""

    if table.source_prefix not in {"opprcd", "secprd"}:
        return []

    query_result = clickhouse_client.query(date_range_sql(database, table.target_table))
    min_date, max_date = query_result.result_rows[0]
    return [
        ValidationResult(table.target_table, "min_date", str(min_date)),
        ValidationResult(table.target_table, "max_date", str(max_date)),
    ]


def _validate_required_keys(
    clickhouse_client: object,
    database: str,
    table: TablePlan,
) -> list[ValidationResult]:
    """Return null-count checks for required key columns."""

    required_columns = _required_key_columns(table)
    results: list[ValidationResult] = []
    for column in required_columns:
        query_result = clickhouse_client.query(
            required_key_null_count_sql(database, table.target_table, column)
        )
        results.append(
            ValidationResult(
                table=table.target_table,
                check_name=f"null_{column}",
                value=query_result.result_rows[0][0],
            )
        )

    return results


def _required_key_columns(table: TablePlan) -> list[str]:
    """Return validation key columns for one target table."""

    if table.source_prefix == "opprcd":
        return ["secid", "date", "optionid", "exdate", "cp_flag", "strike_price"]
    if table.source_prefix == "secprd":
        return ["secid", "date"]
    if table.target_table == "opcrsphist":
        return ["permno", "sdate", "edate"]
    return ["secid"] if table.target_table in {"securd", "secnmd", "exchgd", "distrd", "opinfd"} else []
