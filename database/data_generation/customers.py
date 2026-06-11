from __future__ import annotations

import duckdb

from data_generation.config import GeneratorConfig


def populate_dim_customer(
    connection: duckdb.DuckDBPyConnection,
    config: GeneratorConfig,
) -> None:
    connection.execute("DELETE FROM dim_customer")
    connection.execute(
        """
        INSERT INTO dim_customer
        WITH versioned AS (
            SELECT
                s.*,
                version_n,
                CASE
                    WHEN s.scd_version_target = 1 THEN ?::DATE
                    WHEN version_n = 1 THEN ?::DATE
                    WHEN version_n = 2 AND s.customer_type_code = 'Corporate'
                        THEN DATE '2023-01-01'
                    WHEN version_n = 2
                        THEN make_date(
                            2021 + (s.noise_seed % 3),
                            ((s.noise_seed % 12) + 1),
                            1
                        )
                    WHEN s.customer_type_code = 'Corporate'
                        THEN make_date(2025, (((s.noise_seed / 3)::INTEGER % 12) + 1), 1)
                    ELSE make_date(
                        2024 + (s.noise_seed % 2),
                        (((s.noise_seed / 3)::INTEGER % 12) + 1),
                        1
                    )
                END AS valid_from_date
            FROM stg_customer_seed AS s
            CROSS JOIN generate_series(1, s.scd_version_target) AS versions(version_n)
        ),
        bounded AS (
            SELECT
                *,
                LEAD(valid_from_date) OVER (
                    PARTITION BY customer_id
                    ORDER BY version_n
                ) AS next_valid_from_date
            FROM versioned
        )
        SELECT
            ROW_NUMBER() OVER (
                ORDER BY customer_id, version_n
            ) AS customer_sk,
            customer_id,
            customer_type_code,
            CASE
                WHEN customer_type_code = 'Corporate' AND version_n > 1
                    THEN REPLACE(legal_entity_name, ' GmbH', ' Group GmbH')
                ELSE legal_entity_name
            END AS legal_entity_name,
            first_name,
            last_name,
            date_of_birth,
            gender_code,
            nationality_code,
            country_of_residence_code,
            postal_code,
            city,
            federal_state_code,
            employment_status_code,
            ROUND(
                annual_income_gross
                * CASE version_n WHEN 1 THEN 0.97 WHEN 2 THEN 1.00 ELSE 1.05 END,
                2
            ) AS annual_income_gross,
            ROUND(
                monthly_income_net
                * CASE version_n WHEN 1 THEN 0.96 WHEN 2 THEN 1.00 ELSE 1.04 END,
                2
            ) AS monthly_income_net,
            GREATEST(
                250,
                credit_score_nominal
                + CASE version_n WHEN 1 THEN -18 WHEN 2 THEN 0 ELSE 14 END
            ) AS credit_score_nominal,
            CASE
                WHEN customer_type_code = 'Corporate' AND scd_version_target > 1 THEN
                    CASE version_n
                        WHEN 1 THEN 'LOW'
                        WHEN 2 THEN 'MEDIUM'
                        ELSE 'HIGH'
                    END
                WHEN version_n = 1 AND scd_version_target > 1 AND risk_class_code <> 'HIGH' THEN
                    CASE risk_class_code
                        WHEN 'LOW' THEN 'MEDIUM'
                        WHEN 'MEDIUM' THEN 'HIGH'
                        ELSE risk_class_code
                    END
                ELSE risk_class_code
            END AS risk_class_code,
            consent_marketing_flag,
            CASE
                WHEN version_n = 1 AND preferred_channel_code = 'ONLINE' THEN 'BRANCH'
                WHEN version_n = 3 THEN 'ONLINE'
                ELSE preferred_channel_code
            END AS preferred_channel_code,
            valid_from_date,
            CASE
                WHEN next_valid_from_date IS NULL THEN NULL
                ELSE next_valid_from_date - INTERVAL 1 DAY
            END::DATE AS valid_to_date,
            next_valid_from_date IS NULL AS is_current_record
        FROM bounded
        ORDER BY customer_id, version_n
        """,
        [config.date_start, config.date_start],
    )
