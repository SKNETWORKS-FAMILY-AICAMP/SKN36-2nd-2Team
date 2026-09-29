"""CloudCare web application with Excel-first and optional MySQL data sources."""
from __future__ import annotations

import os
import json
import threading
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import inspect

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)
DATA_SOURCE = os.getenv("DATA_SOURCE", "excel").lower()
if DATA_SOURCE not in {"mysql", "excel"}:
    raise RuntimeError("DATA_SOURCE는 excel 또는 mysql이어야 합니다.")
DATA_DIR = ROOT / "data"
RAW_ROOT = DATA_DIR / "raw"
DEFAULT_DATA_VERSION = os.getenv("DATA_VERSION", "v3").lower()


def _default_raw_dir() -> Path:
    if os.getenv("EXCEL_DATA_DIR"):
        return Path(os.environ["EXCEL_DATA_DIR"]).expanduser().resolve()
    matches = sorted(p for p in RAW_ROOT.glob(f"*{DEFAULT_DATA_VERSION}*") if p.is_dir())
    if matches:
        return matches[-1]
    return next(iter(sorted((p for p in RAW_ROOT.glob("*") if p.is_dir()), reverse=True)), RAW_ROOT)


RAW_DIR = _default_raw_dir()
FILES = {
    "user": "5.1_user.xlsx", "plan": "5.2_plan.xlsx", "subscription": "5.3_subscription.xlsx",
    "storage_usage_monthly": "5.4_storage_usage_monthly.xlsx", "user_activity_daily": "5.5_user_activity_daily.xlsx",
    "device": "5.6_device.xlsx", "payment_history": "5.7_payment_history.xlsx",
    "support_ticket": "5.8_support_ticket.xlsx", "subscription_event": "5.9_subscription_event.xlsx",
}
PREDICTION_CSV = ROOT / "data/processed/v3/customer_churn_predictions_v3_5tier.csv"
RISK_FACTOR_CSV = ROOT / "data/processed/v3/customer_risk_factors_v3.csv"
FEATURE_IMPORTANCE_CSV = ROOT / "data/processed/v3/feature_importance_v3.csv"
FEATURE_LIST_CSV = ROOT / "data/processed/v3/feature_list_dtypes_v3.csv"
SPLIT_SUMMARY_JSON = ROOT / "data/processed/v3/split_summary_v3.json"
FINAL_MODEL_FEATURES_CSV = ROOT / "data/processed/v3/final_model_features_v3.csv"
RISK_LEVELS = ["VERY HIGH", "HIGH", "MEDIUM", "LOW", "VERY LOW"]
RISK_LABELS_KO = {"VERY HIGH": "매우 높음", "HIGH": "높음", "MEDIUM": "보통", "LOW": "낮음", "VERY LOW": "매우 낮음"}
RISK_BANDS = {
    "VERY HIGH": ">= 0.9745",
    "HIGH": "0.6321 ~ 0.9745",
    "MEDIUM": "0.0554 ~ 0.6321",
    "LOW": "0.0033 ~ 0.0554",
    "VERY LOW": "< 0.0033",
}
RISK_PERCENTILE_BASIS = {
    "VERY HIGH": "전체 예측 확률분포 상위 1%",
    "HIGH": "상위 1~5%",
    "MEDIUM": "상위 5~20%",
    "LOW": "상위 20~50%",
    "VERY LOW": "하위 50%",
}
PAGE_SIZES = {10, 30, 50, 100}
_inquiry_lock = threading.Lock()

app = Flask(__name__, template_folder="frontend", static_folder="frontend", static_url_path="/static")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "cloudcare-demo-secret")


def _ensure_workbooks() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    admin = DATA_DIR / "admin.xlsx"
    inquiry = DATA_DIR / "inquiry.xlsx"
    if not admin.exists():
        pd.DataFrame([{"admin_id": 1, "username": "admin", "password": "1234"}]).to_excel(admin, index=False)
    if not inquiry.exists():
        pd.DataFrame(columns=["inquiry_id", "name", "email", "topic", "message", "status", "created_at"]).to_excel(inquiry, index=False)


@lru_cache(maxsize=16)
def _read_excel_cached(path: str, modified_ns: int) -> pd.DataFrame:
    """Read a workbook once per unchanged file version; callers must treat it as immutable."""
    del modified_ns
    return pd.read_excel(path)


def _read(name: str) -> pd.DataFrame:
    # Admin credentials remain local application data even when service data
    # is served from MySQL. This keeps the login path independent of the
    # customer-data source selection.
    if name == "admin" or (name == "inquiry" and DATA_SOURCE == "excel"):
        path = DATA_DIR / f"{name}.xlsx"
        return _read_excel_cached(str(path), path.stat().st_mtime_ns)
    if name == "inquiry" and DATA_SOURCE == "mysql":
        engine = _get_engine()
        with engine.connect() as conn:
            if not inspect(conn).has_table("inquiry"):
                _ensure_workbooks()
                path = DATA_DIR / "inquiry.xlsx"
                return _read_excel_cached(str(path), path.stat().st_mtime_ns)
    if DATA_SOURCE == "excel":
        path = RAW_DIR / FILES[name]
        return _read_excel_cached(str(path), path.stat().st_mtime_ns)
    return pd.read_sql_table(name, _get_engine())


def _validate_excel_files() -> None:
    missing = [RAW_DIR / filename for filename in FILES.values() if not (RAW_DIR / filename).is_file()]
    if missing:
        paths = "\n".join(str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p) for p in missing)
        raise RuntimeError(f"[ERROR] DATA_SOURCE=excel\n필수 데이터 파일을 찾을 수 없습니다.\nMissing:\n{paths}")


@lru_cache(maxsize=1)
def _get_engine():
    from sqlalchemy import create_engine
    host = os.getenv("DB_HOST", os.getenv("MYSQL_HOST", "localhost"))
    port = int(os.getenv("DB_PORT", os.getenv("MYSQL_PORT", "3306")))
    db = os.getenv("MYSQL_DATABASE")
    user = os.getenv("MYSQL_USER", os.getenv("DB_USER"))
    password = os.getenv("MYSQL_PASSWORD", os.getenv("DB_PASSWORD"))
    if not db or not user or password is None:
        raise RuntimeError("MySQL 연결 설정이 없습니다. MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD를 확인하세요.")
    return create_engine(f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}?charset=utf8mb4", pool_pre_ping=True)


def _records(df: pd.DataFrame):
    rows = df.astype(object).where(pd.notna(df), None).to_dict(orient="records")
    for row in rows:
        for key, value in row.items():
            if hasattr(value, "isoformat"):
                row[key] = value.isoformat()
    return rows


def _prediction_label(value):
    if value is None or pd.isna(value):
        return "미산출"
    return "이탈 위험" if int(value) == 1 else "유지 예상"


def _format_probability(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value) * 100:.2f}%"


@lru_cache(maxsize=2)
def _read_predictions_cached(path: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    from src.predictions import read_prediction_csv

    return read_prediction_csv(path)


def _prediction_frame() -> pd.DataFrame:
    if not PREDICTION_CSV.exists():
        return pd.DataFrame(columns=["user_id", "snapshot_date", "churn_probability", "prediction", "risk_level", "split", "actual_churn_60d"])
    return _read_predictions_cached(str(PREDICTION_CSV), PREDICTION_CSV.stat().st_mtime_ns).copy()


def _global_latest_prediction_frame() -> pd.DataFrame:
    frame = _prediction_frame()
    if frame.empty:
        return frame
    latest = frame["snapshot_date"].max()
    return frame.loc[frame["snapshot_date"] == latest].copy()


def _latest_prediction_frame() -> pd.DataFrame:
    """Return one most-recent prediction row per user for list/detail joins."""
    frame = _prediction_frame()
    if frame.empty:
        return frame
    return (
        frame.sort_values(["user_id", "snapshot_date"], kind="stable")
        .drop_duplicates("user_id", keep="last")
        .copy()
    )


@lru_cache(maxsize=2)
def _read_risk_factors_cached(path: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
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
    return frame


def _risk_factor_frame() -> pd.DataFrame:
    columns = ["user_id", "snapshot_date", "churn_probability", *[f"risk_factor_{i}" for i in range(1, 6)]]
    if not RISK_FACTOR_CSV.exists():
        return pd.DataFrame(columns=columns)
    return _read_risk_factors_cached(str(RISK_FACTOR_CSV), RISK_FACTOR_CSV.stat().st_mtime_ns).copy()


def _risk_factors_for(user_id: int, snapshot_date) -> list[str]:
    if snapshot_date is None or pd.isna(snapshot_date):
        return []
    frame = _risk_factor_frame()
    if frame.empty:
        return []
    snapshot = pd.to_datetime(snapshot_date, utc=True).tz_convert(None).normalize()
    row = frame.loc[(frame["user_id"] == int(user_id)) & (frame["snapshot_date"] == snapshot)]
    if row.empty:
        return []
    values = row.iloc[0][[f"risk_factor_{i}" for i in range(1, 6)]]
    return [str(value).strip() for value in values if pd.notna(value) and str(value).strip()]


@lru_cache(maxsize=2)
def _read_feature_importance_cached(path: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    frame = pd.read_csv(path, encoding="utf-8-sig")
    missing = [col for col in ("feature", "importance") if col not in frame.columns]
    if missing:
        raise ValueError(f"Feature importance CSV missing columns: {missing}")
    frame = frame[["feature", "importance"]].copy()
    frame["importance"] = pd.to_numeric(frame["importance"], errors="raise")
    return frame.sort_values("importance", ascending=False, kind="stable")


def _feature_importance_frame() -> pd.DataFrame:
    if not FEATURE_IMPORTANCE_CSV.exists():
        return pd.DataFrame(columns=["feature", "importance"])
    return _read_feature_importance_cached(str(FEATURE_IMPORTANCE_CSV), FEATURE_IMPORTANCE_CSV.stat().st_mtime_ns).copy()


@lru_cache(maxsize=2)
def _read_feature_list_cached(path: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "feature" not in frame.columns:
        return pd.DataFrame(columns=["feature", "dtype"])
    if "dtype" not in frame.columns:
        frame["dtype"] = None
    return frame[["feature", "dtype"]].copy()


def _feature_list_frame() -> pd.DataFrame:
    if not FEATURE_LIST_CSV.exists():
        return pd.DataFrame(columns=["feature", "dtype"])
    return _read_feature_list_cached(str(FEATURE_LIST_CSV), FEATURE_LIST_CSV.stat().st_mtime_ns).copy()


@lru_cache(maxsize=2)
def _read_split_summary_cached(path: str, modified_ns: int) -> dict:
    del modified_ns
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _split_summary() -> dict:
    if not SPLIT_SUMMARY_JSON.exists():
        return {}
    return _read_split_summary_cached(str(SPLIT_SUMMARY_JSON), SPLIT_SUMMARY_JSON.stat().st_mtime_ns)


def _dataset_summary() -> dict:
    splits = _split_summary()
    total_rows = sum(int(v.get("rows", 0)) for v in splits.values()) if splits else None
    positive = sum(int(v.get("positive", 0)) for v in splits.values()) if splits else None
    negative = sum(int(v.get("negative", 0)) for v in splits.values()) if splits else None
    customers = None
    snapshots = None
    if FINAL_MODEL_FEATURES_CSV.exists():
        try:
            frame = pd.read_csv(FINAL_MODEL_FEATURES_CSV, usecols=["user_id", "snapshot_date", "churn_60d"], encoding="utf-8-sig")
            customers = int(frame["user_id"].nunique())
            snapshots = int(frame[["user_id", "snapshot_date"]].drop_duplicates().shape[0])
            if total_rows is None:
                total_rows = int(len(frame))
                positive = int(frame["churn_60d"].sum())
                negative = int(total_rows - positive)
        except Exception:
            app.logger.exception("model dataset summary failed")
    return {
        "total_rows": total_rows,
        "unique_customers": customers,
        "total_snapshots": snapshots or total_rows,
        "positive": positive,
        "negative": negative,
        "positive_ratio": (float(positive) / float(total_rows)) if total_rows else None,
        "splits": splits,
    }


def _prediction_stats_from_frame(frame: pd.DataFrame, total_customers: int) -> dict:
    if not frame.empty:
        frame = frame.copy()
        frame["snapshot_date"] = pd.to_datetime(frame["snapshot_date"], errors="coerce")
        current = (
            frame.sort_values(["user_id", "snapshot_date"], kind="stable")
            .drop_duplicates("user_id", keep="last")
            .copy()
        )
        latest = current["snapshot_date"].max()
        trend = (
            frame.assign(month=frame["snapshot_date"].dt.to_period("M").astype(str))
            .loc[lambda x: x["prediction"].eq(1)]
            .groupby("month")["user_id"].nunique()
            .tail(12)
        )
    else:
        current = frame.copy()
        latest = None
        trend = pd.Series(dtype="int64")
    current_counts = current["risk_level"].value_counts().reindex(RISK_LEVELS, fill_value=0)
    missing = max(0, int(total_customers) - int(current["user_id"].nunique()))
    return {
        "rows": int(len(frame)),
        "unique_users": int(frame["user_id"].nunique()) if not frame.empty else 0,
        "latest_snapshot": latest.date().isoformat() if latest is not None else None,
        "current_counts": {level: int(current_counts[level]) for level in RISK_LEVELS},
        "missing_current_predictions": missing,
        "risky_customers": int((current["prediction"] == 1).sum()) if not current.empty else 0,
        "average_probability": float(current["churn_probability"].mean()) if not current.empty else None,
        "trend": [{"month": month, "count": int(count)} for month, count in trend.items()],
    }


def _mysql_prediction_table_exists(conn) -> bool:
    return inspect(conn).has_table("customer_churn_prediction")


def _mysql_risk_factor_table_exists(conn) -> bool:
    return inspect(conn).has_table("customer_risk_factor")


def _excel_customer_version() -> tuple:
    names = ("user", "subscription", "plan", "storage_usage_monthly", "support_ticket", "payment_history")
    base = [(name, (RAW_DIR / FILES[name]).stat().st_mtime_ns) for name in names]
    pred = [("prediction", PREDICTION_CSV.stat().st_mtime_ns if PREDICTION_CSV.exists() else 0)]
    return tuple(base + pred)


@lru_cache(maxsize=2)
def _build_excel_customer_frame(version: tuple) -> pd.DataFrame:
    """Build and cache one row per user for an unchanged workbook set."""
    del version
    users, subs, plans = _read("user"), _read("subscription"), _read("plan")
    # Subscription may contain multiple rows per user. Select the most recently updated one.
    subs = subs.sort_values(["updated_at", "subscription_id"], kind="stable").drop_duplicates("user_id", keep="last")
    result = users.merge(subs, on="user_id", how="left", suffixes=("", "_subscription"))
    result = result.merge(plans, on="plan_id", how="left")
    usage = _read("storage_usage_monthly").sort_values(["usage_month", "usage_id"], kind="stable").drop_duplicates("user_id", keep="last")
    result = result.merge(usage[["user_id", "storage_used_gb", "usage_month"]], on="user_id", how="left")
    tickets = _read("support_ticket").groupby("user_id").size().rename("ticket_count").reset_index()
    result = result.merge(tickets, on="user_id", how="left")
    payments = _read("payment_history").sort_values(["payment_date", "payment_id"], kind="stable").drop_duplicates("subscription_id", keep="last")
    result = result.merge(payments[["subscription_id", "payment_status"]], on="subscription_id", how="left")
    result["ticket_count"] = result["ticket_count"].fillna(0).astype(int)
    result["customer_name"] = "고객 " + result["user_id"].astype(str)
    latest_predictions = _latest_prediction_frame()
    if not latest_predictions.empty:
        result = result.merge(
            latest_predictions[["user_id", "snapshot_date", "churn_probability", "prediction", "risk_level"]],
            on="user_id",
            how="left",
        )
    else:
        result["snapshot_date"] = None
        result["churn_probability"] = None
        result["prediction"] = None
        result["risk_level"] = None
    result["prediction_label"] = result["prediction"].map(_prediction_label)
    result["churn_probability_display"] = result["churn_probability"].map(_format_probability)
    return result


def _customer_frame() -> pd.DataFrame:
    if DATA_SOURCE == "excel":
        return _build_excel_customer_frame(_excel_customer_version())
    from sqlalchemy import text
    prediction_join = ""
    prediction_cols = "NULL snapshot_date,NULL churn_probability,NULL prediction,NULL risk_level"
    with _get_engine().connect() as conn:
        has_predictions = _mysql_prediction_table_exists(conn)
    if has_predictions:
        prediction_join = """
        LEFT JOIN customer_churn_prediction cp ON cp.user_id=u.user_id
          AND cp.snapshot_date=(
            SELECT MAX(cp2.snapshot_date)
            FROM customer_churn_prediction cp2
            WHERE cp2.user_id=u.user_id
          )
        """
        prediction_cols = "cp.snapshot_date,cp.churn_probability,cp.prediction,cp.risk_level"
    query = text(f"""SELECT u.*,s.subscription_id,s.plan_id,s.start_date,s.next_billing_date,s.end_date,
        s.auto_renewal,s.subscription_status,p.plan_name,p.storage_limit_gb,su.storage_used_gb,
        su.usage_month,COALESCE(t.ticket_count,0) ticket_count,NULL payment_status,
        CONCAT('고객 ',u.user_id) customer_name,{prediction_cols} FROM `user` u
        LEFT JOIN subscription s ON s.subscription_id=(SELECT s2.subscription_id FROM subscription s2
          WHERE s2.user_id=u.user_id ORDER BY s2.updated_at DESC,s2.subscription_id DESC LIMIT 1)
        LEFT JOIN plan p ON p.plan_id=s.plan_id
        LEFT JOIN storage_usage_monthly su ON su.usage_id=(SELECT x.usage_id FROM storage_usage_monthly x
          WHERE x.user_id=u.user_id ORDER BY x.usage_month DESC,x.usage_id DESC LIMIT 1)
        LEFT JOIN (SELECT user_id,COUNT(*) ticket_count FROM support_ticket GROUP BY user_id) t ON t.user_id=u.user_id
        {prediction_join}""")
    frame = pd.read_sql_query(query, _get_engine())
    frame["prediction_label"] = frame["prediction"].map(_prediction_label)
    frame["churn_probability_display"] = frame["churn_probability"].map(_format_probability)
    return frame


def _excel_risk_version() -> tuple:
    names = ("user", "subscription", "plan")
    base = [(name, (RAW_DIR / FILES[name]).stat().st_mtime_ns) for name in names]
    return tuple(base + [("prediction", PREDICTION_CSV.stat().st_mtime_ns if PREDICTION_CSV.exists() else 0)])


@lru_cache(maxsize=2)
def _build_excel_risk_frame(version: tuple) -> pd.DataFrame:
    """Build the risk-list projection without reading detail-only workbooks."""
    del version
    users = _read("user")[["user_id", "status"]].copy()
    subscriptions = _read("subscription").sort_values(
        ["updated_at", "subscription_id"], kind="stable"
    ).drop_duplicates("user_id", keep="last")
    plans = _read("plan")[["plan_id", "plan_name"]].copy()
    frame = users.merge(
        subscriptions[["user_id", "subscription_id", "plan_id", "next_billing_date"]],
        on="user_id", how="left",
    ).merge(plans, on="plan_id", how="left")
    predictions = _latest_prediction_frame()
    frame = frame.merge(
        predictions[["user_id", "snapshot_date", "churn_probability", "prediction", "risk_level"]],
        on="user_id", how="left",
    )
    frame["customer_name"] = "고객 " + frame["user_id"].astype(str)
    frame["prediction_label"] = frame["prediction"].map(_prediction_label)
    frame["churn_probability_display"] = frame["churn_probability"].map(_format_probability)
    return frame


def _score_customer_value(frame: pd.DataFrame) -> pd.DataFrame:
    """Assign relative customer-value scores without using churn probability."""
    from src.retention_strategy import CUSTOMER_PRIORITY_POLICY, get_customer_priority

    result = frame.copy()
    value_columns = list(CUSTOMER_PRIORITY_POLICY["weights"])
    for column in value_columns:
        result[column] = pd.to_numeric(result.get(column, 0), errors="coerce").fillna(0).clip(lower=0)
    result["customer_value_score"] = sum(
        result[column].rank(method="average", pct=True) * weight
        for column, weight in CUSTOMER_PRIORITY_POLICY["weights"].items()
    ).round(4)
    result["customer_priority"] = result["customer_value_score"].map(get_customer_priority)
    return result


@lru_cache(maxsize=2)
def _excel_strategy_profiles(version: tuple) -> pd.DataFrame:
    del version
    users = _read("user")[["user_id"]].copy()
    subscriptions = _read("subscription").copy()
    plans = _read("plan")[["plan_id", "plan_name", "monthly_price"]].copy()
    payments = _read("payment_history").copy()
    subscriptions["start_date"] = pd.to_datetime(subscriptions["start_date"], errors="coerce")
    latest = subscriptions.sort_values(["updated_at", "subscription_id"], kind="stable").drop_duplicates("user_id", keep="last")
    latest = latest.merge(plans, on="plan_id", how="left")
    active = subscriptions["subscription_status"].eq("ACTIVE").groupby(subscriptions["user_id"]).sum().rename("active_subscription_count")
    paid = payments.loc[payments["payment_status"].eq("SUCCESS"), ["subscription_id", "amount"]]
    paid = paid.merge(subscriptions[["subscription_id", "user_id"]], on="subscription_id", how="left")
    paid = paid.groupby("user_id")["amount"].sum().rename("successful_payment_amount")
    profile = users.merge(latest[["user_id", "plan_name", "monthly_price", "start_date", "next_billing_date", "auto_renewal", "subscription_status"]], on="user_id", how="left")
    profile = profile.merge(active, on="user_id", how="left").merge(paid, on="user_id", how="left")
    profile["tenure_days"] = (pd.Timestamp.now().normalize() - profile["start_date"]).dt.days.clip(lower=0)
    predictions = _latest_prediction_frame()
    if not predictions.empty:
        profile = profile.merge(predictions[["user_id", "snapshot_date", "churn_probability", "prediction", "risk_level"]], on="user_id", how="left")
    return _score_customer_value(profile)


@lru_cache(maxsize=1)
def _mysql_strategy_profiles() -> pd.DataFrame:
    from sqlalchemy import text

    with _get_engine().connect() as conn:
        has_predictions = _mysql_prediction_table_exists(conn)
        prediction_cte = """, latest_prediction AS (
            SELECT cp.*, ROW_NUMBER() OVER (PARTITION BY cp.user_id ORDER BY cp.snapshot_date DESC) rn
            FROM customer_churn_prediction cp
        )""" if has_predictions else ""
        prediction_join = "LEFT JOIN latest_prediction cp ON cp.user_id=u.user_id AND cp.rn=1" if has_predictions else ""
        prediction_cols = "cp.snapshot_date,cp.churn_probability,cp.prediction,cp.risk_level" if has_predictions else "NULL snapshot_date,NULL churn_probability,NULL prediction,NULL risk_level"
        frame = pd.read_sql_query(text(f"""
            WITH latest_subscription AS (
                SELECT s.*, ROW_NUMBER() OVER (PARTITION BY s.user_id ORDER BY s.updated_at DESC,s.subscription_id DESC) rn
                FROM subscription s
            ), active_subscriptions AS (
                SELECT user_id,SUM(subscription_status='ACTIVE') active_subscription_count
                FROM subscription GROUP BY user_id
            ), successful_payments AS (
                SELECT s.user_id,COALESCE(SUM(ph.amount),0) successful_payment_amount
                FROM subscription s LEFT JOIN payment_history ph
                  ON ph.subscription_id=s.subscription_id AND ph.payment_status='SUCCESS'
                GROUP BY s.user_id
            ){prediction_cte}
            SELECT u.user_id,ls.start_date,ls.next_billing_date,ls.auto_renewal,ls.subscription_status,p.plan_name,p.monthly_price,
                   COALESCE(a.active_subscription_count,0) active_subscription_count,
                   COALESCE(sp.successful_payment_amount,0) successful_payment_amount,
                   GREATEST(DATEDIFF(CURDATE(),ls.start_date),0) tenure_days,
                   {prediction_cols}
            FROM `user` u
            LEFT JOIN latest_subscription ls ON ls.user_id=u.user_id AND ls.rn=1
            LEFT JOIN plan p ON p.plan_id=ls.plan_id
            LEFT JOIN active_subscriptions a ON a.user_id=u.user_id
            LEFT JOIN successful_payments sp ON sp.user_id=u.user_id
            {prediction_join}
        """), conn)
    return _score_customer_value(frame)


def _strategy_profiles() -> pd.DataFrame:
    if DATA_SOURCE == "excel":
        return _excel_strategy_profiles(_excel_customer_version()).copy()
    return _mysql_strategy_profiles().copy()


def _customer_operational_metrics(user_id: int) -> list[dict]:
    """Return only operational values that exist for the selected customer."""
    metrics = []
    if DATA_SOURCE == "mysql":
        from sqlalchemy import text
        with _get_engine().connect() as conn:
            usage = conn.execute(text(
                "SELECT usage_month,storage_used_gb FROM storage_usage_monthly WHERE user_id=:user_id ORDER BY usage_month DESC,usage_id DESC LIMIT 2"
            ), {"user_id": user_id}).mappings().all()
            device_count = conn.execute(text("SELECT COUNT(*) FROM device WHERE user_id=:user_id"), {"user_id": user_id}).scalar()
            ticket_count = conn.execute(text(
                "SELECT COUNT(*) FROM support_ticket WHERE user_id=:user_id AND created_at >= (SELECT MAX(created_at) FROM support_ticket) - INTERVAL 60 DAY"
            ), {"user_id": user_id}).scalar()
            unresolved_count = conn.execute(text(
                "SELECT COUNT(*) FROM support_ticket WHERE user_id=:user_id AND status NOT IN ('RESOLVED','CLOSED')"
            ), {"user_id": user_id}).scalar()
            failed_payments = conn.execute(text(
                """SELECT COUNT(*) FROM payment_history ph JOIN subscription s ON s.subscription_id=ph.subscription_id
                   WHERE s.user_id=:user_id AND ph.payment_status='FAILED'
                     AND ph.payment_date >= (SELECT MAX(payment_date) FROM payment_history) - INTERVAL 90 DAY"""
            ), {"user_id": user_id}).scalar()
    else:
        usage_frame = _read("storage_usage_monthly")
        usage = _records(usage_frame.loc[usage_frame["user_id"].eq(user_id)].sort_values(["usage_month", "usage_id"], ascending=False).head(2))
        device_count = int(_read("device")["user_id"].eq(user_id).sum())
        tickets = _read("support_ticket").copy()
        tickets["created_at"] = pd.to_datetime(tickets["created_at"], errors="coerce")
        ticket_cutoff = tickets["created_at"].max() - pd.Timedelta(days=60)
        customer_tickets = tickets.loc[tickets["user_id"].eq(user_id)]
        ticket_count = int(customer_tickets["created_at"].ge(ticket_cutoff).sum())
        unresolved_count = int((~customer_tickets["status"].isin(["RESOLVED", "CLOSED"])).sum())
        subscriptions = _read("subscription")[["subscription_id", "user_id"]]
        payments = _read("payment_history").merge(subscriptions, on="subscription_id", how="left")
        payments["payment_date"] = pd.to_datetime(payments["payment_date"], errors="coerce")
        payment_cutoff = payments["payment_date"].max() - pd.Timedelta(days=90)
        failed_payments = int((payments["user_id"].eq(user_id) & payments["payment_status"].eq("FAILED") & payments["payment_date"].ge(payment_cutoff)).sum())
    usage = list(usage)
    if usage:
        current = float(usage[0]["storage_used_gb"])
        metrics.append({"group": "이용 변화", "label": "최근 저장소 사용량", "value": f"{current:,.1f} GB"})
        if len(usage) > 1 and usage[1].get("storage_used_gb") not in (None, 0):
            previous = float(usage[1]["storage_used_gb"])
            change = (current - previous) / previous * 100
            metrics.append({"group": "이용 변화", "label": "저장소 사용 변화", "value": f"{change:+.1f}%", "comparison": "직전 월 대비"})
    if device_count:
        metrics.append({"group": "이용 상태", "label": "등록 기기", "value": f"{int(device_count)}대"})
    if ticket_count:
        metrics.append({"group": "고객 경험", "label": "최근 Support", "value": f"{int(ticket_count)}건", "comparison": "최근 60일"})
    if unresolved_count:
        metrics.append({"group": "고객 경험", "label": "미해결 문의", "value": f"{int(unresolved_count)}건"})
    if failed_payments:
        metrics.append({"group": "결제", "label": "최근 결제 실패", "value": f"{int(failed_payments)}회", "comparison": "최근 90일"})
    return metrics


def _sql_risk_customer_page(page: int, page_size: int, query: str, risk: str, plan_name: str, sort: str, direction: str):
    """Read latest stored predictions without ranking the full history table."""
    from sqlalchemy import text

    allowed_sort = {
        "user_id": "cp.user_id", "customer_name": "cp.user_id", "plan_name": "p.plan_name",
        "next_billing_date": "s.next_billing_date", "status": "u.status",
        "risk_level": "cp.risk_level", "churn_probability": "cp.churn_probability",
    }
    order_by = allowed_sort.get(sort, "cp.user_id")
    order_dir = "DESC" if direction.lower() == "desc" else "ASC"
    params = {"offset": (page - 1) * page_size, "limit": page_size}
    filters = ["newer.user_id IS NULL"]
    if risk == "PREDICTION_1":
        filters.append("cp.prediction = 1")
    else:
        filters.append("cp.risk_level = :risk_level")
        params["risk_level"] = risk
    if query:
        filters.append("(CAST(u.user_id AS CHAR) LIKE :like_q OR CONCAT('고객 ',u.user_id) LIKE :like_q OR p.plan_name LIKE :like_q)")
        params["like_q"] = f"%{query}%"
    if plan_name:
        filters.append("p.plan_name = :plan_name")
        params["plan_name"] = plan_name
    where = " AND ".join(filters)
    latest_prediction = """
        FROM customer_churn_prediction cp
        LEFT JOIN customer_churn_prediction newer
          ON newer.user_id=cp.user_id AND newer.snapshot_date>cp.snapshot_date
    """
    customer_joins = """
        JOIN `user` u ON u.user_id=cp.user_id
        LEFT JOIN subscription s ON s.subscription_id=(
          SELECT s2.subscription_id FROM subscription s2
          WHERE s2.user_id=cp.user_id
          ORDER BY s2.updated_at DESC,s2.subscription_id DESC LIMIT 1
        )
        LEFT JOIN plan p ON p.plan_id=s.plan_id
    """
    # Count can skip customer/subscription joins when no customer-side filter is used.
    count_joins = customer_joins if query or plan_name else ""
    with _get_engine().connect() as conn:
        total = int(conn.execute(text(f"SELECT COUNT(*) {latest_prediction} {count_joins} WHERE {where}"), params).scalar() or 0)
        rows = conn.execute(text(f"""
            SELECT cp.user_id,u.status,s.subscription_id,s.plan_id,s.next_billing_date,p.plan_name,
                   cp.snapshot_date,cp.churn_probability,cp.prediction,cp.risk_level,
                   CONCAT('고객 ',u.user_id) customer_name
            {latest_prediction} {customer_joins}
            WHERE {where}
            ORDER BY {order_by} {order_dir},cp.user_id ASC
            LIMIT :limit OFFSET :offset
        """), params).mappings().all()
    items = []
    for row in rows:
        item = dict(row)
        item["prediction_label"] = _prediction_label(item.get("prediction"))
        item["churn_probability_display"] = _format_probability(item.get("churn_probability"))
        items.append(item)
    return items, total


def _sql_customer_page(page: int, page_size: int, query: str, risk: str, plan_name: str, sort: str, direction: str):
    """Fetch only the requested list page from MySQL.

    The list endpoint deliberately returns contract/user fields only. Heavy
    usage, ticket and payment history is loaded by the detail endpoint.
    """
    from sqlalchemy import text
    if risk == "PREDICTION_1" or risk in RISK_LEVELS:
        with _get_engine().connect() as conn:
            if not _mysql_prediction_table_exists(conn):
                return [], 0
        return _sql_risk_customer_page(page, page_size, query, risk, plan_name, sort, direction)
    allowed_sort = {
        "user_id": "user_id", "customer_name": "user_id", "plan_name": "plan_name",
        "next_billing_date": "next_billing_date", "status": "status",
        "risk_level": "risk_level", "churn_probability": "churn_probability",
    }
    order_by = allowed_sort.get(sort, "u.user_id")
    if order_by == "u.user_id":
        order_by = "user_id"
    order_dir = "DESC" if direction.lower() == "desc" else "ASC"
    with _get_engine().connect() as conn:
        has_predictions = _mysql_prediction_table_exists(conn)
    filters = ["(:q = '' OR CAST(u.user_id AS CHAR) LIKE :like_q OR CONCAT('고객 ', u.user_id) LIKE :like_q OR p.plan_name LIKE :like_q)"]
    params = {"q": query, "like_q": f"%{query}%", "offset": (page - 1) * page_size, "limit": page_size}
    if plan_name:
        filters.append("p.plan_name = :plan_name"); params["plan_name"] = plan_name
    if has_predictions:
        if risk == "MISSING":
            filters.append("cp.user_id IS NULL")
        elif risk in RISK_LEVELS:
            filters.append("cp.risk_level = :risk_level"); params["risk_level"] = risk
        elif risk == "PREDICTION_1":
            filters.append("cp.prediction = 1")
    elif risk:
        return [], 0
    where = " AND ".join(filters)
    prediction_cte = """,
          latest_prediction AS (
            SELECT cp.*,
                   ROW_NUMBER() OVER (
                     PARTITION BY cp.user_id
                     ORDER BY cp.snapshot_date DESC
                   ) AS rn
            FROM customer_churn_prediction cp
          )""" if has_predictions else ""
    prediction_join = "LEFT JOIN latest_prediction cp ON cp.user_id=u.user_id AND cp.rn=1" if has_predictions else ""
    prediction_cols = "cp.snapshot_date,cp.churn_probability,cp.prediction,cp.risk_level" if has_predictions else "NULL snapshot_date,NULL churn_probability,NULL prediction,NULL risk_level"
    # latest_subscription is one row per user; the page CTE applies LIMIT/OFFSET
    # before the final projection and before any detail-table access.
    filtered_where = where
    with _get_engine().connect() as conn:
        rows = conn.execute(text(f"""
          WITH ranked_subscription AS (
            SELECT s.subscription_id,s.user_id,s.plan_id,s.next_billing_date,s.updated_at,
                   ROW_NUMBER() OVER (
                     PARTITION BY s.user_id
                     ORDER BY s.updated_at DESC,s.subscription_id DESC
                   ) AS rn
            FROM subscription s
          ){prediction_cte}, filtered_users AS (
            SELECT u.user_id,u.status,rs.subscription_id,rs.plan_id,rs.next_billing_date,
                   p.plan_name,CONCAT('고객 ',u.user_id) AS customer_name,
                   {prediction_cols}
            FROM `user` u
            LEFT JOIN ranked_subscription rs ON rs.user_id=u.user_id AND rs.rn=1
            LEFT JOIN plan p ON p.plan_id=rs.plan_id
            {prediction_join}
            WHERE {filtered_where}
          ), page_users AS (
            SELECT filtered_users.*, COUNT(*) OVER() AS total_count
            FROM filtered_users
            ORDER BY {order_by} {order_dir},user_id ASC
            LIMIT :limit OFFSET :offset
          )
          SELECT user_id,status,subscription_id,plan_id,next_billing_date,plan_name,
                 snapshot_date,churn_probability,prediction,risk_level,customer_name,total_count
          FROM page_users
          ORDER BY {order_by} {order_dir},user_id ASC
        """), params).mappings().all()
    total = int(rows[0]["total_count"]) if rows else 0
    items = []
    for row in rows:
        item = dict(row)
        item.pop("total_count", None)
        item["prediction_label"] = _prediction_label(item.get("prediction"))
        item["churn_probability_display"] = _format_probability(item.get("churn_probability"))
        items.append(item)
    return items, total


def _customer_page(page: int, page_size: int, query: str, risk: str, plan_name: str, sort: str, direction: str):
    if DATA_SOURCE == "mysql":
        return _sql_customer_page(page, page_size, query, risk, plan_name, sort, direction)
    frame = _build_excel_risk_frame(_excel_risk_version()) if risk == "PREDICTION_1" or risk in RISK_LEVELS else _customer_frame()
    if query:
        q = query.lower()
        matches = frame["user_id"].astype(str).str.contains(q, regex=False)
        matches |= frame["customer_name"].astype(str).str.lower().str.contains(q, regex=False)
        matches |= frame["plan_name"].fillna("").astype(str).str.lower().str.contains(q, regex=False)
        frame = frame.loc[matches]
    if plan_name:
        frame = frame.loc[frame["plan_name"] == plan_name]
    if risk:
        if risk == "MISSING":
            frame = frame.loc[frame["risk_level"].isna()]
        elif risk == "PREDICTION_1":
            frame = frame.loc[frame["prediction"] == 1]
        elif risk in RISK_LEVELS:
            frame = frame.loc[frame["risk_level"] == risk]
        else:
            frame = frame.iloc[0:0]
    allowed_sort = {"user_id", "customer_name", "plan_name", "next_billing_date", "status", "risk_level", "churn_probability"}
    column = sort if sort in allowed_sort else "user_id"
    ascending = direction != "desc"
    frame = frame.sort_values([column, "user_id"] if column != "user_id" else ["user_id"],
                              ascending=[ascending, True] if column != "user_id" else [ascending],
                              kind="stable", na_position="last")
    total = len(frame)
    fields = [
        "user_id", "status", "subscription_id", "plan_id", "next_billing_date", "plan_name",
        "snapshot_date", "churn_probability", "churn_probability_display", "prediction",
        "prediction_label", "risk_level", "customer_name",
    ]
    return _records(frame.iloc[(page - 1) * page_size:page * page_size][fields]), total


def _page_params():
    page = max(1, request.args.get("page", default=1, type=int) or 1)
    page_size = request.args.get("page_size", default=10, type=int) or 10
    page_size = min(100, max(1, page_size))
    return page, page_size


@app.get("/")
def home(): return render_template("index.html")

@app.get("/admin")
def admin_page():
    if not session.get("admin_authenticated"): return redirect(url_for("home"))
    return render_template("admin.html")

@app.post("/api/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    try:
        _ensure_workbooks()
        admins = _read("admin")
        ok = ((admins["username"].astype(str) == str(payload.get("username", ""))) & (admins["password"].astype(str) == str(payload.get("password", "")))).any()
    except Exception:
        app.logger.exception("admin login failed")
        return jsonify(error="로그인 처리 중 서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요."), 500
    if not ok: return jsonify(error="아이디 또는 비밀번호가 올바르지 않습니다."), 401
    session["admin_authenticated"] = True
    return jsonify(ok=True, redirect="/admin")

@app.post("/api/auth/logout")
def logout():
    session.clear(); return jsonify(ok=True, redirect="/")

@app.get("/api/dashboard")
def dashboard():
    if not session.get("admin_authenticated"): return jsonify(error="로그인이 필요합니다."), 401
    if DATA_SOURCE == "excel":
        total = int(_read("user")["user_id"].nunique())
        prediction_stats = _prediction_stats_from_frame(_prediction_frame(), total)
    else:
        from sqlalchemy import text
        with _get_engine().connect() as conn:
            total = int(conn.execute(text("SELECT COUNT(DISTINCT user_id) FROM `user`")).scalar() or 0)
            if _mysql_prediction_table_exists(conn):
                frame = pd.read_sql_query(text(
                    "SELECT user_id,snapshot_date,churn_probability,prediction,risk_level,split,actual_churn_60d "
                    "FROM customer_churn_prediction"
                ), conn)
                if not frame.empty:
                    frame["snapshot_date"] = pd.to_datetime(frame["snapshot_date"])
                prediction_stats = _prediction_stats_from_frame(frame, total)
            else:
                prediction_stats = _prediction_stats_from_frame(pd.DataFrame(), total)
    from src.retention_strategy import PRIORITY_LABELS, get_action_level, map_risk_factor_to_playbook
    profiles = _strategy_profiles()
    profiles = profiles.loc[profiles["prediction"].eq(1)].copy()
    profiles["action_level"] = [get_action_level(risk, priority) for risk, priority in zip(profiles["risk_level"], profiles["customer_priority"])]
    profiles["action_rank"] = profiles["action_level"].map({"A4": 4, "A3": 3, "A2": 2, "A1": 1, "A0": 0}).fillna(0)
    top = profiles.sort_values(["action_rank", "churn_probability", "user_id"], ascending=[False, False, True], kind="stable").head(5)
    priority_customers = []
    for row in _records(top):
        factors = _risk_factors_for(row["user_id"], row.get("snapshot_date"))
        priority_customers.append({
            "user_id": row["user_id"],
            "plan_name": row.get("plan_name"),
            "snapshot_date": row.get("snapshot_date"),
            "churn_probability": row.get("churn_probability"),
            "churn_probability_display": _format_probability(row.get("churn_probability")),
            "risk_level": row.get("risk_level"),
            "customer_priority": row.get("customer_priority"),
            "customer_priority_label": PRIORITY_LABELS.get(row.get("customer_priority")),
            "action_level": row.get("action_level"),
            "risk_factors": [map_risk_factor_to_playbook(factor)["label"] for factor in factors[:2]],
        })
    return jsonify(
        total_customers=total,
        inquiries=len(_read("inquiry")),
        prediction_stats=prediction_stats,
        priority_customers=priority_customers,
    )

@app.get("/api/customers")
def customers():
    if not session.get("admin_authenticated"): return jsonify(error="로그인이 필요합니다."), 401
    page, page_size = _page_params()
    query = request.args.get("q", "").strip()[:200]
    risk = request.args.get("risk", "").strip().upper()
    plan_name = request.args.get("plan", "").strip()[:64]
    sort = request.args.get("sort", "user_id").strip()
    direction = request.args.get("direction", "asc").strip().lower()
    rows, total = _customer_page(page, page_size, query, risk, plan_name, sort, direction)
    return jsonify(items=rows, page=page, page_size=page_size, total=total, total_pages=(total + page_size - 1) // page_size, risk_data_available=True)

@app.get("/api/plans")
def plans():
    if not session.get("admin_authenticated"): return jsonify(error="로그인이 필요합니다."), 401
    values = sorted({str(v).strip() for v in _read("plan")["plan_name"].dropna() if str(v).strip()})
    return jsonify(items=values)


@app.get("/api/model/feature-importance")
def feature_importance():
    if not session.get("admin_authenticated"): return jsonify(error="로그인이 필요합니다."), 401
    limit = min(77, max(1, request.args.get("limit", default=15, type=int) or 15))
    from src.model_metadata import feature_metadata

    frame = _feature_importance_frame()
    rows = []
    for row in _records(frame.head(limit)):
        rows.append({**row, **feature_metadata(row["feature"])})
    return jsonify(items=rows, total=int(len(frame)), source=str(FEATURE_IMPORTANCE_CSV.relative_to(ROOT)))


@app.get("/api/model/info")
def model_info():
    if not session.get("admin_authenticated"): return jsonify(error="로그인이 필요합니다."), 401
    from src.model_metadata import (
        METRIC_DESCRIPTIONS,
        MODEL_INFO,
        MODEL_PERFORMANCE,
        RISK_LEVEL_DESCRIPTIONS,
        feature_metadata,
    )

    features = []
    for row in _records(_feature_list_frame()):
        features.append({**feature_metadata(row["feature"]), "dtype": row.get("dtype")})
    importance = []
    for row in _records(_feature_importance_frame().head(10)):
        importance.append({**row, **feature_metadata(row["feature"])})
    risk_levels = [
        {
            "level": level,
            "ko_name": RISK_LABELS_KO[level],
            "probability_range": RISK_BANDS[level],
            "basis": RISK_PERCENTILE_BASIS[level],
            "description": RISK_LEVEL_DESCRIPTIONS[level],
        }
        for level in RISK_LEVELS
    ]
    return jsonify(
        model={**MODEL_INFO, "model_file_exists": (ROOT / MODEL_INFO["model_file"]).exists()},
        performance={**MODEL_PERFORMANCE, "metric_descriptions": METRIC_DESCRIPTIONS},
        risk_levels=risk_levels,
        features=features,
        feature_importance=importance,
        dataset=_dataset_summary(),
        sources={
            "performance": MODEL_PERFORMANCE["source"],
            "feature_importance": str(FEATURE_IMPORTANCE_CSV.relative_to(ROOT)),
            "feature_metadata": "src/model_metadata.py",
            "risk_levels": "app.py RISK_BANDS + models/v3/predict.py RISK_CUTOFFS",
            "dataset": str(SPLIT_SUMMARY_JSON.relative_to(ROOT)) if SPLIT_SUMMARY_JSON.exists() else None,
        },
    )


@app.get("/api/retention/customers")
def retention_customers():
    if not session.get("admin_authenticated"): return jsonify(error="로그인이 필요합니다."), 401
    page = max(1, request.args.get("page", default=1, type=int) or 1)
    page_size = min(50, max(1, request.args.get("page_size", default=12, type=int) or 12))
    query = request.args.get("q", "").strip().lower()[:200]
    risk = request.args.get("risk", "").strip().upper()
    priority = request.args.get("priority", "").strip().upper()
    action = request.args.get("action", "").strip().upper()
    from src.retention_strategy import PRIORITY_LABELS, get_action_level

    frame = _strategy_profiles()
    frame = frame.loc[frame["prediction"].eq(1)].copy()
    frame["action_level"] = [get_action_level(risk_level, customer_priority) for risk_level, customer_priority in zip(frame["risk_level"], frame["customer_priority"])]
    if query:
        ids = frame["user_id"].astype(str)
        plans = frame["plan_name"].fillna("").astype(str).str.lower()
        frame = frame.loc[ids.str.contains(query, regex=False) | ("u" + ids).str.contains(query, regex=False) | plans.str.contains(query, regex=False)]
    if risk in RISK_LEVELS:
        frame = frame.loc[frame["risk_level"].eq(risk)]
    if priority in PRIORITY_LABELS:
        frame = frame.loc[frame["customer_priority"].eq(priority)]
    if action in {"A0", "A1", "A2", "A3", "A4"}:
        frame = frame.loc[frame["action_level"].eq(action)]
    frame = frame.sort_values(["churn_probability", "user_id"], ascending=[False, True], kind="stable")
    total = len(frame)
    page_rows = frame.iloc[(page - 1) * page_size:page * page_size].copy()
    page_rows["customer_name"] = "고객 " + page_rows["user_id"].astype(str)
    page_rows["customer_priority_label"] = page_rows["customer_priority"].map(PRIORITY_LABELS)
    page_rows["churn_probability_display"] = page_rows["churn_probability"].map(_format_probability)
    columns = ["user_id", "customer_name", "plan_name", "snapshot_date", "churn_probability", "churn_probability_display", "risk_level", "customer_priority", "customer_priority_label", "action_level"]
    return jsonify(items=_records(page_rows[columns]), page=page, page_size=page_size, total=total, total_pages=(total + page_size - 1) // page_size)


@app.get("/api/customers/<int:user_id>/strategy")
def customer_strategy(user_id):
    if not session.get("admin_authenticated"): return jsonify(error="로그인이 필요합니다."), 401
    from src.retention_strategy import build_customer_strategy

    frame = _strategy_profiles()
    row = frame.loc[frame["user_id"].eq(user_id)]
    if row.empty:
        return jsonify(error="고객을 찾을 수 없습니다."), 404
    customer = _records(row.head(1))[0]
    customer["customer_name"] = f"고객 {user_id}"
    customer["churn_probability_display"] = _format_probability(customer.get("churn_probability"))
    customer["operational_metrics"] = _customer_operational_metrics(user_id)
    factors = _risk_factors_for(user_id, customer.get("snapshot_date"))
    return jsonify(data=build_customer_strategy(customer, factors))

@app.get("/api/customers/<int:user_id>")
def customer_detail(user_id):
    if not session.get("admin_authenticated"): return jsonify(error="로그인이 필요합니다."), 401
    if DATA_SOURCE == "mysql":
        from sqlalchemy import text
        engine = _get_engine()
        with engine.connect() as conn:
            has_predictions = _mysql_prediction_table_exists(conn)
            prediction_join = """
                LEFT JOIN customer_churn_prediction cp ON cp.user_id=u.user_id
                    AND cp.snapshot_date=(
                        SELECT MAX(cp2.snapshot_date)
                        FROM customer_churn_prediction cp2
                        WHERE cp2.user_id=u.user_id
                    )
            """ if has_predictions else ""
            prediction_cols = "cp.snapshot_date,cp.churn_probability,cp.prediction,cp.risk_level" if has_predictions else "NULL snapshot_date,NULL churn_probability,NULL prediction,NULL risk_level"
            row = conn.execute(text("""
                SELECT u.user_id,u.status,s.subscription_id,s.plan_id,s.start_date,
                       s.next_billing_date,s.end_date,s.auto_renewal,s.subscription_status,
                       p.plan_name,p.storage_limit_gb,CONCAT('고객 ',u.user_id) customer_name,
                       """ + prediction_cols + """
                FROM `user` u
                LEFT JOIN subscription s ON s.subscription_id=(
                    SELECT s2.subscription_id FROM subscription s2
                    WHERE s2.user_id=u.user_id
                    ORDER BY s2.updated_at DESC,s2.subscription_id DESC LIMIT 1
                )
                LEFT JOIN plan p ON p.plan_id=s.plan_id
                """ + prediction_join + """
                WHERE u.user_id=:user_id
            """), {"user_id": user_id}).mappings().first()
            if row is None: return jsonify(error="고객을 찾을 수 없습니다."), 404
            data = dict(row)
            data["prediction_label"] = _prediction_label(data.get("prediction"))
            data["churn_probability_display"] = _format_probability(data.get("churn_probability"))
            if has_predictions:
                data["prediction_history"] = [dict(r) for r in conn.execute(text(
                    """SELECT snapshot_date,churn_probability,prediction,risk_level
                       FROM customer_churn_prediction
                       WHERE user_id=:user_id
                       ORDER BY snapshot_date DESC"""
                ), {"user_id": user_id}).mappings()]
            else:
                data["prediction_history"] = []
            data["risk_factors"] = []
            if has_predictions and _mysql_risk_factor_table_exists(conn) and data.get("snapshot_date") is not None:
                factor_row = conn.execute(text(
                    """SELECT risk_factor_1,risk_factor_2,risk_factor_3,risk_factor_4,risk_factor_5
                       FROM customer_risk_factor
                       WHERE user_id=:user_id AND snapshot_date=:snapshot_date"""
                ), {"user_id": user_id, "snapshot_date": data["snapshot_date"]}).mappings().first()
                if factor_row:
                    data["risk_factors"] = [str(value).strip() for value in factor_row.values() if value is not None and str(value).strip()]
            if not data["risk_factors"]:
                data["risk_factors"] = _risk_factors_for(user_id, data.get("snapshot_date"))
            data["usage"] = [dict(r) for r in conn.execute(text(
                "SELECT * FROM storage_usage_monthly WHERE user_id=:user_id ORDER BY usage_month DESC,usage_id DESC"
            ), {"user_id": user_id}).mappings()]
            data["devices"] = [dict(r) for r in conn.execute(text(
                "SELECT * FROM device WHERE user_id=:user_id ORDER BY registered_at DESC,device_id DESC"
            ), {"user_id": user_id}).mappings()]
            data["tickets"] = [dict(r) for r in conn.execute(text(
                "SELECT * FROM support_ticket WHERE user_id=:user_id ORDER BY created_at DESC,ticket_id DESC"
            ), {"user_id": user_id}).mappings()]
            data["payments"] = [dict(r) for r in conn.execute(text(
                """SELECT ph.* FROM payment_history ph
                   JOIN subscription s ON s.subscription_id=ph.subscription_id
                   WHERE s.user_id=:user_id
                   ORDER BY ph.payment_date DESC,ph.payment_id DESC"""
            ), {"user_id": user_id}).mappings()]
        return jsonify(data=_records(pd.DataFrame([data]))[0])
    c = _customer_frame(); row = c[c.user_id == user_id]
    if row.empty: return jsonify(error="고객을 찾을 수 없습니다."), 404
    subscription_ids = _read("subscription").loc[lambda df: df["user_id"] == user_id, "subscription_id"]
    payments = _read("payment_history")
    data = row.iloc[0].to_dict()
    history = _prediction_frame()
    if not history.empty:
        history = history.loc[history["user_id"] == user_id, ["snapshot_date", "churn_probability", "prediction", "risk_level"]].sort_values("snapshot_date", ascending=False)
    data["prediction_history"] = _records(history) if not history.empty else []
    data["risk_factors"] = _risk_factors_for(user_id, data.get("snapshot_date"))
    data.update(
        usage=_records(_read("storage_usage_monthly").query("user_id == @user_id")),
        devices=_records(_read("device").query("user_id == @user_id")),
        tickets=_records(_read("support_ticket").query("user_id == @user_id")),
        payments=_records(payments[payments["subscription_id"].isin(subscription_ids)]),
    )
    return jsonify(data=_records(pd.DataFrame([data]))[0])

@app.get("/api/inquiries")
def inquiries():
    if not session.get("admin_authenticated"): return jsonify(error="로그인이 필요합니다."), 401
    return jsonify(items=_records(_read("inquiry")))

@app.post("/api/inquiries")
def create_inquiry():
    payload = request.get_json(silent=True) or {}
    required = ["name", "email", "topic", "message"]
    if any(not str(payload.get(k, "")).strip() for k in required): return jsonify(error="필수 항목을 입력해주세요."), 400
    _ensure_workbooks()
    if DATA_SOURCE == "excel":
        with _inquiry_lock:
            df = _read("inquiry"); next_id = int(df["inquiry_id"].max()) + 1 if not df.empty else 1
            row = {"inquiry_id": next_id, **{k: str(payload[k]).strip() for k in required}, "status": "RECEIVED", "created_at": datetime.now().isoformat(timespec="seconds")}
            target = DATA_DIR / "inquiry.xlsx"
            temporary = DATA_DIR / "inquiry.pending.xlsx"
            try:
                pd.concat([df, pd.DataFrame([row])], ignore_index=True).to_excel(temporary, index=False)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
            _read_excel_cached.cache_clear()
    else:
        from sqlalchemy import text
        with _get_engine().begin() as conn: conn.execute(text("INSERT INTO inquiry (name,email,topic,message,status,created_at) VALUES (:name,:email,:topic,:message,'RECEIVED',NOW())"), payload)
    return jsonify(ok=True)

if __name__ == "__main__":
    if DATA_SOURCE == "excel":
        _validate_excel_files()
        shown_dir = RAW_DIR.relative_to(ROOT) if RAW_DIR.is_relative_to(ROOT) else RAW_DIR
        print(f"CloudCare / 어딜가 | DATA SOURCE: EXCEL | DATA DIR: {shown_dir} | MySQL: NOT USED", flush=True)
    else:
        from sqlalchemy import text
        with _get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"CloudCare / 어딜가 | DATA SOURCE: MYSQL | DATABASE: {os.getenv('MYSQL_DATABASE', '')}", flush=True)
    _ensure_workbooks()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
