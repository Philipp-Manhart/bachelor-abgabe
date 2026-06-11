from __future__ import annotations

import duckdb

from data_generation.config import GeneratorConfig


def populate_dim_dealer(
    connection: duckdb.DuckDBPyConnection,
    config: GeneratorConfig,
) -> None:
    connection.execute("DELETE FROM dim_dealer")
    connection.execute(
        """
        INSERT INTO dim_dealer
        WITH versioned AS (
            SELECT
                s.*,
                version_n,
                CASE
                    WHEN s.scd_version_target = 1 THEN ?::DATE
                    WHEN version_n = 1 THEN ?::DATE
                    WHEN version_n = 2
                        THEN make_date(
                            2022 + (s.noise_seed % 2),
                            ((s.noise_seed % 12) + 1),
                            1
                        )
                    ELSE make_date(2025, (((s.noise_seed / 5)::INTEGER % 12) + 1), 1)
                END AS valid_from_date
            FROM stg_dealer_seed AS s
            CROSS JOIN generate_series(1, s.scd_version_target) AS versions(version_n)
        ),
        bounded AS (
            SELECT
                *,
                LEAD(valid_from_date) OVER (
                    PARTITION BY dealer_id
                    ORDER BY version_n
                ) AS next_valid_from_date
            FROM versioned
        )
        SELECT
            ROW_NUMBER() OVER (
                ORDER BY dealer_id, version_n
            ) AS dealer_sk,
            dealer_id,
            CASE
                WHEN version_n = 1 AND dealer_status_code = 'Active'
                    THEN dealer_name || ' Legacy'
                ELSE dealer_name
            END AS dealer_name,
            legal_entity_name,
            dealer_type_code,
            country_code,
            postal_code,
            city,
            sales_region_code,
            CASE
                WHEN version_n = 1 AND risk_rating_code = 'LOW' THEN 'MODERATE'
                WHEN version_n = 1 AND risk_rating_code = 'MODERATE' THEN 'ELEVATED'
                ELSE risk_rating_code
            END AS risk_rating_code,
            CASE
                WHEN version_n = 1
                 AND dealer_status_code = 'Active'
                 AND dormant_dealer_flag
                    THEN 'Watchlist'
                ELSE dealer_status_code
            END AS dealer_status_code,
            onboarding_date,
            termination_date,
            valid_from_date,
            CASE
                WHEN next_valid_from_date IS NULL THEN NULL
                ELSE next_valid_from_date - INTERVAL 1 DAY
            END::DATE AS valid_to_date,
            next_valid_from_date IS NULL AS is_current_record
        FROM bounded
        ORDER BY dealer_id, version_n
        """,
        [config.date_start, config.date_start],
    )
