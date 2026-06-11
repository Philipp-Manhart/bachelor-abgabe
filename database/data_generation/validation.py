from __future__ import annotations

from collections.abc import Mapping

import duckdb

from data_generation.config import GeneratorConfig

SCENARIO_MINIMUMS: dict[str, dict[str, int]] = {
    "dev": {
        "bavaria_corporate_active_leasing": 3,
        "bev_defaults_or_repossessions": 2,
        "high_ltv_independent_loans": 2,
        "refinance_pairs": 2,
        "returned_2023_with_follow_financing": 2,
        "returned_2023_without_follow_financing": 2,
        "dormant_bev_franchise_dealers": 1,
        "active_dealers_without_originations": 2,
        "low_to_high_risk_migration": 2,
        "active_loan_plus_blocked_active_account": 2,
        "overdraft_transition_episodes": 5,
        "three_missed_monthly_rates": 2,
        "late_fee_gt15d": 2,
        "reversed_inflows_target2": 1,
        "reversed_inflows_non_target2": 1,
        "fx_settled_payments": 2,
        "commission_payouts_performing_high_ltv_loans": 2,
    },
    "benchmark": {
        "bavaria_corporate_active_leasing": 50,
        "bev_defaults_or_repossessions": 25,
        "high_ltv_independent_loans": 20,
        "refinance_pairs": 30,
        "returned_2023_with_follow_financing": 10,
        "returned_2023_without_follow_financing": 15,
        "dormant_bev_franchise_dealers": 3,
        "active_dealers_without_originations": 10,
        "low_to_high_risk_migration": 15,
        "active_loan_plus_blocked_active_account": 25,
        "overdraft_transition_episodes": 40,
        "three_missed_monthly_rates": 20,
        "late_fee_gt15d": 25,
        "reversed_inflows_target2": 10,
        "reversed_inflows_non_target2": 10,
        "fx_settled_payments": 30,
        "commission_payouts_performing_high_ltv_loans": 20,
    },
}


def validate_base_dimensions(connection: duckdb.DuckDBPyConnection) -> None:
    expected_non_empty_tables = (
        "dim_date",
        "dim_contract_status",
        "dim_cashflow_type",
        "dim_product",
    )
    for table_name in expected_non_empty_tables:
        row_count = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        if row_count <= 0:
            msg = f"Expected non-empty base dimension {table_name}, found {row_count} rows"
            raise RuntimeError(msg)

    current_products = connection.execute(
        """
        SELECT COUNT(*)
        FROM dim_product
        WHERE product_status_code = 'ACTIVE'
        """
    ).fetchone()[0]
    if current_products <= 0:
        raise RuntimeError("Expected at least one active product in dim_product")

    duplicate_dates = connection.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT full_date
            FROM dim_date
            GROUP BY full_date
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    if duplicate_dates != 0:
        raise RuntimeError(f"dim_date contains {duplicate_dates} duplicate full_date values")


def validate_seed_staging(
    connection: duckdb.DuckDBPyConnection,
    config: GeneratorConfig,
) -> None:
    expected_counts = {
        "stg_customer_seed": config.scale.customers,
        "stg_dealer_seed": config.scale.dealers,
        "stg_vehicle_seed": config.scale.vehicles,
        "stg_contract_seed": config.scale.leasing_contracts + config.scale.loan_contracts,
        "stg_account_seed": config.scale.account_seeds,
    }
    for table_name, expected_count in expected_counts.items():
        actual_count = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        if actual_count != expected_count:
            raise RuntimeError(
                f"Expected {expected_count} rows in {table_name}, found {actual_count}"
            )

    orphan_counts = {
        "customer": connection.execute(
            """
            SELECT COUNT(*)
            FROM stg_contract_seed c
            LEFT JOIN stg_customer_seed s USING (customer_id)
            WHERE s.customer_id IS NULL
            """
        ).fetchone()[0],
        "dealer": connection.execute(
            """
            SELECT COUNT(*)
            FROM stg_contract_seed c
            LEFT JOIN stg_dealer_seed s USING (dealer_id)
            WHERE s.dealer_id IS NULL
            """
        ).fetchone()[0],
        "vehicle": connection.execute(
            """
            SELECT COUNT(*)
            FROM stg_contract_seed c
            LEFT JOIN stg_vehicle_seed s USING (vehicle_id)
            WHERE s.vehicle_id IS NULL
            """
        ).fetchone()[0],
        "product": connection.execute(
            """
            SELECT COUNT(*)
            FROM stg_contract_seed c
            LEFT JOIN dim_product p
              ON c.product_id = p.product_id
            WHERE p.product_id IS NULL
            """
        ).fetchone()[0],
        "account_customer": connection.execute(
            """
            SELECT COUNT(*)
            FROM stg_account_seed a
            LEFT JOIN stg_customer_seed s USING (customer_id)
            WHERE s.customer_id IS NULL
            """
        ).fetchone()[0],
    }
    broken_links = {name: count for name, count in orphan_counts.items() if count != 0}
    if broken_links:
        raise RuntimeError(f"Seed staging contains broken references: {broken_links}")

    reused_vehicles = connection.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT vehicle_id
            FROM stg_contract_seed
            GROUP BY vehicle_id
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    minimum_reused_vehicles = max(1, round(config.scale.vehicles * 0.08))
    if reused_vehicles < minimum_reused_vehicles:
        raise RuntimeError(
            f"Expected at least {minimum_reused_vehicles} reused vehicles, found {reused_vehicles}"
        )

    scenario_contracts = connection.execute(
        """
        SELECT COUNT(*)
        FROM stg_contract_seed
        WHERE scenario_code IS NOT NULL
        """
    ).fetchone()[0]
    if scenario_contracts <= 0:
        raise RuntimeError("Expected at least one explicit contract scenario in stg_contract_seed")


def validate_core_model(
    connection: duckdb.DuckDBPyConnection,
    config: GeneratorConfig,
) -> None:
    expected_fact_counts = {
        "fact_leasing_contracts": config.scale.leasing_contracts,
        "fact_loan_contracts": config.scale.loan_contracts,
        "dim_vehicle": config.scale.vehicles,
    }
    for table_name, expected_count in expected_fact_counts.items():
        actual_count = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        if actual_count != expected_count:
            raise RuntimeError(
                f"Expected {expected_count} rows in {table_name}, found {actual_count}"
            )

    expected_scd_rows = {
        "dim_customer": connection.execute(
            "SELECT SUM(scd_version_target) FROM stg_customer_seed"
        ).fetchone()[0],
        "dim_dealer": connection.execute(
            "SELECT SUM(scd_version_target) FROM stg_dealer_seed"
        ).fetchone()[0],
    }
    for table_name, expected_count in expected_scd_rows.items():
        actual_count = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        if actual_count != expected_count:
            raise RuntimeError(
                f"Expected {expected_count} rows in {table_name}, found {actual_count}"
            )

    duplicate_current_customer = connection.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT customer_id
            FROM dim_customer
            WHERE is_current_record
            GROUP BY customer_id
            HAVING COUNT(*) <> 1
        )
        """
    ).fetchone()[0]
    duplicate_current_dealer = connection.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT dealer_id
            FROM dim_dealer
            WHERE is_current_record
            GROUP BY dealer_id
            HAVING COUNT(*) <> 1
        )
        """
    ).fetchone()[0]
    if duplicate_current_customer or duplicate_current_dealer:
        raise RuntimeError(
            "SCD2 current-record validation failed for customer or dealer dimensions"
        )

    customer_overlap_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM dim_customer a
        JOIN dim_customer b
          ON a.customer_id = b.customer_id
         AND a.customer_sk < b.customer_sk
         AND a.valid_from_date <= COALESCE(b.valid_to_date, DATE '9999-12-31')
         AND b.valid_from_date <= COALESCE(a.valid_to_date, DATE '9999-12-31')
        """
    ).fetchone()[0]
    dealer_overlap_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM dim_dealer a
        JOIN dim_dealer b
          ON a.dealer_id = b.dealer_id
         AND a.dealer_sk < b.dealer_sk
         AND a.valid_from_date <= COALESCE(b.valid_to_date, DATE '9999-12-31')
         AND b.valid_from_date <= COALESCE(a.valid_to_date, DATE '9999-12-31')
        """
    ).fetchone()[0]
    if customer_overlap_count or dealer_overlap_count:
        raise RuntimeError(
            "SCD2 overlap detected: "
            f"customer={customer_overlap_count}, dealer={dealer_overlap_count}"
        )

    unresolved_contract_fks = connection.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM fact_leasing_contracts
              WHERE customer_sk IS NULL OR vehicle_sk IS NULL OR dealer_sk IS NULL
                 OR product_sk IS NULL OR contract_status_sk IS NULL)
          + (SELECT COUNT(*) FROM fact_loan_contracts
              WHERE customer_sk IS NULL OR vehicle_sk IS NULL OR dealer_sk IS NULL
                 OR product_sk IS NULL OR contract_status_sk IS NULL)
        """
    ).fetchone()[0]
    if unresolved_contract_fks != 0:
        raise RuntimeError(
            f"Contract facts contain {unresolved_contract_fks} unresolved foreign keys"
        )

    active_contracts_with_end_date = connection.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM fact_leasing_contracts l
             JOIN dim_contract_status s ON s.contract_status_sk = l.contract_status_sk
             WHERE s.status_code = 'ACTIVE' AND l.actual_end_date_sk IS NOT NULL)
          + (SELECT COUNT(*) FROM fact_loan_contracts l
             JOIN dim_contract_status s ON s.contract_status_sk = l.contract_status_sk
             WHERE s.status_code = 'ACTIVE' AND l.actual_end_date_sk IS NOT NULL)
        """
    ).fetchone()[0]
    if active_contracts_with_end_date != 0:
        raise RuntimeError(
            f"Found {active_contracts_with_end_date} active contracts with actual_end_date_sk"
        )


def validate_expansion_model(connection: duckdb.DuckDBPyConnection) -> None:
    expected_non_empty = (
        "fact_contract_status_history",
        "fact_banking_accounts",
        "fact_contract_cashflows",
        "fact_payment_transactions",
    )
    for table_name in expected_non_empty:
        row_count = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        if row_count <= 0:
            raise RuntimeError(f"Expected non-empty expanded fact table {table_name}")

    current_status_violations = connection.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT COALESCE(
                'L' || leasing_contract_sk::VARCHAR,
                'N' || loan_contract_sk::VARCHAR
            ) AS contract_key
            FROM fact_contract_status_history
            WHERE is_current_status
            GROUP BY 1
            HAVING COUNT(*) <> 1
        )
        """
    ).fetchone()[0]
    if current_status_violations != 0:
        raise RuntimeError(
            "Status history current-row validation failed for "
            f"{current_status_violations} contracts"
        )

    status_overlap_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM fact_contract_status_history a
        JOIN fact_contract_status_history b
          ON COALESCE(
                a.leasing_contract_sk,
                -a.loan_contract_sk
             ) = COALESCE(
                b.leasing_contract_sk,
                -b.loan_contract_sk
             )
         AND a.status_history_sk < b.status_history_sk
         AND a.valid_from_date_sk <= COALESCE(b.valid_to_date_sk, 99991231)
         AND b.valid_from_date_sk <= COALESCE(a.valid_to_date_sk, 99991231)
        """
    ).fetchone()[0]
    if status_overlap_count != 0:
        raise RuntimeError(f"Detected {status_overlap_count} overlapping status history windows")

    status_fact_mismatch = connection.execute(
        """
        SELECT
            (SELECT COUNT(*)
             FROM fact_leasing_contracts l
             JOIN fact_contract_status_history h
               ON h.leasing_contract_sk = l.leasing_contract_sk
              AND h.is_current_status
             WHERE l.contract_status_sk <> h.contract_status_sk)
          + (SELECT COUNT(*)
             FROM fact_loan_contracts l
             JOIN fact_contract_status_history h
               ON h.loan_contract_sk = l.loan_contract_sk
              AND h.is_current_status
             WHERE l.contract_status_sk <> h.contract_status_sk)
        """
    ).fetchone()[0]
    if status_fact_mismatch != 0:
        raise RuntimeError(
            f"Found {status_fact_mismatch} contracts whose current history status "
            "differs from the fact status"
        )

    reversal_reference_errors = connection.execute(
        """
        SELECT COUNT(*)
        FROM fact_payment_transactions
        WHERE is_reversal_flag
          AND reverses_payment_transaction_sk IS NULL
        """
    ).fetchone()[0]
    if reversal_reference_errors != 0:
        raise RuntimeError(
            f"Found {reversal_reference_errors} reversal payments without a "
            "referenced original payment"
        )

    missed_payment_errors = connection.execute(
        """
        SELECT COUNT(*)
        FROM stg_contract_seed s
        JOIN fact_loan_contracts l
          ON l.loan_contract_id = s.contract_id
        JOIN fact_contract_cashflows cf
          ON cf.related_loan_contract_sk = l.loan_contract_sk
        JOIN dim_cashflow_type cft
          ON cft.cashflow_type_sk = cf.cashflow_type_sk
        LEFT JOIN fact_payment_transactions p
          ON p.related_contract_cashflow_sk = cf.contract_cashflow_sk
         AND p.is_reversal_flag = FALSE
        WHERE s.missed_payment_flag
          AND cft.cashflow_type_code = 'LOAN_INSTALLMENT'
          AND cf.installment_number IN (1, 2, 3)
          AND p.payment_transaction_sk IS NOT NULL
        """
    ).fetchone()[0]
    if missed_payment_errors != 0:
        raise RuntimeError(
            f"Found {missed_payment_errors} missed-payment cashflows that still have payment rows"
        )

    blocked_active_accounts = connection.execute(
        """
        SELECT COUNT(*)
        FROM fact_banking_accounts a
        JOIN dim_contract_status s
          ON s.contract_status_sk = a.contract_status_sk
        WHERE s.status_code = 'ACTIVE'
          AND a.blocked_amount_effective > 0
        """
    ).fetchone()[0]
    if blocked_active_accounts <= 0:
        raise RuntimeError(
            "Expected at least one active banking account snapshot with blocked amount"
        )


def validate_business_coverage(
    connection: duckdb.DuckDBPyConnection,
    config: GeneratorConfig,
) -> dict[str, int]:
    summary = collect_generation_summary(connection)
    thresholds = SCENARIO_MINIMUMS[config.scale.name]

    failures = {
        metric: (summary[metric], minimum)
        for metric, minimum in thresholds.items()
        if summary[metric] < minimum
    }
    if failures:
        raise RuntimeError(
            f"Scenario coverage below threshold for scale={config.scale.name}: {failures}"
        )

    required_flags = {
        "brand_count": 5,
        "current_retail_customers": 1,
        "current_corporate_customers": 1,
        "active_german_dealers": 1,
        "bev_vehicle_count": 1,
        "overdraft_account_count": 1,
        "avg_balance_30d_rows": 1,
        "franchise_bev_leasing": 1,
        "dealer_without_contracts": 1,
        "historized_customer_keys": 1,
        "historized_dealer_keys": 1,
        "cashflow_rows": 1,
        "payment_rows": 1,
        "reversal_rows": 1,
        "returned_vehicle_rows": 1,
    }
    missing = {
        metric: (summary[metric], minimum)
        for metric, minimum in required_flags.items()
        if summary[metric] < minimum
    }
    if missing:
        raise RuntimeError(f"Query coverage check failed for scale={config.scale.name}: {missing}")

    if summary["bmw_group_share_pct"] < 80:
        raise RuntimeError(f"BMW Group portfolio share too low: {summary['bmw_group_share_pct']}%")

    return summary


def collect_generation_summary(connection: duckdb.DuckDBPyConnection) -> dict[str, int]:
    summary_queries: Mapping[str, str] = {
        "dim_customer_rows": "SELECT COUNT(*) FROM dim_customer",
        "dim_dealer_rows": "SELECT COUNT(*) FROM dim_dealer",
        "dim_vehicle_rows": "SELECT COUNT(*) FROM dim_vehicle",
        "leasing_contract_rows": "SELECT COUNT(*) FROM fact_leasing_contracts",
        "loan_contract_rows": "SELECT COUNT(*) FROM fact_loan_contracts",
        "status_history_rows": "SELECT COUNT(*) FROM fact_contract_status_history",
        "banking_account_rows": "SELECT COUNT(*) FROM fact_banking_accounts",
        "cashflow_rows": "SELECT COUNT(*) FROM fact_contract_cashflows",
        "payment_rows": "SELECT COUNT(*) FROM fact_payment_transactions",
        "current_retail_customers": """
            SELECT COUNT(*)
            FROM dim_customer
            WHERE is_current_record
              AND customer_type_code = 'Retail'
        """,
        "current_corporate_customers": """
            SELECT COUNT(*)
            FROM dim_customer
            WHERE is_current_record
              AND customer_type_code = 'Corporate'
        """,
        "active_german_dealers": """
            SELECT COUNT(*)
            FROM dim_dealer
            WHERE is_current_record
              AND country_code = 'DE'
              AND dealer_status_code = 'Active'
        """,
        "brand_count": "SELECT COUNT(DISTINCT brand_name) FROM dim_vehicle",
        "bev_vehicle_count": "SELECT COUNT(*) FROM dim_vehicle WHERE fuel_type_code = 'BEV'",
        "overdraft_account_count": """
            SELECT COUNT(DISTINCT banking_account_id)
            FROM fact_banking_accounts
            WHERE authorized_overdraft_limit_net > 0
        """,
        "avg_balance_30d_rows": """
            SELECT COUNT(*)
            FROM fact_banking_accounts
            WHERE average_balance_30d_net IS NOT NULL
        """,
        "historized_customer_keys": """
            SELECT COUNT(*)
            FROM (
                SELECT customer_id
                FROM dim_customer
                GROUP BY customer_id
                HAVING COUNT(*) > 1
            )
        """,
        "historized_dealer_keys": """
            SELECT COUNT(*)
            FROM (
                SELECT dealer_id
                FROM dim_dealer
                GROUP BY dealer_id
                HAVING COUNT(*) > 1
            )
        """,
        "franchise_bev_leasing": """
            SELECT COUNT(*)
            FROM fact_leasing_contracts l
            JOIN dim_vehicle v ON v.vehicle_sk = l.vehicle_sk
            JOIN dim_dealer d ON d.dealer_sk = l.dealer_sk
            WHERE v.fuel_type_code = 'BEV'
              AND d.dealer_type_code = 'Franchise'
        """,
        "dealer_without_contracts": """
            SELECT COUNT(*)
            FROM stg_dealer_seed d
            LEFT JOIN stg_contract_seed c
              ON c.dealer_id = d.dealer_id
            WHERE c.contract_id IS NULL
        """,
        "reversal_rows": "SELECT COUNT(*) FROM fact_payment_transactions WHERE is_reversal_flag",
        "returned_vehicle_rows": """
            SELECT COUNT(DISTINCT vehicle_id)
            FROM stg_contract_seed
            WHERE scenario_code IN ('LEASE_RETURN_2023_WITH_REUSE', 'LEASE_RETURN_2023_NO_FOLLOWUP')
        """,
        "bavaria_corporate_active_leasing": """
            SELECT COUNT(*)
            FROM stg_contract_seed
            WHERE scenario_code = 'BAVARIA_CORPORATE_ACTIVE_LEASING'
        """,
        "bev_defaults_or_repossessions": """
            SELECT COUNT(*)
            FROM stg_contract_seed s
            JOIN stg_vehicle_seed v USING(vehicle_id)
            WHERE v.fuel_type_code = 'BEV'
              AND s.target_status_code IN ('DEFAULT', 'REPOSSESSED')
        """,
        "high_ltv_independent_loans": """
            SELECT COUNT(*)
            FROM stg_contract_seed s
            JOIN stg_dealer_seed d USING(dealer_id)
            WHERE s.contract_type_code = 'LOAN'
              AND s.high_ltv_flag
              AND d.dealer_type_code = 'Independent'
        """,
        "refinance_pairs": "SELECT COUNT(*) FROM stg_contract_seed WHERE refinance_flag",
        "returned_2023_with_follow_financing": """
            WITH returned AS (
                SELECT DISTINCT vehicle_id
                FROM stg_contract_seed
                WHERE scenario_code = 'LEASE_RETURN_2023_WITH_REUSE'
            ),
            followup AS (
                SELECT DISTINCT vehicle_id
                FROM stg_contract_seed
                WHERE scenario_code = 'SAME_MODEL_REFINANCING'
            )
            SELECT COUNT(*)
            FROM returned
            WHERE vehicle_id IN (SELECT vehicle_id FROM followup)
        """,
        "returned_2023_without_follow_financing": """
            SELECT COUNT(DISTINCT vehicle_id)
            FROM stg_contract_seed
            WHERE scenario_code = 'LEASE_RETURN_2023_NO_FOLLOWUP'
        """,
        "dormant_bev_franchise_dealers": """
            SELECT COUNT(*)
            FROM stg_dealer_seed
            WHERE scenario_code = 'DORMANT_FRANCHISE_BEV_DEALER'
        """,
        "active_dealers_without_originations": """
            SELECT COUNT(*)
            FROM stg_dealer_seed
            WHERE scenario_code = 'ACTIVE_WITHOUT_ORIGINATIONS'
        """,
        "low_to_high_risk_migration": """
            WITH first_loan AS (
                SELECT customer_id, MIN(booking_date) AS booking_date
                FROM stg_contract_seed
                WHERE contract_type_code = 'LOAN'
                GROUP BY 1
            ),
            loan_risk AS (
                SELECT fl.customer_id, dc.risk_class_code
                FROM first_loan fl
                JOIN dim_customer dc
                  ON dc.customer_id = fl.customer_id
                 AND fl.booking_date BETWEEN dc.valid_from_date
                                        AND COALESCE(dc.valid_to_date, DATE '9999-12-31')
            ),
            first_account AS (
                SELECT a.customer_id, MIN(d.full_date) AS snapshot_date
                FROM stg_account_seed a
                JOIN fact_banking_accounts f USING (banking_account_id)
                JOIN dim_date d ON d.date_sk = f.snapshot_date_sk
                GROUP BY 1
            ),
            account_risk AS (
                SELECT fa.customer_id, dc.risk_class_code
                FROM first_account fa
                JOIN dim_customer dc
                  ON dc.customer_id = fa.customer_id
                 AND fa.snapshot_date BETWEEN dc.valid_from_date
                                         AND COALESCE(dc.valid_to_date, DATE '9999-12-31')
            )
            SELECT COUNT(*)
            FROM loan_risk l
            JOIN account_risk a USING(customer_id)
            WHERE l.risk_class_code = 'LOW'
              AND a.risk_class_code = 'HIGH'
        """,
        "active_loan_plus_blocked_active_account": """
            SELECT COUNT(DISTINCT loan_customer.customer_id)
            FROM fact_loan_contracts l
            JOIN dim_contract_status ls ON ls.contract_status_sk = l.contract_status_sk
            JOIN dim_customer loan_customer ON loan_customer.customer_sk = l.customer_sk
            JOIN fact_banking_accounts a ON TRUE
            JOIN dim_customer account_customer ON account_customer.customer_sk = a.customer_sk
            JOIN dim_contract_status account_status
              ON account_status.contract_status_sk = a.contract_status_sk
            WHERE ls.status_code = 'ACTIVE'
              AND account_customer.customer_id = loan_customer.customer_id
              AND account_status.status_code = 'ACTIVE'
              AND a.blocked_amount_effective > 0
        """,
        "overdraft_transition_episodes": """
            WITH seq AS (
                SELECT
                    banking_account_id,
                    available_balance_effective,
                    LAG(available_balance_effective) OVER (
                        PARTITION BY banking_account_id
                        ORDER BY snapshot_date_sk
                    ) AS prev_balance
                FROM fact_banking_accounts
            )
            SELECT COUNT(*)
            FROM seq
            WHERE prev_balance >= 0
              AND available_balance_effective < 0
        """,
        "three_missed_monthly_rates": """
            SELECT COUNT(*)
            FROM stg_contract_seed
            WHERE scenario_code = 'THREE_MISSED_INSTALLMENTS'
        """,
        "late_fee_gt15d": """
            SELECT COUNT(*)
            FROM fact_payment_transactions
            WHERE transaction_type_code = 'LATE_FEE_COLLECTION'
        """,
        "reversed_inflows_target2": """
            SELECT COUNT(*)
            FROM fact_payment_transactions p
            JOIN dim_date d ON d.date_sk = p.transaction_date_sk
            WHERE p.is_reversal_flag
              AND d.target2_business_day_flag
        """,
        "reversed_inflows_non_target2": """
            SELECT COUNT(*)
            FROM fact_payment_transactions p
            JOIN dim_date d ON d.date_sk = p.transaction_date_sk
            WHERE p.is_reversal_flag
              AND NOT d.target2_business_day_flag
        """,
        "fx_settled_payments": """
            SELECT COUNT(*)
            FROM fact_payment_transactions
            WHERE transaction_type_code = 'FX_SETTLEMENT'
        """,
        "commission_payouts_performing_high_ltv_loans": """
            SELECT COUNT(*)
            FROM fact_payment_transactions p
            JOIN fact_loan_contracts l ON l.loan_contract_sk = p.related_loan_contract_sk
            JOIN stg_contract_seed s ON s.contract_id = l.loan_contract_id
            JOIN dim_contract_status ds ON ds.contract_status_sk = l.contract_status_sk
            WHERE p.transaction_type_code = 'COMMISSION_PAYOUT'
              AND s.high_ltv_flag
              AND ds.status_code = 'ACTIVE'
        """,
        "bmw_group_share_pct": """
            SELECT CAST(
                ROUND(
                    100.0
                    * SUM(
                        CASE
                            WHEN brand_name IN ('BMW', 'MINI', 'Rolls-Royce')
                                THEN 1
                            ELSE 0
                        END
                    )
                    / COUNT(*),
                    2
                ) AS INTEGER
            )
            FROM dim_vehicle
        """,
    }
    return {
        metric: int(connection.execute(query).fetchone()[0] or 0)
        for metric, query in summary_queries.items()
    }
