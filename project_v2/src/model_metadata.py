"""Display metadata for the CloudCare V3 model administration screen."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODEL_INFO = {
    "model_name": "LightGBM",
    "model_version": "V3",
    "model_file": "models/v3/final_model_v3.joblib",
    "threshold": 0.432,
    "feature_count": 77,
    "risk_level_count": 5,
    "prediction_snapshot_basis": "user_id + snapshot_date 기준 월별 Snapshot",
    "target": "churn_60d",
    "target_description": "해당 Snapshot 시점으로부터 60일 이내 고객이 이탈하는지를 나타내는 Target",
    "prediction_window": "D-60",
    "preprocessing": [
        "SimpleImputer(strategy='median')",
        "StandardScaler",
        "age_group / region / signup_channel 원-핫 인코딩",
        "Encoder / Scaler / Imputer는 final_model_v3.joblib 내부 bundle에 포함",
    ],
}

MODEL_PERFORMANCE = {
    "source": "models/v3/model_evaluation_report_v3.md",
    "split": "Test",
    "threshold": 0.432,
    "metrics": {
        "accuracy": 0.9544,
        "precision": 0.2365,
        "recall": 0.7273,
        "f1": 0.3569,
        "roc_auc": 0.9516,
        "pr_auc": 0.3972,
    },
    "confusion_matrix": {"TN": 3576, "FP": 155, "FN": 18, "TP": 48},
}

RISK_LEVEL_DESCRIPTIONS = {
    "VERY HIGH": "전체 예측 확률분포에서 최상위 구간에 있는 고객입니다.",
    "HIGH": "이탈 가능성이 높은 구간에 속해 우선 확인이 필요한 고객입니다.",
    "MEDIUM": "일반 고객보다 이탈 신호가 상대적으로 높은 고객입니다.",
    "LOW": "이탈 신호가 낮은 편인 고객입니다.",
    "VERY LOW": "현재 예측 기준에서 이탈 신호가 가장 낮은 구간의 고객입니다.",
}

METRIC_DESCRIPTIONS = {
    "accuracy": "전체 예측 중 맞춘 비율",
    "precision": "이탈한다고 예측한 고객 중 실제 이탈 고객 비율",
    "recall": "실제 이탈 고객 중 모델이 찾아낸 비율",
    "f1": "Precision과 Recall의 균형",
    "roc_auc": "이탈/유지 고객을 구분하는 모델의 전반적인 능력",
    "pr_auc": "불균형 데이터에서 이탈 고객 탐지 성능 확인에 유용",
}

FEATURE_METADATA = {
    "account_age_days": ("고객 기본 정보", "계정 생성 후 경과일", "계정이 생성된 뒤 Snapshot 시점까지 지난 일수입니다."),
    "login_count_30d": ("사용량 / 활동", "최근 30일 로그인 횟수", "최근 30일 동안 고객이 로그인한 횟수입니다."),
    "login_count_prev30d": ("사용량 / 활동", "이전 30일 로그인 횟수", "최근 30일 직전 기간의 로그인 횟수입니다."),
    "login_change_rate_30d": ("사용량 / 활동", "로그인 변화율", "이전 30일 대비 최근 30일 로그인 횟수가 얼마나 변했는지 나타냅니다."),
    "login_slope_90d": ("사용량 / 활동", "90일 로그인 추세", "최근 90일 동안 로그인 활동이 늘거나 줄어드는 흐름입니다."),
    "active_days_30d": ("사용량 / 활동", "최근 30일 활성 일수", "최근 30일 중 실제로 서비스를 사용한 날짜 수입니다."),
    "active_days_change_rate": ("사용량 / 활동", "활성 일수 변화율", "이전 기간 대비 서비스 사용 일수가 얼마나 변했는지 나타냅니다."),
    "active_minutes_30d": ("사용량 / 활동", "최근 30일 사용 시간", "최근 30일 동안 서비스를 사용한 총 시간입니다."),
    "active_minutes_change_rate": ("사용량 / 활동", "사용 시간 변화율", "이전 기간 대비 최근 사용 시간이 얼마나 변했는지 나타냅니다."),
    "action_count_30d": ("사용량 / 활동", "최근 30일 주요 행동 수", "최근 30일 동안 서비스 안에서 발생한 주요 행동 횟수입니다."),
    "action_count_change_rate": ("사용량 / 활동", "주요 행동 변화율", "이전 기간 대비 서비스 내 주요 행동이 얼마나 변했는지 나타냅니다."),
    "days_since_last_activity": ("사용량 / 활동", "마지막 활동 후 경과일", "고객이 마지막으로 서비스를 사용한 뒤 지난 일수입니다."),
    "storage_used_gb_latest": ("사용량 / 활동", "최근 스토리지 사용량", "가장 최근 Snapshot 기준 스토리지 사용량입니다."),
    "storage_change_rate_1m": ("사용량 / 활동", "1개월 스토리지 변화율", "직전 1개월 동안 스토리지 사용량이 얼마나 변했는지 나타냅니다."),
    "storage_change_rate_3m": ("사용량 / 활동", "3개월 스토리지 변화율", "최근 3개월 동안 스토리지 사용량이 얼마나 변했는지 나타냅니다."),
    "storage_slope_90d": ("사용량 / 활동", "90일 스토리지 추세", "최근 90일 동안 스토리지 사용량이 늘거나 줄어드는 흐름입니다."),
    "consecutive_storage_decline_months": ("사용량 / 활동", "연속 스토리지 감소 개월 수", "스토리지 사용량이 연속해서 감소한 개월 수입니다."),
    "storage_utilization_ratio": ("사용량 / 활동", "스토리지 사용률", "계약한 저장공간 한도 대비 실제 사용 중인 비율입니다."),
    "payment_count_90d": ("결제", "최근 90일 결제 횟수", "최근 90일 동안 발생한 결제 건수입니다."),
    "failed_payment_count_30d": ("결제", "최근 30일 결제 실패 횟수", "최근 30일 동안 결제가 실패한 횟수입니다."),
    "failed_payment_count_90d": ("결제", "최근 90일 결제 실패 횟수", "최근 90일 동안 결제가 실패한 횟수입니다."),
    "payment_failure_rate_90d": ("결제", "최근 90일 결제 실패율", "최근 90일 결제 중 실패한 비율입니다."),
    "retry_count_90d": ("결제", "최근 90일 재시도 횟수", "최근 90일 동안 결제 재시도가 발생한 횟수입니다."),
    "overdue_count_90d": ("결제", "최근 90일 연체 횟수", "최근 90일 동안 결제 연체가 발생한 횟수입니다."),
    "days_since_last_failed_payment": ("결제", "마지막 결제 실패 후 경과일", "마지막 결제 실패 이후 지난 일수입니다."),
    "days_since_last_failed_payment_never": ("결제", "결제 실패 없음 여부", "결제 실패 기록이 없는 고객인지 표시하는 값입니다."),
    "ticket_count_30d": ("고객 지원", "최근 30일 문의 수", "최근 30일 동안 접수된 고객 문의 건수입니다."),
    "ticket_count_90d": ("고객 지원", "최근 90일 문의 수", "최근 90일 동안 접수된 고객 문의 건수입니다."),
    "ticket_change_rate": ("고객 지원", "문의 수 변화율", "이전 기간 대비 문의 건수가 얼마나 변했는지 나타냅니다."),
    "urgent_ticket_share": ("고객 지원", "긴급 문의 비중", "전체 문의 중 긴급 성격 문의가 차지하는 비율입니다."),
    "unresolved_ticket_count": ("고객 지원", "미해결 문의 수", "Snapshot 시점까지 해결되지 않은 문의 건수입니다."),
    "avg_resolution_hours_90d": ("고객 지원", "최근 90일 평균 해결 시간", "최근 90일 문의가 해결되기까지 걸린 평균 시간입니다."),
    "downgrade_count_90d": ("구독 / 계약", "최근 90일 다운그레이드 횟수", "최근 90일 동안 요금제 다운그레이드가 발생한 횟수입니다."),
    "days_since_last_downgrade": ("구독 / 계약", "마지막 다운그레이드 후 경과일", "마지막 다운그레이드 이후 지난 일수입니다."),
    "days_since_last_downgrade_never": ("구독 / 계약", "다운그레이드 없음 여부", "다운그레이드 기록이 없는 고객인지 표시하는 값입니다."),
    "plan_change_count_90d": ("구독 / 계약", "최근 90일 요금제 변경 횟수", "최근 90일 동안 요금제 변경이 발생한 횟수입니다."),
    "days_to_renewal": ("구독 / 계약", "갱신일까지 남은 일수", "다음 결제 또는 계약 갱신일까지 남은 일수입니다."),
    "auto_renewal_off_flag": ("구독 / 계약", "자동 갱신 해제 여부", "자동 갱신이 꺼져 있는 고객인지 표시합니다."),
    "active_sub_count_asof": ("구독 / 계약", "활성 구독 수", "Snapshot 시점 기준 활성 상태인 구독 수입니다."),
    "paid_sub_count_asof": ("구독 / 계약", "유료 구독 수", "Snapshot 시점 기준 유료 구독 수입니다."),
    "total_storage_limit_gb": ("구독 / 계약", "총 스토리지 한도", "고객이 계약한 전체 저장공간 한도입니다."),
    "total_monthly_price": ("구독 / 계약", "월 구독료 합계", "고객의 월 구독료 합계입니다."),
    "min_tenure_days": ("구독 / 계약", "최단 구독 유지일", "고객 구독 중 가장 짧은 유지 기간입니다."),
    "max_tenure_days": ("구독 / 계약", "최장 구독 유지일", "고객 구독 중 가장 긴 유지 기간입니다."),
    "device_count_asof": ("기기", "등록 기기 수", "Snapshot 시점까지 등록된 기기 수입니다."),
    "device_type_count": ("기기", "기기 종류 수", "고객이 사용하는 기기 종류의 수입니다."),
    "os_type_count": ("기기", "OS 종류 수", "고객이 사용하는 운영체제 종류의 수입니다."),
    "devices_per_account_year": ("기기", "계정 연수 대비 기기 수", "계정 사용 기간을 1년 단위로 환산했을 때 등록된 기기 수입니다."),
    "device_count_per_tenure": ("기기", "가입기간 대비 등록 기기 수", "고객이 서비스를 이용한 기간을 고려하여 등록된 기기 수를 나타낸 값입니다."),
    "device_count_per_sqrt_age": ("기기", "가입기간 보정 기기 수", "가입 기간의 영향을 완화해 등록 기기 수를 비교하기 위한 값입니다."),
    "days_since_last_activity_never": ("사용량 / 활동", "활동 기록 없음 여부", "서비스 활동 기록이 없는 고객인지 표시하는 값입니다."),
}


def _one_hot_metadata(feature: str) -> tuple[str, str, str] | None:
    if feature.startswith("age_group_"):
        value = feature.removeprefix("age_group_")
        return ("고객 기본 정보", f"연령대 {value} 여부", f"고객의 연령대가 {value}인지 표시하는 값입니다.")
    if feature.startswith("region_"):
        value = feature.removeprefix("region_")
        return ("고객 기본 정보", f"지역 {value} 여부", f"고객의 지역이 {value}인지 표시하는 값입니다.")
    if feature.startswith("signup_channel_"):
        value = feature.removeprefix("signup_channel_")
        return ("고객 기본 정보", f"가입 채널 {value} 여부", f"고객의 가입 채널이 {value}인지 표시하는 값입니다.")
    return None


def feature_metadata(feature: str) -> dict:
    category, ko_name, description = FEATURE_METADATA.get(feature) or _one_hot_metadata(feature) or (
        "기타",
        feature,
        "현재 코드/데이터 정의에서 별도 설명을 확인하지 못했습니다.",
    )
    return {
        "feature": feature,
        "category": category,
        "ko_name": ko_name,
        "description": description,
    }
