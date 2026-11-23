import hashlib
import pandas as pd

TARGET_HUBS = {"DFW", "SEA", "ORD"}

CARRIER_NAMES = {
    "AA": "American Airlines Inc.",
    "AS": "Alaska Airlines Inc.",
    "B6": "JetBlue Airways",
    "DL": "Delta Air Lines Inc.",
    "F9": "Frontier Airlines Inc.",
    "G4": "Allegiant Air",
    "HA": "Hawaiian Airlines Inc.",
    "MQ": "Envoy Air",
    "NK": "Spirit Air Lines",
    "OH": "PSA Airlines Inc.",
    "OO": "SkyWest Airlines Inc.",
    "QX": "Horizon Air",
    "UA": "United Air Lines Inc.",
    "WN": "Southwest Airlines Co.",
    "YX": "Republic Airline",
    "9E": "Endeavor Air Inc.",
    "YV": "Mesa Airlines Inc.",
}

def _make_business_key(row) -> str:
    raw = (
        f"{row['date_id']}|{row['carrier_code']}|{row['origin_airport']}|"
        f"{row['dest_airport']}|{row['sched_dep_hhmm']}|{row['sched_arr_hhmm']}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def transform_flights(raw_df: pd.DataFrame):
    """Cleans, validates, deduplicates, and splits raw hub flights into star-schema tables."""
    print("[TRANSFORM] Cleaning dates, times, and delay metrics...")
    df = raw_df.copy()

    # 1. Parse FlightDate cleanly (handles '1/1/2026 12:00:00 AM' or '2026-01-01')
    df["date_id"] = pd.to_datetime(df["FlightDate"]).dt.date
    df = df.dropna(subset=["date_id", "Reporting_Airline", "Origin", "Dest"])

    # 2. Standardize codes
    df["carrier_code"] = df["Reporting_Airline"].astype(str).str.strip().str.upper()
    df["origin_airport"] = df["Origin"].astype(str).str.strip().str.upper()
    df["dest_airport"] = df["Dest"].astype(str).str.strip().str.upper()
    df["tail_num"] = df["Tail_Number"].fillna("UNKNOWN").astype(str).str.strip()
    df["flight_num"] = df["Flight_Number_Reporting_Airline"].fillna("0").astype(str).str.strip()

    # 3. Scheduled departure hour (0-23) & zero-padded HHMM for unique key
    dep_hhmm = pd.to_numeric(df["CRSDepTime"], errors="coerce").fillna(0).astype(int)
    arr_hhmm = pd.to_numeric(df["CRSArrTime"], errors="coerce").fillna(0).astype(int)
    df["sched_dep_hhmm"] = dep_hhmm.astype(str).str.zfill(4)
    df["sched_arr_hhmm"] = arr_hhmm.astype(str).str.zfill(4)
    df["sched_dep_hour"] = (dep_hhmm // 100).clip(0, 23)

    # 4. Numeric delay & flight metrics
    df["dep_delay_mins"] = pd.to_numeric(df["DepDelay"], errors="coerce").fillna(0.0)
    df["arr_delay_mins"] = pd.to_numeric(df["ArrDelay"], errors="coerce").fillna(0.0)
    df["cancelled"] = pd.to_numeric(df["Cancelled"], errors="coerce").fillna(0).astype(int)
    df["diverted"] = pd.to_numeric(df["Diverted"], errors="coerce").fillna(0).astype(int)
    df["distance"] = pd.to_numeric(df["Distance"], errors="coerce").fillna(0.0)
    df["cancellation_code"] = df["CancellationCode"].fillna("").astype(str).str.strip()

    for src_col, dst_col in [
        ("CarrierDelay", "carrier_delay"),
        ("WeatherDelay", "weather_delay"),
        ("NASDelay", "nas_delay"),
        ("SecurityDelay", "security_delay"),
        ("LateAircraftDelay", "late_aircraft_delay"),
    ]:
        df[dst_col] = pd.to_numeric(df[src_col], errors="coerce").fillna(0.0).clip(lower=0.0)

    # Target label for BI & ML: delayed >= 15 mins OR cancelled
    df["is_delayed_15"] = ((df["arr_delay_mins"] >= 15.0) | (df["cancelled"] == 1)).astype(int)

    # 5. Deterministic SHA-256 business key + deduplication
    df["flight_business_key"] = df.apply(_make_business_key, axis=1)
    before_dedup = len(df)
    df = df.drop_duplicates(subset=["flight_business_key"], keep="last").copy()
    duplicates_dropped = before_dedup - len(df)
    print(f"[TRANSFORM] Deduplicated: dropped {duplicates_dropped:,} duplicate rows | Clean rows: {len(df):,}")

    # 6. Data quality assertions (fail fast if invalid values appear)
    assert df["sched_dep_hour"].between(0, 23).all(), "Invalid sched_dep_hour outside 0..23"
    assert (df["distance"] >= 0).all(), "Negative flight distance detected"
    assert df["is_delayed_15"].isin([0, 1]).all(), "Invalid is_delayed_15 flag"

    # 7. Build Dimension DataFrames
    # dim_airports
    origins = df[["origin_airport", "OriginCityName"]].rename(
        columns={"origin_airport": "airport_code", "OriginCityName": "city_name"}
    )
    dests = df[["dest_airport", "DestCityName"]].rename(
        columns={"dest_airport": "airport_code", "DestCityName": "city_name"}
    )
    dim_airports = pd.concat([origins, dests], ignore_index=True).drop_duplicates(subset=["airport_code"])
    dim_airports["city_name"] = dim_airports["city_name"].fillna("Unknown").astype(str).str.strip()
    dim_airports["is_target_hub"] = dim_airports["airport_code"].isin(TARGET_HUBS)

    # dim_carriers
    dim_carriers = pd.DataFrame({"carrier_code": df["carrier_code"].unique()})
    dim_carriers["carrier_name"] = dim_carriers["carrier_code"].map(CARRIER_NAMES).fillna(dim_carriers["carrier_code"])

    # dim_date
    unique_dates = pd.Series(df["date_id"].unique())
    dt_series = pd.to_datetime(unique_dates)
    dim_date = pd.DataFrame({
        "date_id": unique_dates,
        "year": dt_series.dt.year,
        "month": dt_series.dt.month,
        "day_of_month": dt_series.dt.day,
        "day_of_week": dt_series.dt.dayofweek + 1,  # 1=Mon .. 7=Sun
        "is_weekend": dt_series.dt.dayofweek.isin([5, 6]),
    })

    # fact_flights
    fact_cols = [
        "flight_business_key",
        "date_id",
        "carrier_code",
        "origin_airport",
        "dest_airport",
        "tail_num",
        "flight_num",
        "sched_dep_hour",
        "dep_delay_mins",
        "arr_delay_mins",
        "is_delayed_15",
        "carrier_delay",
        "weather_delay",
        "nas_delay",
        "security_delay",
        "late_aircraft_delay",
        "cancelled",
        "cancellation_code",
        "diverted",
        "distance",
    ]
    fact_flights = df[fact_cols].copy()

    return {
        "dim_airports": dim_airports,
        "dim_carriers": dim_carriers,
        "dim_date": dim_date,
        "fact_flights": fact_flights,
        "duplicates_dropped": duplicates_dropped,
    }
