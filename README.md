# Aviation Operations & Delay Reliability Pipeline (ETL + Predictive ML)

An end-to-end data engineering and predictive analytics pipeline that ingests **1.67M+ U.S. DOT (BTS) flight records**, filters **372,757 flights** across major hubs (**DFW, SEA, ORD**), loads a star-schema PostgreSQL warehouse on **Neon**, scores flight delay probabilities with a Gradient Boosted classifier (`HistGradientBoostingClassifier`), and powers a 3-page **Power BI** dashboard.

## Architecture
1. **Extract (`src/extract.py`):** Ingests monthly BTS `T_ONTIME_REPORTING` CSVs, standardizes schemas, and filters for `DFW`, `SEA`, and `ORD`.
2. **Transform (`src/transform.py`):** Cleans timestamps, computes deterministic SHA-256 `flight_business_key` hashes, deduplicates records, and enforces data quality assertions.
3. **Load (`src/load.py`):** Streams data into Neon PostgreSQL via `COPY` and atomic `ON CONFLICT` upserts across `dim_airports`, `dim_carriers`, `dim_date`, and `fact_flights`.
4. **Predictive ML (`src/predict.py`):** Trains `HistGradientBoostingClassifier` on temporal and historical hub-congestion features to predict `15+` minute arrival delays, writing risk scores (`Low`, `Medium`, `High`) and top delay drivers to `fact_flight_predictions`.
5. **Observability & Automation:** Logs row counts, dropped duplicates, and validation `ROC-AUC` into `etl_audit_logs`, with manual dispatch via GitHub Actions (`.github/workflows/weekly_etl.yml`).

## Key Warehouse Insights
- **SEA:** 35,757 departures | **82.46%** On-Time Performance
- **DFW:** 72,256 departures | **72.88%** On-Time Performance
- **ORD:** 82,025 departures | **64.87%** On-Time Performance
