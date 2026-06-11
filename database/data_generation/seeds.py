from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import astuple, dataclass
from datetime import date, timedelta

import duckdb

from data_generation.config import GeneratorConfig

FIRST_NAMES = (
    "Anna",
    "Leon",
    "Mia",
    "Paul",
    "Emma",
    "Lukas",
    "Lina",
    "Noah",
    "Sophie",
    "Jonas",
    "Clara",
    "Felix",
)

LAST_NAMES = (
    "Mueller",
    "Schmidt",
    "Schneider",
    "Fischer",
    "Weber",
    "Meyer",
    "Wagner",
    "Becker",
    "Hoffmann",
    "Schaefer",
)

COMPANY_PARTS = (
    "Mobility",
    "Logistics",
    "Technik",
    "Consulting",
    "Solutions",
    "Services",
    "Handel",
    "Flottenmanagement",
)

CORPORATE_PREFIXES = (
    "Bavaria",
    "Alpen",
    "Rhein",
    "Nord",
    "Main",
    "Isar",
    "Atlas",
    "Prime",
)

GERMAN_LOCATIONS = (
    ("Muenchen", "BY", "80331"),
    ("Nuernberg", "BY", "90402"),
    ("Augsburg", "BY", "86150"),
    ("Berlin", "BE", "10115"),
    ("Hamburg", "HH", "20095"),
    ("Koeln", "NW", "50667"),
    ("Frankfurt", "HE", "60311"),
    ("Stuttgart", "BW", "70173"),
    ("Leipzig", "SN", "04109"),
    ("Duesseldorf", "NW", "40213"),
)

AT_CH_LOCATIONS = (
    ("Wien", "AT", "AT-1010"),
    ("Salzburg", "AT", "AT-5020"),
    ("Zuerich", "CH", "CH-8001"),
    ("Basel", "CH", "CH-4001"),
)

CUSTOMER_CHANNELS = ("BRANCH", "ONLINE", "PHONE", "DEALER")
RETAIL_EMPLOYMENT_STATUSES = (
    "EMPLOYED",
    "SELF_EMPLOYED",
    "CIVIL_SERVANT",
    "RETIRED",
    "STUDENT",
)
CUSTOMER_RISK_CLASSES = ("LOW", "MEDIUM", "HIGH")
DEALER_TYPES = ("Franchise", "Independent", "Captive Branch")
DEALER_STATUSES = ("Active", "Watchlist", "Restricted", "Terminated")
DEALER_RISK_RATINGS = ("LOW", "MODERATE", "ELEVATED", "HIGH")
ACCOUNT_INFLOW_PROFILES = ("SALARY", "MIXED", "CORPORATE")
ACCOUNT_OUTFLOW_PROFILES = ("HOUSEHOLD", "FLEET", "PREMIUM")
VEHICLE_COLORS = (
    "Black Sapphire",
    "Alpine White",
    "Skyscraper Grey",
    "Midnight Blue",
    "British Racing Green",
)
VEHICLE_LINES = ("Base", "Sport", "M Sport", "Luxury", "JCW", "Signature")


@dataclass(frozen=True, slots=True)
class VehicleTemplate:
    manufacturer_name: str
    brand_name: str
    model_name: str
    body_type_code: str
    vehicle_class_code: str
    fuel_type_code: str
    drivetrain_code: str
    transmission_type_code: str
    engine_power_kw: int
    battery_capacity_kwh: float | None
    electric_range_wltp_km: int | None
    co2_emissions_g_km: float | None
    list_price_gross_min: int
    list_price_gross_max: int


VEHICLE_TEMPLATES: tuple[VehicleTemplate, ...] = (
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "1 Series",
        "Hatchback",
        "COMPACT",
        "Petrol",
        "RWD",
        "Automatic",
        100,
        None,
        None,
        128.0,
        33000,
        41000,
    ),
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "2 Series Gran Coupe",
        "Sedan",
        "COMPACT",
        "Petrol",
        "FWD",
        "Automatic",
        103,
        None,
        None,
        132.0,
        39000,
        47000,
    ),
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "2 Series Active Tourer",
        "MPV",
        "COMPACT",
        "PHEV",
        "FWD",
        "Automatic",
        110,
        14.2,
        82,
        22.0,
        41000,
        49000,
    ),
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "3 Series",
        "Sedan",
        "MID",
        "Diesel",
        "RWD",
        "Automatic",
        140,
        None,
        None,
        126.0,
        46000,
        61000,
    ),
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "4 Series Gran Coupe",
        "Sedan",
        "MID",
        "Petrol",
        "RWD",
        "Automatic",
        135,
        None,
        None,
        138.0,
        52000,
        68000,
    ),
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "5 Series",
        "Sedan",
        "EXECUTIVE",
        "PHEV",
        "RWD",
        "Automatic",
        160,
        18.7,
        95,
        18.0,
        61000,
        82000,
    ),
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "7 Series",
        "Sedan",
        "LUXURY",
        "PHEV",
        "AWD",
        "Automatic",
        220,
        20.0,
        85,
        22.0,
        98000,
        145000,
    ),
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "X1",
        "SUV",
        "COMPACT_SUV",
        "Petrol",
        "FWD",
        "Automatic",
        110,
        None,
        None,
        142.0,
        41000,
        52000,
    ),
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "X2",
        "SUV",
        "COMPACT_SUV",
        "Petrol",
        "FWD",
        "Automatic",
        125,
        None,
        None,
        149.0,
        43000,
        55000,
    ),
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "X3",
        "SUV",
        "MID_SUV",
        "Diesel",
        "AWD",
        "Automatic",
        145,
        None,
        None,
        154.0,
        56000,
        74000,
    ),
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "X4",
        "SUV",
        "MID_SUV",
        "Diesel",
        "AWD",
        "Automatic",
        160,
        None,
        None,
        162.0,
        62000,
        79000,
    ),
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "X5",
        "SUV",
        "LARGE_SUV",
        "PHEV",
        "AWD",
        "Automatic",
        230,
        25.7,
        100,
        20.0,
        86000,
        118000,
    ),
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "X6",
        "SUV",
        "LARGE_SUV",
        "Petrol",
        "AWD",
        "Automatic",
        250,
        None,
        None,
        198.0,
        92000,
        126000,
    ),
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "X7",
        "SUV",
        "LARGE_SUV",
        "Diesel",
        "AWD",
        "Automatic",
        250,
        None,
        None,
        186.0,
        98000,
        138000,
    ),
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "i4",
        "Sedan",
        "MID_EV",
        "BEV",
        "RWD",
        "Direct Drive",
        210,
        83.9,
        590,
        0.0,
        59000,
        76000,
    ),
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "i5",
        "Sedan",
        "EXECUTIVE_EV",
        "BEV",
        "RWD",
        "Direct Drive",
        250,
        81.2,
        580,
        0.0,
        72000,
        93000,
    ),
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "i7",
        "Sedan",
        "LUXURY_EV",
        "BEV",
        "AWD",
        "Direct Drive",
        330,
        101.7,
        625,
        0.0,
        128000,
        172000,
    ),
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "iX1",
        "SUV",
        "COMPACT_SUV_EV",
        "BEV",
        "AWD",
        "Direct Drive",
        230,
        64.7,
        438,
        0.0,
        56000,
        69000,
    ),
    VehicleTemplate(
        "BMW AG",
        "BMW",
        "iX",
        "SUV",
        "LARGE_SUV_EV",
        "BEV",
        "AWD",
        "Direct Drive",
        300,
        111.5,
        620,
        0.0,
        94000,
        132000,
    ),
    VehicleTemplate(
        "BMW AG",
        "MINI",
        "Cooper 3 Door",
        "Hatchback",
        "COMPACT",
        "Petrol",
        "FWD",
        "Automatic",
        100,
        None,
        None,
        121.0,
        29000,
        37000,
    ),
    VehicleTemplate(
        "BMW AG",
        "MINI",
        "Cooper 5 Door",
        "Hatchback",
        "COMPACT",
        "Petrol",
        "FWD",
        "Automatic",
        100,
        None,
        None,
        124.0,
        30000,
        39000,
    ),
    VehicleTemplate(
        "BMW AG",
        "MINI",
        "Cooper Convertible",
        "Convertible",
        "COMPACT",
        "Petrol",
        "FWD",
        "Automatic",
        110,
        None,
        None,
        129.0,
        35000,
        43000,
    ),
    VehicleTemplate(
        "BMW AG",
        "MINI",
        "Cooper Electric",
        "Hatchback",
        "COMPACT_EV",
        "BEV",
        "FWD",
        "Direct Drive",
        135,
        40.7,
        402,
        0.0,
        36000,
        45000,
    ),
    VehicleTemplate(
        "BMW AG",
        "MINI",
        "Aceman",
        "SUV",
        "COMPACT_EV",
        "BEV",
        "FWD",
        "Direct Drive",
        140,
        54.2,
        405,
        0.0,
        39000,
        47000,
    ),
    VehicleTemplate(
        "BMW AG",
        "MINI",
        "Clubman",
        "Hatchback",
        "COMPACT",
        "Petrol",
        "AWD",
        "Automatic",
        130,
        None,
        None,
        146.0,
        38000,
        47000,
    ),
    VehicleTemplate(
        "BMW AG",
        "MINI",
        "Countryman",
        "SUV",
        "COMPACT_SUV",
        "Petrol",
        "AWD",
        "Automatic",
        125,
        None,
        None,
        152.0,
        39000,
        50000,
    ),
    VehicleTemplate(
        "BMW AG",
        "MINI",
        "Countryman SE",
        "SUV",
        "COMPACT_SUV_EV",
        "BEV",
        "AWD",
        "Direct Drive",
        190,
        64.6,
        433,
        0.0,
        47000,
        59000,
    ),
    VehicleTemplate(
        "BMW AG",
        "MINI",
        "John Cooper Works",
        "Hatchback",
        "SPORT",
        "Petrol",
        "AWD",
        "Automatic",
        170,
        None,
        None,
        161.0,
        41000,
        52000,
    ),
    VehicleTemplate(
        "Rolls-Royce Motor Cars",
        "Rolls-Royce",
        "Ghost",
        "Sedan",
        "ULTRA_LUXURY",
        "Petrol",
        "AWD",
        "Automatic",
        420,
        None,
        None,
        285.0,
        310000,
        390000,
    ),
    VehicleTemplate(
        "Rolls-Royce Motor Cars",
        "Rolls-Royce",
        "Cullinan",
        "SUV",
        "ULTRA_LUXURY_SUV",
        "Petrol",
        "AWD",
        "Automatic",
        420,
        None,
        None,
        305.0,
        340000,
        430000,
    ),
    VehicleTemplate(
        "Rolls-Royce Motor Cars",
        "Rolls-Royce",
        "Spectre",
        "Sedan",
        "ULTRA_LUXURY_EV",
        "BEV",
        "AWD",
        "Direct Drive",
        430,
        102.0,
        520,
        0.0,
        390000,
        480000,
    ),
    VehicleTemplate(
        "AUDI AG",
        "Audi",
        "A6",
        "Sedan",
        "EXECUTIVE",
        "Diesel",
        "AWD",
        "Automatic",
        150,
        None,
        None,
        149.0,
        57000,
        76000,
    ),
    VehicleTemplate(
        "AUDI AG",
        "Audi",
        "Q4 e-tron",
        "SUV",
        "COMPACT_SUV_EV",
        "BEV",
        "AWD",
        "Direct Drive",
        210,
        76.6,
        510,
        0.0,
        56000,
        70000,
    ),
    VehicleTemplate(
        "Mercedes-Benz AG",
        "Mercedes-Benz",
        "C-Class",
        "Sedan",
        "EXECUTIVE",
        "Petrol",
        "RWD",
        "Automatic",
        150,
        None,
        None,
        141.0,
        54000,
        72000,
    ),
    VehicleTemplate(
        "Mercedes-Benz AG",
        "Mercedes-Benz",
        "EQA",
        "SUV",
        "COMPACT_SUV_EV",
        "BEV",
        "AWD",
        "Direct Drive",
        215,
        70.5,
        495,
        0.0,
        57000,
        71000,
    ),
)

VEHICLE_TEMPLATE_WEIGHTS: tuple[int, ...] = tuple(
    9
    if template.brand_name in {"BMW", "MINI"}
    else 2
    if template.brand_name == "Rolls-Royce"
    else 3
    for template in VEHICLE_TEMPLATES
)


@dataclass(frozen=True, slots=True)
class CustomerSeed:
    customer_id: str
    customer_type_code: str
    internal_profile_code: str
    scenario_code: str | None
    scenario_group_id: str | None
    noise_seed: int
    first_name: str | None
    last_name: str | None
    legal_entity_name: str | None
    date_of_birth: date | None
    gender_code: str | None
    nationality_code: str
    country_of_residence_code: str
    postal_code: str
    city: str
    federal_state_code: str | None
    employment_status_code: str | None
    annual_income_gross: float
    monthly_income_net: float
    credit_score_nominal: int
    risk_class_code: str
    consent_marketing_flag: bool
    preferred_channel_code: str
    scd_version_target: int


@dataclass(frozen=True, slots=True)
class DealerSeed:
    dealer_id: str
    dealer_name: str
    legal_entity_name: str
    dealer_type_code: str
    country_code: str
    postal_code: str
    city: str
    sales_region_code: str
    risk_rating_code: str
    dealer_status_code: str
    onboarding_date: date
    termination_date: date | None
    scd_version_target: int
    scenario_code: str | None
    scenario_group_id: str | None
    noise_seed: int
    dormant_dealer_flag: bool
    preferred_brand_mix: str
    high_ltv_focus_flag: bool


@dataclass(frozen=True, slots=True)
class VehicleSeed:
    vehicle_id: str
    vin: str
    manufacturer_name: str
    brand_name: str
    model_name: str
    model_variant_name: str
    body_type_code: str
    vehicle_class_code: str
    production_year: int
    model_year: int
    first_registration_date: date
    fuel_type_code: str
    drivetrain_code: str
    transmission_type_code: str
    engine_power_kw: int
    battery_capacity_kwh: float | None
    electric_range_wltp_km: int | None
    co2_emissions_g_km: float | None
    list_price_gross: float
    list_price_net: float
    color_exterior_name: str
    equipment_line_name: str
    asset_condition_code: str
    warranty_months: int
    reuse_target_count: int
    scenario_code: str | None
    scenario_group_id: str | None
    noise_seed: int


@dataclass(frozen=True, slots=True)
class ContractSeed:
    contract_id: str
    contract_type_code: str
    customer_id: str
    dealer_id: str
    vehicle_id: str
    product_id: str
    booking_date: date
    start_date: date
    end_date: date
    maturity_date: date
    target_status_code: str
    currency_code: str
    contract_term_months: int
    financed_amount_net: float
    financed_amount_gross: float
    down_payment_gross: float
    monthly_payment_gross: float
    residual_value_nominal: float | None
    balloon_payment_nominal: float | None
    interest_rate_nominal: float
    ltv_ratio: float
    scenario_code: str | None
    scenario_group_id: str | None
    noise_seed: int
    late_payment_flag: bool
    missed_payment_flag: bool
    reversal_flag: bool
    fx_flag: bool
    blocked_account_flag: bool
    overdraft_flag: bool
    high_ltv_flag: bool
    default_flag: bool
    refinance_flag: bool


@dataclass(frozen=True, slots=True)
class AccountSeed:
    banking_account_id: str
    customer_id: str
    product_id: str
    open_date: date
    close_date: date | None
    snapshot_start_date: date
    base_balance_net: float
    monthly_inflow_base: float
    monthly_outflow_base: float
    authorized_overdraft_limit_net: float
    blocked_amount_base: float
    inflow_profile_code: str
    outflow_profile_code: str
    scenario_code: str | None
    scenario_group_id: str | None
    noise_seed: int
    blocked_account_flag: bool
    overdraft_flag: bool
    fx_flag: bool


def populate_seed_staging(
    connection: duckdb.DuckDBPyConnection,
    config: GeneratorConfig,
) -> None:
    randomizer = random.Random(config.seed)
    _create_staging_tables(connection)

    customers = _build_customer_seeds(config, randomizer)
    dealers = _build_dealer_seeds(config, randomizer)
    vehicles = _build_vehicle_seeds(config, randomizer)
    contracts = _build_contract_seeds(config, randomizer, customers, dealers, vehicles)
    accounts = _build_account_seeds(config, randomizer, customers, contracts)

    _insert_rows(connection, "stg_customer_seed", customers)
    _insert_rows(connection, "stg_dealer_seed", dealers)
    _insert_rows(connection, "stg_vehicle_seed", vehicles)
    _insert_rows(connection, "stg_contract_seed", contracts)
    _insert_rows(connection, "stg_account_seed", accounts)


def _create_staging_tables(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute("DROP TABLE IF EXISTS stg_account_seed")
    connection.execute("DROP TABLE IF EXISTS stg_contract_seed")
    connection.execute("DROP TABLE IF EXISTS stg_vehicle_seed")
    connection.execute("DROP TABLE IF EXISTS stg_dealer_seed")
    connection.execute("DROP TABLE IF EXISTS stg_customer_seed")
    connection.execute(
        """
        CREATE TABLE stg_customer_seed (
            customer_id VARCHAR PRIMARY KEY,
            customer_type_code VARCHAR NOT NULL,
            internal_profile_code VARCHAR NOT NULL,
            scenario_code VARCHAR,
            scenario_group_id VARCHAR,
            noise_seed INTEGER NOT NULL,
            first_name VARCHAR,
            last_name VARCHAR,
            legal_entity_name VARCHAR,
            date_of_birth DATE,
            gender_code VARCHAR,
            nationality_code VARCHAR NOT NULL,
            country_of_residence_code VARCHAR NOT NULL,
            postal_code VARCHAR NOT NULL,
            city VARCHAR NOT NULL,
            federal_state_code VARCHAR,
            employment_status_code VARCHAR,
            annual_income_gross DECIMAL(18, 2) NOT NULL,
            monthly_income_net DECIMAL(18, 2) NOT NULL,
            credit_score_nominal INTEGER NOT NULL,
            risk_class_code VARCHAR NOT NULL,
            consent_marketing_flag BOOLEAN NOT NULL,
            preferred_channel_code VARCHAR NOT NULL,
            scd_version_target INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE stg_dealer_seed (
            dealer_id VARCHAR PRIMARY KEY,
            dealer_name VARCHAR NOT NULL,
            legal_entity_name VARCHAR NOT NULL,
            dealer_type_code VARCHAR NOT NULL,
            country_code VARCHAR NOT NULL,
            postal_code VARCHAR NOT NULL,
            city VARCHAR NOT NULL,
            sales_region_code VARCHAR NOT NULL,
            risk_rating_code VARCHAR NOT NULL,
            dealer_status_code VARCHAR NOT NULL,
            onboarding_date DATE NOT NULL,
            termination_date DATE,
            scd_version_target INTEGER NOT NULL,
            scenario_code VARCHAR,
            scenario_group_id VARCHAR,
            noise_seed INTEGER NOT NULL,
            dormant_dealer_flag BOOLEAN NOT NULL,
            preferred_brand_mix VARCHAR NOT NULL,
            high_ltv_focus_flag BOOLEAN NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE stg_vehicle_seed (
            vehicle_id VARCHAR PRIMARY KEY,
            vin VARCHAR NOT NULL,
            manufacturer_name VARCHAR NOT NULL,
            brand_name VARCHAR NOT NULL,
            model_name VARCHAR NOT NULL,
            model_variant_name VARCHAR NOT NULL,
            body_type_code VARCHAR NOT NULL,
            vehicle_class_code VARCHAR NOT NULL,
            production_year INTEGER NOT NULL,
            model_year INTEGER NOT NULL,
            first_registration_date DATE NOT NULL,
            fuel_type_code VARCHAR NOT NULL,
            drivetrain_code VARCHAR NOT NULL,
            transmission_type_code VARCHAR NOT NULL,
            engine_power_kw INTEGER NOT NULL,
            battery_capacity_kwh DECIMAL(10, 2),
            electric_range_wltp_km INTEGER,
            co2_emissions_g_km DECIMAL(10, 2),
            list_price_gross DECIMAL(18, 2) NOT NULL,
            list_price_net DECIMAL(18, 2) NOT NULL,
            color_exterior_name VARCHAR NOT NULL,
            equipment_line_name VARCHAR NOT NULL,
            asset_condition_code VARCHAR NOT NULL,
            warranty_months INTEGER NOT NULL,
            reuse_target_count INTEGER NOT NULL,
            scenario_code VARCHAR,
            scenario_group_id VARCHAR,
            noise_seed INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE stg_contract_seed (
            contract_id VARCHAR PRIMARY KEY,
            contract_type_code VARCHAR NOT NULL,
            customer_id VARCHAR NOT NULL,
            dealer_id VARCHAR NOT NULL,
            vehicle_id VARCHAR NOT NULL,
            product_id VARCHAR NOT NULL,
            booking_date DATE NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            maturity_date DATE NOT NULL,
            target_status_code VARCHAR NOT NULL,
            currency_code VARCHAR NOT NULL,
            contract_term_months INTEGER NOT NULL,
            financed_amount_net DECIMAL(18, 2) NOT NULL,
            financed_amount_gross DECIMAL(18, 2) NOT NULL,
            down_payment_gross DECIMAL(18, 2) NOT NULL,
            monthly_payment_gross DECIMAL(18, 2) NOT NULL,
            residual_value_nominal DECIMAL(18, 2),
            balloon_payment_nominal DECIMAL(18, 2),
            interest_rate_nominal DECIMAL(9, 6) NOT NULL,
            ltv_ratio DECIMAL(9, 6) NOT NULL,
            scenario_code VARCHAR,
            scenario_group_id VARCHAR,
            noise_seed INTEGER NOT NULL,
            late_payment_flag BOOLEAN NOT NULL,
            missed_payment_flag BOOLEAN NOT NULL,
            reversal_flag BOOLEAN NOT NULL,
            fx_flag BOOLEAN NOT NULL,
            blocked_account_flag BOOLEAN NOT NULL,
            overdraft_flag BOOLEAN NOT NULL,
            high_ltv_flag BOOLEAN NOT NULL,
            default_flag BOOLEAN NOT NULL,
            refinance_flag BOOLEAN NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE stg_account_seed (
            banking_account_id VARCHAR PRIMARY KEY,
            customer_id VARCHAR NOT NULL,
            product_id VARCHAR NOT NULL,
            open_date DATE NOT NULL,
            close_date DATE,
            snapshot_start_date DATE NOT NULL,
            base_balance_net DECIMAL(18, 2) NOT NULL,
            monthly_inflow_base DECIMAL(18, 2) NOT NULL,
            monthly_outflow_base DECIMAL(18, 2) NOT NULL,
            authorized_overdraft_limit_net DECIMAL(18, 2) NOT NULL,
            blocked_amount_base DECIMAL(18, 2) NOT NULL,
            inflow_profile_code VARCHAR NOT NULL,
            outflow_profile_code VARCHAR NOT NULL,
            scenario_code VARCHAR,
            scenario_group_id VARCHAR,
            noise_seed INTEGER NOT NULL,
            blocked_account_flag BOOLEAN NOT NULL,
            overdraft_flag BOOLEAN NOT NULL,
            fx_flag BOOLEAN NOT NULL
        )
        """
    )


def _insert_rows(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    rows: Sequence[object],
) -> None:
    if not rows:
        return
    placeholder_sql = ", ".join(["?"] * len(astuple(rows[0])))
    connection.executemany(
        f"INSERT INTO {table_name} VALUES ({placeholder_sql})",
        [astuple(row) for row in rows],
    )


def _build_customer_seeds(
    config: GeneratorConfig,
    randomizer: random.Random,
) -> list[CustomerSeed]:
    count = config.scale.customers
    version_targets = _build_version_targets(count, one_version_share=0.82, two_version_share=0.15)
    customers: list[CustomerSeed] = []
    bavaria_corporate_count = max(3, count // 35)

    for index in range(count):
        customer_id = f"CUST-{index + 1:05d}"
        noise_seed = config.seed * 1000 + index
        vip_cutoff = max(1, round(count * 0.04))
        corporate_cutoff = vip_cutoff + max(1, round(count * 0.10))

        if index < vip_cutoff:
            customer_type_code = "VIP"
            internal_profile_code = "VIP_PREMIUM"
        elif index < corporate_cutoff:
            customer_type_code = "Corporate"
            internal_profile_code = ("SME", "FLEET", "LARGE_CORPORATE")[index % 3]
        else:
            customer_type_code = "Retail"
            internal_profile_code = RETAIL_EMPLOYMENT_STATUSES[
                index % len(RETAIL_EMPLOYMENT_STATUSES)
            ]

        if customer_type_code == "Corporate" and index < vip_cutoff + bavaria_corporate_count:
            city, state, postal_code = GERMAN_LOCATIONS[index % 3]
            scenario_code = "BAVARIA_CORPORATE_ACTIVE_LEASING"
            scenario_group_id = f"SG-BC-{index + 1:03d}"
            country_code = "DE"
        else:
            if index % 11 == 0:
                ext_city, country_code, postal_code = AT_CH_LOCATIONS[index % len(AT_CH_LOCATIONS)]
                city = ext_city
                state = None
            else:
                city, state, postal_code = GERMAN_LOCATIONS[index % len(GERMAN_LOCATIONS)]
                country_code = "DE"
            scenario_code = None
            scenario_group_id = None

        if customer_type_code == "Corporate":
            legal_entity_name = (
                f"{CORPORATE_PREFIXES[index % len(CORPORATE_PREFIXES)]} "
                f"{COMPANY_PARTS[index % len(COMPANY_PARTS)]} GmbH"
            )
            annual_income = float(220000 + (index % 9) * 75000)
            monthly_income = round(annual_income / 14, 2)
            first_name = None
            last_name = None
            birth_date = None
            gender_code = None
            employment_status = None
            consent = False
        else:
            first_name = FIRST_NAMES[index % len(FIRST_NAMES)]
            last_name = LAST_NAMES[(index * 3) % len(LAST_NAMES)]
            legal_entity_name = None
            birth_date = date(1959 + (index % 35), (index % 12) + 1, (index % 27) + 1)
            gender_code = ("F", "M")[index % 2]
            employment_status = internal_profile_code if customer_type_code == "Retail" else None
            annual_income = float(
                38000 + (index % 8) * 11000 + (22000 if customer_type_code == "VIP" else 0)
            )
            monthly_income = round(annual_income * 0.58 / 12, 2)
            consent = customer_type_code != "VIP"

        credit_score = 780 - (index % 7) * 25 - (40 if customer_type_code == "Corporate" else 0)
        risk_class = CUSTOMER_RISK_CLASSES[
            min(len(CUSTOMER_RISK_CLASSES) - 1, max(0, (800 - credit_score) // 75))
        ]
        scd_version_target = version_targets[index]
        if customer_type_code == "Corporate":
            scd_version_target = max(scd_version_target, 2 if index % 4 else 3)

        customers.append(
            CustomerSeed(
                customer_id=customer_id,
                customer_type_code=customer_type_code,
                internal_profile_code=internal_profile_code,
                scenario_code=scenario_code,
                scenario_group_id=scenario_group_id,
                noise_seed=noise_seed,
                first_name=first_name,
                last_name=last_name,
                legal_entity_name=legal_entity_name,
                date_of_birth=birth_date,
                gender_code=gender_code,
                nationality_code="DE",
                country_of_residence_code=country_code,
                postal_code=postal_code,
                city=city,
                federal_state_code=state,
                employment_status_code=employment_status,
                annual_income_gross=round(annual_income, 2),
                monthly_income_net=monthly_income,
                credit_score_nominal=credit_score,
                risk_class_code=risk_class,
                consent_marketing_flag=consent,
                preferred_channel_code=CUSTOMER_CHANNELS[index % len(CUSTOMER_CHANNELS)],
                scd_version_target=scd_version_target,
            )
        )

    randomizer.shuffle(customers)
    return customers


def _build_dealer_seeds(
    config: GeneratorConfig,
    randomizer: random.Random,
) -> list[DealerSeed]:
    count = config.scale.dealers
    version_targets = _build_version_targets(count, one_version_share=0.88, two_version_share=0.10)
    dealers: list[DealerSeed] = []
    dormant_count = max(1, count // 12)
    no_origination_count = max(1, count // 10)
    high_ltv_count = max(2, count // 8)

    for index in range(count):
        dealer_id = f"DEAL-{index + 1:04d}"
        city, state, postal_code = GERMAN_LOCATIONS[index % len(GERMAN_LOCATIONS)]
        country_code = "DE"
        if index % 13 == 0:
            alt_city, country_code, postal_code = AT_CH_LOCATIONS[index % len(AT_CH_LOCATIONS)]
            city = alt_city
            state = country_code

        dealer_type = DEALER_TYPES[index % len(DEALER_TYPES)]
        status = "Active"
        scenario_code = None
        scenario_group_id = None
        dormant_flag = False
        high_ltv_focus = False
        termination_date = None

        if index < dormant_count:
            dealer_type = "Franchise"
            scenario_code = "DORMANT_FRANCHISE_BEV_DEALER"
            scenario_group_id = f"SG-DD-{index + 1:03d}"
            dormant_flag = True
        elif index < dormant_count + no_origination_count:
            scenario_code = "ACTIVE_WITHOUT_ORIGINATIONS"
            scenario_group_id = f"SG-AO-{index + 1:03d}"
        elif index < dormant_count + no_origination_count + high_ltv_count:
            dealer_type = "Independent"
            scenario_code = "INDEPENDENT_HIGH_LTV"
            scenario_group_id = f"SG-HL-{index + 1:03d}"
            high_ltv_focus = True
            status = "Watchlist" if index % 3 == 0 else "Active"
        elif index % 17 == 0:
            status = "Restricted"
        elif index % 29 == 0:
            status = "Terminated"
            termination_date = date(2024, ((index % 12) + 1), min(28, (index % 27) + 1))

        preferred_brand_mix = (
            "BMW/MINI"
            if dealer_type == "Franchise"
            else "PREMIUM_MULTI_BRAND"
            if dealer_type == "Independent"
            else "BMW_CAPTIVE"
        )

        dealers.append(
            DealerSeed(
                dealer_id=dealer_id,
                dealer_name=f"{city} {preferred_brand_mix} Center",
                legal_entity_name=f"{city} Mobility Partner GmbH",
                dealer_type_code=dealer_type,
                country_code=country_code,
                postal_code=postal_code,
                city=city,
                sales_region_code=state or country_code,
                risk_rating_code=DEALER_RISK_RATINGS[index % len(DEALER_RISK_RATINGS)],
                dealer_status_code=status,
                onboarding_date=date(
                    2018 + (index % 5), ((index % 12) + 1), min(28, (index % 27) + 1)
                ),
                termination_date=termination_date,
                scd_version_target=version_targets[index],
                scenario_code=scenario_code,
                scenario_group_id=scenario_group_id,
                noise_seed=config.seed * 2000 + index,
                dormant_dealer_flag=dormant_flag,
                preferred_brand_mix=preferred_brand_mix,
                high_ltv_focus_flag=high_ltv_focus,
            )
        )

    randomizer.shuffle(dealers)
    return dealers


def _build_vehicle_seeds(
    config: GeneratorConfig,
    randomizer: random.Random,
) -> list[VehicleSeed]:
    vehicles: list[VehicleSeed] = []
    reused_vehicle_count = max(1, round(config.scale.vehicles * 0.10))

    for index in range(config.scale.vehicles):
        template = randomizer.choices(VEHICLE_TEMPLATES, weights=VEHICLE_TEMPLATE_WEIGHTS, k=1)[0]
        noise_seed = config.seed * 3000 + index
        production_year = 2018 + (index % 8)
        if template.fuel_type_code == "BEV":
            production_year = max(2021, production_year)
        first_registration = date(production_year, ((index % 12) + 1), min(28, (index % 27) + 1))
        list_price_gross = float(
            template.list_price_gross_min
            + ((noise_seed % 100) / 100)
            * (template.list_price_gross_max - template.list_price_gross_min)
        )
        asset_condition_code = "USED" if index % 7 == 0 else "NEW"

        scenario_code = None
        scenario_group_id = None
        if template.brand_name == "Rolls-Royce":
            scenario_code = "ULTRA_LUXURY_OUTLIER"
        elif template.fuel_type_code == "BEV" and index < reused_vehicle_count:
            scenario_code = "BEV_REUSE_POOL"
            scenario_group_id = f"SG-BR-{index + 1:03d}"

        vehicles.append(
            VehicleSeed(
                vehicle_id=f"VEH-{index + 1:05d}",
                vin=f"WBA{noise_seed:014d}"[-17:],
                manufacturer_name=template.manufacturer_name,
                brand_name=template.brand_name,
                model_name=template.model_name,
                model_variant_name=(
                    f"{template.model_name} {VEHICLE_LINES[index % len(VEHICLE_LINES)]}"
                ),
                body_type_code=template.body_type_code,
                vehicle_class_code=template.vehicle_class_code,
                production_year=production_year,
                model_year=production_year,
                first_registration_date=first_registration,
                fuel_type_code=template.fuel_type_code,
                drivetrain_code=template.drivetrain_code,
                transmission_type_code=template.transmission_type_code,
                engine_power_kw=template.engine_power_kw + (index % 4) * 5,
                battery_capacity_kwh=template.battery_capacity_kwh,
                electric_range_wltp_km=template.electric_range_wltp_km,
                co2_emissions_g_km=template.co2_emissions_g_km,
                list_price_gross=round(list_price_gross, 2),
                list_price_net=round(list_price_gross / 1.19, 2),
                color_exterior_name=VEHICLE_COLORS[index % len(VEHICLE_COLORS)],
                equipment_line_name=VEHICLE_LINES[index % len(VEHICLE_LINES)],
                asset_condition_code=asset_condition_code,
                warranty_months=24 if asset_condition_code == "USED" else 36,
                reuse_target_count=2 if index < reused_vehicle_count else 1,
                scenario_code=scenario_code,
                scenario_group_id=scenario_group_id,
                noise_seed=noise_seed,
            )
        )

    return vehicles


def _build_contract_seeds(
    config: GeneratorConfig,
    randomizer: random.Random,
    customers: Sequence[CustomerSeed],
    dealers: Sequence[DealerSeed],
    vehicles: Sequence[VehicleSeed],
) -> list[ContractSeed]:
    contracts: list[ContractSeed] = []
    total_contracts = config.scale.leasing_contracts + config.scale.loan_contracts
    vehicles_by_id = {vehicle.vehicle_id: vehicle for vehicle in vehicles}
    vehicle_ids = [vehicle.vehicle_id for vehicle in vehicles]
    reuse_vehicle_ids = [
        vehicle.vehicle_id for vehicle in vehicles if vehicle.reuse_target_count > 1
    ]
    assignable_dealers = [
        dealer for dealer in dealers if dealer.scenario_code != "ACTIVE_WITHOUT_ORIGINATIONS"
    ]
    independent_high_ltv_dealers = [dealer for dealer in dealers if dealer.high_ltv_focus_flag]
    corporate_customers = [
        customer for customer in customers if customer.customer_type_code == "Corporate"
    ]
    migration_customers = [
        customer for customer in corporate_customers if customer.scd_version_target > 2
    ]
    retail_like_customers = [
        customer for customer in customers if customer.customer_type_code != "Corporate"
    ]
    account_risk_customers = [
        customer for customer in customers if customer.customer_type_code != "Corporate"
    ]
    bavaria_count = max(3, len(corporate_customers) // 2)
    returned_with_follow_count = min(
        len(reuse_vehicle_ids) // 2, max(2, config.scale.leasing_contracts // 30)
    )
    returned_without_follow_count = min(
        max(0, len(reuse_vehicle_ids) - returned_with_follow_count),
        max(2, config.scale.leasing_contracts // 40),
    )
    migration_loan_count = max(2, config.scale.loan_contracts // 30)
    returned_with_follow_vehicle_ids = reuse_vehicle_ids[:returned_with_follow_count]
    returned_without_follow_vehicle_ids = reuse_vehicle_ids[
        returned_with_follow_count : returned_with_follow_count + returned_without_follow_count
    ]

    for index in range(total_contracts):
        contract_type = "LEASING" if index < config.scale.leasing_contracts else "LOAN"
        leasing_index = index
        loan_index = index - config.scale.leasing_contracts
        contract_number = index + 1
        vehicle_id = (
            vehicle_ids[index]
            if index < len(vehicle_ids)
            else reuse_vehicle_ids[(index - len(vehicle_ids)) % len(reuse_vehicle_ids)]
        )
        contract_start = _deterministic_contract_start(index)
        term_months = _choose_term_months(contract_type, index)
        maturity_date = add_months(contract_start, term_months)
        booking_date = contract_start - timedelta(days=7 + (index % 9))
        dealer_pool = assignable_dealers
        customer_pool = retail_like_customers
        product_id = "LEASE_CLASSIC_DE" if contract_type == "LEASING" else "LOAN_CLASSIC_DE"
        scenario_code = None
        scenario_group_id = None
        target_status = "ACTIVE"
        late_flag = index % 9 == 0
        missed_flag = index % 19 == 0
        reversal_flag = index % 23 == 0
        fx_flag = index % 27 == 0
        blocked_account_flag = index % 13 == 0
        overdraft_flag = index % 11 == 0
        high_ltv_flag = False
        default_flag = False
        refinance_flag = False

        if contract_type == "LEASING" and corporate_customers and leasing_index < bavaria_count:
            customer_pool = corporate_customers
            scenario_code = "BAVARIA_CORPORATE_ACTIVE_LEASING"
            scenario_group_id = f"SG-BC-{leasing_index + 1:03d}"
            target_status = "ACTIVE"
        elif (
            contract_type == "LEASING"
            and leasing_index < bavaria_count + returned_with_follow_count
        ):
            vehicle_id = returned_with_follow_vehicle_ids[leasing_index - bavaria_count]
            scenario_code = "LEASE_RETURN_2023_WITH_REUSE"
            scenario_group_id = f"SG-LR-{leasing_index - bavaria_count + 1:03d}"
            target_status = "CLOSED"
            contract_start = date(
                2021, ((leasing_index % 12) + 1), min(28, (leasing_index % 27) + 1)
            )
            maturity_date = date(2023, 2 + (leasing_index % 10), min(28, 6 + (leasing_index % 18)))
            booking_date = contract_start - timedelta(days=10)
        elif (
            contract_type == "LEASING"
            and leasing_index
            < bavaria_count + returned_with_follow_count + returned_without_follow_count
        ):
            vehicle_id = returned_without_follow_vehicle_ids[
                leasing_index - bavaria_count - returned_with_follow_count
            ]
            scenario_code = "LEASE_RETURN_2023_NO_FOLLOWUP"
            scenario_group_id = (
                f"SG-RN-{leasing_index - bavaria_count - returned_with_follow_count + 1:03d}"
            )
            target_status = "CLOSED"
            contract_start = date(
                2021, ((leasing_index % 12) + 1), min(28, (leasing_index % 27) + 1)
            )
            maturity_date = date(2023, 3 + (leasing_index % 9), min(28, 5 + (leasing_index % 20)))
            booking_date = contract_start - timedelta(days=10)
        elif contract_type == "LOAN" and loan_index < returned_with_follow_count:
            vehicle_id = returned_with_follow_vehicle_ids[loan_index]
            scenario_code = "SAME_MODEL_REFINANCING"
            scenario_group_id = f"SG-RF-{loan_index + 1:03d}"
            refinance_flag = True
            target_status = "ACTIVE"
            product_id = "LOAN_BALLOON_DE"
            contract_start = date(2024, ((loan_index % 12) + 1), min(28, 5 + (loan_index % 18)))
            maturity_date = add_months(contract_start, term_months)
            booking_date = contract_start - timedelta(days=8)
        elif (
            contract_type == "LOAN"
            and loan_index < returned_with_follow_count + migration_loan_count
        ):
            customer_pool = migration_customers or corporate_customers
            scenario_code = "LOW_TO_HIGH_RISK_MIGRATION"
            scenario_group_id = f"SG-RM-{loan_index - returned_with_follow_count + 1:03d}"
            target_status = "ACTIVE"
            contract_start = date(2021, ((loan_index % 12) + 1), min(28, 7 + (loan_index % 14)))
            maturity_date = add_months(contract_start, term_months)
            booking_date = contract_start - timedelta(days=9)
        elif contract_type == "LOAN" and independent_high_ltv_dealers and index % 7 == 0:
            dealer_pool = independent_high_ltv_dealers
            scenario_code = "HIGH_LTV_INDEPENDENT_LOAN"
            scenario_group_id = f"SG-HL-{index + 1:03d}"
            high_ltv_flag = True
            target_status = "ACTIVE"
        elif contract_type == "LOAN" and vehicle_id in reuse_vehicle_ids and index % 5 == 1:
            scenario_code = "SAME_MODEL_REFINANCING"
            scenario_group_id = f"SG-RF-{index + 1:03d}"
            refinance_flag = True
            target_status = "ACTIVE"
            product_id = "LOAN_BALLOON_DE"
        elif contract_type == "LOAN" and index % 17 == 0:
            scenario_code = "THREE_MISSED_INSTALLMENTS"
            scenario_group_id = f"SG-MI-{index + 1:03d}"
            missed_flag = True
            default_flag = True
            target_status = "DEFAULT"
        elif contract_type == "LEASING" and index % 21 == 0:
            scenario_code = "LATE_FEE_COLLECTION"
            scenario_group_id = f"SG-LF-{index + 1:03d}"
            late_flag = True
            target_status = "ACTIVE"
        elif contract_type == "LOAN" and index % 31 == 0:
            scenario_code = "BEV_REPOSSESSION"
            scenario_group_id = f"SG-BD-{index + 1:03d}"
            default_flag = True
            target_status = "REPOSSESSED"

        customer = customer_pool[index % len(customer_pool)]
        dealer = dealer_pool[index % len(dealer_pool)]
        vehicle = vehicles_by_id[vehicle_id]
        financed_amount_gross = round(vehicle.list_price_gross * (0.74 + (index % 10) * 0.02), 2)
        down_payment = round(financed_amount_gross * (0.08 + (index % 4) * 0.03), 2)
        financed_amount_net = round(financed_amount_gross / 1.19, 2)
        if high_ltv_flag:
            down_payment = round(financed_amount_gross * 0.03, 2)
        ltv_ratio = round((financed_amount_gross - down_payment) / vehicle.list_price_gross, 4)
        monthly_payment = round(
            (financed_amount_gross - down_payment) / max(term_months, 1) * 1.02, 2
        )
        residual_value = (
            round(vehicle.list_price_gross * 0.38, 2) if contract_type == "LEASING" else None
        )
        balloon_payment = (
            round(vehicle.list_price_gross * 0.27, 2) if product_id == "LOAN_BALLOON_DE" else None
        )
        interest_rate = round(0.019 + (index % 9) * 0.004 + (0.012 if high_ltv_flag else 0), 6)
        maturity_date = min(maturity_date, config.date_end)

        contracts.append(
            ContractSeed(
                contract_id=f"CTR-{contract_number:06d}",
                contract_type_code=contract_type,
                customer_id=customer.customer_id,
                dealer_id=dealer.dealer_id,
                vehicle_id=vehicle_id,
                product_id=product_id
                if contract_type == "LOAN"
                else (
                    "LEASE_FLEET_DE"
                    if customer.customer_type_code == "Corporate"
                    else "LEASE_CLASSIC_DE"
                ),
                booking_date=booking_date,
                start_date=contract_start,
                end_date=maturity_date,
                maturity_date=maturity_date,
                target_status_code=target_status,
                currency_code="EUR",
                contract_term_months=term_months,
                financed_amount_net=financed_amount_net,
                financed_amount_gross=financed_amount_gross,
                down_payment_gross=down_payment,
                monthly_payment_gross=monthly_payment,
                residual_value_nominal=residual_value,
                balloon_payment_nominal=balloon_payment,
                interest_rate_nominal=interest_rate,
                ltv_ratio=ltv_ratio,
                scenario_code=scenario_code,
                scenario_group_id=scenario_group_id,
                noise_seed=config.seed * 4000 + index,
                late_payment_flag=late_flag,
                missed_payment_flag=missed_flag,
                reversal_flag=reversal_flag,
                fx_flag=fx_flag,
                blocked_account_flag=blocked_account_flag,
                overdraft_flag=overdraft_flag,
                high_ltv_flag=high_ltv_flag,
                default_flag=default_flag,
                refinance_flag=refinance_flag,
            )
        )

    if account_risk_customers and contracts:
        first_risky_customer = account_risk_customers[0].customer_id
        for index, contract in enumerate(contracts):
            if contract.contract_type_code == "LOAN":
                contracts[index] = ContractSeed(
                    contract_id=contract.contract_id,
                    contract_type_code=contract.contract_type_code,
                    customer_id=first_risky_customer,
                    dealer_id=contract.dealer_id,
                    vehicle_id=contract.vehicle_id,
                    product_id=contract.product_id,
                    booking_date=contract.booking_date,
                    start_date=contract.start_date,
                    end_date=contract.end_date,
                    maturity_date=contract.maturity_date,
                    target_status_code=contract.target_status_code,
                    currency_code=contract.currency_code,
                    contract_term_months=contract.contract_term_months,
                    financed_amount_net=contract.financed_amount_net,
                    financed_amount_gross=contract.financed_amount_gross,
                    down_payment_gross=contract.down_payment_gross,
                    monthly_payment_gross=contract.monthly_payment_gross,
                    residual_value_nominal=contract.residual_value_nominal,
                    balloon_payment_nominal=contract.balloon_payment_nominal,
                    interest_rate_nominal=contract.interest_rate_nominal,
                    ltv_ratio=contract.ltv_ratio,
                    scenario_code=contract.scenario_code,
                    scenario_group_id=contract.scenario_group_id,
                    noise_seed=contract.noise_seed,
                    late_payment_flag=contract.late_payment_flag,
                    missed_payment_flag=contract.missed_payment_flag,
                    reversal_flag=contract.reversal_flag,
                    fx_flag=contract.fx_flag,
                    blocked_account_flag=True,
                    overdraft_flag=contract.overdraft_flag,
                    high_ltv_flag=contract.high_ltv_flag,
                    default_flag=contract.default_flag,
                    refinance_flag=contract.refinance_flag,
                )
                break

    return contracts


def _build_account_seeds(
    config: GeneratorConfig,
    randomizer: random.Random,
    customers: Sequence[CustomerSeed],
    contracts: Sequence[ContractSeed],
) -> list[AccountSeed]:
    accounts: list[AccountSeed] = []
    blocked_count = max(3, config.scale.account_seeds // 12)
    overdraft_count = max(4, config.scale.account_seeds // 10)
    migration_customer_ids = list(
        dict.fromkeys(
            contract.customer_id
            for contract in contracts
            if contract.scenario_code == "LOW_TO_HIGH_RISK_MIGRATION"
        )
    )
    active_loan_customer_ids = list(
        dict.fromkeys(
            contract.customer_id
            for contract in contracts
            if contract.contract_type_code == "LOAN" and contract.target_status_code == "ACTIVE"
        )
    )
    priority_customer_ids = migration_customer_ids + [
        customer_id
        for customer_id in active_loan_customer_ids
        if customer_id not in migration_customer_ids
    ]
    customers_by_id = {customer.customer_id: customer for customer in customers}

    for index in range(config.scale.account_seeds):
        preferred_customer_id = None
        if priority_customer_ids and index < min(
            len(priority_customer_ids), config.scale.account_seeds
        ):
            preferred_customer_id = priority_customer_ids[index]
        customer = (
            customers_by_id[preferred_customer_id]
            if preferred_customer_id is not None
            else customers[index % len(customers)]
        )
        business_customer = customer.customer_type_code == "Corporate"
        product_id = "ACCOUNT_BUSINESS_DE" if business_customer else "ACCOUNT_CURRENT_DE"
        open_date = max(
            config.banking_snapshot_start - timedelta(days=250),
            date(2022, 1, 1) + timedelta(days=(index % 400)),
        )
        if customer.customer_id in migration_customer_ids:
            open_date = max(open_date, date(2025, 7, 1) + timedelta(days=(index % 60)))
        scenario_code = None
        scenario_group_id = None
        blocked_flag = index < blocked_count
        overdraft_flag = index < overdraft_count or index % 9 == 0
        fx_flag = index % 17 == 0

        if blocked_flag and overdraft_flag:
            scenario_code = "BLOCKED_AND_OVERDRAFT_ACCOUNT"
            scenario_group_id = f"SG-BA-{index + 1:03d}"
        elif blocked_flag:
            scenario_code = "BLOCKED_AMOUNT_ACCOUNT"
            scenario_group_id = f"SG-BL-{index + 1:03d}"
        elif overdraft_flag:
            scenario_code = "NEGATIVE_AVAILABLE_BALANCE"
            scenario_group_id = f"SG-OD-{index + 1:03d}"

        inflow_profile = (
            "CORPORATE"
            if business_customer
            else ACCOUNT_INFLOW_PROFILES[index % len(ACCOUNT_INFLOW_PROFILES)]
        )
        outflow_profile = (
            "FLEET"
            if business_customer
            else ACCOUNT_OUTFLOW_PROFILES[index % len(ACCOUNT_OUTFLOW_PROFILES)]
        )
        if overdraft_flag and not business_customer:
            base_balance = float(850 + (index % 4) * 180)
            monthly_inflow = round(base_balance * 1.45, 2)
            monthly_outflow = round(base_balance * 2.55, 2)
        else:
            base_balance = (
                float(18000 + (index % 7) * 3500)
                if business_customer
                else float(1800 + (index % 9) * 700)
            )
            monthly_inflow = round(base_balance * (0.55 if business_customer else 1.25), 2)
            monthly_outflow = round(base_balance * (0.52 if business_customer else 1.18), 2)
        overdraft_limit = 25000.0 if business_customer else 1500.0
        blocked_amount = round(base_balance * 0.35, 2) if blocked_flag else 0.0
        close_date = None if index % 8 else config.date_end - timedelta(days=(index % 60))

        accounts.append(
            AccountSeed(
                banking_account_id=f"ACC-{index + 1:05d}",
                customer_id=customer.customer_id,
                product_id=product_id,
                open_date=open_date,
                close_date=close_date,
                snapshot_start_date=config.banking_snapshot_start,
                base_balance_net=round(base_balance, 2),
                monthly_inflow_base=monthly_inflow,
                monthly_outflow_base=monthly_outflow,
                authorized_overdraft_limit_net=overdraft_limit,
                blocked_amount_base=blocked_amount,
                inflow_profile_code=inflow_profile,
                outflow_profile_code=outflow_profile,
                scenario_code=scenario_code,
                scenario_group_id=scenario_group_id,
                noise_seed=config.seed * 5000 + index,
                blocked_account_flag=blocked_flag,
                overdraft_flag=overdraft_flag,
                fx_flag=fx_flag,
            )
        )

    randomizer.shuffle(accounts)
    return accounts


def _build_version_targets(
    count: int,
    one_version_share: float,
    two_version_share: float,
) -> list[int]:
    one_version_count = round(count * one_version_share)
    two_version_count = round(count * two_version_share)
    three_version_count = max(0, count - one_version_count - two_version_count)
    targets = [1] * one_version_count + [2] * two_version_count + [3] * three_version_count
    if len(targets) < count:
        targets.extend([1] * (count - len(targets)))
    return targets[:count]


def _choose_term_months(contract_type: str, index: int) -> int:
    options = (24, 30, 36, 42, 48) if contract_type == "LEASING" else (24, 36, 48, 60, 72)
    return options[index % len(options)]


def _deterministic_contract_start(index: int) -> date:
    base = date(2019, 1, 15)
    return base + timedelta(days=(index * 7) % 2800)


def add_months(value: date, months: int) -> date:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    month_lengths = (31, 29 if _is_leap_year(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    day = min(value.day, month_lengths[month - 1])
    return date(year, month, day)


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
