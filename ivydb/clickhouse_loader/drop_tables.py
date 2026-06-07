"""Drop selected IvyDB ClickHouse tables after explicit manual confirmation.

This module owns the destructive table-removal path for the IvyDB loader. The
normal workflow is still ``create-tables`` followed by ``load``. Dropping tables
is an exceptional reset step for a selected config batch, so callers must
require two confirmations before executing any ``DROP TABLE`` command.
"""

from __future__ import annotations

from collections.abc import Callable

from ivydb.clickhouse_loader.clickhouse_client import create_client
from ivydb.clickhouse_loader.config import AppConfig
from ivydb.clickhouse_loader.create_tables import planned_create_table_names


ConfirmationReader = Callable[[str], str]
OutputWriter = Callable[[str], None]


def planned_drop_table_names(config: AppConfig) -> list[str]:
    """Return ClickHouse table names that one drop-tables run would remove.

    Parameters
    ----------
    config:
        Parsed loader configuration. The enabled table families and year lists
        define the target tables, using the same selection surface as
        ``create-tables``.

    Returns
    -------
    list[str]
        Deduplicated ClickHouse table names selected for removal.
    """

    return planned_create_table_names(config)


def confirmed_drop_table_names(
    *,
    database: str,
    tables: list[str],
    read_confirmation: ConfirmationReader,
    write_output: OutputWriter,
) -> list[str]:
    """Return table names only after two exact manual confirmations.

    Parameters
    ----------
    database:
        ClickHouse database that contains the target tables.
    tables:
        Deduplicated table names selected for deletion.
    read_confirmation:
        Function used to read operator input. The CLI passes ``input``.
    write_output:
        Function used to show warnings and the expected confirmation text.

    Returns
    -------
    list[str]
        The original ``tables`` list when both confirmations match exactly.

    Raises
    ------
    ValueError
        Raised when either confirmation does not match the expected value.
    """

    table_list = ",".join(tables)
    qualified_table_list = ", ".join(f"{database}.{table}" for table in tables)

    write_output("DANGER: this will permanently drop selected IvyDB ClickHouse tables.")
    write_output(f"Target database: {database}")
    write_output(f"Target tables: {qualified_table_list}")

    database_answer = read_confirmation(
        f"First confirmation: type exactly '{database}' as the database name: "
    )
    if database_answer != database:
        raise ValueError("drop-tables aborted: database confirmation did not match")

    table_answer = read_confirmation(
        f"Second confirmation: type exactly this table list '{table_list}': "
    )
    if table_answer != table_list:
        raise ValueError("drop-tables aborted: table-list confirmation did not match")

    return tables


def drop_tables_from_config(config: AppConfig) -> list[str]:
    """Submit drop commands for every selected ClickHouse table.

    Parameters
    ----------
    config:
        Parsed loader configuration. The selected table families decide which
        tables are dropped. The CLI confirms the destructive action before
        calling this function.

    Returns
    -------
    list[str]
        ClickHouse table names that were submitted to ``DROP TABLE IF EXISTS``.
    """

    planned_tables = planned_drop_table_names(config)
    if not planned_tables:
        return []

    client = create_client(config.clickhouse)
    database = config.clickhouse.database
    for table in planned_tables:
        client.command(f"DROP TABLE IF EXISTS `{database}`.`{table}`")

    return planned_tables
