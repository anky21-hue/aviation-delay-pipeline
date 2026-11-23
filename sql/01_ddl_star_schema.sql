-- 1. Dimension: Airports
CREATE TABLE IF NOT EXISTS dim_airports (
    airport_code VARCHAR(10) PRIMARY KEY,
    city_name VARCHAR(100),
    is_target_hub BOOLEAN DEFAULT FALSE
);

-- 2. Dimension: Airlines / Carriers
CREATE TABLE IF NOT EXISTS dim_carriers (
    carrier_code VARCHAR(10) PRIMARY KEY,
    carrier_name VARCHAR(100)
);

-- 3. Dimension: Calendar Date
CREATE TABLE IF NOT EXISTS dim_date (
    date_id DATE PRIMARY KEY,
    year INT NOT NULL,
    month INT NOT NULL,
    day_of_month INT NOT NULL,
    day_of_week INT NOT NULL,
    is_weekend BOOLEAN NOT NULL
);

-- 4. Fact Table: Flight Operations & Delays
CREATE TABLE IF NOT EXISTS fact_flights (
    flight_sk SERIAL PRIMARY KEY,
    flight_business_key VARCHAR(64) UNIQUE NOT NULL,
    date_id DATE REFERENCES dim_date(date_id),
    carrier_code VARCHAR(10) REFERENCES dim_carriers(carrier_code),
    origin_airport VARCHAR(10) REFERENCES dim_airports(airport_code),
    dest_airport VARCHAR(10) REFERENCES dim_airports(airport_code),
    tail_num VARCHAR(20),
    flight_num VARCHAR(15),
    sched_dep_hour INT,
    dep_delay_mins FLOAT,
    arr_delay_mins FLOAT,
    is_delayed_15 INT,
    carrier_delay FLOAT DEFAULT 0,
    weather_delay FLOAT DEFAULT 0,
    nas_delay FLOAT DEFAULT 0,
    security_delay FLOAT DEFAULT 0,
    late_aircraft_delay FLOAT DEFAULT 0,
    cancelled INT DEFAULT 0,
    cancellation_code VARCHAR(5),
    diverted INT DEFAULT 0,
    distance FLOAT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Fact Table: Predictive Delay Risk Scores (ML Output)
CREATE TABLE IF NOT EXISTS fact_flight_predictions (
    prediction_sk SERIAL PRIMARY KEY,
    flight_business_key VARCHAR(64) UNIQUE REFERENCES fact_flights(flight_business_key) ON DELETE CASCADE,
    delay_probability FLOAT NOT NULL,
    risk_tier VARCHAR(15) NOT NULL,
    top_risk_factor VARCHAR(100),
    model_version VARCHAR(50),
    scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Audit Table: ETL Quality & ML Drift Logs
CREATE TABLE IF NOT EXISTS etl_audit_logs (
    run_id SERIAL PRIMARY KEY,
    run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_file VARCHAR(255),
    records_extracted INT,
    records_filtered INT,
    duplicates_dropped INT,
    records_upserted INT,
    model_roc_auc FLOAT,
    status VARCHAR(20),
    error_message TEXT
);

-- Indexes for fast Power BI & ML queries
CREATE INDEX IF NOT EXISTS idx_fact_flights_date ON fact_flights(date_id);
CREATE INDEX IF NOT EXISTS idx_fact_flights_origin ON fact_flights(origin_airport);
CREATE INDEX IF NOT EXISTS idx_fact_flights_dest ON fact_flights(dest_airport);
CREATE INDEX IF NOT EXISTS idx_fact_flights_carrier ON fact_flights(carrier_code);
