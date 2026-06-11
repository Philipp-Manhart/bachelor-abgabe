# /// script
# requires-python = "==3.14.*"
# dependencies = ["duckdb"]
# ///

"""Initialize or populate a DuckDB data warehouse for an automotive bank."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from data_generation.accounts import populate_banking_accounts
from data_generation.cashflows import populate_contract_cashflows
from data_generation.config import DEFAULT_SEED, SCALE_PROFILES, build_config
from data_generation.contracts import populate_contract_facts
from data_generation.customers import populate_dim_customer
from data_generation.dates import populate_dim_date
from data_generation.dealers import populate_dim_dealer
from data_generation.payments import populate_payment_transactions
from data_generation.reference_data import load_reference_data
from data_generation.seeds import populate_seed_staging
from data_generation.status_history import populate_contract_status_history
from data_generation.validation import (
    validate_base_dimensions,
    validate_business_coverage,
    validate_core_model,
    validate_expansion_model,
    validate_seed_staging,
)
from data_generation.vehicles import populate_dim_vehicle

EXPECTED_TABLES = (
    "dim_customer",
    "dim_vehicle",
    "dim_dealer",
    "dim_product",
    "dim_contract_status",
    "dim_cashflow_type",
    "dim_date",
    "fact_leasing_contracts",
    "fact_loan_contracts",
    "fact_contract_status_history",
    "fact_banking_accounts",
    "fact_contract_cashflows",
    "fact_payment_transactions",
)

STAGING_TABLES = (
    "stg_customer_seed",
    "stg_dealer_seed",
    "stg_vehicle_seed",
    "stg_contract_seed",
    "stg_account_seed",
)


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(
        description="Create or populate an automotive-bank star schema in DuckDB."
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=project_root / "database" / "benchmark.duckdb",
        help="Target DuckDB database file. Defaults to database/benchmark.duckdb.",
    )
    parser.add_argument(
        "--schema-path",
        type=Path,
        default=Path(__file__).with_name("schema.sql"),
        help="SQL DDL file to execute.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="Create the empty warehouse schema.")

    demo_parser = subparsers.add_parser(
        "demo",
        help="Load the step-1 demo foundation dimensions into the warehouse.",
    )
    demo_parser.add_argument(
        "--scale",
        choices=sorted(SCALE_PROFILES),
        default="dev",
        help="Scale profile placeholder for later generation steps.",
    )
    demo_parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Deterministic seed for future generation steps.",
    )
    return parser.parse_args()


def initialize_database(database_path: Path, schema_path: Path) -> None:
    if not schema_path.exists():
        msg = f"Schema file does not exist: {schema_path}"
        raise FileNotFoundError(msg)

    database_path.parent.mkdir(parents=True, exist_ok=True)
    ddl = schema_path.read_text(encoding="utf-8")

    with duckdb.connect(str(database_path)) as connection:
        connection.execute(ddl)
        validate_empty_schema(connection)


def load_demo_foundation(
    database_path: Path,
    schema_path: Path,
    scale_name: str,
    seed: int,
) -> dict[str, int]:
    config = build_config(scale_name=scale_name, seed=seed)
    initialize_database(database_path=database_path, schema_path=schema_path)

    with duckdb.connect(str(database_path)) as connection:
        populate_dim_date(
            connection=connection,
            start_date=config.date_start,
            end_date=config.date_end,
        )
        load_reference_data(connection)
        validate_base_dimensions(connection)
        populate_seed_staging(connection, config)
        validate_seed_staging(connection, config)
        populate_dim_customer(connection, config)
        populate_dim_dealer(connection, config)
        populate_dim_vehicle(connection)
        populate_contract_facts(connection)
        validate_core_model(connection, config)
        populate_contract_status_history(connection)
        populate_banking_accounts(connection)
        populate_contract_cashflows(connection)
        populate_payment_transactions(connection)
        validate_expansion_model(connection)
        summary = validate_business_coverage(connection, config)
        drop_demo_staging_tables(connection)
        return summary


def drop_demo_staging_tables(connection: duckdb.DuckDBPyConnection) -> None:
    for table_name in STAGING_TABLES:
        connection.execute(f"DROP TABLE IF EXISTS {table_name}")


def validate_empty_schema(connection: duckdb.DuckDBPyConnection) -> None:
    existing_tables = {
        row[0]
        for row in connection.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main'
              AND table_type = 'BASE TABLE'
            """
        ).fetchall()
    }

    missing_tables = set(EXPECTED_TABLES) - existing_tables
    if missing_tables:
        formatted_tables = ", ".join(sorted(missing_tables))
        msg = f"Schema initialization incomplete; missing tables: {formatted_tables}"
        raise RuntimeError(msg)

    for table_name in EXPECTED_TABLES:
        row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        if row is None:
            msg = f"Could not count rows for table {table_name}"
            raise RuntimeError(msg)
        row_count = row[0]
        if row_count != 0:
            msg = f"Expected empty table {table_name}, found {row_count} rows"
            raise RuntimeError(msg)


def main() -> None:
    args = parse_args()
    if args.command == "init":
        initialize_database(args.database_path, args.schema_path)
        print(f"Initialized empty DuckDB warehouse at {args.database_path}")
        print(f"Created {len(EXPECTED_TABLES)} tables with keys and metadata comments.")
        return

    if args.command == "demo":
        summary = load_demo_foundation(
            database_path=args.database_path,
            schema_path=args.schema_path,
            scale_name=args.scale,
            seed=args.seed,
        )
        print(f"Loaded foundation dimensions into {args.database_path}")
        print(
            "Populated dim_date, dim_contract_status, dim_cashflow_type, and dim_product "
            f"for scale={args.scale} seed={args.seed}."
        )
        print("Created staging seeds for customers, dealers, vehicles, contracts, and accounts.")
        print("Materialized dim_customer, dim_dealer, dim_vehicle, and both contract facts.")
        print(
            "Expanded status history, banking accounts, contract cashflows, "
            "and payment transactions."
        )
        print(
            "Summary: "
            f"customers={summary['dim_customer_rows']} dealers={summary['dim_dealer_rows']} "
            f"vehicles={summary['dim_vehicle_rows']} leasing={summary['leasing_contract_rows']} "
            f"loans={summary['loan_contract_rows']} accounts={summary['banking_account_rows']} "
            f"cashflows={summary['cashflow_rows']} payments={summary['payment_rows']} "
            f"brands={summary['brand_count']} bmw_group_share={summary['bmw_group_share_pct']}%"
        )
        return

    msg = f"Unsupported command: {args.command}"
    raise ValueError(msg)


if __name__ == "__main__":
    main()
