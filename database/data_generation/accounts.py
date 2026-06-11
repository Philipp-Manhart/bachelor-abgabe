from __future__ import annotations

import duckdb


def populate_banking_accounts(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute("DELETE FROM fact_banking_accounts")
    connection.execute(
        """
        INSERT INTO fact_banking_accounts
        WITH snapshots AS (
            SELECT
                a.*,
                d.full_date AS snapshot_date
            FROM stg_account_seed AS a
            JOIN dim_date AS d
              ON d.full_date BETWEEN GREATEST(a.open_date, a.snapshot_start_date)
                                 AND COALESCE(a.close_date, DATE '2026-12-31')
        ),
        resolved AS (
            SELECT
                s.*,
                customer.customer_sk,
                product.product_sk,
                CASE
                    WHEN s.close_date IS NOT NULL AND s.snapshot_date = s.close_date
                        THEN closed_status.contract_status_sk
                    ELSE active_status.contract_status_sk
                END AS contract_status_sk
            FROM snapshots AS s
            JOIN dim_customer AS customer
              ON customer.customer_id = s.customer_id
             AND s.snapshot_date BETWEEN customer.valid_from_date
                                    AND COALESCE(customer.valid_to_date, DATE '9999-12-31')
            JOIN dim_product AS product
              ON product.product_id = s.product_id
            JOIN dim_contract_status AS active_status
              ON active_status.status_code = 'ACTIVE'
            JOIN dim_contract_status AS closed_status
              ON closed_status.status_code = 'CLOSED'
        ),
        balances AS (
            SELECT
                *,
                ROUND(
                    base_balance_net
                    + CASE
                        WHEN day(snapshot_date) >= CASE inflow_profile_code
                            WHEN 'CORPORATE' THEN 4
                            WHEN 'MIXED' THEN 8
                            ELSE 3
                        END THEN monthly_inflow_base
                        ELSE 0
                    END
                    - CASE WHEN day(snapshot_date) >= 5 THEN monthly_outflow_base * 0.38 ELSE 0 END
                    - CASE WHEN day(snapshot_date) >= 12 THEN monthly_outflow_base * 0.31 ELSE 0 END
                    - CASE WHEN day(snapshot_date) >= 24 THEN monthly_outflow_base * 0.27 ELSE 0 END
                    + ((noise_seed + date_diff('day', open_date, snapshot_date)) % 19 - 9) * 11
                    - CASE
                        WHEN overdraft_flag
                         AND day(snapshot_date) BETWEEN 19 AND 27
                            THEN authorized_overdraft_limit_net * 1.15
                        ELSE 0
                    END,
                    2
                ) AS current_balance_net_raw,
                CASE
                    WHEN blocked_account_flag
                     AND day(snapshot_date) BETWEEN 7 AND 11
                        THEN blocked_amount_base
                    WHEN blocked_account_flag
                     AND day(snapshot_date) BETWEEN 12 AND 16
                        THEN blocked_amount_base * 0.5
                    ELSE 0
                END AS blocked_amount_effective
            FROM resolved
        ),
        enriched AS (
            SELECT
                *,
                ROUND(current_balance_net_raw, 2) AS current_balance_net,
                ROUND(current_balance_net_raw, 2) AS current_balance_gross,
                ROUND(
                    current_balance_net_raw - blocked_amount_effective,
                    2
                ) AS available_balance_effective,
                ROUND(
                    CASE WHEN overdraft_flag THEN 0.089 ELSE 0.011 END,
                    6
                ) AS interest_rate_nominal,
                ROUND(
                    CASE WHEN overdraft_flag THEN 0.095 ELSE 0.013 END,
                    6
                ) AS interest_rate_effective,
                ROUND(
                    CASE WHEN day(snapshot_date) >= 2 THEN 4.50 ELSE 0 END,
                    2
                ) AS fee_income_month_to_date_net
            FROM balances
        )
        SELECT
            ROW_NUMBER() OVER (ORDER BY banking_account_id, snapshot_date) AS banking_account_sk,
            banking_account_id,
            customer_sk,
            product_sk,
            contract_status_sk,
            CAST(strftime(open_date, '%Y%m%d') AS INTEGER) AS account_open_date_sk,
            CASE
                WHEN close_date IS NULL THEN NULL
                ELSE CAST(strftime(close_date, '%Y%m%d') AS INTEGER)
            END AS account_close_date_sk,
            CAST(strftime(snapshot_date, '%Y%m%d') AS INTEGER) AS snapshot_date_sk,
            md5('IBAN-' || banking_account_id) AS iban_hash,
            'EUR' AS account_currency_code,
            ROUND(authorized_overdraft_limit_net * 1.20, 2) AS credit_limit_nominal,
            authorized_overdraft_limit_net,
            current_balance_net,
            current_balance_gross,
            available_balance_effective,
            ROUND(
                AVG(current_balance_net) OVER (
                    PARTITION BY banking_account_id
                    ORDER BY snapshot_date
                    ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
                ),
                2
            ) AS average_balance_30d_net,
            ROUND(
                AVG(current_balance_net) OVER (
                    PARTITION BY banking_account_id
                    ORDER BY snapshot_date
                    ROWS BETWEEN 89 PRECEDING AND CURRENT ROW
                ),
                2
            ) AS average_balance_90d_net,
            interest_rate_nominal,
            interest_rate_effective,
            fee_income_month_to_date_net,
            ROUND(
                SUM(fee_income_month_to_date_net * 1.19) OVER (
                    PARTITION BY banking_account_id, year(snapshot_date)
                    ORDER BY snapshot_date
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ),
                2
            ) AS fee_income_year_to_date_gross,
            SUM(
                CASE WHEN current_balance_net < 0 THEN 1 ELSE 0 END
            ) OVER (
                PARTITION BY banking_account_id, year(snapshot_date), month(snapshot_date)
                ORDER BY snapshot_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS overdraft_days_month_to_date,
            ROUND(blocked_amount_effective, 2) AS blocked_amount_effective
        FROM enriched
        ORDER BY banking_account_id, snapshot_date
        """
    )
