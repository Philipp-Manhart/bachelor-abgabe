from __future__ import annotations

import duckdb

COMMON_ACCOUNT_CTE = """
WITH preferred_accounts AS (
    SELECT
        banking_account_id,
        customer_id,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY banking_account_id
        ) AS rn
    FROM stg_account_seed
),
selected_accounts AS (
    SELECT banking_account_id, customer_id
    FROM preferred_accounts
    WHERE rn = 1
)
"""


def populate_contract_cashflows(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute("DELETE FROM fact_contract_cashflows")
    connection.execute("DROP TABLE IF EXISTS tmp_contract_cashflow_raw")
    connection.execute(
        """
        CREATE TEMP TABLE tmp_contract_cashflow_raw (
            synthetic_key VARCHAR,
            contract_cashflow_id VARCHAR,
            cashflow_type_code VARCHAR,
            customer_sk BIGINT,
            vehicle_sk BIGINT,
            dealer_sk BIGINT,
            product_sk BIGINT,
            contract_status_sk BIGINT,
            due_date DATE,
            related_leasing_contract_sk BIGINT,
            related_loan_contract_sk BIGINT,
            banking_account_id VARCHAR,
            cashflow_sequence_number INTEGER,
            installment_number INTEGER,
            amount_net DECIMAL(18, 2),
            amount_gross DECIMAL(18, 2),
            tax_amount_gross DECIMAL(18, 2),
            principal_component_net DECIMAL(18, 2),
            interest_component_nominal DECIMAL(18, 2),
            interest_component_gross DECIMAL(18, 2),
            fee_component_net DECIMAL(18, 2),
            commission_amount_net DECIMAL(18, 2),
            residual_value_component_effective DECIMAL(18, 2),
            currency_code VARCHAR
        )
        """
    )

    leasing_base = """
    , leasing_base AS (
        SELECT
            l.leasing_contract_sk,
            l.leasing_contract_id AS contract_id,
            l.customer_sk,
            l.vehicle_sk,
            l.dealer_sk,
            l.product_sk,
            l.contract_status_sk,
            ds.full_date AS start_date,
            dm.full_date AS maturity_date,
            l.contract_term_months,
            l.financed_amount_net,
            l.financed_amount_gross,
            l.down_payment_gross,
            l.monthly_payment_net,
            l.monthly_payment_gross,
            l.residual_value_nominal,
            l.service_fee_net,
            l.insurance_fee_gross,
            selected_accounts.banking_account_id
        FROM fact_leasing_contracts AS l
        JOIN dim_date AS ds ON ds.date_sk = l.contract_start_date_sk
        JOIN dim_date AS dm ON dm.date_sk = l.maturity_date_sk
        JOIN stg_contract_seed AS s ON s.contract_id = l.leasing_contract_id
        LEFT JOIN selected_accounts
          ON selected_accounts.customer_id = s.customer_id
    )
    """

    loan_base = """
    , loan_base AS (
        SELECT
            l.loan_contract_sk,
            l.loan_contract_id AS contract_id,
            l.customer_sk,
            l.vehicle_sk,
            l.dealer_sk,
            l.product_sk,
            l.contract_status_sk,
            ds.full_date AS start_date,
            dm.full_date AS maturity_date,
            l.loan_term_months,
            l.financed_amount_net,
            l.financed_amount_gross,
            l.down_payment_gross,
            l.monthly_installment_net,
            l.monthly_installment_gross,
            l.balloon_payment_nominal,
            selected_accounts.banking_account_id
        FROM fact_loan_contracts AS l
        JOIN dim_date AS ds ON ds.date_sk = l.origination_date_sk
        JOIN dim_date AS dm ON dm.date_sk = l.maturity_date_sk
        JOIN stg_contract_seed AS s ON s.contract_id = l.loan_contract_id
        LEFT JOIN selected_accounts
          ON selected_accounts.customer_id = s.customer_id
    )
    """

    connection.execute(
        COMMON_ACCOUNT_CTE
        + leasing_base
        + """
        INSERT INTO tmp_contract_cashflow_raw
        SELECT
            'DP-' || contract_id,
            contract_id || '-DOWN',
            'DOWN_PAYMENT',
            customer_sk,
            vehicle_sk,
            dealer_sk,
            product_sk,
            contract_status_sk,
            start_date,
            leasing_contract_sk,
            NULL,
            banking_account_id,
            1,
            NULL,
            ROUND(down_payment_gross / 1.19, 2),
            down_payment_gross,
            ROUND(down_payment_gross - down_payment_gross / 1.19, 2),
            ROUND(down_payment_gross / 1.19, 2),
            0,
            0,
            0,
            0,
            0,
            'EUR'
        FROM leasing_base
        """
    )
    connection.execute(
        COMMON_ACCOUNT_CTE
        + leasing_base
        + """
        INSERT INTO tmp_contract_cashflow_raw
        SELECT
            'LS-' || contract_id || '-' || installment_n::VARCHAR,
            contract_id || '-LEASE-' || LPAD(installment_n::VARCHAR, 3, '0'),
            'LEASE_INSTALLMENT',
            customer_sk,
            vehicle_sk,
            dealer_sk,
            product_sk,
            contract_status_sk,
            (start_date + installment_n * INTERVAL 1 MONTH)::DATE,
            leasing_contract_sk,
            NULL,
            banking_account_id,
            installment_n + 1,
            installment_n,
            monthly_payment_net,
            monthly_payment_gross,
            ROUND(monthly_payment_gross - monthly_payment_net, 2),
            ROUND(monthly_payment_net * 0.78, 2),
            ROUND(monthly_payment_net * 0.22, 2),
            ROUND(monthly_payment_gross - monthly_payment_net, 2),
            0,
            0,
            0,
            'EUR'
        FROM leasing_base
        CROSS JOIN generate_series(1, contract_term_months) AS gs(installment_n)
        """
    )
    connection.execute(
        COMMON_ACCOUNT_CTE
        + leasing_base
        + """
        INSERT INTO tmp_contract_cashflow_raw
        SELECT
            'LR-' || contract_id,
            contract_id || '-RESIDUAL',
            'BALLOON_PAYMENT',
            customer_sk,
            vehicle_sk,
            dealer_sk,
            product_sk,
            contract_status_sk,
            maturity_date,
            leasing_contract_sk,
            NULL,
            banking_account_id,
            contract_term_months + 2,
            contract_term_months + 1,
            ROUND(residual_value_nominal / 1.19, 2),
            residual_value_nominal,
            ROUND(residual_value_nominal - residual_value_nominal / 1.19, 2),
            ROUND(residual_value_nominal / 1.19, 2),
            0,
            0,
            0,
            0,
            residual_value_nominal,
            'EUR'
        FROM leasing_base
        WHERE residual_value_nominal IS NOT NULL
        """
    )
    connection.execute(
        COMMON_ACCOUNT_CTE
        + leasing_base
        + """
        INSERT INTO tmp_contract_cashflow_raw
        SELECT
            'LF-' || contract_id,
            contract_id || '-SERVICE',
            'ACCOUNT_FEE',
            customer_sk,
            vehicle_sk,
            dealer_sk,
            product_sk,
            contract_status_sk,
            (start_date + INTERVAL 1 MONTH)::DATE,
            leasing_contract_sk,
            NULL,
            banking_account_id,
            contract_term_months + 3,
            NULL,
            service_fee_net,
            ROUND(service_fee_net * 1.19, 2),
            ROUND(service_fee_net * 0.19, 2),
            0,
            0,
            0,
            service_fee_net,
            0,
            0,
            'EUR'
        FROM leasing_base
        """
    )
    connection.execute(
        COMMON_ACCOUNT_CTE
        + leasing_base
        + """
        INSERT INTO tmp_contract_cashflow_raw
        SELECT
            'LI-' || contract_id,
            contract_id || '-INSURANCE',
            'ACCOUNT_FEE',
            customer_sk,
            vehicle_sk,
            dealer_sk,
            product_sk,
            contract_status_sk,
            (start_date + INTERVAL 2 MONTH)::DATE,
            leasing_contract_sk,
            NULL,
            banking_account_id,
            contract_term_months + 4,
            NULL,
            ROUND(insurance_fee_gross / 1.19, 2),
            insurance_fee_gross,
            ROUND(insurance_fee_gross - insurance_fee_gross / 1.19, 2),
            0,
            0,
            0,
            ROUND(insurance_fee_gross / 1.19, 2),
            0,
            0,
            'EUR'
        FROM leasing_base
        """
    )

    connection.execute(
        COMMON_ACCOUNT_CTE
        + loan_base
        + """
        INSERT INTO tmp_contract_cashflow_raw
        SELECT
            'DP-' || contract_id,
            contract_id || '-DOWN',
            'DOWN_PAYMENT',
            customer_sk,
            vehicle_sk,
            dealer_sk,
            product_sk,
            contract_status_sk,
            start_date,
            NULL,
            loan_contract_sk,
            banking_account_id,
            1,
            NULL,
            ROUND(down_payment_gross / 1.19, 2),
            down_payment_gross,
            ROUND(down_payment_gross - down_payment_gross / 1.19, 2),
            ROUND(down_payment_gross / 1.19, 2),
            0,
            0,
            0,
            0,
            0,
            'EUR'
        FROM loan_base
        """
    )
    connection.execute(
        COMMON_ACCOUNT_CTE
        + loan_base
        + """
        INSERT INTO tmp_contract_cashflow_raw
        SELECT
            'LN-' || contract_id || '-' || installment_n::VARCHAR,
            contract_id || '-LOAN-' || LPAD(installment_n::VARCHAR, 3, '0'),
            'LOAN_INSTALLMENT',
            customer_sk,
            vehicle_sk,
            dealer_sk,
            product_sk,
            contract_status_sk,
            (start_date + installment_n * INTERVAL 1 MONTH)::DATE,
            NULL,
            loan_contract_sk,
            banking_account_id,
            installment_n + 1,
            installment_n,
            monthly_installment_net,
            monthly_installment_gross,
            ROUND(monthly_installment_gross - monthly_installment_net, 2),
            ROUND(
                monthly_installment_net
                * GREATEST(0.35, 1 - (installment_n::DOUBLE / loan_term_months)),
                2
            ),
            ROUND(
                monthly_installment_net
                * LEAST(0.65, installment_n::DOUBLE / loan_term_months),
                2
            ),
            ROUND(monthly_installment_gross - monthly_installment_net, 2),
            0,
            0,
            0,
            'EUR'
        FROM loan_base
        CROSS JOIN generate_series(1, loan_term_months) AS gs(installment_n)
        """
    )
    connection.execute(
        COMMON_ACCOUNT_CTE
        + loan_base
        + """
        INSERT INTO tmp_contract_cashflow_raw
        SELECT
            'LB-' || contract_id,
            contract_id || '-BALLOON',
            'BALLOON_PAYMENT',
            customer_sk,
            vehicle_sk,
            dealer_sk,
            product_sk,
            contract_status_sk,
            maturity_date,
            NULL,
            loan_contract_sk,
            banking_account_id,
            loan_term_months + 2,
            loan_term_months + 1,
            ROUND(balloon_payment_nominal / 1.19, 2),
            balloon_payment_nominal,
            ROUND(balloon_payment_nominal - balloon_payment_nominal / 1.19, 2),
            ROUND(balloon_payment_nominal / 1.19, 2),
            0,
            0,
            0,
            0,
            balloon_payment_nominal,
            'EUR'
        FROM loan_base
        WHERE balloon_payment_nominal IS NOT NULL
        """
    )
    connection.execute(
        COMMON_ACCOUNT_CTE
        + loan_base
        + """
        INSERT INTO tmp_contract_cashflow_raw
        SELECT
            'LC-' || contract_id,
            contract_id || '-COMMISSION',
            'DEALER_SUBSIDY',
            customer_sk,
            vehicle_sk,
            dealer_sk,
            product_sk,
            contract_status_sk,
            (start_date + INTERVAL 3 DAY)::DATE,
            NULL,
            loan_contract_sk,
            banking_account_id,
            loan_term_months + 3,
            NULL,
            ROUND(financed_amount_net * 0.012, 2),
            ROUND(financed_amount_net * 0.012, 2),
            0,
            0,
            0,
            0,
            0,
            ROUND(financed_amount_net * 0.012, 2),
            0,
            'EUR'
        FROM loan_base
        """
    )

    connection.execute(
        """
        INSERT INTO fact_contract_cashflows
        SELECT
            ROW_NUMBER() OVER (ORDER BY contract_cashflow_id) AS contract_cashflow_sk,
            contract_cashflow_id,
            cft.cashflow_type_sk,
            raw.customer_sk,
            raw.vehicle_sk,
            raw.dealer_sk,
            raw.product_sk,
            raw.contract_status_sk,
            CAST(strftime(raw.due_date, '%Y%m%d') AS INTEGER) AS due_date_sk,
            raw.related_leasing_contract_sk,
            raw.related_loan_contract_sk,
            ba.banking_account_sk AS related_banking_account_sk,
            raw.cashflow_sequence_number,
            raw.installment_number,
            raw.amount_net,
            raw.amount_gross,
            raw.tax_amount_gross,
            raw.principal_component_net,
            raw.interest_component_nominal,
            raw.interest_component_gross,
            raw.fee_component_net,
            raw.commission_amount_net,
            raw.residual_value_component_effective,
            raw.currency_code
        FROM tmp_contract_cashflow_raw AS raw
        JOIN dim_cashflow_type AS cft
          ON cft.cashflow_type_code = raw.cashflow_type_code
        LEFT JOIN fact_banking_accounts AS ba
          ON ba.banking_account_id = raw.banking_account_id
         AND ba.snapshot_date_sk = CAST(strftime(raw.due_date, '%Y%m%d') AS INTEGER)
        WHERE raw.due_date <= DATE '2026-12-31'
        ORDER BY contract_cashflow_id
        """
    )
    connection.execute("DROP TABLE IF EXISTS tmp_contract_cashflow_raw")
