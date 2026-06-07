"""Configuration parsing for the IvyDB ClickHouse loader.

The loader is config-driven. Edit ``config.toml`` to choose which table families
are enabled, then run ``create-tables`` and ``load`` with no CLI flags beyond an
optional ``--config`` path override.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import tomllib
from typing import Any


DEFAULT_START_YEAR = 1996
DEFAULT_END_YEAR = 2025
DEFAULT_WRDS_BATCH_SIZE = 100000
DEFAULT_CLICKHOUSE_INSERT_SIZE = 100000
DEFAULT_RESUME = True
OPTIONM_LIBRARY = "optionm_all"
CRSP_LINK_LIBRARY = "wrdsapps_link_crsp_optionm"
OPTION_PRICE_PREFIX = "opprcd"
UNDERLYING_PRICE_PREFIX = "secprd"
UNDERLYING_TARGET_TABLE = "secprd"
SOURCE_YEAR_COLUMN = "source_year"
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
IVYDB_YEARS = tuple(range(DEFAULT_START_YEAR, DEFAULT_END_YEAR + 1))
ENV_FILE_NAME = ".env"
CLICKHOUSE_ENV_PREFIX = "IVYDB_CLICKHOUSE_"
STATIC_TABLES = (
    (OPTIONM_LIBRARY, "securd", "securd"),
    (OPTIONM_LIBRARY, "secnmd", "secnmd"),
    (OPTIONM_LIBRARY, "exchgd", "exchgd"),
    (OPTIONM_LIBRARY, "distrd", "distrd"),
    (OPTIONM_LIBRARY, "opinfd", "opinfd"),
    (CRSP_LINK_LIBRARY, "opcrsphist", "opcrsphist"),
)
STATIC_TABLE_BY_NAME = {
    source_table: (source_library, source_table, target_table)
    for source_library, source_table, target_table in STATIC_TABLES
}


@dataclass(frozen=True)
class ClickHouseConfig:
    """Connection settings for the target ClickHouse database.

    Parameters
    ----------
    host:
        ClickHouse host name or URL. The client module accepts plain host names
        and HTTP or HTTPS URLs.
    port:
        HTTP interface port for ClickHouse.
    username:
        ClickHouse username.
    password:
        ClickHouse password.
    secure:
        Whether to use HTTPS/TLS.
    database:
        Target ClickHouse database that receives IvyDB tables.
    """

    host: str
    port: int
    username: str
    password: str
    secure: bool
    database: str


@dataclass(frozen=True)
class LoaderConfig:
    """Internal operational settings for WRDS streaming, ClickHouse insertion, and logs.

    Parameters
    ----------
    wrds_batch_size:
        Number of WRDS PostgreSQL rows to fetch per streamed pandas DataFrame.
    clickhouse_insert_size:
        Number of rows to send to ClickHouse in each insert batch.
    resume:
        Whether completed local audit records should skip already-loaded source
        tables.
    audit_log_path:
        Local JSON-lines file that records load status for resume checks. This
        file intentionally lives outside ClickHouse so the target database only
        contains IvyDB data tables.
    run_log_path:
        Local text log for human-readable loader progress. ``None`` disables
        file logging while still printing to the terminal.
    """

    wrds_batch_size: int
    clickhouse_insert_size: int
    resume: bool
    audit_log_path: Path
    run_log_path: Path | None


@dataclass(frozen=True)
class OptionPriceConfig:
    """Settings for yearly option price tables named like ``opprcd2024``."""

    source_library: str
    source_prefix: str
    years: tuple[int, ...]
    target_template: str


@dataclass(frozen=True)
class UnderlyingPriceConfig:
    """Settings for yearly underlying price tables named like ``secprd2024``."""

    source_library: str
    source_prefix: str
    years: tuple[int, ...]
    target_table: str
    source_year_column: str


@dataclass(frozen=True)
class StaticTableConfig:
    """One full-table copy from WRDS into one ClickHouse table."""

    source_library: str
    source_table: str
    target_table: str


@dataclass(frozen=True)
class AppConfig:
    """Full loader configuration assembled from TOML plus fixed IvyDB defaults."""

    clickhouse: ClickHouseConfig
    loader: LoaderConfig
    option_prices: OptionPriceConfig
    underlying_prices: UnderlyingPriceConfig
    static_tables: tuple[StaticTableConfig, ...]

    @property
    def option_price_years(self) -> list[int]:
        """Return configured option price years as a list for CLI display."""

        return list(self.option_prices.years)

    @property
    def underlying_price_years(self) -> list[int]:
        """Return configured underlying price years as a list for CLI display."""

        return list(self.underlying_prices.years)


def default_config_path() -> Path:
    """Return the package-local default TOML configuration path."""

    return Path(__file__).resolve().parent / "config.toml"


def project_root() -> Path:
    """Return the repository root inferred from this package file."""

    return Path(__file__).resolve().parents[2]


def default_config() -> AppConfig:
    """Load the package default configuration."""

    return load_config(default_config_path())


def load_config(path: Path) -> AppConfig:
    """Read and validate an IvyDB ClickHouse loader TOML file.

    Parameters
    ----------
    path:
        Path to the TOML configuration file.

    Returns
    -------
    AppConfig
        Typed configuration used by the CLI and loader modules.
    """

    with path.open("rb") as config_file:
        raw_config = tomllib.load(config_file)

    env_config = _load_ivydb_env(path)
    clickhouse = _parse_clickhouse_config(raw_config.get("clickhouse", {}), env_config)
    loader = _parse_loader_config(raw_config.get("loader", {}))
    tables_config = raw_config.get("tables", {})

    return AppConfig(
        clickhouse=clickhouse,
        loader=loader,
        option_prices=_parse_option_price_config(tables_config.get("option_prices", {})),
        underlying_prices=_parse_underlying_price_config(tables_config.get("underlying_prices", {})),
        static_tables=_parse_static_tables(tables_config.get("static_reference", {})),
    )


def _parse_clickhouse_config(
    raw_config: dict[str, Any],
    env_config: dict[str, str] | None = None,
) -> ClickHouseConfig:
    """Parse ClickHouse connection settings from raw TOML values."""

    env_config = {} if env_config is None else env_config
    host = _clickhouse_setting(raw_config, env_config, "host", "localhost")
    port = int(_clickhouse_setting(raw_config, env_config, "port", "8123"))
    username = _clickhouse_setting(raw_config, env_config, "username", "ivydb_user")
    password = _clickhouse_setting(raw_config, env_config, "password", "")
    secure = _parse_bool(_clickhouse_setting(raw_config, env_config, "secure", "false"))
    database = _validated_identifier(
        _clickhouse_setting(raw_config, env_config, "database", "ivydb"),
        "clickhouse.database",
    )

    return ClickHouseConfig(
        host=host,
        port=port,
        username=username,
        password=password,
        secure=secure,
        database=database,
    )


def _load_ivydb_env(config_path: Path) -> dict[str, str]:
    """Load ClickHouse environment values from process env and ``ivydb/.env``.

    Process environment variables win over the local file so Docker, shell
    exports, and one-off command prefixes can override saved defaults.
    """

    env_file_values = _read_env_file(_ivydb_env_path(config_path))
    merged_values = dict(env_file_values)
    for key, value in os.environ.items():
        if key.startswith(CLICKHOUSE_ENV_PREFIX):
            merged_values[key] = value
    return merged_values


def _ivydb_env_path(config_path: Path) -> Path:
    """Return the ``ivydb/.env`` path adjacent to ``clickhouse_loader``."""

    return config_path.resolve().parent.parent / ENV_FILE_NAME


def _read_env_file(env_path: Path) -> dict[str, str]:
    """Read a simple KEY=VALUE env file without mutating ``os.environ``."""

    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    env_lines = env_path.read_text(encoding="utf-8").splitlines()
    for line_number, raw_line in enumerate(env_lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{env_path}:{line_number} is not KEY=VALUE syntax")
        key, raw_value = line.split("=", maxsplit=1)
        key = key.strip()
        value = raw_value.strip().strip('"').strip("'")
        values[key] = value
    return values


def _clickhouse_setting(
    raw_config: dict[str, Any],
    env_config: dict[str, str],
    name: str,
    default: str,
) -> str:
    """Return one ClickHouse setting from env first, TOML second, default last."""

    env_key = f"{CLICKHOUSE_ENV_PREFIX}{name.upper()}"
    if env_key in env_config:
        return env_config[env_key]
    if name in raw_config:
        return str(raw_config[name])
    return default


def _parse_bool(value: str) -> bool:
    """Parse common environment spellings for a boolean flag."""

    normalized_value = value.strip().lower()
    if normalized_value in {"1", "true", "yes", "on"}:
        return True
    if normalized_value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"expected a boolean value, got {value!r}")


def _parse_loader_config(raw_config: dict[str, Any]) -> LoaderConfig:
    """Build internal loader settings.

    The public TOML file intentionally does not expose batch sizes. This loader
    targets one known IvyDB source, so operational tuning values stay as code
    defaults while the TOML controls only local connection and table selection.
    """

    return LoaderConfig(
        wrds_batch_size=DEFAULT_WRDS_BATCH_SIZE,
        clickhouse_insert_size=DEFAULT_CLICKHOUSE_INSERT_SIZE,
        resume=bool(raw_config.get("resume", DEFAULT_RESUME)),
        audit_log_path=_parse_local_path(
            raw_config.get("audit_log_path", "logs/ivydb_load_audit.jsonl"),
            "loader.audit_log_path",
        ),
        run_log_path=_parse_optional_local_path(
            raw_config.get("run_log_path", "logs/ivydb_loader.log"),
            "loader.run_log_path",
        ),
    )


def _parse_local_path(raw_path: Any, field_name: str) -> Path:
    """Parse a local filesystem path and resolve relative paths from the repo root."""

    path = Path(str(raw_path)).expanduser()
    if path.is_absolute():
        return path
    if not str(path):
        raise ValueError(f"{field_name} must not be empty")
    return project_root() / path


def _parse_optional_local_path(raw_path: Any, field_name: str) -> Path | None:
    """Parse an optional local filesystem path from TOML.

    An empty string disables file logging. This is useful for short smoke tests
    where terminal output is enough.
    """

    if raw_path is None or str(raw_path) == "":
        return None
    return _parse_local_path(raw_path, field_name)


def _parse_enabled_years(raw_config: dict[str, Any], years_field_name: str) -> list[int]:
    """Return configured years, or an empty list when the table family is disabled."""

    if not bool(raw_config.get("enabled", True)):
        return []
    return _parse_years(raw_config.get("years", []), years_field_name)


def _parse_option_price_config(raw_config: dict[str, Any]) -> OptionPriceConfig:
    """Parse selected yearly option-price tables from TOML."""

    source_library = _validated_identifier(
        str(raw_config.get("source_library", OPTIONM_LIBRARY)),
        "tables.option_prices.source_library",
    )
    source_prefix = _validated_identifier(
        str(raw_config.get("source_prefix", OPTION_PRICE_PREFIX)),
        "tables.option_prices.source_prefix",
    )
    target_template = str(raw_config.get("target_template", f"{OPTION_PRICE_PREFIX}" + "{year}"))
    if "{year}" not in target_template:
        raise ValueError("tables.option_prices.target_template must contain {year}")
    years = _parse_enabled_years(raw_config, "tables.option_prices.years")

    return OptionPriceConfig(
        source_library=source_library,
        source_prefix=source_prefix,
        years=tuple(years),
        target_template=target_template,
    )


def _parse_underlying_price_config(raw_config: dict[str, Any]) -> UnderlyingPriceConfig:
    """Parse selected yearly underlying-price tables from TOML."""

    source_library = _validated_identifier(
        str(raw_config.get("source_library", OPTIONM_LIBRARY)),
        "tables.underlying_prices.source_library",
    )
    source_prefix = _validated_identifier(
        str(raw_config.get("source_prefix", UNDERLYING_PRICE_PREFIX)),
        "tables.underlying_prices.source_prefix",
    )
    years = _parse_enabled_years(raw_config, "tables.underlying_prices.years")

    return UnderlyingPriceConfig(
        source_library=source_library,
        source_prefix=source_prefix,
        years=tuple(years),
        target_table=_validated_identifier(
            str(raw_config.get("target_table", UNDERLYING_TARGET_TABLE)),
            "tables.underlying_prices.target_table",
        ),
        source_year_column=_validated_identifier(
            str(raw_config.get("source_year_column", SOURCE_YEAR_COLUMN)),
            "tables.underlying_prices.source_year_column",
        ),
    )


def _parse_static_tables(raw_config: dict[str, Any]) -> tuple[StaticTableConfig, ...]:
    """Parse selected static/reference tables from TOML."""

    if not bool(raw_config.get("enabled", True)):
        return ()
    selected_tables = raw_config.get("tables", [])
    if not isinstance(selected_tables, list):
        raise ValueError("tables.static_reference.tables must be a list")

    parsed_tables: list[StaticTableConfig] = []
    for index, table_config in enumerate(selected_tables):
        prefix = f"tables.static_reference.tables[{index}]"
        if isinstance(table_config, str):
            if table_config not in STATIC_TABLE_BY_NAME:
                allowed_tables = ", ".join(sorted(STATIC_TABLE_BY_NAME))
                raise ValueError(
                    f"unknown IvyDB static table {table_config!r}; allowed values: {allowed_tables}"
                )
            source_library, source_table, target_table = STATIC_TABLE_BY_NAME[table_config]
        elif isinstance(table_config, dict):
            source_library = _validated_identifier(
                str(table_config["source_library"]),
                f"{prefix}.source_library",
            )
            source_table = _validated_identifier(
                str(table_config["source_table"]),
                f"{prefix}.source_table",
            )
            target_table = _validated_identifier(
                str(table_config["target_table"]),
                f"{prefix}.target_table",
            )
        else:
            raise ValueError(f"{prefix} must be a table name string or table mapping")

        parsed_tables.append(
            StaticTableConfig(
                source_library=source_library,
                source_table=source_table,
                target_table=target_table,
            )
        )

    return tuple(parsed_tables)


def _parse_years(raw_years: Any, field_name: str) -> list[int]:
    """Validate and normalize a user-selected list of table years."""

    if not isinstance(raw_years, list):
        raise ValueError(f"{field_name} must be a list of integer years")

    years: list[int] = []
    for year in raw_years:
        if not isinstance(year, int):
            raise ValueError(f"{field_name} must contain integer years")
        years.append(year)
    if years != sorted(set(years)):
        raise ValueError(f"{field_name} must be sorted and unique")
    if years and (years[0] < DEFAULT_START_YEAR or years[-1] > DEFAULT_END_YEAR):
        raise ValueError(
            f"{field_name} must stay between {DEFAULT_START_YEAR} and {DEFAULT_END_YEAR}"
        )
    return years


def _validated_identifier(value: str, field_name: str) -> str:
    """Validate a SQL identifier that will later be quoted.

    The loader still quotes PostgreSQL and ClickHouse identifiers, but rejecting
    unusual values at the configuration boundary keeps mistakes obvious before
    a long data load starts.
    """

    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} is not a simple SQL identifier: {value!r}")
    return value
