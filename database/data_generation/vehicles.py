from __future__ import annotations

import duckdb


def populate_dim_vehicle(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute("DELETE FROM dim_vehicle")
    connection.execute(
        """
        INSERT INTO dim_vehicle
        SELECT
            ROW_NUMBER() OVER (ORDER BY vehicle_id) AS vehicle_sk,
            vehicle_id,
            vin,
            manufacturer_name,
            brand_name,
            model_name,
            model_variant_name,
            body_type_code,
            vehicle_class_code,
            production_year,
            model_year,
            first_registration_date,
            fuel_type_code,
            drivetrain_code,
            transmission_type_code,
            engine_power_kw,
            battery_capacity_kwh,
            electric_range_wltp_km,
            co2_emissions_g_km,
            list_price_gross,
            list_price_net,
            color_exterior_name,
            equipment_line_name,
            asset_condition_code,
            warranty_months
        FROM stg_vehicle_seed
        ORDER BY vehicle_id
        """
    )
