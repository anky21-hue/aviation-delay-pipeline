import traceback
from src.db import get_native_conn
from src.extract import extract_raw_files
from src.transform import transform_flights
from src.load import load_star_schema
from src.predict import train_and_score_predictions

def _write_audit_log(
    source_file: str,
    records_extracted: int,
    records_filtered: int,
    duplicates_dropped: int,
    records_upserted: int,
    model_roc_auc: float | None,
    status: str,
    error_message: str | None = None,
):
    conn = get_native_conn()
    try:
        conn.run(
            """
            INSERT INTO etl_audit_logs (
                source_file, records_extracted, records_filtered,
                duplicates_dropped, records_upserted, model_roc_auc,
                status, error_message
            )
            VALUES (:sf, :re, :rf, :dd, :ru, :auc, :st, :err);
            """,
            sf=source_file,
            re=records_extracted,
            rf=records_filtered,
            dd=duplicates_dropped,
            ru=records_upserted,
            auc=model_roc_auc,
            st=status,
            err=error_message,
        )
    finally:
        conn.close()

def run_pipeline():
    print("=== STARTING AVIATION ETL & PREDICTIVE ML PIPELINE ===")
    total_extracted = 0
    filtered_count = 0
    dups_dropped = 0
    upserted = 0
    roc_auc = None
    files_str = "none"

    try:
        raw_df, total_extracted, file_list = extract_raw_files("data/raw")
        files_str = ", ".join(file_list)
        filtered_count = len(raw_df)

        transformed = transform_flights(raw_df)
        dups_dropped = transformed["duplicates_dropped"]

        upserted = load_star_schema(transformed)
        roc_auc = train_and_score_predictions()

        _write_audit_log(
            source_file=files_str,
            records_extracted=total_extracted,
            records_filtered=filtered_count,
            duplicates_dropped=dups_dropped,
            records_upserted=upserted,
            model_roc_auc=roc_auc,
            status="SUCCESS",
        )
        print(f"=== PIPELINE FINISHED SUCCESSFULLY | Upserted: {upserted:,} | ROC-AUC: {roc_auc} ===")
    except Exception as exc:
        err_trace = traceback.format_exc()
        print(f"[ERROR] Pipeline failed: {exc}")
        _write_audit_log(
            source_file=files_str,
            records_extracted=total_extracted,
            records_filtered=filtered_count,
            duplicates_dropped=dups_dropped,
            records_upserted=upserted,
            model_roc_auc=roc_auc,
            status="FAILED",
            error_message=err_trace[:2000],
        )
        raise

if __name__ == "__main__":
    run_pipeline()
