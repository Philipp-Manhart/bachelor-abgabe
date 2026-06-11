from __future__ import annotations

import duckdb


def populate_payment_transactions(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute("DELETE FROM fact_payment_transactions")
    connection.execute("DROP TABLE IF EXISTS tmp_payment_raw")
    connection.execute(
        """
        CREATE TEMP TABLE tmp_payment_raw (
            synthetic_key VARCHAR,
            payment_transaction_id VARCHAR,
            customer_sk BIGINT,
            cashflow_type_sk BIGINT,
            product_sk BIGINT,
            contract_status_sk BIGINT,
            transaction_date DATE,
            value_date DATE,
            booking_date DATE,
            related_leasing_contract_sk BIGINT,
            related_loan_contract_sk BIGINT,
            related_banking_account_sk BIGINT,
            related_contract_cashflow_sk BIGINT,
            reverse_of_key VARCHAR,
            transaction_type_code VARCHAR,
            transaction_channel_code VARCHAR,
            counterparty_country_code VARCHAR,
            amount_net DECIMAL(18, 2),
            amount_gross DECIMAL(18, 2),
            principal_component_net DECIMAL(18, 2),
            interest_component_gross DECIMAL(18, 2),
            fee_amount_net DECIMAL(18, 2),
            tax_amount_gross DECIMAL(18, 2),
            settlement_amount_effective DECIMAL(18, 2),
            exchange_rate_effective DECIMAL(18, 8),
            is_reversal_flag BOOLEAN,
            currency_code VARCHAR,
            sort_group INTEGER
        )
        """
    )
    connection.execute(
        """
        INSERT INTO tmp_payment_raw
        WITH contract_flags AS (
            SELECT
                contract_id,
                late_payment_flag,
                missed_payment_flag,
                reversal_flag,
                fx_flag,
                high_ltv_flag,
                default_flag,
                refinance_flag
            FROM stg_contract_seed
        ),
        enriched AS (
            SELECT
                cf.*,
                cft.cashflow_type_code,
                dd.full_date AS due_date,
                COALESCE(l.leasing_contract_id, n.loan_contract_id) AS contract_id,
                flags.late_payment_flag,
                flags.missed_payment_flag,
                flags.reversal_flag,
                flags.fx_flag,
                flags.high_ltv_flag,
                flags.default_flag,
                flags.refinance_flag
            FROM fact_contract_cashflows AS cf
            JOIN dim_cashflow_type AS cft
              ON cft.cashflow_type_sk = cf.cashflow_type_sk
            JOIN dim_date AS dd
              ON dd.date_sk = cf.due_date_sk
            LEFT JOIN fact_leasing_contracts AS l
              ON l.leasing_contract_sk = cf.related_leasing_contract_sk
            LEFT JOIN fact_loan_contracts AS n
              ON n.loan_contract_sk = cf.related_loan_contract_sk
            LEFT JOIN contract_flags AS flags
              ON flags.contract_id = COALESCE(l.leasing_contract_id, n.loan_contract_id)
        )
        SELECT
            'PAY-' || contract_cashflow_id,
            contract_cashflow_id || '-PMT',
            customer_sk,
            cashflow_type_sk,
            product_sk,
            contract_status_sk,
            CASE
                WHEN late_payment_flag
                 AND cashflow_type_code IN ('LEASE_INSTALLMENT', 'LOAN_INSTALLMENT')
                 AND installment_number IN (2, 3)
                    THEN due_date + INTERVAL 18 DAY
                ELSE due_date
            END::DATE,
            CASE
                WHEN late_payment_flag
                 AND cashflow_type_code IN ('LEASE_INSTALLMENT', 'LOAN_INSTALLMENT')
                 AND installment_number IN (2, 3)
                    THEN due_date + INTERVAL 19 DAY
                ELSE due_date
            END::DATE,
            CASE
                WHEN late_payment_flag
                 AND cashflow_type_code IN ('LEASE_INSTALLMENT', 'LOAN_INSTALLMENT')
                 AND installment_number IN (2, 3)
                    THEN due_date + INTERVAL 20 DAY
                ELSE due_date
            END::DATE,
            related_leasing_contract_sk,
            related_loan_contract_sk,
            related_banking_account_sk,
            contract_cashflow_sk,
            NULL,
            CASE
                WHEN cashflow_type_code = 'DEALER_SUBSIDY' THEN 'COMMISSION_PAYOUT'
                WHEN fx_flag
                 AND cashflow_type_code IN (
                    'LEASE_INSTALLMENT',
                    'LOAN_INSTALLMENT',
                    'BALLOON_PAYMENT'
                 )
                    THEN 'FX_SETTLEMENT'
                ELSE 'PAYMENT'
            END,
            CASE
                WHEN cashflow_type_code = 'DEALER_SUBSIDY' THEN 'DEALER_PORTAL'
                WHEN fx_flag THEN 'SWIFT'
                WHEN late_payment_flag
                 AND cashflow_type_code IN ('LEASE_INSTALLMENT', 'LOAN_INSTALLMENT')
                    THEN 'COLLECTION'
                ELSE 'SEPA'
            END,
            CASE WHEN fx_flag THEN 'CH' ELSE 'DE' END,
            CASE WHEN cashflow_type_code = 'DEALER_SUBSIDY' THEN -amount_net ELSE amount_net END,
            CASE
                WHEN cashflow_type_code = 'DEALER_SUBSIDY' THEN -amount_gross
                ELSE amount_gross
            END,
            CASE
                WHEN cashflow_type_code = 'DEALER_SUBSIDY' THEN -principal_component_net
                ELSE principal_component_net
            END,
            interest_component_gross,
            CASE
                WHEN cashflow_type_code = 'DEALER_SUBSIDY' THEN -commission_amount_net
                ELSE fee_component_net
            END,
            tax_amount_gross,
            CASE WHEN fx_flag THEN ROUND(amount_gross * 1.07, 2) ELSE amount_gross END,
            CASE WHEN fx_flag THEN 1.07 ELSE 1.00 END,
            FALSE,
            CASE WHEN fx_flag THEN 'CHF' ELSE currency_code END,
            1
        FROM enriched
        WHERE NOT (
            missed_payment_flag
            AND cashflow_type_code = 'LOAN_INSTALLMENT'
            AND installment_number IN (1, 2, 3)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO tmp_payment_raw
        WITH enriched AS (
            SELECT
                cf.*,
                cft.cashflow_type_code,
                dd.full_date AS due_date,
                s.late_payment_flag,
                COALESCE(l.leasing_contract_id, n.loan_contract_id) AS contract_id
            FROM fact_contract_cashflows AS cf
            JOIN dim_cashflow_type AS cft
              ON cft.cashflow_type_sk = cf.cashflow_type_sk
            JOIN dim_date AS dd
              ON dd.date_sk = cf.due_date_sk
            LEFT JOIN fact_leasing_contracts AS l
              ON l.leasing_contract_sk = cf.related_leasing_contract_sk
            LEFT JOIN fact_loan_contracts AS n
              ON n.loan_contract_sk = cf.related_loan_contract_sk
            JOIN stg_contract_seed AS s
              ON s.contract_id = COALESCE(l.leasing_contract_id, n.loan_contract_id)
        ),
        fee_type AS (
            SELECT cashflow_type_sk
            FROM dim_cashflow_type
            WHERE cashflow_type_code = 'ACCOUNT_FEE'
        )
        SELECT
            'LATEFEE-' || contract_cashflow_id,
            contract_cashflow_id || '-LATEFEE',
            customer_sk,
            (SELECT cashflow_type_sk FROM fee_type),
            product_sk,
            contract_status_sk,
            (due_date + INTERVAL 23 DAY)::DATE,
            (due_date + INTERVAL 23 DAY)::DATE,
            (due_date + INTERVAL 24 DAY)::DATE,
            related_leasing_contract_sk,
            related_loan_contract_sk,
            related_banking_account_sk,
            contract_cashflow_sk,
            NULL,
            'LATE_FEE_COLLECTION',
            'COLLECTION',
            'DE',
            12.50,
            14.88,
            0,
            0,
            12.50,
            2.38,
            14.88,
            1.00,
            FALSE,
            'EUR',
            2
        FROM enriched
        WHERE late_payment_flag
          AND cashflow_type_code = 'LEASE_INSTALLMENT'
          AND installment_number = 2
        """
    )
    connection.execute(
        """
        INSERT INTO tmp_payment_raw
        WITH enriched AS (
            SELECT
                cf.*,
                cft.cashflow_type_code,
                dd.full_date AS due_date,
                s.reversal_flag,
                COALESCE(l.leasing_contract_id, n.loan_contract_id) AS contract_id
            FROM fact_contract_cashflows AS cf
            JOIN dim_cashflow_type AS cft
              ON cft.cashflow_type_sk = cf.cashflow_type_sk
            JOIN dim_date AS dd
              ON dd.date_sk = cf.due_date_sk
            LEFT JOIN fact_leasing_contracts AS l
              ON l.leasing_contract_sk = cf.related_leasing_contract_sk
            LEFT JOIN fact_loan_contracts AS n
              ON n.loan_contract_sk = cf.related_loan_contract_sk
            JOIN stg_contract_seed AS s
              ON s.contract_id = COALESCE(l.leasing_contract_id, n.loan_contract_id)
        )
        SELECT
            'REV-' || contract_cashflow_id,
            contract_cashflow_id || '-REV',
            customer_sk,
            cashflow_type_sk,
            product_sk,
            contract_status_sk,
            CASE
                WHEN contract_cashflow_sk % 2 = 0 THEN (due_date + INTERVAL 2 DAY)::DATE
                ELSE (due_date + INTERVAL 5 DAY)::DATE
            END,
            CASE
                WHEN contract_cashflow_sk % 2 = 0 THEN (due_date + INTERVAL 2 DAY)::DATE
                ELSE (due_date + INTERVAL 5 DAY)::DATE
            END,
            CASE
                WHEN contract_cashflow_sk % 2 = 0 THEN (due_date + INTERVAL 3 DAY)::DATE
                ELSE (due_date + INTERVAL 6 DAY)::DATE
            END,
            related_leasing_contract_sk,
            related_loan_contract_sk,
            related_banking_account_sk,
            contract_cashflow_sk,
            contract_cashflow_id || '-PMT',
            'REVERSAL',
            'OPS',
            'DE',
            -amount_net,
            -amount_gross,
            -principal_component_net,
            -interest_component_gross,
            -fee_component_net,
            -tax_amount_gross,
            -amount_gross,
            1.00,
            TRUE,
            currency_code,
            3
        FROM enriched
        WHERE reversal_flag
          AND cashflow_type_code = 'DOWN_PAYMENT'
        """
    )
    connection.execute(
        """
        INSERT INTO fact_payment_transactions
        WITH ordered AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    ORDER BY transaction_date, sort_group, payment_transaction_id
                ) AS payment_transaction_sk
            FROM tmp_payment_raw
            WHERE is_reversal_flag = FALSE
        )
        SELECT
            ordered.payment_transaction_sk,
            ordered.payment_transaction_id,
            ordered.customer_sk,
            ordered.cashflow_type_sk,
            ordered.product_sk,
            ordered.contract_status_sk,
            CAST(strftime(ordered.transaction_date, '%Y%m%d') AS INTEGER) AS transaction_date_sk,
            CAST(strftime(ordered.value_date, '%Y%m%d') AS INTEGER) AS value_date_sk,
            CAST(strftime(ordered.booking_date, '%Y%m%d') AS INTEGER) AS booking_date_sk,
            ordered.related_leasing_contract_sk,
            ordered.related_loan_contract_sk,
            ordered.related_banking_account_sk,
            ordered.related_contract_cashflow_sk,
            NULL AS reverses_payment_transaction_sk,
            ordered.transaction_type_code,
            ordered.transaction_channel_code,
            ordered.counterparty_country_code,
            ordered.amount_net,
            ordered.amount_gross,
            ordered.principal_component_net,
            ordered.interest_component_gross,
            ordered.fee_amount_net,
            ordered.tax_amount_gross,
            ordered.settlement_amount_effective,
            ordered.exchange_rate_effective,
            ordered.is_reversal_flag,
            ordered.currency_code
        FROM ordered
        WHERE ordered.transaction_date <= DATE '2026-12-31'
          AND ordered.value_date <= DATE '2026-12-31'
          AND ordered.booking_date <= DATE '2026-12-31'
        ORDER BY ordered.payment_transaction_sk
        """
    )
    connection.execute(
        """
        INSERT INTO fact_payment_transactions
        WITH reversal_rows AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    ORDER BY transaction_date, payment_transaction_id
                ) + (SELECT COUNT(*) FROM fact_payment_transactions) AS payment_transaction_sk
            FROM tmp_payment_raw
            WHERE is_reversal_flag = TRUE
              AND transaction_date <= DATE '2026-12-31'
              AND value_date <= DATE '2026-12-31'
              AND booking_date <= DATE '2026-12-31'
        )
        SELECT
            reversal_rows.payment_transaction_sk,
            reversal_rows.payment_transaction_id,
            reversal_rows.customer_sk,
            reversal_rows.cashflow_type_sk,
            reversal_rows.product_sk,
            reversal_rows.contract_status_sk,
            CAST(
                strftime(reversal_rows.transaction_date, '%Y%m%d') AS INTEGER
            ) AS transaction_date_sk,
            CAST(strftime(reversal_rows.value_date, '%Y%m%d') AS INTEGER) AS value_date_sk,
            CAST(strftime(reversal_rows.booking_date, '%Y%m%d') AS INTEGER) AS booking_date_sk,
            reversal_rows.related_leasing_contract_sk,
            reversal_rows.related_loan_contract_sk,
            reversal_rows.related_banking_account_sk,
            reversal_rows.related_contract_cashflow_sk,
            base.payment_transaction_sk AS reverses_payment_transaction_sk,
            reversal_rows.transaction_type_code,
            reversal_rows.transaction_channel_code,
            reversal_rows.counterparty_country_code,
            reversal_rows.amount_net,
            reversal_rows.amount_gross,
            reversal_rows.principal_component_net,
            reversal_rows.interest_component_gross,
            reversal_rows.fee_amount_net,
            reversal_rows.tax_amount_gross,
            reversal_rows.settlement_amount_effective,
            reversal_rows.exchange_rate_effective,
            reversal_rows.is_reversal_flag,
            reversal_rows.currency_code
        FROM reversal_rows
        JOIN fact_payment_transactions AS base
          ON base.payment_transaction_id = reversal_rows.reverse_of_key
        ORDER BY reversal_rows.payment_transaction_sk
        """
    )
    connection.execute("DROP TABLE IF EXISTS tmp_payment_raw")
