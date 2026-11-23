-- View 1: Executive Hub On-Time Performance & Delay Root Causes
CREATE OR REPLACE VIEW vw_hub_otp_summary AS
SELECT
    d.year,
    d.month,
    f.origin_airport AS hub_code,
    a.city_name AS hub_city,
    f.carrier_code,
    c.carrier_name,
    COUNT(*) AS total_flights,
    SUM(CASE WHEN f.is_delayed_15 = 0 THEN 1 ELSE 0 END) AS on_time_flights,
    ROUND(100.0 * SUM(CASE WHEN f.is_delayed_15 = 0 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS otp_pct,
    ROUND(AVG(f.arr_delay_mins)::NUMERIC, 2) AS avg_arr_delay_mins,
    SUM(f.cancelled) AS cancelled_flights,
    ROUND(SUM(f.carrier_delay)::NUMERIC, 0) AS total_carrier_delay_mins,
    ROUND(SUM(f.weather_delay)::NUMERIC, 0) AS total_weather_delay_mins,
    ROUND(SUM(f.nas_delay)::NUMERIC, 0) AS total_nas_delay_mins,
    ROUND(SUM(f.security_delay)::NUMERIC, 0) AS total_security_delay_mins,
    ROUND(SUM(f.late_aircraft_delay)::NUMERIC, 0) AS total_late_aircraft_delay_mins
FROM fact_flights f
JOIN dim_date d ON f.date_id = d.date_id
JOIN dim_airports a ON f.origin_airport = a.airport_code
JOIN dim_carriers c ON f.carrier_code = c.carrier_code
WHERE a.is_target_hub = TRUE
GROUP BY d.year, d.month, f.origin_airport, a.city_name, f.carrier_code, c.carrier_name;

-- View 2: Hourly Departure Bottlenecks & Day-of-Week Heatmap
CREATE OR REPLACE VIEW vw_hourly_bottlenecks AS
SELECT
    f.origin_airport AS hub_code,
    d.day_of_week,
    d.is_weekend,
    f.sched_dep_hour,
    COUNT(*) AS flight_volume,
    ROUND(100.0 * AVG(f.is_delayed_15)::NUMERIC, 2) AS delay_rate_pct,
    ROUND(AVG(f.dep_delay_mins)::NUMERIC, 2) AS avg_dep_delay_mins,
    ROUND(AVG(f.arr_delay_mins)::NUMERIC, 2) AS avg_arr_delay_mins
FROM fact_flights f
JOIN dim_date d ON f.date_id = d.date_id
JOIN dim_airports a ON f.origin_airport = a.airport_code
WHERE a.is_target_hub = TRUE
GROUP BY f.origin_airport, d.day_of_week, d.is_weekend, f.sched_dep_hour;

-- View 3: Predictive Delay Risk Watchlist & What-If Risk Explorer
CREATE OR REPLACE VIEW vw_predictive_delay_risk AS
SELECT
    f.flight_business_key,
    f.date_id,
    d.month,
    d.day_of_week,
    f.origin_airport,
    f.dest_airport,
    f.carrier_code,
    c.carrier_name,
    f.sched_dep_hour,
    f.distance,
    f.arr_delay_mins AS actual_arr_delay_mins,
    f.is_delayed_15 AS actual_delayed_flag,
    p.delay_probability,
    p.risk_tier,
    p.top_risk_factor,
    p.model_version
FROM fact_flights f
JOIN dim_date d ON f.date_id = d.date_id
JOIN dim_carriers c ON f.carrier_code = c.carrier_code
JOIN fact_flight_predictions p ON f.flight_business_key = p.flight_business_key;

-- View 4: Pipeline & Model Observability Log Summary
CREATE OR REPLACE VIEW vw_pipeline_health AS
SELECT
    run_id,
    run_timestamp,
    source_file,
    records_extracted,
    records_filtered,
    duplicates_dropped,
    records_upserted,
    model_roc_auc,
    status
FROM etl_audit_logs
ORDER BY run_timestamp DESC;
