from __future__ import annotations

from datetime import date

import duckdb


def populate_dim_date(
    connection: duckdb.DuckDBPyConnection,
    start_date: date,
    end_date: date,
) -> None:
    connection.execute("DELETE FROM dim_date")
    connection.execute(
        """
        INSERT INTO dim_date
        SELECT
            CAST(strftime(d, '%Y%m%d') AS INTEGER) AS date_sk,
            d AS full_date,
            year(d) AS calendar_year,
            CASE WHEN quarter(d) <= 2 THEN 1 ELSE 2 END AS calendar_half_year,
            quarter(d) AS calendar_quarter,
            month(d) AS calendar_month,
            monthname(d) AS calendar_month_name,
            weekofyear(d) AS calendar_week,
            dayofyear(d) AS calendar_day_of_year,
            day(d) AS day_of_month,
            CAST(strftime(d, '%u') AS INTEGER) AS day_of_week,
            dayname(d) AS day_name,
            year(d) AS fiscal_year,
            quarter(d) AS fiscal_quarter,
            CAST(strftime(d, '%u') AS INTEGER) IN (6, 7) AS is_weekend_flag,
            day(d) = 1 AS is_month_start_flag,
            d = last_day(d) AS is_month_end_flag,
            d = date_trunc('quarter', d) AS is_quarter_start_flag,
            d = (
                date_trunc('quarter', d) + INTERVAL '3 MONTHS' - INTERVAL '1 DAY'
            )::DATE AS is_quarter_end_flag,
            d = date_trunc('year', d) AS is_year_start_flag,
            d = make_date(year(d), 12, 31) AS is_year_end_flag,
            FALSE AS is_public_holiday_flag,
            CAST(strftime(d, '%u') AS INTEGER) BETWEEN 1 AND 5 AS banking_business_day_flag,
            CAST(strftime(d, '%u') AS INTEGER) BETWEEN 1 AND 5 AS target2_business_day_flag
        FROM generate_series(?::DATE, ?::DATE, INTERVAL 1 DAY) AS dates(d)
        ORDER BY d
        """,
        [start_date, end_date],
    )
