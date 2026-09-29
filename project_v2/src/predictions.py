"""Load and validate LightGBM V3 five-tier prediction CSV files."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.prediction_schema import (
    DATASET_VERSION,
    MODEL_VERSION,
    RISK_CUTOFFS,
    RISK_LEVELS,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREDICTION_CSV = ROOT / "data/processed/v3/customer_churn_predictions_v3_5tier.csv"
PREDICTION_COLUMNS = [
    "user_id",
    "snapshot_date",
    "churn_probability",
    "prediction",
    "risk_level",
    "split",
    "actual_churn_60d",
]


def expected_risk_level(probability: float) -> str:
    if probability >= RISK_CUTOFFS["very_high"]:
        return "VERY HIGH"
    if probability >= RISK_CUTOFFS["high"]:
        return "HIGH"
    if probability >= RISK_CUTOFFS["medium"]:
        return "MEDIUM"
    if probability >= RISK_CUTOFFS["low"]:
        return "LOW"
    return "VERY LOW"


def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for col in frame.columns:
        if col.startswith("actual_churn_60d"):
            rename[col] = "actual_churn_60d"
    return frame.rename(columns=rename)


def read_prediction_csv(path: str | Path = DEFAULT_PREDICTION_CSV) -> pd.DataFrame:
    path = Path(path)
    frame = _normalize_columns(pd.read_csv(path, encoding="utf-8-sig"))
    missing = [col for col in PREDICTION_COLUMNS if col not in frame.columns]
    if missing:
        raise ValueError(f"Prediction CSV missing columns: {missing}")
    frame = frame[PREDICTION_COLUMNS].copy()
    if frame.isna().any().any():
        raise ValueError(f"Prediction CSV contains NULL values: {frame.isna().sum().to_dict()}")

    frame["user_id"] = pd.to_numeric(frame["user_id"], errors="raise").astype("int64")
    frame["snapshot_date"] = pd.to_datetime(frame["snapshot_date"], errors="raise").dt.normalize()
    frame["churn_probability"] = pd.to_numeric(frame["churn_probability"], errors="raise")
    frame["prediction"] = pd.to_numeric(frame["prediction"], errors="raise").astype("int64")
    frame["actual_churn_60d"] = pd.to_numeric(frame["actual_churn_60d"], errors="raise").astype("int64")
    frame["risk_level"] = frame["risk_level"].astype(str).str.strip().str.upper()
    frame["split"] = frame["split"].astype(str).str.strip()

    if frame.duplicated(["user_id", "snapshot_date"]).any():
        examples = frame.loc[frame.duplicated(["user_id", "snapshot_date"], keep=False), ["user_id", "snapshot_date"]].head().to_dict("records")
        raise ValueError(f"Duplicate user_id + snapshot_date rows: {examples}")
    invalid_risk = sorted(set(frame["risk_level"]) - set(RISK_LEVELS))
    if invalid_risk:
        raise ValueError(f"Invalid risk_level values: {invalid_risk}")
    if not frame["prediction"].isin([0, 1]).all():
        raise ValueError("prediction must contain only 0/1")
    if not frame["actual_churn_60d"].isin([0, 1]).all():
        raise ValueError("actual_churn_60d must contain only 0/1")
    if ((frame["churn_probability"] < 0) | (frame["churn_probability"] > 1)).any():
        raise ValueError("churn_probability must be between 0 and 1")

    expected = frame["churn_probability"].map(expected_risk_level)
    mismatches = frame.loc[expected != frame["risk_level"], ["user_id", "snapshot_date", "churn_probability", "risk_level"]]
    if not mismatches.empty:
        raise ValueError(f"risk_level disagrees with cutoff definition: {mismatches.head().to_dict('records')}")

    frame["model_version"] = MODEL_VERSION
    frame["dataset_version"] = DATASET_VERSION
    return frame


def prediction_summary(frame: pd.DataFrame) -> dict:
    counts = frame["risk_level"].value_counts().reindex(RISK_LEVELS, fill_value=0)
    overall_rate = float(frame["actual_churn_60d"].mean())
    by_level = []
    for level in RISK_LEVELS:
        subset = frame.loc[frame["risk_level"] == level]
        churn_rate = float(subset["actual_churn_60d"].mean()) if len(subset) else 0.0
        by_level.append(
            {
                "risk_level": level,
                "count": int(len(subset)),
                "actual_churn_rate": churn_rate,
                "lift": churn_rate / overall_rate if overall_rate else None,
            }
        )
    return {
        "rows": int(len(frame)),
        "unique_users": int(frame["user_id"].nunique()),
        "snapshot_min": frame["snapshot_date"].min().date().isoformat(),
        "snapshot_max": frame["snapshot_date"].max().date().isoformat(),
        "duplicates": int(frame.duplicated(["user_id", "snapshot_date"]).sum()),
        "risk_counts": {level: int(counts[level]) for level in RISK_LEVELS},
        "overall_actual_churn_rate": overall_rate,
        "by_level": by_level,
    }
