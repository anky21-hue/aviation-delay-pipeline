import io
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from src.db import get_dbapi_conn, get_native_conn

MODEL_VERSION = "HistGBDT-v1.0"

def _determine_top_risk_factor(df: pd.DataFrame) -> pd.Series:
    """Assigns a clear, business-readable primary delay driver for each flight."""
    reasons = np.full(len(df), "Baseline Route & Schedule", dtype=object)

    reasons = np.where(df["distance"] >= 1500, "Long-Haul Sector Exposure", reasons)
    reasons = np.where(df["carrier_hub_delay_rate"] >= 0.24, "Carrier Hub Congestion History", reasons)
    reasons = np.where(df["origin_airport"].isin(["ORD", "DFW"]), "High-Volume Hub Bottleneck", reasons)
    reasons = np.where(df["sched_dep_hour"] >= 16, "Late-Afternoon Cascading Delay Wave", reasons)
    reasons = np.where(
        (df["sched_dep_hour"] >= 16) & (df["origin_airport"].isin(["ORD", "DFW"])),
        "Peak Evening Hub Departure Wave",
        reasons,
    )
    return pd.Series(reasons, index=df.index)

def train_and_score_predictions() -> float:
    """Trains delay risk classifier on warehouse data and writes predictions to Neon."""
    print("[ML] Loading 372K+ flights from warehouse for feature engineering...")
    dbapi_conn = get_dbapi_conn()
    try:
        query = """
            SELECT
                f.flight_business_key,
                f.date_id,
                f.carrier_code,
                f.origin_airport,
                f.dest_airport,
                f.sched_dep_hour,
                f.distance,
                f.is_delayed_15,
                d.month,
                d.day_of_week,
                CASE WHEN d.is_weekend THEN 1 ELSE 0 END AS is_weekend
            FROM fact_flights f
            JOIN dim_date d ON f.date_id = d.date_id
            ORDER BY f.date_id, f.sched_dep_hour;
        """
        df = pd.read_sql(query, dbapi_conn)
    finally:
        dbapi_conn.close()

    # 1. Feature Engineering (pre-departure operational signals)
    df["is_origin_hub"] = df["origin_airport"].isin(["DFW", "SEA", "ORD"]).astype(int)
    df["is_dest_hub"] = df["dest_airport"].isin(["DFW", "SEA", "ORD"]).astype(int)
    df["is_peak_hour"] = df["sched_dep_hour"].between(15, 21).astype(int)

    # Expanding historical delay rate per (carrier, origin) to prevent target leakage
    df["carrier_hub_delay_rate"] = (
        df.groupby(["carrier_code", "origin_airport"])["is_delayed_15"]
        .transform(lambda s: s.expanding().mean().shift(1))
        .fillna(df["is_delayed_15"].mean())
    )

    # Encode categoricals as category dtype for HistGradientBoostingClassifier
    cat_cols = ["carrier_code", "origin_airport", "dest_airport"]
    for c in cat_cols:
        df[c] = df[c].astype("category")

    feature_cols = [
        "carrier_code",
        "origin_airport",
        "dest_airport",
        "sched_dep_hour",
        "distance",
        "month",
        "day_of_week",
        "is_weekend",
        "is_origin_hub",
        "is_dest_hub",
        "is_peak_hour",
        "carrier_hub_delay_rate",
    ]

    # 2. Time-aware Train / Validation Split (first 80% train, newest 20% test)
    split_idx = int(len(df) * 0.80)
    X_train, y_train = df.iloc[:split_idx][feature_cols], df.iloc[:split_idx]["is_delayed_15"]
    X_test, y_test = df.iloc[split_idx:][feature_cols], df.iloc[split_idx:]["is_delayed_15"]

    print(f"[ML] Training {MODEL_VERSION} on {len(X_train):,} flights | Validating on {len(X_test):,} flights...")
    clf = HistGradientBoostingClassifier(
        max_iter=150,
        learning_rate=0.08,
        max_depth=6,
        categorical_features=cat_cols,
        random_state=42,
    )
    clf.fit(X_train, y_train)

    test_probs = clf.predict_proba(X_test)[:, 1]
    roc_auc = round(float(roc_auc_score(y_test, test_probs)), 4)
    print(f"[ML] Validation ROC-AUC Score: {roc_auc:.4f}")

    # 3. Score all warehouse flights & assign Risk Tiers
    all_probs = clf.predict_proba(df[feature_cols])[:, 1]
    df["delay_probability"] = np.round(all_probs, 4)
    df["risk_tier"] = np.select(
        [df["delay_probability"] >= 0.60, df["delay_probability"] >= 0.30],
        ["High", "Medium"],
        default="Low",
    )
    df["top_risk_factor"] = _determine_top_risk_factor(df)
    df["model_version"] = MODEL_VERSION

    pred_df = df[
        ["flight_business_key", "delay_probability", "risk_tier", "top_risk_factor", "model_version"]
    ].copy()

    # 4. Bulk COPY + Upsert into fact_flight_predictions
    print(f"[ML] Writing {len(pred_df):,} delay risk predictions to Neon...")
    conn = get_native_conn()
    try:
        conn.run("""
            CREATE TEMP TABLE stg_predictions (
                flight_business_key VARCHAR(64),
                delay_probability FLOAT,
                risk_tier VARCHAR(15),
                top_risk_factor VARCHAR(100),
                model_version VARCHAR(50)
            );
        """)
        buf = io.StringIO()
        pred_df.to_csv(buf, index=False, header=False)
        buf.seek(0)

        conn.run(
            "COPY stg_predictions (flight_business_key, delay_probability, risk_tier, top_risk_factor, model_version) FROM STDIN WITH (FORMAT CSV)",
            stream=buf,
        )
        conn.run("""
            INSERT INTO fact_flight_predictions (
                flight_business_key, delay_probability, risk_tier, top_risk_factor, model_version
            )
            SELECT
                flight_business_key, delay_probability, risk_tier, top_risk_factor, model_version
            FROM stg_predictions
            ON CONFLICT (flight_business_key) DO UPDATE SET
                delay_probability = EXCLUDED.delay_probability,
                risk_tier = EXCLUDED.risk_tier,
                top_risk_factor = EXCLUDED.top_risk_factor,
                model_version = EXCLUDED.model_version,
                scored_at = CURRENT_TIMESTAMP;
        """)
        tier_counts = pred_df["risk_tier"].value_counts().to_dict()
        print(f"[ML] COMPLETE! Risk Tier Breakdown: {tier_counts}")
    finally:
        conn.close()

    return roc_auc
