from __future__ import annotations

import duckdb


def populate_contract_facts(connection: duckdb.DuckDBPyConnection) -> None:
    _populate_fact_leasing_contracts(connection)
    _populate_fact_loan_contracts(connection)


def _populate_fact_leasing_contracts(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute("DELETE FROM fact_leasing_contracts")
    connection.execute(
        """
        INSERT INTO fact_leasing_contracts
        WITH resolved AS (
            SELECT
                s.*,
                customer.customer_sk,
                vehicle.vehicle_sk,
                dealer.dealer_sk,
                product.product_sk,
                status.contract_status_sk
            FROM stg_contract_seed AS s
            INNER JOIN dim_customer AS customer
                ON customer.customer_id = s.customer_id
               AND s.booking_date BETWEEN customer.valid_from_date
                                      AND COALESCE(customer.valid_to_date, DATE '9999-12-31')
            INNER JOIN dim_dealer AS dealer
                ON dealer.dealer_id = s.dealer_id
               AND s.booking_date BETWEEN dealer.valid_from_date
                                      AND COALESCE(dealer.valid_to_date, DATE '9999-12-31')
            INNER JOIN dim_vehicle AS vehicle
                ON vehicle.vehicle_id = s.vehicle_id
            INNER JOIN dim_product AS product
                ON product.product_id = s.product_id
            INNER JOIN dim_contract_status AS status
                ON status.status_code = s.target_status_code
            WHERE s.contract_type_code = 'LEASING'
        )
        SELECT
            ROW_NUMBER() OVER (ORDER BY contract_id) AS leasing_contract_sk,
            contract_id AS leasing_contract_id,
            customer_sk,
            vehicle_sk,
            dealer_sk,
            product_sk,
            contract_status_sk,
            CAST(strftime(start_date, '%Y%m%d') AS INTEGER) AS contract_start_date_sk,
            CAST(strftime(end_date, '%Y%m%d') AS INTEGER) AS contract_end_date_sk,
            CAST(strftime(booking_date, '%Y%m%d') AS INTEGER) AS booking_date_sk,
            CAST(strftime(maturity_date, '%Y%m%d') AS INTEGER) AS maturity_date_sk,
            CASE
                WHEN target_status_code IN ('CLOSED', 'DEFAULT', 'REPOSSESSED')
                    THEN CAST(strftime(end_date, '%Y%m%d') AS INTEGER)
                ELSE NULL
            END AS actual_end_date_sk,
            CASE
                WHEN target_status_code IN ('CLOSED', 'REPOSSESSED')
                    THEN CAST(strftime(end_date, '%Y%m%d') AS INTEGER)
                ELSE NULL
            END AS vehicle_return_date_sk,
            (
                refinance_flag
                OR (target_status_code = 'CLOSED' AND contract_term_months < 36)
            ) AS early_termination_flag,
            CASE
                WHEN refinance_flag THEN 'REFINANCE'
                WHEN default_flag THEN 'DEFAULT'
                WHEN target_status_code = 'REPOSSESSED' THEN 'REPOSSESSION'
                WHEN target_status_code = 'CLOSED' THEN 'MATURED_OR_RETURNED'
                ELSE NULL
            END AS termination_reason_code,
            contract_term_months,
            10000 + ((noise_seed % 8) * 5000) AS agreed_annual_mileage_km,
            financed_amount_net,
            financed_amount_gross,
            down_payment_gross,
            ROUND(monthly_payment_gross / 1.19, 2) AS monthly_payment_net,
            monthly_payment_gross,
            residual_value_nominal,
            ROUND(
                COALESCE(residual_value_nominal, 0)
                * CASE WHEN target_status_code = 'CLOSED' THEN 0.98 ELSE 1.00 END,
                2
            ) AS residual_value_effective,
            interest_rate_nominal,
            ROUND(interest_rate_nominal + 0.0025, 6) AS interest_rate_effective,
            ROUND(financed_amount_net * 0.004, 2) AS service_fee_net,
            ROUND(financed_amount_gross * 0.0025, 2) AS insurance_fee_gross,
            'EUR' AS currency_code
        FROM resolved
        ORDER BY contract_id
        """
    )


def _populate_fact_loan_contracts(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute("DELETE FROM fact_loan_contracts")
    connection.execute(
        """
        INSERT INTO fact_loan_contracts
        WITH resolved AS (
            SELECT
                s.*,
                customer.customer_sk,
                vehicle.vehicle_sk,
                dealer.dealer_sk,
                product.product_sk,
                status.contract_status_sk
            FROM stg_contract_seed AS s
            INNER JOIN dim_customer AS customer
                ON customer.customer_id = s.customer_id
               AND s.booking_date BETWEEN customer.valid_from_date
                                      AND COALESCE(customer.valid_to_date, DATE '9999-12-31')
            INNER JOIN dim_dealer AS dealer
                ON dealer.dealer_id = s.dealer_id
               AND s.booking_date BETWEEN dealer.valid_from_date
                                      AND COALESCE(dealer.valid_to_date, DATE '9999-12-31')
            INNER JOIN dim_vehicle AS vehicle
                ON vehicle.vehicle_id = s.vehicle_id
            INNER JOIN dim_product AS product
                ON product.product_id = s.product_id
            INNER JOIN dim_contract_status AS status
                ON status.status_code = s.target_status_code
            WHERE s.contract_type_code = 'LOAN'
        )
        SELECT
            ROW_NUMBER() OVER (ORDER BY contract_id) AS loan_contract_sk,
            contract_id AS loan_contract_id,
            customer_sk,
            vehicle_sk,
            dealer_sk,
            product_sk,
            contract_status_sk,
            CAST(strftime(start_date, '%Y%m%d') AS INTEGER) AS origination_date_sk,
            CAST(
                strftime(start_date + INTERVAL 1 MONTH, '%Y%m%d') AS INTEGER
            ) AS first_payment_date_sk,
            CAST(strftime(maturity_date, '%Y%m%d') AS INTEGER) AS maturity_date_sk,
            CAST(strftime(booking_date, '%Y%m%d') AS INTEGER) AS booking_date_sk,
            CASE
                WHEN target_status_code IN ('CLOSED', 'DEFAULT', 'REPOSSESSED')
                    THEN CAST(strftime(end_date, '%Y%m%d') AS INTEGER)
                ELSE NULL
            END AS actual_end_date_sk,
            CASE
                WHEN target_status_code = 'REPOSSESSED'
                    THEN CAST(strftime(end_date, '%Y%m%d') AS INTEGER)
                ELSE NULL
            END AS vehicle_return_date_sk,
            refinance_flag AS early_termination_flag,
            CASE
                WHEN refinance_flag THEN 'REFINANCE'
                WHEN default_flag THEN 'DEFAULT'
                WHEN target_status_code = 'REPOSSESSED' THEN 'REPOSSESSION'
                WHEN target_status_code = 'CLOSED' THEN 'EARLY_SETTLEMENT'
                ELSE NULL
            END AS termination_reason_code,
            contract_term_months AS loan_term_months,
            financed_amount_net,
            financed_amount_gross,
            down_payment_gross,
            balloon_payment_nominal,
            ROUND(monthly_payment_gross / 1.19, 2) AS monthly_installment_net,
            monthly_payment_gross AS monthly_installment_gross,
            interest_rate_nominal,
            ROUND(interest_rate_nominal + 0.0035, 6) AS annual_percentage_rate_effective,
            ltv_ratio AS loan_to_value_effective,
            'EUR' AS currency_code
        FROM resolved
        ORDER BY contract_id
        """
    )
