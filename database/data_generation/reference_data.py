from __future__ import annotations

from collections.abc import Sequence
from dataclasses import astuple, dataclass

import duckdb


@dataclass(frozen=True, slots=True)
class ContractStatus:
    contract_status_sk: int
    status_code: str
    status_name: str
    status_group_code: str
    lifecycle_stage_code: str
    is_active_flag: bool
    is_signed_flag: bool
    is_disbursed_flag: bool
    is_performing_flag: bool
    is_delinquent_flag: bool
    is_defaulted_flag: bool
    is_closed_flag: bool
    is_cancelled_flag: bool
    is_restructured_flag: bool
    is_repossessed_flag: bool
    dpd_bucket_min: int | None
    dpd_bucket_max: int | None
    collection_stage_code: str | None


@dataclass(frozen=True, slots=True)
class CashflowType:
    cashflow_type_sk: int
    cashflow_type_code: str
    cashflow_type_name: str
    cashflow_class_code: str
    cashflow_party_role_code: str
    is_inflow_flag: bool
    is_customer_cashflow_flag: bool
    is_dealer_cashflow_flag: bool
    is_vehicle_cost_flag: bool
    is_principal_component_flag: bool
    is_interest_component_flag: bool
    is_fee_component_flag: bool
    is_tax_relevant_flag: bool
    is_recurring_flag: bool
    is_planned_flag: bool


@dataclass(frozen=True, slots=True)
class Product:
    product_sk: int
    product_id: str
    product_family_code: str
    product_type_code: str
    product_name: str
    currency_code: str
    market_country_code: str
    min_term_months: int | None
    max_term_months: int | None
    regulatory_product_class_code: str | None
    residual_value_policy_code: str | None
    balloon_payment_allowed_flag: bool
    early_termination_allowed_flag: bool
    insurance_bundle_flag: bool
    maintenance_bundle_flag: bool
    product_status_code: str
    catalog_launch_date: str
    catalog_phase_out_date: str | None


CONTRACT_STATUSES: tuple[ContractStatus, ...] = (
    ContractStatus(
        1,
        "APPLICATION",
        "Application",
        "PIPELINE",
        "PRE_ORIGINATION",
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        None,
        None,
        None,
    ),
    ContractStatus(
        2,
        "APPROVED",
        "Approved",
        "PIPELINE",
        "PRE_ORIGINATION",
        False,
        True,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        None,
        None,
        None,
    ),
    ContractStatus(
        3,
        "ACTIVE",
        "Active",
        "ACTIVE",
        "BOOKED",
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
        False,
        False,
        0,
        0,
        "NONE",
    ),
    ContractStatus(
        4,
        "LATE_1_30",
        "Late 1-30 DPD",
        "DELINQUENT",
        "SERVICING",
        True,
        True,
        True,
        False,
        True,
        False,
        False,
        False,
        False,
        False,
        1,
        30,
        "SOFT_COLLECTION",
    ),
    ContractStatus(
        5,
        "LATE_31_60",
        "Late 31-60 DPD",
        "DELINQUENT",
        "SERVICING",
        True,
        True,
        True,
        False,
        True,
        False,
        False,
        False,
        False,
        False,
        31,
        60,
        "HARD_COLLECTION",
    ),
    ContractStatus(
        6,
        "DEFAULT",
        "Default",
        "DEFAULT",
        "WORKOUT",
        False,
        True,
        True,
        False,
        False,
        True,
        False,
        False,
        False,
        False,
        61,
        None,
        "WORKOUT",
    ),
    ContractStatus(
        7,
        "RESTRUCTURED",
        "Restructured",
        "ACTIVE",
        "WORKOUT",
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
        True,
        False,
        0,
        0,
        "REMEDIATION",
    ),
    ContractStatus(
        8,
        "CLOSED",
        "Closed",
        "CLOSED",
        "CLOSED",
        False,
        True,
        True,
        False,
        False,
        False,
        True,
        False,
        False,
        False,
        0,
        0,
        "NONE",
    ),
    ContractStatus(
        9,
        "CANCELLED",
        "Cancelled",
        "CLOSED",
        "CLOSED",
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        True,
        False,
        False,
        None,
        None,
        "NONE",
    ),
    ContractStatus(
        10,
        "REPOSSESSED",
        "Repossessed",
        "DEFAULT",
        "WORKOUT",
        False,
        True,
        True,
        False,
        False,
        True,
        False,
        False,
        False,
        True,
        61,
        None,
        "ASSET_RECOVERY",
    ),
)

CASHFLOW_TYPES: tuple[CashflowType, ...] = (
    CashflowType(
        1,
        "DOWN_PAYMENT",
        "Down Payment",
        "UPFRONT",
        "CUSTOMER",
        True,
        True,
        False,
        False,
        True,
        False,
        False,
        True,
        False,
        True,
    ),
    CashflowType(
        2,
        "LEASE_INSTALLMENT",
        "Lease Installment",
        "INSTALLMENT",
        "CUSTOMER",
        True,
        True,
        False,
        False,
        True,
        True,
        False,
        True,
        True,
        True,
    ),
    CashflowType(
        3,
        "LOAN_INSTALLMENT",
        "Loan Installment",
        "INSTALLMENT",
        "CUSTOMER",
        True,
        True,
        False,
        False,
        True,
        True,
        False,
        True,
        True,
        True,
    ),
    CashflowType(
        4,
        "BALLOON_PAYMENT",
        "Balloon Payment",
        "MATURITY",
        "CUSTOMER",
        True,
        True,
        False,
        False,
        True,
        False,
        False,
        True,
        False,
        True,
    ),
    CashflowType(
        5,
        "DEALER_SUBSIDY",
        "Dealer Subsidy",
        "DEALER",
        "DEALER",
        True,
        False,
        True,
        False,
        False,
        False,
        True,
        False,
        False,
        True,
    ),
    CashflowType(
        6,
        "VEHICLE_PURCHASE",
        "Vehicle Purchase",
        "ASSET",
        "BANK",
        False,
        False,
        False,
        True,
        True,
        False,
        False,
        True,
        False,
        True,
    ),
    CashflowType(
        7,
        "ACCOUNT_FEE",
        "Account Fee",
        "FEE",
        "CUSTOMER",
        True,
        True,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        True,
    ),
    CashflowType(
        8,
        "INTEREST_CHARGE",
        "Interest Charge",
        "INTEREST",
        "CUSTOMER",
        True,
        True,
        False,
        False,
        False,
        True,
        False,
        True,
        True,
        True,
    ),
    CashflowType(
        9,
        "REVERSAL",
        "Reversal",
        "ADJUSTMENT",
        "BANK",
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
    ),
)

PRODUCTS: tuple[Product, ...] = (
    Product(
        1,
        "LEASE_CLASSIC_DE",
        "LEASING",
        "CLOSED_END_LEASE",
        "BMW Classic Lease DE",
        "EUR",
        "DE",
        24,
        60,
        "CONSUMER_FINANCE",
        "STANDARD_RV",
        False,
        True,
        True,
        True,
        "ACTIVE",
        "2019-01-01",
        None,
    ),
    Product(
        2,
        "LEASE_FLEET_DE",
        "LEASING",
        "FLEET_LEASE",
        "BMW Fleet Lease DE",
        "EUR",
        "DE",
        24,
        60,
        "COMMERCIAL_FINANCE",
        "FLEET_RV",
        False,
        True,
        True,
        True,
        "ACTIVE",
        "2019-01-01",
        None,
    ),
    Product(
        3,
        "LOAN_CLASSIC_DE",
        "LOAN",
        "INSTALLMENT_LOAN",
        "BMW Installment Loan DE",
        "EUR",
        "DE",
        12,
        84,
        "CONSUMER_FINANCE",
        None,
        True,
        True,
        False,
        False,
        "ACTIVE",
        "2018-01-01",
        None,
    ),
    Product(
        4,
        "LOAN_BALLOON_DE",
        "LOAN",
        "BALLOON_LOAN",
        "BMW Select Balloon Loan DE",
        "EUR",
        "DE",
        24,
        72,
        "CONSUMER_FINANCE",
        None,
        True,
        True,
        False,
        False,
        "ACTIVE",
        "2018-01-01",
        None,
    ),
    Product(
        5,
        "ACCOUNT_CURRENT_DE",
        "ACCOUNT",
        "CURRENT_ACCOUNT",
        "BMW Bank Current Account DE",
        "EUR",
        "DE",
        None,
        None,
        "DEPOSIT",
        None,
        False,
        False,
        False,
        False,
        "ACTIVE",
        "2020-01-01",
        None,
    ),
    Product(
        6,
        "ACCOUNT_BUSINESS_DE",
        "ACCOUNT",
        "BUSINESS_ACCOUNT",
        "BMW Bank Business Account DE",
        "EUR",
        "DE",
        None,
        None,
        "DEPOSIT",
        None,
        False,
        False,
        False,
        False,
        "ACTIVE",
        "2021-01-01",
        None,
    ),
)


def load_reference_data(connection: duckdb.DuckDBPyConnection) -> None:
    _replace_contract_statuses(connection, CONTRACT_STATUSES)
    _replace_cashflow_types(connection, CASHFLOW_TYPES)
    _replace_products(connection, PRODUCTS)


def _replace_contract_statuses(
    connection: duckdb.DuckDBPyConnection,
    rows: Sequence[ContractStatus],
) -> None:
    connection.execute("DELETE FROM dim_contract_status")
    connection.executemany(
        """
        INSERT INTO dim_contract_status
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [astuple(row) for row in rows],
    )


def _replace_cashflow_types(
    connection: duckdb.DuckDBPyConnection,
    rows: Sequence[CashflowType],
) -> None:
    connection.execute("DELETE FROM dim_cashflow_type")
    connection.executemany(
        """
        INSERT INTO dim_cashflow_type VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [astuple(row) for row in rows],
    )


def _replace_products(
    connection: duckdb.DuckDBPyConnection,
    rows: Sequence[Product],
) -> None:
    connection.execute("DELETE FROM dim_product")
    connection.executemany(
        """
        INSERT INTO dim_product VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [astuple(row) for row in rows],
    )
