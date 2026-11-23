import io
import pandas as pd
from src.db import get_native_conn

def _df_to_csv_buffer(df: pd.DataFrame) -> io.StringIO:
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False)
    buf.seek(0)
    return buf

def load_star_schema(transformed: dict):
    """Bulk-loads dimensions and fact_flights into Neon PostgreSQL via COPY + ON CONFLICT upserts."""
    conn = get_native_conn()
    try:
        print("[LOAD] Upserting dimension tables (dim_airports, dim_carriers, dim_date)...")

        # 1. dim_airports
        conn.run("CREATE TEMP TABLE stg_airports (LIKE dim_airports INCLUDING DEFAULTS);")
        conn.run(
            "COPY stg_airports (airport_code, city_name, is_target_hub) FROM STDIN WITH (FORMAT CSV)",
            stream=_df_to_csv_buffer(transformed["dim_airports"]),
        )
        conn.run("""
            INSERT INTO dim_airports (airport_code, city_name, is_target_hub)
            SELECT airport_code, city_name, is_target_hub FROM stg_airports
            ON CONFLICT (airport_code) DO UPDATE SET
                city_name = EXCLUDED.city_name,
                is_target_hub = EXCLUDED.is_target_hub;
        """)

        # 2. dim_carriers
        conn.run("CREATE TEMP TABLE stg_carriers (LIKE dim_carriers INCLUDING DEFAULTS);")
        conn.run(
            "COPY stg_carriers (carrier_code, carrier_name) FROM STDIN WITH (FORMAT CSV)",
            stream=_df_to_csv_buffer(transformed["dim_carriers"]),
        )
        conn.run("""
            INSERT INTO dim_carriers (carrier_code, carrier_name)
            SELECT carrier_code, carrier_name FROM stg_carriers
            ON CONFLICT (carrier_code) DO UPDATE SET
                carrier_name = EXCLUDED.carrier_name;
        """)

        # 3. dim_date
        conn.run("CREATE TEMP TABLE stg_date (LIKE dim_date INCLUDING DEFAULTS);")
        conn.run(
            "COPY stg_date (date_id, year, month, day_of_month, day_of_week, is_weekend) FROM STDIN WITH (FORMAT CSV)",
            stream=_df_to_csv_buffer(transformed["dim_date"]),
        )
        conn.run("""
            INSERT INTO dim_date (date_id, year, month, day_of_month, day_of_week, is_weekend)
            SELECT date_id, year, month, day_of_month, day_of_week, is_weekend FROM stg_date
            ON CONFLICT (date_id) DO NOTHING;
        """)

        # 4. fact_flights (Bulk COPY into temp staging -> atomic upsert)
        fact_df = transformed["fact_flights"]
        print(f"[LOAD] Bulk-streaming {len(fact_df):,} rows into fact_flights via PostgreSQL COPY...")

        conn.run("""
            CREATE TEMP TABLE stg_fact_flights (
                flight_business_key VARCHAR(64),
                date_id DATE,
                carrier_code VARCHAR(10),
                origin_airport VARCHAR(10),
                dest_airport VARCHAR(10),
                tail_num VARCHAR(20),
                flight_num VARCHAR(15),
                sched_dep_hour INT,
                dep_delay_mins FLOAT,
                arr_delay_mins FLOAT,
                is_delayed_15 INT,
                carrier_delay FLOAT,
                weather_delay FLOAT,
                nas_delay FLOAT,
                security_delay FLOAT,
                late_aircraft_delay FLOAT,
                cancelled INT,
                cancellation_code VARCHAR(5),
                diverted INT,
                distance FLOAT
            );
        """)

        cols_str = ", ".join(fact_df.columns)
        conn.run(
            f"COPY stg_fact_flights ({cols_str}) FROM STDIN WITH (FORMAT CSV)",
            stream=_df_to_csv_buffer(fact_df),
        )

        conn.run(f"""
            INSERT INTO fact_flights ({cols_str})
            SELECT {cols_str} FROM stg_fact_flights
            ON CONFLICT (flight_business_key) DO UPDATE SET
                dep_delay_mins = EXCLUDED.dep_delay_mins,
                arr_delay_mins = EXCLUDED.arr_delay_mins,
                is_delayed_15 = EXCLUDED.is_delayed_15,
                carrier_delay = EXCLUDED.carrier_delay,
                weather_delay = EXCLUDED.weather_delay,
                nas_delay = EXCLUDED.nas_delay,
                security_delay = EXCLUDED.security_delay,
                late_aircraft_delay = EXCLUDED.late_aircraft_delay,
                cancelled = EXCLUDED.cancelled,
                cancellation_code = EXCLUDED.cancellation_code,
                diverted = EXCLUDED.diverted,
                updated_at = CURRENT_TIMESTAMP;
        """)

        count_res = conn.run("SELECT COUNT(*) FROM fact_flights;")
        total_in_db = count_res[0][0]
        print(f"[LOAD] COMPLETE! Total rows now in fact_flights: {total_in_db:,}")
        return len(fact_df)
    finally:
        conn.close()
