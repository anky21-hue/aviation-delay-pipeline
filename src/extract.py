import glob
import os
import pandas as pd

TARGET_HUBS = {"DFW", "SEA", "ORD"}

COLUMN_MAPPING = {
    "FL_DATE": "FlightDate",
    "OP_UNIQUE_CARRIER": "Reporting_Airline",
    "TAIL_NUM": "Tail_Number",
    "OP_CARRIER_FL_NUM": "Flight_Number_Reporting_Airline",
    "ORIGIN": "Origin",
    "ORIGIN_CITY_NAME": "OriginCityName",
    "DEST": "Dest",
    "DEST_CITY_NAME": "DestCityName",
    "CRS_DEP_TIME": "CRSDepTime",
    "DEP_TIME": "DepTime",
    "DEP_DELAY": "DepDelay",
    "CRS_ARR_TIME": "CRSArrTime",
    "ARR_TIME": "ArrTime",
    "ARR_DELAY": "ArrDelay",
    "CANCELLED": "Cancelled",
    "CANCELLATION_CODE": "CancellationCode",
    "DIVERTED": "Diverted",
    "DISTANCE": "Distance",
    "CARRIER_DELAY": "CarrierDelay",
    "WEATHER_DELAY": "WeatherDelay",
    "NAS_DELAY": "NASDelay",
    "SECURITY_DELAY": "SecurityDelay",
    "LATE_AIRCRAFT_DELAY": "LateAircraftDelay",
}

REQUIRED_RAW_COLS = [
    "FL_DATE",
    "OP_UNIQUE_CARRIER",
    "ORIGIN",
    "ORIGIN_CITY_NAME",
    "DEST",
    "DEST_CITY_NAME",
    "CRS_DEP_TIME",
    "DEP_TIME",
    "DEP_DELAY",
    "CRS_ARR_TIME",
    "ARR_TIME",
    "ARR_DELAY",
    "CANCELLED",
    "CANCELLATION_CODE",
    "DIVERTED",
    "DISTANCE",
    "CARRIER_DELAY",
    "WEATHER_DELAY",
    "NAS_DELAY",
    "SECURITY_DELAY",
    "LATE_AIRCRAFT_DELAY",
]

def extract_raw_files(raw_dir: str = "data/raw"):
    """Reads all BTS CSV files in raw_dir, standardizes headers, and filters for DFW, SEA, and ORD."""
    csv_files = sorted(glob.glob(os.path.join(raw_dir, "*.csv")))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {raw_dir}")

    frames = []
    total_extracted = 0

    for file_path in csv_files:
        print(f"[EXTRACT] Reading {os.path.basename(file_path)}...")
        df = pd.read_csv(file_path, low_memory=False)
        total_extracted += len(df)

        missing_cols = [c for c in REQUIRED_RAW_COLS if c not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing expected columns in {file_path}: {missing_cols}")

        df = df.rename(columns=COLUMN_MAPPING)
        for opt_col in ["Tail_Number", "Flight_Number_Reporting_Airline"]:
            if opt_col not in df.columns:
                df[opt_col] = None

        keep_cols = list(COLUMN_MAPPING.values())
        df = df[keep_cols].copy()

        df["Origin"] = df["Origin"].astype(str).str.strip().str.upper()
        df["Dest"] = df["Dest"].astype(str).str.strip().str.upper()

        hub_mask = df["Origin"].isin(TARGET_HUBS) | df["Dest"].isin(TARGET_HUBS)
        filtered_df = df[hub_mask].copy()
        print(f"          Total rows: {len(df):,} | Hub-filtered rows: {len(filtered_df):,}")
        frames.append(filtered_df)

    combined_df = pd.concat(frames, ignore_index=True)
    return combined_df, total_extracted, [os.path.basename(f) for f in csv_files]
