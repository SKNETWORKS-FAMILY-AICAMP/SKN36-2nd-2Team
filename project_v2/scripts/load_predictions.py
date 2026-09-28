"""Validate and load LightGBM V3 five-tier customer churn predictions."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from sqlalchemy import func, select

from src.prediction_schema import (
    DATASET_VERSION,
    MODEL_VERSION,
    RISK_BANDS,
    RISK_LEVELS,
    metadata,
    prediction_table,
    risk_factor_table,
)
from src.predictions import DEFAULT_PREDICTION_CSV, prediction_summary, read_prediction_csv
from src.schema import metadata as raw_metadata


def _validate_users(conn, frame: pd.DataFrame) -> None:
    user_table = raw_metadata.tables["user"]
    users = set(conn.scalars(select(user_table.c.user_id)))
    missing = sorted(set(frame["user_id"]) - users)
    if missing:
        raise ValueError(f"Prediction user_id not found in V3 user table: {missing[:10]}")


def _print_summary(frame: pd.DataFrame) -> None:
    summary = prediction_summary(frame)
    print("[PREDICTION CSV]")
    print(f"Rows: {summary['rows']:,}")
    print(f"Unique users: {summary['unique_users']:,}")
    print(f"Snapshot range: {summary['snapshot_min']} ~ {summary['snapshot_max']}")
    print(f"Duplicate user_id + snapshot_date: {summary['duplicates']}")
    print("Risk distribution:")
    for level in RISK_LEVELS:
        print(f"- {level}: {summary['risk_counts'][level]:,}")
    print("Evaluation by risk level:")
    for row in summary["by_level"]:
        lift = "-" if row["lift"] is None else f"{row['lift']:.2f}x"
        print(
            f"- {row['risk_level']} ({RISK_BANDS[row['risk_level']]}): "
            f"{row['count']:,}, churn_rate={row['actual_churn_rate']:.4%}, lift={lift}"
        )


def load_predictions(conn, frame: pd.DataFrame) -> None:
    metadata.create_all(conn, checkfirst=True)
    conn.commit()
    _validate_users(conn, frame)
    conn.commit()
    with conn.begin():
        conn.execute(
            prediction_table.delete().where(
                prediction_table.c.model_version == MODEL_VERSION,
                prediction_table.c.dataset_version == DATASET_VERSION,
            )
        )
        records = frame.astype(object).where(frame.notna(), None)
        for start in range(0, len(records), 2000):
            conn.execute(prediction_table.insert(), records.iloc[start : start + 2000].to_dict("records"))
        count = conn.scalar(
            select(func.count()).select_from(prediction_table).where(
                prediction_table.c.model_version == MODEL_VERSION,
                prediction_table.c.dataset_version == DATASET_VERSION,
            )
        )
        duplicates = conn.execute(
            select(prediction_table.c.user_id, prediction_table.c.snapshot_date, func.count())
            .group_by(prediction_table.c.user_id, prediction_table.c.snapshot_date)
            .having(func.count() > 1)
            .limit(5)
        ).all()
        latest = conn.scalar(select(func.max(prediction_table.c.snapshot_date)))
        if count != len(frame):
            raise ValueError(f"Prediction row count mismatch: DB {count:,} != CSV {len(frame):,}")
        if duplicates:
            raise ValueError(f"Duplicate predictions in DB: {duplicates}")
        print(f"[DB] Loaded rows: {count:,}")
        print(f"[DB] Latest snapshot: {latest}")
    print("[DONE] Prediction load committed")


def read_risk_factor_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    required = ["user_id", "snapshot_date", "churn_probability", *[f"risk_factor_{i}" for i in range(1, 6)]]
    missing = [col for col in required if col not in frame.columns]
    if missing:
        raise ValueError(f"Risk factor CSV missing columns: {missing}")
    frame = frame[required].copy()
    frame["user_id"] = pd.to_numeric(frame["user_id"], errors="raise").astype("int64")
    frame["snapshot_date"] = pd.to_datetime(frame["snapshot_date"], errors="raise").dt.normalize()
    frame["churn_probability"] = pd.to_numeric(frame["churn_probability"], errors="raise")
    if frame.duplicated(["user_id", "snapshot_date"]).any():
        examples = frame.loc[frame.duplicated(["user_id", "snapshot_date"], keep=False), ["user_id", "snapshot_date"]].head().to_dict("records")
        raise ValueError(f"Duplicate risk factor user_id + snapshot_date rows: {examples}")
    frame["model_version"] = MODEL_VERSION
    frame["dataset_version"] = DATASET_VERSION
    return frame


def load_risk_factors(conn, frame: pd.DataFrame, prediction_frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    keys = prediction_frame[["user_id", "snapshot_date", "churn_probability"]]
    check = frame.merge(keys, on=["user_id", "snapshot_date"], how="left", suffixes=("", "_prediction"))
    missing = check["churn_probability_prediction"].isna()
    if missing.any():
        raise ValueError(f"Risk factors without matching prediction rows: {check.loc[missing, ['user_id', 'snapshot_date']].head().to_dict('records')}")
    mismatch = (check["churn_probability"] - check["churn_probability_prediction"]).abs() > 1e-10
    if mismatch.any():
        raise ValueError(f"Risk factor probability mismatch: {check.loc[mismatch, ['user_id', 'snapshot_date']].head().to_dict('records')}")
    metadata.create_all(conn, checkfirst=True)
    conn.commit()
    with conn.begin():
        conn.execute(
            risk_factor_table.delete().where(
                risk_factor_table.c.model_version == MODEL_VERSION,
                risk_factor_table.c.dataset_version == DATASET_VERSION,
            )
        )
        records = frame.astype(object).where(frame.notna(), None)
        for start in range(0, len(records), 2000):
            conn.execute(risk_factor_table.insert(), records.iloc[start : start + 2000].to_dict("records"))
        count = conn.scalar(select(func.count()).select_from(risk_factor_table))
        print(f"[DB] Loaded risk factor rows: {count:,}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=str(DEFAULT_PREDICTION_CSV), help="Prediction CSV path")
    parser.add_argument("--risk-factors", default=str(Path(DEFAULT_PREDICTION_CSV).with_name("customer_risk_factors_v3.csv")), help="Risk factor CSV path")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    frame = read_prediction_csv(args.csv)
    _print_summary(frame)
    if args.validate_only:
        risk_path = Path(args.risk_factors)
        if risk_path.exists():
            risk_frame = read_risk_factor_csv(risk_path)
            joined = risk_frame.merge(frame[["user_id", "snapshot_date", "churn_probability"]], on=["user_id", "snapshot_date"], how="left", suffixes=("", "_prediction"))
            missing = int(joined["churn_probability_prediction"].isna().sum())
            mismatch = int(((joined["churn_probability"] - joined["churn_probability_prediction"]).abs() > 1e-10).sum())
            print(f"Risk factor rows: {len(risk_frame):,}, missing prediction join: {missing:,}, probability mismatch: {mismatch:,}")
        print("ALL PREDICTION CSV CHECKS PASSED")
        return

    from src.db import engine

    with engine.connect() as conn:
        load_predictions(conn, frame)
        risk_path = Path(args.risk_factors)
        if risk_path.exists():
            load_risk_factors(conn, read_risk_factor_csv(risk_path), frame)


if __name__ == "__main__":
    from src.cli import run

    run(main)
