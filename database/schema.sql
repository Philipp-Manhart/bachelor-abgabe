-- Automotive banking data warehouse star schema for DuckDB.
-- This script creates table structures, keys, and metadata comments only.
-- It intentionally contains no data-loading statements or synthetic data generation.

DROP TABLE IF EXISTS fact_payment_transactions;
DROP TABLE IF EXISTS fact_contract_cashflows;
DROP TABLE IF EXISTS fact_banking_accounts;
DROP TABLE IF EXISTS fact_contract_status_history;
DROP TABLE IF EXISTS fact_loan_contracts;
DROP TABLE IF EXISTS fact_leasing_contracts;
DROP TABLE IF EXISTS dim_cashflow_type;
DROP TABLE IF EXISTS dim_contract_status;
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_dealer;
DROP TABLE IF EXISTS dim_vehicle;
DROP TABLE IF EXISTS dim_customer;
DROP TABLE IF EXISTS dim_date;

CREATE TABLE dim_customer (
    customer_sk BIGINT PRIMARY KEY,
    customer_id VARCHAR NOT NULL,
    customer_type_code VARCHAR NOT NULL,
    legal_entity_name VARCHAR,
    first_name VARCHAR,
    last_name VARCHAR,
    date_of_birth DATE,
    gender_code VARCHAR,
    nationality_code VARCHAR,
    country_of_residence_code VARCHAR,
    postal_code VARCHAR,
    city VARCHAR,
    federal_state_code VARCHAR,
    employment_status_code VARCHAR,
    annual_income_gross DECIMAL(18, 2),
    monthly_income_net DECIMAL(18, 2),
    credit_score_nominal INTEGER,
    risk_class_code VARCHAR,
    consent_marketing_flag BOOLEAN,
    preferred_channel_code VARCHAR,
    valid_from_date DATE NOT NULL,
    valid_to_date DATE,
    is_current_record BOOLEAN NOT NULL
);

CREATE TABLE dim_vehicle (
    vehicle_sk BIGINT PRIMARY KEY,
    vehicle_id VARCHAR NOT NULL,
    vin VARCHAR,
    manufacturer_name VARCHAR NOT NULL,
    brand_name VARCHAR NOT NULL,
    model_name VARCHAR NOT NULL,
    model_variant_name VARCHAR,
    body_type_code VARCHAR,
    vehicle_class_code VARCHAR,
    production_year INTEGER,
    model_year INTEGER,
    first_registration_date DATE,
    fuel_type_code VARCHAR,
    drivetrain_code VARCHAR,
    transmission_type_code VARCHAR,
    engine_power_kw INTEGER,
    battery_capacity_kwh DECIMAL(10, 2),
    electric_range_wltp_km INTEGER,
    co2_emissions_g_km DECIMAL(10, 2),
    list_price_gross DECIMAL(18, 2),
    list_price_net DECIMAL(18, 2),
    color_exterior_name VARCHAR,
    equipment_line_name VARCHAR,
    asset_condition_code VARCHAR,
    warranty_months INTEGER
);

CREATE TABLE dim_dealer (
    dealer_sk BIGINT PRIMARY KEY,
    dealer_id VARCHAR NOT NULL,
    dealer_name VARCHAR NOT NULL,
    legal_entity_name VARCHAR,
    dealer_type_code VARCHAR,
    country_code VARCHAR NOT NULL,
    postal_code VARCHAR,
    city VARCHAR,
    sales_region_code VARCHAR,
    risk_rating_code VARCHAR,
    dealer_status_code VARCHAR,
    onboarding_date DATE,
    termination_date DATE,
    valid_from_date DATE NOT NULL,
    valid_to_date DATE,
    is_current_record BOOLEAN NOT NULL
);

CREATE TABLE dim_product (
    product_sk BIGINT PRIMARY KEY,
    product_id VARCHAR NOT NULL,
    product_family_code VARCHAR NOT NULL,
    product_type_code VARCHAR NOT NULL,
    product_name VARCHAR NOT NULL,
    currency_code VARCHAR NOT NULL,
    market_country_code VARCHAR NOT NULL,
    min_term_months INTEGER,
    max_term_months INTEGER,
    regulatory_product_class_code VARCHAR,
    residual_value_policy_code VARCHAR,
    balloon_payment_allowed_flag BOOLEAN,
    early_termination_allowed_flag BOOLEAN,
    insurance_bundle_flag BOOLEAN,
    maintenance_bundle_flag BOOLEAN,
    product_status_code VARCHAR,
    catalog_launch_date DATE,
    catalog_phase_out_date DATE
);

CREATE TABLE dim_contract_status (
    contract_status_sk BIGINT PRIMARY KEY,
    status_code VARCHAR NOT NULL,
    status_name VARCHAR NOT NULL,
    status_group_code VARCHAR NOT NULL,
    lifecycle_stage_code VARCHAR NOT NULL,
    is_active_flag BOOLEAN NOT NULL,
    is_signed_flag BOOLEAN NOT NULL,
    is_disbursed_flag BOOLEAN NOT NULL,
    is_performing_flag BOOLEAN NOT NULL,
    is_delinquent_flag BOOLEAN NOT NULL,
    is_defaulted_flag BOOLEAN NOT NULL,
    is_closed_flag BOOLEAN NOT NULL,
    is_cancelled_flag BOOLEAN NOT NULL,
    is_restructured_flag BOOLEAN NOT NULL,
    is_repossessed_flag BOOLEAN NOT NULL,
    dpd_bucket_min INTEGER,
    dpd_bucket_max INTEGER,
    collection_stage_code VARCHAR
);

CREATE TABLE dim_cashflow_type (
    cashflow_type_sk BIGINT PRIMARY KEY,
    cashflow_type_code VARCHAR NOT NULL,
    cashflow_type_name VARCHAR NOT NULL,
    cashflow_class_code VARCHAR NOT NULL,
    cashflow_party_role_code VARCHAR NOT NULL,
    is_inflow_flag BOOLEAN NOT NULL,
    is_customer_cashflow_flag BOOLEAN NOT NULL,
    is_dealer_cashflow_flag BOOLEAN NOT NULL,
    is_vehicle_cost_flag BOOLEAN NOT NULL,
    is_principal_component_flag BOOLEAN NOT NULL,
    is_interest_component_flag BOOLEAN NOT NULL,
    is_fee_component_flag BOOLEAN NOT NULL,
    is_tax_relevant_flag BOOLEAN NOT NULL,
    is_recurring_flag BOOLEAN NOT NULL,
    is_planned_flag BOOLEAN NOT NULL
);

CREATE TABLE dim_date (
    date_sk INTEGER PRIMARY KEY,
    full_date DATE NOT NULL,
    calendar_year INTEGER NOT NULL,
    calendar_half_year INTEGER NOT NULL,
    calendar_quarter INTEGER NOT NULL,
    calendar_month INTEGER NOT NULL,
    calendar_month_name VARCHAR NOT NULL,
    calendar_week INTEGER NOT NULL,
    calendar_day_of_year INTEGER NOT NULL,
    day_of_month INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL,
    day_name VARCHAR NOT NULL,
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter INTEGER NOT NULL,
    is_weekend_flag BOOLEAN NOT NULL,
    is_month_start_flag BOOLEAN NOT NULL,
    is_month_end_flag BOOLEAN NOT NULL,
    is_quarter_start_flag BOOLEAN NOT NULL,
    is_quarter_end_flag BOOLEAN NOT NULL,
    is_year_start_flag BOOLEAN NOT NULL,
    is_year_end_flag BOOLEAN NOT NULL,
    is_public_holiday_flag BOOLEAN NOT NULL,
    banking_business_day_flag BOOLEAN NOT NULL,
    target2_business_day_flag BOOLEAN NOT NULL
);

CREATE TABLE fact_leasing_contracts (
    leasing_contract_sk BIGINT PRIMARY KEY,
    leasing_contract_id VARCHAR NOT NULL,
    customer_sk BIGINT NOT NULL REFERENCES dim_customer(customer_sk),
    vehicle_sk BIGINT NOT NULL REFERENCES dim_vehicle(vehicle_sk),
    dealer_sk BIGINT NOT NULL REFERENCES dim_dealer(dealer_sk),
    product_sk BIGINT NOT NULL REFERENCES dim_product(product_sk),
    contract_status_sk BIGINT NOT NULL REFERENCES dim_contract_status(contract_status_sk),
    contract_start_date_sk INTEGER NOT NULL REFERENCES dim_date(date_sk),
    contract_end_date_sk INTEGER NOT NULL REFERENCES dim_date(date_sk),
    booking_date_sk INTEGER NOT NULL REFERENCES dim_date(date_sk),
    maturity_date_sk INTEGER REFERENCES dim_date(date_sk),
    actual_end_date_sk INTEGER REFERENCES dim_date(date_sk),
    vehicle_return_date_sk INTEGER REFERENCES dim_date(date_sk),
    early_termination_flag BOOLEAN,
    termination_reason_code VARCHAR,
    contract_term_months INTEGER NOT NULL,
    agreed_annual_mileage_km INTEGER,
    financed_amount_net DECIMAL(18, 2),
    financed_amount_gross DECIMAL(18, 2),
    down_payment_gross DECIMAL(18, 2),
    monthly_payment_net DECIMAL(18, 2),
    monthly_payment_gross DECIMAL(18, 2),
    residual_value_nominal DECIMAL(18, 2),
    residual_value_effective DECIMAL(18, 2),
    interest_rate_nominal DECIMAL(9, 6),
    interest_rate_effective DECIMAL(9, 6),
    service_fee_net DECIMAL(18, 2),
    insurance_fee_gross DECIMAL(18, 2),
    currency_code VARCHAR NOT NULL
);

CREATE TABLE fact_loan_contracts (
    loan_contract_sk BIGINT PRIMARY KEY,
    loan_contract_id VARCHAR NOT NULL,
    customer_sk BIGINT NOT NULL REFERENCES dim_customer(customer_sk),
    vehicle_sk BIGINT NOT NULL REFERENCES dim_vehicle(vehicle_sk),
    dealer_sk BIGINT NOT NULL REFERENCES dim_dealer(dealer_sk),
    product_sk BIGINT NOT NULL REFERENCES dim_product(product_sk),
    contract_status_sk BIGINT NOT NULL REFERENCES dim_contract_status(contract_status_sk),
    origination_date_sk INTEGER NOT NULL REFERENCES dim_date(date_sk),
    first_payment_date_sk INTEGER REFERENCES dim_date(date_sk),
    maturity_date_sk INTEGER NOT NULL REFERENCES dim_date(date_sk),
    booking_date_sk INTEGER NOT NULL REFERENCES dim_date(date_sk),
    actual_end_date_sk INTEGER REFERENCES dim_date(date_sk),
    vehicle_return_date_sk INTEGER REFERENCES dim_date(date_sk),
    early_termination_flag BOOLEAN,
    termination_reason_code VARCHAR,
    loan_term_months INTEGER NOT NULL,
    financed_amount_net DECIMAL(18, 2),
    financed_amount_gross DECIMAL(18, 2),
    down_payment_gross DECIMAL(18, 2),
    balloon_payment_nominal DECIMAL(18, 2),
    monthly_installment_net DECIMAL(18, 2),
    monthly_installment_gross DECIMAL(18, 2),
    interest_rate_nominal DECIMAL(9, 6),
    annual_percentage_rate_effective DECIMAL(9, 6),
    loan_to_value_effective DECIMAL(9, 6),
    currency_code VARCHAR NOT NULL
);

CREATE TABLE fact_contract_status_history (
    status_history_sk BIGINT PRIMARY KEY,
    leasing_contract_sk BIGINT REFERENCES fact_leasing_contracts(leasing_contract_sk),
    loan_contract_sk BIGINT REFERENCES fact_loan_contracts(loan_contract_sk),
    contract_status_sk BIGINT NOT NULL REFERENCES dim_contract_status(contract_status_sk),
    valid_from_date_sk INTEGER NOT NULL REFERENCES dim_date(date_sk),
    valid_to_date_sk INTEGER REFERENCES dim_date(date_sk),
    is_current_status BOOLEAN NOT NULL
);

CREATE TABLE fact_banking_accounts (
    banking_account_sk BIGINT PRIMARY KEY,
    banking_account_id VARCHAR NOT NULL,
    customer_sk BIGINT NOT NULL REFERENCES dim_customer(customer_sk),
    product_sk BIGINT NOT NULL REFERENCES dim_product(product_sk),
    contract_status_sk BIGINT NOT NULL REFERENCES dim_contract_status(contract_status_sk),
    account_open_date_sk INTEGER NOT NULL REFERENCES dim_date(date_sk),
    account_close_date_sk INTEGER REFERENCES dim_date(date_sk),
    snapshot_date_sk INTEGER NOT NULL REFERENCES dim_date(date_sk),
    iban_hash VARCHAR,
    account_currency_code VARCHAR NOT NULL,
    credit_limit_nominal DECIMAL(18, 2),
    authorized_overdraft_limit_net DECIMAL(18, 2),
    current_balance_net DECIMAL(18, 2),
    current_balance_gross DECIMAL(18, 2),
    available_balance_effective DECIMAL(18, 2),
    average_balance_30d_net DECIMAL(18, 2),
    average_balance_90d_net DECIMAL(18, 2),
    interest_rate_nominal DECIMAL(9, 6),
    interest_rate_effective DECIMAL(9, 6),
    fee_income_month_to_date_net DECIMAL(18, 2),
    fee_income_year_to_date_gross DECIMAL(18, 2),
    overdraft_days_month_to_date INTEGER,
    blocked_amount_effective DECIMAL(18, 2)
);

CREATE TABLE fact_contract_cashflows (
    contract_cashflow_sk BIGINT PRIMARY KEY,
    contract_cashflow_id VARCHAR NOT NULL,
    cashflow_type_sk BIGINT NOT NULL REFERENCES dim_cashflow_type(cashflow_type_sk),
    customer_sk BIGINT NOT NULL REFERENCES dim_customer(customer_sk),
    vehicle_sk BIGINT REFERENCES dim_vehicle(vehicle_sk),
    dealer_sk BIGINT REFERENCES dim_dealer(dealer_sk),
    product_sk BIGINT NOT NULL REFERENCES dim_product(product_sk),
    contract_status_sk BIGINT NOT NULL REFERENCES dim_contract_status(contract_status_sk),
    due_date_sk INTEGER NOT NULL REFERENCES dim_date(date_sk),
    related_leasing_contract_sk BIGINT REFERENCES fact_leasing_contracts(leasing_contract_sk),
    related_loan_contract_sk BIGINT REFERENCES fact_loan_contracts(loan_contract_sk),
    related_banking_account_sk BIGINT REFERENCES fact_banking_accounts(banking_account_sk),
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
    currency_code VARCHAR NOT NULL
);

CREATE TABLE fact_payment_transactions (
    payment_transaction_sk BIGINT PRIMARY KEY,
    payment_transaction_id VARCHAR NOT NULL,
    customer_sk BIGINT NOT NULL REFERENCES dim_customer(customer_sk),
    cashflow_type_sk BIGINT REFERENCES dim_cashflow_type(cashflow_type_sk),
    product_sk BIGINT REFERENCES dim_product(product_sk),
    contract_status_sk BIGINT REFERENCES dim_contract_status(contract_status_sk),
    transaction_date_sk INTEGER NOT NULL REFERENCES dim_date(date_sk),
    value_date_sk INTEGER REFERENCES dim_date(date_sk),
    booking_date_sk INTEGER NOT NULL REFERENCES dim_date(date_sk),
    related_leasing_contract_sk BIGINT REFERENCES fact_leasing_contracts(leasing_contract_sk),
    related_loan_contract_sk BIGINT REFERENCES fact_loan_contracts(loan_contract_sk),
    related_banking_account_sk BIGINT REFERENCES fact_banking_accounts(banking_account_sk),
    related_contract_cashflow_sk BIGINT REFERENCES fact_contract_cashflows(contract_cashflow_sk),
    reverses_payment_transaction_sk BIGINT REFERENCES fact_payment_transactions(payment_transaction_sk),
    transaction_type_code VARCHAR NOT NULL,
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
    currency_code VARCHAR NOT NULL
);

COMMENT ON TABLE dim_customer IS 'SCD Type 2 customer dimension for private and business automotive-bank customers; contains no facts and preserves historical attribute versions.';
COMMENT ON COLUMN dim_customer.customer_sk IS 'Surrogate primary key for the historized customer record version.';
COMMENT ON COLUMN dim_customer.customer_id IS 'Stable business key for the customer across source systems and historical versions.';
COMMENT ON COLUMN dim_customer.customer_type_code IS 'Customer type, generated values include Retail, Corporate, and VIP. Business customer wording maps to Corporate; do not use a literal Business value.';
COMMENT ON COLUMN dim_customer.legal_entity_name IS 'Registered legal entity name for corporate or business customers.';
COMMENT ON COLUMN dim_customer.first_name IS 'Given name for natural-person customers.';
COMMENT ON COLUMN dim_customer.last_name IS 'Family name for natural-person customers.';
COMMENT ON COLUMN dim_customer.date_of_birth IS 'Birth date for age and eligibility analysis; analytical queries must calculate age from this date.';
COMMENT ON COLUMN dim_customer.gender_code IS 'Optional gender code as delivered by the source under applicable consent rules.';
COMMENT ON COLUMN dim_customer.nationality_code IS 'ISO-style nationality code for risk and compliance segmentation.';
COMMENT ON COLUMN dim_customer.country_of_residence_code IS 'Country of tax or ordinary residence.';
COMMENT ON COLUMN dim_customer.postal_code IS 'Postal code of the primary customer address.';
COMMENT ON COLUMN dim_customer.city IS 'City of the primary customer address.';
COMMENT ON COLUMN dim_customer.federal_state_code IS 'Regional state or province code for location analysis.';
COMMENT ON COLUMN dim_customer.employment_status_code IS 'Employment status used in underwriting and affordability models.';
COMMENT ON COLUMN dim_customer.annual_income_gross IS 'Annual income before taxes and deductions; suffix intentionally marks gross amount ambiguity.';
COMMENT ON COLUMN dim_customer.monthly_income_net IS 'Monthly income after deductions; suffix intentionally marks net amount ambiguity.';
COMMENT ON COLUMN dim_customer.credit_score_nominal IS 'Nominal credit score from the selected scoring provider.';
COMMENT ON COLUMN dim_customer.risk_class_code IS 'Internal underwriting risk class. Generated values are A, B, C, D, and E; risk severity increases alphabetically, so A is the best class and E is the riskiest class.';
COMMENT ON COLUMN dim_customer.consent_marketing_flag IS 'Whether the customer has active marketing consent.';
COMMENT ON COLUMN dim_customer.preferred_channel_code IS 'Preferred servicing or sales channel.';
COMMENT ON COLUMN dim_customer.valid_from_date IS 'SCD2 start date for this customer attribute version.';
COMMENT ON COLUMN dim_customer.valid_to_date IS 'SCD2 end date for this customer attribute version; null means open-ended.';
COMMENT ON COLUMN dim_customer.is_current_record IS 'True if this is the current SCD2 customer version; queries for current customers must filter on this flag.';

COMMENT ON TABLE dim_vehicle IS 'Vehicle asset dimension for financed or leased vehicles, including technical, valuation, and residual-value attributes.';
COMMENT ON COLUMN dim_vehicle.vehicle_sk IS 'Surrogate primary key for the vehicle dimension.';
COMMENT ON COLUMN dim_vehicle.vehicle_id IS 'Business key for the vehicle or asset record.';
COMMENT ON COLUMN dim_vehicle.vin IS 'Vehicle identification number when available.';
COMMENT ON COLUMN dim_vehicle.manufacturer_name IS 'Original equipment manufacturer name.';
COMMENT ON COLUMN dim_vehicle.brand_name IS 'Commercial vehicle brand.';
COMMENT ON COLUMN dim_vehicle.model_name IS 'Vehicle model name.';
COMMENT ON COLUMN dim_vehicle.model_variant_name IS 'Detailed model variant or trim descriptor.';
COMMENT ON COLUMN dim_vehicle.body_type_code IS 'Body type such as SUV, sedan, wagon, van, or coupe.';
COMMENT ON COLUMN dim_vehicle.vehicle_class_code IS 'Vehicle class used by the bank for product and risk analytics.';
COMMENT ON COLUMN dim_vehicle.production_year IS 'Calendar year of production.';
COMMENT ON COLUMN dim_vehicle.model_year IS 'Manufacturer model year.';
COMMENT ON COLUMN dim_vehicle.first_registration_date IS 'Date of first registration.';
COMMENT ON COLUMN dim_vehicle.fuel_type_code IS 'Fuel or energy type. Generated values use exact uppercase codes such as BEV and PHEV; battery-electric vehicle wording maps to fuel_type_code = ''BEV''. Do not infer BEV from battery_capacity_kwh alone.';
COMMENT ON COLUMN dim_vehicle.drivetrain_code IS 'Drivetrain type such as FWD, RWD, AWD, or 4x4.';
COMMENT ON COLUMN dim_vehicle.transmission_type_code IS 'Transmission type such as manual, automatic, or direct drive.';
COMMENT ON COLUMN dim_vehicle.engine_power_kw IS 'Engine or motor power in kilowatts.';
COMMENT ON COLUMN dim_vehicle.battery_capacity_kwh IS 'Usable or nominal battery capacity in kilowatt hours.';
COMMENT ON COLUMN dim_vehicle.electric_range_wltp_km IS 'WLTP electric driving range in kilometers.';
COMMENT ON COLUMN dim_vehicle.co2_emissions_g_km IS 'CO2 emissions in grams per kilometer.';
COMMENT ON COLUMN dim_vehicle.list_price_gross IS 'Gross manufacturer list price including taxes.';
COMMENT ON COLUMN dim_vehicle.list_price_net IS 'Net manufacturer list price excluding taxes.';
COMMENT ON COLUMN dim_vehicle.color_exterior_name IS 'Exterior color name.';
COMMENT ON COLUMN dim_vehicle.equipment_line_name IS 'Equipment line or package name.';
COMMENT ON COLUMN dim_vehicle.asset_condition_code IS 'Condition code such as new, used, demo, or certified pre-owned.';
COMMENT ON COLUMN dim_vehicle.warranty_months IS 'Warranty period in months.';

COMMENT ON TABLE dim_dealer IS 'Dealer and broker dimension for automotive sales partners, including network, territory, risk, and commission attributes.';
COMMENT ON COLUMN dim_dealer.dealer_sk IS 'Surrogate primary key for the historized dealer record version.';
COMMENT ON COLUMN dim_dealer.dealer_id IS 'Business key for the dealer or broker.';
COMMENT ON COLUMN dim_dealer.dealer_name IS 'Commercial dealer name; use legal_entity_name when the question asks for legal or registered names.';
COMMENT ON COLUMN dim_dealer.legal_entity_name IS 'Registered legal entity of the dealer; use this column for legal dealer names. Legal names can repeat across technical dealer records, so use DISTINCT when the requested output is legal names rather than dealer records.';
COMMENT ON COLUMN dim_dealer.dealer_type_code IS 'Dealer type such as franchise, independent, online broker, or captive branch.';
COMMENT ON COLUMN dim_dealer.country_code IS 'Country of the dealer location.';
COMMENT ON COLUMN dim_dealer.postal_code IS 'Postal code of the dealer location.';
COMMENT ON COLUMN dim_dealer.city IS 'City of the dealer location.';
COMMENT ON COLUMN dim_dealer.sales_region_code IS 'Sales region used for network reporting.';
COMMENT ON COLUMN dim_dealer.risk_rating_code IS 'Internal dealer risk rating. Generated values are LOW, MODERATE, ELEVATED, and HIGH; risk severity increases in that order, so HIGH is the strongest or riskiest rating. Use categorical profiling if exact values are uncertain.';
COMMENT ON COLUMN dim_dealer.dealer_status_code IS 'Operational dealer status. Generated values are case-sensitive labels such as Active, Watchlist, Restricted, and Terminated; active dealer wording maps to dealer_status_code = ''Active''. Do not use this as a synonym for current dealer unless the question explicitly asks for active dealers.';
COMMENT ON COLUMN dim_dealer.onboarding_date IS 'Date on which the dealer was onboarded.';
COMMENT ON COLUMN dim_dealer.termination_date IS 'Date on which the dealer relationship ended.';
COMMENT ON COLUMN dim_dealer.valid_from_date IS 'SCD2 start date for this dealer attribute version.';
COMMENT ON COLUMN dim_dealer.valid_to_date IS 'SCD2 end date for this dealer attribute version; null means open-ended.';
COMMENT ON COLUMN dim_dealer.is_current_record IS 'True if this is the current SCD2 dealer version; queries for current dealers must filter on this flag rather than dealer_status_code unless active operational status is explicitly requested.';

COMMENT ON TABLE dim_product IS 'Product dimension for leasing, loans, accounts, and payment products offered by the automotive bank.';
COMMENT ON COLUMN dim_product.product_sk IS 'Surrogate primary key for the product dimension.';
COMMENT ON COLUMN dim_product.product_id IS 'Business key for the financial product.';
COMMENT ON COLUMN dim_product.product_family_code IS 'Product family such as leasing, loan, deposit, account, or payment.';
COMMENT ON COLUMN dim_product.product_type_code IS 'Detailed product type within the family.';
COMMENT ON COLUMN dim_product.product_name IS 'Human-readable product name.';
COMMENT ON COLUMN dim_product.currency_code IS 'Default product currency.';
COMMENT ON COLUMN dim_product.market_country_code IS 'Market country in which the product is sold.';
COMMENT ON COLUMN dim_product.min_term_months IS 'Minimum catalog term in months.';
COMMENT ON COLUMN dim_product.max_term_months IS 'Maximum catalog term in months.';
COMMENT ON COLUMN dim_product.regulatory_product_class_code IS 'Regulatory product classification used for risk analytics and reporting.';
COMMENT ON COLUMN dim_product.residual_value_policy_code IS 'Residual-value policy applicable to the product.';
COMMENT ON COLUMN dim_product.balloon_payment_allowed_flag IS 'Whether balloon payments are allowed.';
COMMENT ON COLUMN dim_product.early_termination_allowed_flag IS 'Whether early termination is allowed.';
COMMENT ON COLUMN dim_product.insurance_bundle_flag IS 'Whether an insurance bundle is part of the product setup.';
COMMENT ON COLUMN dim_product.maintenance_bundle_flag IS 'Whether maintenance services can be bundled.';
COMMENT ON COLUMN dim_product.product_status_code IS 'Lifecycle status of the product. Generated values use uppercase codes such as ACTIVE; active product wording maps to product_status_code = ''ACTIVE''.';
COMMENT ON COLUMN dim_product.catalog_launch_date IS 'Date when the product became available for sales in the catalog.';
COMMENT ON COLUMN dim_product.catalog_phase_out_date IS 'Date when the product stopped being available for new sales in the catalog.';

COMMENT ON TABLE dim_contract_status IS 'Contract lifecycle status dimension shared by leasing, loan, account, and payment analytics.';
COMMENT ON COLUMN dim_contract_status.contract_status_sk IS 'Surrogate primary key for contract status.';
COMMENT ON COLUMN dim_contract_status.status_code IS 'Business code for the contract status.';
COMMENT ON COLUMN dim_contract_status.status_name IS 'Human-readable status label.';
COMMENT ON COLUMN dim_contract_status.status_group_code IS 'Aggregated status group for reporting.';
COMMENT ON COLUMN dim_contract_status.lifecycle_stage_code IS 'Lifecycle stage such as application, active, collection, closed, or cancelled.';
COMMENT ON COLUMN dim_contract_status.is_active_flag IS 'Whether the status represents an active relationship.';
COMMENT ON COLUMN dim_contract_status.is_signed_flag IS 'Whether the contract has been signed.';
COMMENT ON COLUMN dim_contract_status.is_disbursed_flag IS 'Whether the contract has been paid out or activated financially.';
COMMENT ON COLUMN dim_contract_status.is_performing_flag IS 'Whether the contract is performing.';
COMMENT ON COLUMN dim_contract_status.is_delinquent_flag IS 'Whether the contract is delinquent.';
COMMENT ON COLUMN dim_contract_status.is_defaulted_flag IS 'Whether the contract is defaulted.';
COMMENT ON COLUMN dim_contract_status.is_closed_flag IS 'Whether the contract is closed.';
COMMENT ON COLUMN dim_contract_status.is_cancelled_flag IS 'Whether the contract is cancelled.';
COMMENT ON COLUMN dim_contract_status.is_restructured_flag IS 'Whether the contract has been restructured.';
COMMENT ON COLUMN dim_contract_status.is_repossessed_flag IS 'Whether the underlying vehicle has been repossessed.';
COMMENT ON COLUMN dim_contract_status.dpd_bucket_min IS 'Minimum days past due represented by the status bucket.';
COMMENT ON COLUMN dim_contract_status.dpd_bucket_max IS 'Maximum days past due represented by the status bucket.';
COMMENT ON COLUMN dim_contract_status.collection_stage_code IS 'Collections stage associated with this status. Contracts in collection handling have collection_stage_code IS NOT NULL and collection_stage_code <> ''NONE''.';

COMMENT ON TABLE dim_cashflow_type IS 'Cashflow classification dimension describing the economic purpose of planned contract cashflows and booked payment transactions.';
COMMENT ON COLUMN dim_cashflow_type.cashflow_type_sk IS 'Surrogate primary key for the cashflow type dimension.';
COMMENT ON COLUMN dim_cashflow_type.cashflow_type_code IS 'Business code for a specific cashflow type such as monthly leasing rate, dealer commission, delivery fee, or residual settlement.';
COMMENT ON COLUMN dim_cashflow_type.cashflow_type_name IS 'Human-readable cashflow type name.';
COMMENT ON COLUMN dim_cashflow_type.cashflow_class_code IS 'Higher-level cashflow class such as customer receivable, dealer payout, vehicle cost, tax, fee, interest, or principal.';
COMMENT ON COLUMN dim_cashflow_type.cashflow_party_role_code IS 'Primary economic counterparty role such as customer, dealer, OEM, insurer, tax authority, or bank.';
COMMENT ON COLUMN dim_cashflow_type.is_inflow_flag IS 'True when this cashflow type is an inflow from the bank perspective; false indicates outflow.';
COMMENT ON COLUMN dim_cashflow_type.is_customer_cashflow_flag IS 'Whether this cashflow type is primarily between bank and customer.';
COMMENT ON COLUMN dim_cashflow_type.is_dealer_cashflow_flag IS 'Whether this cashflow type is primarily between bank and dealer.';
COMMENT ON COLUMN dim_cashflow_type.is_vehicle_cost_flag IS 'Whether this cashflow type relates to vehicle acquisition, delivery, residual value, maintenance, or asset handling.';
COMMENT ON COLUMN dim_cashflow_type.is_principal_component_flag IS 'Whether this cashflow type represents principal or capital repayment.';
COMMENT ON COLUMN dim_cashflow_type.is_interest_component_flag IS 'Whether this cashflow type represents interest income or interest expense.';
COMMENT ON COLUMN dim_cashflow_type.is_fee_component_flag IS 'Whether this cashflow type represents a fee, service charge, commission, or operating charge.';
COMMENT ON COLUMN dim_cashflow_type.is_tax_relevant_flag IS 'Whether this cashflow type is relevant for VAT, insurance tax, or other tax reporting.';
COMMENT ON COLUMN dim_cashflow_type.is_recurring_flag IS 'Whether this cashflow type usually repeats according to a payment plan.';
COMMENT ON COLUMN dim_cashflow_type.is_planned_flag IS 'Whether this cashflow type normally originates from a contract schedule rather than only from operational events.';

COMMENT ON TABLE dim_date IS 'Calendar and banking date dimension; intentionally empty until loaded by a later data-generation step.';
COMMENT ON COLUMN dim_date.date_sk IS 'Integer date surrogate key in YYYYMMDD format.';
COMMENT ON COLUMN dim_date.full_date IS 'Calendar date.';
COMMENT ON COLUMN dim_date.calendar_year IS 'Calendar year.';
COMMENT ON COLUMN dim_date.calendar_half_year IS 'Calendar half-year number.';
COMMENT ON COLUMN dim_date.calendar_quarter IS 'Calendar quarter number.';
COMMENT ON COLUMN dim_date.calendar_month IS 'Calendar month number.';
COMMENT ON COLUMN dim_date.calendar_month_name IS 'Calendar month name.';
COMMENT ON COLUMN dim_date.calendar_week IS 'ISO-style calendar week.';
COMMENT ON COLUMN dim_date.calendar_day_of_year IS 'Day number within the calendar year.';
COMMENT ON COLUMN dim_date.day_of_month IS 'Day number within the month.';
COMMENT ON COLUMN dim_date.day_of_week IS 'Day number within the week.';
COMMENT ON COLUMN dim_date.day_name IS 'Day name.';
COMMENT ON COLUMN dim_date.fiscal_year IS 'Fiscal year used by the bank.';
COMMENT ON COLUMN dim_date.fiscal_quarter IS 'Fiscal quarter used by the bank.';
COMMENT ON COLUMN dim_date.is_weekend_flag IS 'Whether the date falls on a weekend.';
COMMENT ON COLUMN dim_date.is_month_start_flag IS 'Whether the date is the first day of a month.';
COMMENT ON COLUMN dim_date.is_month_end_flag IS 'Whether the date is the last day of a month.';
COMMENT ON COLUMN dim_date.is_quarter_start_flag IS 'Whether the date is the first day of a quarter.';
COMMENT ON COLUMN dim_date.is_quarter_end_flag IS 'Whether the date is the last day of a quarter.';
COMMENT ON COLUMN dim_date.is_year_start_flag IS 'Whether the date is the first day of a year.';
COMMENT ON COLUMN dim_date.is_year_end_flag IS 'Whether the date is the last day of a year.';
COMMENT ON COLUMN dim_date.is_public_holiday_flag IS 'Whether the date is a public holiday in the relevant banking calendar.';
COMMENT ON COLUMN dim_date.banking_business_day_flag IS 'Whether the date is a local banking business day.';
COMMENT ON COLUMN dim_date.target2_business_day_flag IS 'Whether the date is a TARGET2 business day.';

COMMENT ON TABLE fact_leasing_contracts IS 'Leasing contract fact table at one row per leasing contract, linked to customer, vehicle, dealer, product, status, and dates.';
COMMENT ON COLUMN fact_leasing_contracts.leasing_contract_sk IS 'Surrogate primary key for the leasing contract fact row.';
COMMENT ON COLUMN fact_leasing_contracts.leasing_contract_id IS 'Business key for the leasing contract.';
COMMENT ON COLUMN fact_leasing_contracts.customer_sk IS 'Foreign key to the historized customer dimension version valid at contract booking time; use for point-in-time customer attributes at origination.';
COMMENT ON COLUMN fact_leasing_contracts.vehicle_sk IS 'Foreign key to the financed or leased vehicle.';
COMMENT ON COLUMN fact_leasing_contracts.dealer_sk IS 'Foreign key to the historized dealer dimension version valid at contract booking time; use for point-in-time dealer attributes at origination.';
COMMENT ON COLUMN fact_leasing_contracts.product_sk IS 'Foreign key to the financial product.';
COMMENT ON COLUMN fact_leasing_contracts.contract_status_sk IS 'Foreign key to the latest known contract lifecycle status for this contract fact row.';
COMMENT ON COLUMN fact_leasing_contracts.contract_start_date_sk IS 'Foreign key to contract start date.';
COMMENT ON COLUMN fact_leasing_contracts.contract_end_date_sk IS 'Foreign key to contractual end date.';
COMMENT ON COLUMN fact_leasing_contracts.booking_date_sk IS 'Foreign key to warehouse booking date.';
COMMENT ON COLUMN fact_leasing_contracts.maturity_date_sk IS 'Foreign key to maturity date.';
COMMENT ON COLUMN fact_leasing_contracts.actual_end_date_sk IS 'Foreign key to the actual contract end date; null means the contract has not actually ended yet.';
COMMENT ON COLUMN fact_leasing_contracts.vehicle_return_date_sk IS 'Foreign key to the date on which the leased vehicle was physically returned or recovered; null means no return has been recorded.';
COMMENT ON COLUMN fact_leasing_contracts.early_termination_flag IS 'True when the leasing contract ended before contractual maturity.';
COMMENT ON COLUMN fact_leasing_contracts.termination_reason_code IS 'Business reason for actual contract termination, such as maturity, early termination, total loss, theft, default, or repossession.';
COMMENT ON COLUMN fact_leasing_contracts.contract_term_months IS 'Contractual leasing term in months.';
COMMENT ON COLUMN fact_leasing_contracts.agreed_annual_mileage_km IS 'Agreed annual mileage in kilometers.';
COMMENT ON COLUMN fact_leasing_contracts.financed_amount_net IS 'Net amount financed by the leasing contract.';
COMMENT ON COLUMN fact_leasing_contracts.financed_amount_gross IS 'Gross amount financed by the leasing contract.';
COMMENT ON COLUMN fact_leasing_contracts.down_payment_gross IS 'Gross upfront customer payment.';
COMMENT ON COLUMN fact_leasing_contracts.monthly_payment_net IS 'Net recurring monthly lease payment.';
COMMENT ON COLUMN fact_leasing_contracts.monthly_payment_gross IS 'Gross recurring monthly lease payment.';
COMMENT ON COLUMN fact_leasing_contracts.residual_value_nominal IS 'Nominal residual value used in the lease calculation.';
COMMENT ON COLUMN fact_leasing_contracts.residual_value_effective IS 'Effective residual value after adjustments.';
COMMENT ON COLUMN fact_leasing_contracts.interest_rate_nominal IS 'Nominal interest rate embedded in the leasing contract.';
COMMENT ON COLUMN fact_leasing_contracts.interest_rate_effective IS 'Effective customer interest rate.';
COMMENT ON COLUMN fact_leasing_contracts.service_fee_net IS 'Net service fee amount.';
COMMENT ON COLUMN fact_leasing_contracts.insurance_fee_gross IS 'Gross bundled insurance fee amount.';
COMMENT ON COLUMN fact_leasing_contracts.currency_code IS 'Contract currency code.';

COMMENT ON TABLE fact_loan_contracts IS 'Loan contract fact table at one row per vehicle financing loan contract.';
COMMENT ON COLUMN fact_loan_contracts.loan_contract_sk IS 'Surrogate primary key for the loan contract fact row.';
COMMENT ON COLUMN fact_loan_contracts.loan_contract_id IS 'Business key for the loan contract.';
COMMENT ON COLUMN fact_loan_contracts.customer_sk IS 'Foreign key to the historized customer dimension version valid at loan origination time; use for point-in-time customer attributes at origination.';
COMMENT ON COLUMN fact_loan_contracts.vehicle_sk IS 'Foreign key to the financed vehicle.';
COMMENT ON COLUMN fact_loan_contracts.dealer_sk IS 'Foreign key to the historized dealer dimension version valid at loan origination time; use for point-in-time dealer attributes at origination.';
COMMENT ON COLUMN fact_loan_contracts.product_sk IS 'Foreign key to the loan product.';
COMMENT ON COLUMN fact_loan_contracts.contract_status_sk IS 'Foreign key to the latest known contract lifecycle status for this loan fact row.';
COMMENT ON COLUMN fact_loan_contracts.origination_date_sk IS 'Foreign key to loan origination date.';
COMMENT ON COLUMN fact_loan_contracts.first_payment_date_sk IS 'Foreign key to first scheduled payment date.';
COMMENT ON COLUMN fact_loan_contracts.maturity_date_sk IS 'Foreign key to scheduled loan maturity date.';
COMMENT ON COLUMN fact_loan_contracts.booking_date_sk IS 'Foreign key to warehouse booking date.';
COMMENT ON COLUMN fact_loan_contracts.actual_end_date_sk IS 'Foreign key to the actual loan end or settlement date; null means the loan has not actually ended yet.';
COMMENT ON COLUMN fact_loan_contracts.vehicle_return_date_sk IS 'Foreign key to the date on which the financed vehicle collateral was returned, surrendered, or recovered; null means no return has been recorded.';
COMMENT ON COLUMN fact_loan_contracts.early_termination_flag IS 'True when the loan ended before scheduled maturity, for example through early settlement or default-related termination.';
COMMENT ON COLUMN fact_loan_contracts.termination_reason_code IS 'Business reason for actual loan termination, such as maturity, early settlement, refinancing, total loss, theft, default, or repossession.';
COMMENT ON COLUMN fact_loan_contracts.loan_term_months IS 'Contractual loan term in months.';
COMMENT ON COLUMN fact_loan_contracts.financed_amount_net IS 'Net financed principal amount.';
COMMENT ON COLUMN fact_loan_contracts.financed_amount_gross IS 'Gross financed amount including taxes or fees.';
COMMENT ON COLUMN fact_loan_contracts.down_payment_gross IS 'Gross customer down payment.';
COMMENT ON COLUMN fact_loan_contracts.balloon_payment_nominal IS 'Nominal balloon payment due at maturity.';
COMMENT ON COLUMN fact_loan_contracts.monthly_installment_net IS 'Net monthly installment.';
COMMENT ON COLUMN fact_loan_contracts.monthly_installment_gross IS 'Gross monthly installment.';
COMMENT ON COLUMN fact_loan_contracts.interest_rate_nominal IS 'Nominal contractual interest rate.';
COMMENT ON COLUMN fact_loan_contracts.annual_percentage_rate_effective IS 'Effective annual percentage rate.';
COMMENT ON COLUMN fact_loan_contracts.loan_to_value_effective IS 'Effective loan-to-value ratio.';
COMMENT ON COLUMN fact_loan_contracts.currency_code IS 'Contract currency code.';

COMMENT ON TABLE fact_contract_status_history IS 'Tracks the full lifecycle of a contract. Use this to find what status a contract was in at any specific historical date.';
COMMENT ON COLUMN fact_contract_status_history.status_history_sk IS 'Surrogate primary key for the contract status history row.';
COMMENT ON COLUMN fact_contract_status_history.leasing_contract_sk IS 'Optional foreign key to the leasing contract whose status is being historized; exactly one of leasing_contract_sk or loan_contract_sk should be populated.';
COMMENT ON COLUMN fact_contract_status_history.loan_contract_sk IS 'Optional foreign key to the loan contract whose status is being historized; exactly one of leasing_contract_sk or loan_contract_sk should be populated.';
COMMENT ON COLUMN fact_contract_status_history.contract_status_sk IS 'Foreign key to the contract lifecycle status valid during this historical period.';
COMMENT ON COLUMN fact_contract_status_history.valid_from_date_sk IS 'Foreign key to the first date on which this contract status was valid.';
COMMENT ON COLUMN fact_contract_status_history.valid_to_date_sk IS 'Foreign key to the last date on which this contract status was valid; null means the status is still open-ended.';
COMMENT ON COLUMN fact_contract_status_history.is_current_status IS 'True if this row represents the current status interval for the contract.';

COMMENT ON TABLE fact_banking_accounts IS 'Banking account snapshot fact table for automotive-bank accounts and balances.';
COMMENT ON COLUMN fact_banking_accounts.banking_account_sk IS 'Surrogate primary key for the account snapshot fact row.';
COMMENT ON COLUMN fact_banking_accounts.banking_account_id IS 'Business key for the banking account.';
COMMENT ON COLUMN fact_banking_accounts.customer_sk IS 'Foreign key to the historized customer dimension version valid at the account snapshot date; use for point-in-time customer attributes of this balance snapshot.';
COMMENT ON COLUMN fact_banking_accounts.product_sk IS 'Foreign key to the account product.';
COMMENT ON COLUMN fact_banking_accounts.contract_status_sk IS 'Foreign key to account or contract status.';
COMMENT ON COLUMN fact_banking_accounts.account_open_date_sk IS 'Foreign key to account opening date.';
COMMENT ON COLUMN fact_banking_accounts.account_close_date_sk IS 'Foreign key to account closing date.';
COMMENT ON COLUMN fact_banking_accounts.snapshot_date_sk IS 'Foreign key to the balance snapshot date.';
COMMENT ON COLUMN fact_banking_accounts.iban_hash IS 'Hashed IBAN or account identifier for privacy-preserving linkage.';
COMMENT ON COLUMN fact_banking_accounts.account_currency_code IS 'Account currency code.';
COMMENT ON COLUMN fact_banking_accounts.credit_limit_nominal IS 'Nominal credit limit assigned to the account.';
COMMENT ON COLUMN fact_banking_accounts.authorized_overdraft_limit_net IS 'Net authorized overdraft limit. Values greater than zero indicate an approved overdraft facility.';
COMMENT ON COLUMN fact_banking_accounts.current_balance_net IS 'Net current account balance stored on each account snapshot. The word current is part of the measure name and does not by itself mean latest snapshot; aggregate all matching snapshots unless the question explicitly asks for latest/current snapshot or as-of logic.';
COMMENT ON COLUMN fact_banking_accounts.current_balance_gross IS 'Gross current account balance.';
COMMENT ON COLUMN fact_banking_accounts.available_balance_effective IS 'Effective available balance after holds and limits. Values below zero indicate overdraft; consecutive overdraft runs are consecutive account snapshots with this value below zero, ordered by snapshot_date_sk.';
COMMENT ON COLUMN fact_banking_accounts.average_balance_30d_net IS 'Net average account balance over the last 30 days.';
COMMENT ON COLUMN fact_banking_accounts.average_balance_90d_net IS 'Net average account balance over the last 90 days.';
COMMENT ON COLUMN fact_banking_accounts.interest_rate_nominal IS 'Nominal account interest rate.';
COMMENT ON COLUMN fact_banking_accounts.interest_rate_effective IS 'Effective account interest rate.';
COMMENT ON COLUMN fact_banking_accounts.fee_income_month_to_date_net IS 'Net account fee income month to date.';
COMMENT ON COLUMN fact_banking_accounts.fee_income_year_to_date_gross IS 'Gross account fee income year to date.';
COMMENT ON COLUMN fact_banking_accounts.overdraft_days_month_to_date IS 'Number of overdraft days in the current month.';
COMMENT ON COLUMN fact_banking_accounts.blocked_amount_effective IS 'Effective amount blocked due to holds, disputes, or compliance. Values greater than zero indicate blocked funds.';

COMMENT ON TABLE fact_contract_cashflows IS 'Planned or contract-derived cashflow fact table; records economic cashflow obligations and expectations before or independently of actual payment booking. The outstanding amount is defined as the sum of planned amounts minus the sum of successfully received non-reversed payments.';
COMMENT ON COLUMN fact_contract_cashflows.contract_cashflow_sk IS 'Surrogate primary key for the planned or contract-derived cashflow fact row.';
COMMENT ON COLUMN fact_contract_cashflows.contract_cashflow_id IS 'Business key for the contract cashflow schedule line or economic cashflow item.';
COMMENT ON COLUMN fact_contract_cashflows.cashflow_type_sk IS 'Foreign key to the cashflow type dimension describing the economic purpose of the cashflow.';
COMMENT ON COLUMN fact_contract_cashflows.customer_sk IS 'Foreign key to the historized customer dimension version valid when the cashflow was planned or assessed.';
COMMENT ON COLUMN fact_contract_cashflows.vehicle_sk IS 'Optional foreign key to the vehicle asset associated with the cashflow.';
COMMENT ON COLUMN fact_contract_cashflows.dealer_sk IS 'Optional foreign key to the historized dealer dimension version valid when the cashflow was planned or assessed, for example dealer commission or payout.';
COMMENT ON COLUMN fact_contract_cashflows.product_sk IS 'Foreign key to the financial product associated with the cashflow.';
COMMENT ON COLUMN fact_contract_cashflows.contract_status_sk IS 'Foreign key to the contract status relevant when the cashflow was planned or assessed.';
COMMENT ON COLUMN fact_contract_cashflows.due_date_sk IS 'Foreign key to the contractual due date of the planned cashflow.';
COMMENT ON COLUMN fact_contract_cashflows.related_leasing_contract_sk IS 'Optional foreign key to the related leasing contract fact.';
COMMENT ON COLUMN fact_contract_cashflows.related_loan_contract_sk IS 'Optional foreign key to the related loan contract fact.';
COMMENT ON COLUMN fact_contract_cashflows.related_banking_account_sk IS 'Optional foreign key to the related banking account fact.';
COMMENT ON COLUMN fact_contract_cashflows.cashflow_sequence_number IS 'Sequence number of the cashflow within a contract schedule.';
COMMENT ON COLUMN fact_contract_cashflows.installment_number IS 'Installment number for recurring contractual rates or repayments.';
COMMENT ON COLUMN fact_contract_cashflows.amount_net IS 'Net planned cashflow amount.';
COMMENT ON COLUMN fact_contract_cashflows.amount_gross IS 'Gross planned cashflow amount.';
COMMENT ON COLUMN fact_contract_cashflows.tax_amount_gross IS 'Gross tax component of the planned cashflow.';
COMMENT ON COLUMN fact_contract_cashflows.principal_component_net IS 'Net principal component embedded in the planned cashflow.';
COMMENT ON COLUMN fact_contract_cashflows.interest_component_nominal IS 'Nominal interest component embedded in the planned cashflow.';
COMMENT ON COLUMN fact_contract_cashflows.interest_component_gross IS 'Gross planned interest component embedded in the cashflow; use for plan-versus-actual gross interest comparisons.';
COMMENT ON COLUMN fact_contract_cashflows.fee_component_net IS 'Net fee or service charge component embedded in the planned cashflow.';
COMMENT ON COLUMN fact_contract_cashflows.commission_amount_net IS 'Net dealer or broker commission amount in the planned cashflow.';
COMMENT ON COLUMN fact_contract_cashflows.residual_value_component_effective IS 'Effective residual-value component for leasing maturity or settlement cashflows.';
COMMENT ON COLUMN fact_contract_cashflows.currency_code IS 'Cashflow currency code.';

COMMENT ON TABLE fact_payment_transactions IS 'Booked payment transaction fact table for actual operational payments, bookings, reversals, settlements, and cash movements. A payment is considered successfully received if is_reversal_flag is false.';
COMMENT ON COLUMN fact_payment_transactions.payment_transaction_sk IS 'Surrogate primary key for the payment transaction fact row.';
COMMENT ON COLUMN fact_payment_transactions.payment_transaction_id IS 'Business key for the payment transaction.';
COMMENT ON COLUMN fact_payment_transactions.customer_sk IS 'Foreign key to the historized customer dimension version valid at payment booking time; use for point-in-time customer attributes of this transaction.';
COMMENT ON COLUMN fact_payment_transactions.cashflow_type_sk IS 'Optional foreign key to the cashflow type dimension, used to classify the booked transaction by economic purpose.';
COMMENT ON COLUMN fact_payment_transactions.product_sk IS 'Optional foreign key to the product associated with the payment.';
COMMENT ON COLUMN fact_payment_transactions.contract_status_sk IS 'Optional foreign key to the related contract status at transaction time.';
COMMENT ON COLUMN fact_payment_transactions.transaction_date_sk IS 'Foreign key to transaction initiation date.';
COMMENT ON COLUMN fact_payment_transactions.value_date_sk IS 'Foreign key to value date. Use this date for successful cash receipt timing; for payments deducted from scheduled cashflows, join by related_contract_cashflow_sk and constrain value_date_sk only when the question asks for receipt timing.';
COMMENT ON COLUMN fact_payment_transactions.booking_date_sk IS 'Foreign key to accounting booking date.';
COMMENT ON COLUMN fact_payment_transactions.related_leasing_contract_sk IS 'Optional foreign key to a related leasing contract fact.';
COMMENT ON COLUMN fact_payment_transactions.related_loan_contract_sk IS 'Optional foreign key to a related loan contract fact.';
COMMENT ON COLUMN fact_payment_transactions.related_banking_account_sk IS 'Optional foreign key to a related banking account fact.';
COMMENT ON COLUMN fact_payment_transactions.related_contract_cashflow_sk IS 'Optional foreign key to the planned contract cashflow that this booked transaction settles, reverses, corrects, or was triggered by; for late-fee transactions this points to the delayed planned installment that caused the fee.';
COMMENT ON COLUMN fact_payment_transactions.reverses_payment_transaction_sk IS 'Optional self-reference to the original payment transaction reversed by this row; populated only when is_reversal_flag is true.';
COMMENT ON COLUMN fact_payment_transactions.transaction_type_code IS 'Payment transaction type such as installment, fee, payout, refund, chargeback, or late-fee collection. Dealer commission or commission payout questions must filter transaction_type_code = ''COMMISSION_PAYOUT'' when using booked payment transactions.';
COMMENT ON COLUMN fact_payment_transactions.transaction_channel_code IS 'Channel through which the payment was initiated.';
COMMENT ON COLUMN fact_payment_transactions.counterparty_country_code IS 'Country code of the payment counterparty.';
COMMENT ON COLUMN fact_payment_transactions.amount_net IS 'Net payment amount.';
COMMENT ON COLUMN fact_payment_transactions.amount_gross IS 'Gross payment amount.';
COMMENT ON COLUMN fact_payment_transactions.principal_component_net IS 'Net principal component actually settled by this payment transaction.';
COMMENT ON COLUMN fact_payment_transactions.interest_component_gross IS 'Gross interest component actually settled by this payment transaction; use for actual gross interest comparisons against planned cashflow interest.';
COMMENT ON COLUMN fact_payment_transactions.fee_amount_net IS 'Net fee component of the payment.';
COMMENT ON COLUMN fact_payment_transactions.tax_amount_gross IS 'Gross tax component of the payment.';
COMMENT ON COLUMN fact_payment_transactions.settlement_amount_effective IS 'Effective settlement amount after fees, reversals, and FX.';
COMMENT ON COLUMN fact_payment_transactions.exchange_rate_effective IS 'Effective foreign-exchange rate used for settlement.';
COMMENT ON COLUMN fact_payment_transactions.is_reversal_flag IS 'If true, this transaction cancels a previous one. Successful receipt metrics filter this flag to false. In this synthetic warehouse, reversal rows are booked with the opposite sign of the original and point to it via reverses_payment_transaction_sk; use those reversal rows only when a question explicitly asks for reversals or reversal-adjusted accounting.';
COMMENT ON COLUMN fact_payment_transactions.currency_code IS 'Transaction currency code.';
