# -*- coding: utf-8 -*-
"""
CloudCare AI 이탈예측 — 최종 모델 추론 스크립트

흐름:
  고객 데이터 불러오기 -> feature 선택/전처리 -> 모델 load -> predict_proba
  -> churn_probability -> prediction -> risk_level(5단계)

사용법:
  python predict.py input.csv output.csv
"""
import sys
import numpy as np
import pandas as pd
import joblib

MODEL_PATH = "final_model_v3.joblib"
TARGET = "churn_60d"

# 원본 스키마에서 999는 "해당 이벤트가 한번도 발생하지 않음"을 의미하는 sentinel 값
SENTINEL_COLS = ["days_since_last_activity", "days_since_last_failed_payment", "days_since_last_downgrade"]
CATEGORICAL = ["age_group", "region", "signup_channel"]

# risk_level 5단계 컷오프 (Validation 확률분포 percentile 기준, 전체 60,371명 population 기준 산출)
# 근거: quiz VERY HIGH=상위1%, HIGH=상위1~5%, MEDIUM=상위5~20%, LOW=상위20~50%, VERY LOW=하위50%
RISK_CUTOFFS = {
    "VERY HIGH": 0.9745,
    "HIGH": 0.6321,
    "MEDIUM": 0.0554,
    "LOW": 0.0033,
}


def clean_reopened(df: pd.DataFrame) -> pd.DataFrame:
    """reopened_count_90d 컬럼의 타입 혼재(숫자/문자열 'True'/'False') 버그 정리"""
    d = df.copy()
    if "reopened_count_90d" in d.columns:
        d["reopened_count_90d"] = d["reopened_count_90d"].replace(
            {"True": 1, "False": 0, True: 1, False: 0}
        )
        d["reopened_count_90d"] = pd.to_numeric(d["reopened_count_90d"], errors="coerce")
    return d


def handle_sentinel(df: pd.DataFrame) -> pd.DataFrame:
    """999(이벤트 없음)를 NaN으로 바꾸고, '이벤트 자체가 없음' 플래그(_never)를 추가 생성"""
    d = df.copy()
    for c in SENTINEL_COLS:
        d[f"{c}_never"] = (d[c] == 999).astype(int)
        d[c] = d[c].replace(999, np.nan)
    return d


def one_hot(df: pd.DataFrame, category_levels: dict) -> pd.DataFrame:
    """Train에서 fit된 카테고리 목록(category_levels) 기준으로 원-핫 인코딩.
    Train에 없던 새로운 카테고리 값이 들어와도 모든 컬럼이 0이 되어 안전하게 처리됨."""
    d = df.copy()
    for c, levels in category_levels.items():
        for lv in levels:
            d[f"{c}_{lv}"] = (d[c] == lv).astype(int)
    return d


def risk_level(p: float) -> str:
    if p >= RISK_CUTOFFS["VERY HIGH"]:
        return "VERY HIGH"
    elif p >= RISK_CUTOFFS["HIGH"]:
        return "HIGH"
    elif p >= RISK_CUTOFFS["MEDIUM"]:
        return "MEDIUM"
    elif p >= RISK_CUTOFFS["LOW"]:
        return "LOW"
    return "VERY LOW"


def predict(input_csv: str, output_csv: str, model_path: str = MODEL_PATH):
    # 1. 고객 데이터 불러오기
    df = pd.read_csv(input_csv)

    # 2. 모델 번들 load (model + imputer + scaler + features + category_levels 전부 포함)
    bundle = joblib.load(model_path)
    model = bundle["model"]
    imputer = bundle["imputer"]
    scaler = bundle["scaler"]
    features = bundle["features"]          # 77개, 순서 고정
    category_levels = bundle["category_levels"]
    threshold = bundle["threshold_recommended"]  # 0.432

    # 3. 전처리 (학습 때와 완전히 동일한 순서: clean -> sentinel -> one-hot -> impute -> scale)
    d = clean_reopened(df)
    d = handle_sentinel(d)
    d = one_hot(d, category_levels)

    missing_cols = [c for c in features if c not in d.columns]
    if missing_cols:
        raise ValueError(f"입력 데이터에 다음 feature가 없습니다: {missing_cols}")

    X = d[features]                        # 순서 고정
    X_imp = imputer.transform(X)
    X_scaled = scaler.transform(X_imp)

    # 4. 모델 예측 (predict_proba)
    churn_probability = model.predict_proba(X_scaled)[:, 1]
    prediction = (churn_probability >= threshold).astype(int)
    risk = [risk_level(p) for p in churn_probability]

    # 5. 결과 조립
    id_cols = [c for c in ["user_id", "snapshot_date"] if c in df.columns]
    out = df[id_cols].copy()
    out["churn_probability"] = np.round(churn_probability, 4)
    out["prediction"] = prediction
    out["risk_level"] = risk

    out.to_csv(output_csv, index=False, encoding="utf-8-sig")
    print(f"완료: {len(out)}행 예측 -> {output_csv}")
    return out


if __name__ == "__main__":
    if len(sys.argv) == 3:
        predict(sys.argv[1], sys.argv[2])
    else:
        # ===== 고객 1명 예시 =====
        sample = pd.DataFrame([{
            "user_id": 999999,
            "snapshot_date": "2026-06-30",
            "account_age_days": 400,
            "age_group": "30대", "region": "서울", "signup_channel": "IOS",
            "login_count_30d": 1, "login_count_prev30d": 10, "login_change_rate_30d": -0.9,
            "login_slope_90d": -0.3,
            "active_days_30d": 1, "active_days_change_rate": -0.8,
            "active_minutes_30d": 5, "active_minutes_change_rate": -0.9,
            "action_count_30d": 2, "action_count_change_rate": -0.85,
            "days_since_last_activity": 25,
            "storage_used_gb_latest": 80, "storage_change_rate_1m": -0.2, "storage_change_rate_3m": -0.35,
            "storage_slope_90d": -0.1, "consecutive_storage_decline_months": 3, "storage_utilization_ratio": 0.9,
            "payment_count_90d": 1, "failed_payment_count_30d": 1, "failed_payment_count_90d": 2,
            "payment_failure_rate_90d": 0.5, "retry_count_90d": 2, "overdue_count_90d": 1,
            "days_since_last_failed_payment": 5,
            "ticket_count_30d": 2, "ticket_count_90d": 4, "ticket_change_rate": 0.5,
            "urgent_ticket_share": 0.5, "reopened_count_90d": 1, "avg_resolution_hours_90d": 48,
            "unresolved_ticket_count": 1,
            "downgrade_count_90d": 1, "days_since_last_downgrade": 10, "plan_change_count_90d": 1,
            "days_to_renewal": 5, "auto_renewal_off_flag": 1,
            "device_count_asof": 1, "device_type_count": 1, "os_type_count": 1,
            "devices_per_account_year": 0.9, "device_count_per_tenure": 0.0025, "device_count_per_sqrt_age": 0.05,
            "active_sub_count_asof": 1, "paid_sub_count_asof": 1,
            "total_storage_limit_gb": 100, "total_monthly_price": 4900,
            "min_tenure_days": 400, "max_tenure_days": 400,
        }])
        sample.to_csv("_sample_input.csv", index=False)
        predict("_sample_input.csv", "_sample_output.csv")
        print(pd.read_csv("_sample_output.csv").to_string(index=False))
