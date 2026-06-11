from __future__ import annotations

import duckdb


def populate_contract_status_history(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute("DELETE FROM fact_contract_status_history")
    connection.execute(
        """
        INSERT INTO fact_contract_status_history
        WITH leasing_events AS (
            SELECT
                CAST(l.leasing_contract_sk AS BIGINT) AS leasing_contract_sk,
                CAST(NULL AS BIGINT) AS loan_contract_sk,
                'ACTIVE' AS status_code,
                s.start_date AS event_date,
                1 AS sort_order
            FROM fact_leasing_contracts AS l
            JOIN stg_contract_seed AS s
              ON s.contract_id = l.leasing_contract_id

            UNION ALL

            SELECT
                l.leasing_contract_sk,
                NULL,
                'LATE_1_30',
                LEAST(s.end_date - INTERVAL 24 DAY, s.start_date + INTERVAL 4 MONTH)::DATE,
                2
            FROM fact_leasing_contracts AS l
            JOIN stg_contract_seed AS s
              ON s.contract_id = l.leasing_contract_id
            WHERE s.late_payment_flag
              AND s.target_status_code = 'ACTIVE'
              AND s.end_date > s.start_date + INTERVAL 40 DAY

            UNION ALL

            SELECT
                l.leasing_contract_sk,
                NULL,
                'ACTIVE',
                LEAST(
                    s.end_date - INTERVAL 6 DAY,
                    s.start_date + INTERVAL 4 MONTH + INTERVAL 18 DAY
                )::DATE,
                3
            FROM fact_leasing_contracts AS l
            JOIN stg_contract_seed AS s
              ON s.contract_id = l.leasing_contract_id
            WHERE s.late_payment_flag
              AND s.target_status_code = 'ACTIVE'
              AND s.end_date > s.start_date + INTERVAL 50 DAY

            UNION ALL

            SELECT
                l.leasing_contract_sk,
                NULL,
                'CLOSED',
                s.end_date,
                4
            FROM fact_leasing_contracts AS l
            JOIN stg_contract_seed AS s
              ON s.contract_id = l.leasing_contract_id
            WHERE s.target_status_code = 'CLOSED'
        ),
        loan_events AS (
            SELECT
                CAST(NULL AS BIGINT) AS leasing_contract_sk,
                CAST(l.loan_contract_sk AS BIGINT) AS loan_contract_sk,
                'ACTIVE' AS status_code,
                s.start_date AS event_date,
                1 AS sort_order
            FROM fact_loan_contracts AS l
            JOIN stg_contract_seed AS s
              ON s.contract_id = l.loan_contract_id

            UNION ALL

            SELECT
                NULL,
                l.loan_contract_sk,
                'LATE_1_30',
                LEAST(s.end_date - INTERVAL 20 DAY, s.start_date + INTERVAL 75 DAY)::DATE,
                2
            FROM fact_loan_contracts AS l
            JOIN stg_contract_seed AS s
              ON s.contract_id = l.loan_contract_id
            WHERE s.late_payment_flag
              AND NOT s.default_flag
              AND s.target_status_code = 'ACTIVE'
              AND s.end_date > s.start_date + INTERVAL 90 DAY

            UNION ALL

            SELECT
                NULL,
                l.loan_contract_sk,
                'ACTIVE',
                LEAST(s.end_date - INTERVAL 5 DAY, s.start_date + INTERVAL 95 DAY)::DATE,
                3
            FROM fact_loan_contracts AS l
            JOIN stg_contract_seed AS s
              ON s.contract_id = l.loan_contract_id
            WHERE s.late_payment_flag
              AND NOT s.default_flag
              AND s.target_status_code = 'ACTIVE'
              AND s.end_date > s.start_date + INTERVAL 110 DAY

            UNION ALL

            SELECT
                NULL,
                l.loan_contract_sk,
                'LATE_31_60',
                LEAST(s.end_date - INTERVAL 10 DAY, s.start_date + INTERVAL 105 DAY)::DATE,
                4
            FROM fact_loan_contracts AS l
            JOIN stg_contract_seed AS s
              ON s.contract_id = l.loan_contract_id
            WHERE (s.default_flag OR s.missed_payment_flag)
              AND s.end_date > s.start_date + INTERVAL 120 DAY

            UNION ALL

            SELECT
                NULL,
                l.loan_contract_sk,
                'ACTIVE',
                LEAST(s.end_date - INTERVAL 4 DAY, s.start_date + INTERVAL 135 DAY)::DATE,
                5
            FROM fact_loan_contracts AS l
            JOIN stg_contract_seed AS s
              ON s.contract_id = l.loan_contract_id
            WHERE s.missed_payment_flag
              AND NOT s.default_flag
              AND s.target_status_code = 'ACTIVE'
              AND s.end_date > s.start_date + INTERVAL 115 DAY

            UNION ALL

            SELECT
                NULL,
                l.loan_contract_sk,
                CASE
                    WHEN s.target_status_code = 'REPOSSESSED' THEN 'REPOSSESSED'
                    ELSE 'DEFAULT'
                END,
                s.end_date,
                6
            FROM fact_loan_contracts AS l
            JOIN stg_contract_seed AS s
              ON s.contract_id = l.loan_contract_id
            WHERE s.target_status_code IN ('DEFAULT', 'REPOSSESSED')
        ),
        all_events AS (
            SELECT * FROM leasing_events
            UNION ALL
            SELECT * FROM loan_events
        ),
        ordered AS (
            SELECT
                *,
                LEAD(event_date) OVER (
                    PARTITION BY COALESCE(
                        'L' || leasing_contract_sk::VARCHAR,
                        'N' || loan_contract_sk::VARCHAR
                    )
                    ORDER BY event_date, sort_order
                ) AS next_event_date
            FROM all_events
        )
        SELECT
            ROW_NUMBER() OVER (
                ORDER BY
                    COALESCE(leasing_contract_sk, 0),
                    COALESCE(loan_contract_sk, 0),
                    event_date,
                    sort_order
            ) AS status_history_sk,
            leasing_contract_sk,
            loan_contract_sk,
            status.contract_status_sk,
            CAST(strftime(event_date, '%Y%m%d') AS INTEGER) AS valid_from_date_sk,
            CASE
                WHEN next_event_date IS NULL THEN NULL
                ELSE CAST(strftime(next_event_date - INTERVAL 1 DAY, '%Y%m%d') AS INTEGER)
            END AS valid_to_date_sk,
            next_event_date IS NULL AS is_current_status
        FROM ordered
        JOIN dim_contract_status AS status
          ON status.status_code = ordered.status_code
        ORDER BY status_history_sk
        """
    )
