"""Business rules for customer retention strategy recommendations."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any


CUSTOMER_PRIORITY_POLICY = {
    "weights": {
        "successful_payment_amount": 0.40,
        "monthly_price": 0.25,
        "active_subscription_count": 0.20,
        "tenure_days": 0.15,
    },
    "p1_min_score": 0.80,
    "p2_min_score": 0.40,
}

ACTION_MATRIX = {
    "VERY HIGH": {"P1": "A4", "P2": "A4", "P3": "A3"},
    "HIGH": {"P1": "A4", "P2": "A3", "P3": "A2"},
    "MEDIUM": {"P1": "A3", "P2": "A2", "P3": "A1"},
    "LOW": {"P1": "A2", "P2": "A1", "P3": "A0"},
    "VERY LOW": {"P1": "A1", "P2": "A0", "P3": "A0"},
}

PRIORITY_LABELS = {"P1": "핵심", "P2": "중요", "P3": "일반"}
ACTION_POLICIES = {
    "A4": {"label": "긴급 대응", "urgency": "최우선", "deadline": "1영업일 내", "contact": "담당자 직접 연락", "headline": "1영업일 내 담당자 직접 확인이 필요합니다.", "core_action": "위험 신호와 실제 고객 상태를 확인하고 필요 시 Support·기술 담당과 협업합니다."},
    "A3": {"label": "집중 대응", "urgency": "높음", "deadline": "1~2영업일", "contact": "담당자 직접 확인", "headline": "1~2영업일 안에 고객 상황을 직접 확인해주세요.", "core_action": "고객 상황에 맞는 지원을 준비하고 담당자가 후속 조치를 관리합니다."},
    "A2": {"label": "선제 대응", "urgency": "보통", "deadline": "3~5영업일", "contact": "맞춤 안내 후 상담 연결", "headline": "3~5영업일 안에 맞춤 안내를 시작해주세요.", "core_action": "맞춤 안내 후 반응이 없거나 위험도가 상승하면 상담으로 연결합니다."},
    "A1": {"label": "예방 관리", "urgency": "정기", "deadline": "정기 운영", "contact": "가이드·리포트 안내", "headline": "정기 운영 과정에서 예방 관리를 이어가세요.", "core_action": "활용 가이드와 서비스 리포트를 제공하며 관계를 관리합니다."},
    "A0": {"label": "모니터링", "urgency": "관찰", "deadline": "정기 관찰", "contact": "별도 연락 없음", "headline": "현재는 정기 관찰과 변화 추적이 적절합니다.", "core_action": "강한 유지 캠페인 없이 다음 예측과 실제 이용 변화를 추적합니다."},
}

PLAYBOOKS = (
    {"key": "usage", "category": "제품 활용", "label": "사용량·활동 감소", "keywords": ("사용량", "활동", "로그인", "액션", "workload"), "summary": "최근 이용 패턴에서 확인이 필요한 변화 신호가 관측되었습니다.", "steps": ("기능 활용을 방해하는 이유 확인", "온보딩 / 활용 교육", "재사용 여부 확인")},
    {"key": "storage", "category": "제품 활용", "label": "저장소 사용 감소", "keywords": ("스토리지", "storage"), "summary": "저장소 이용 패턴에서 확인이 필요한 변화 신호가 관측되었습니다.", "steps": ("업무 패턴 변화 확인", "적합한 활용 사례 확인", "관련 기능 안내")},
    {"key": "support", "category": "지원", "label": "지원문의·미해결 이슈", "keywords": ("문의", "티켓", "support", "미해결"), "summary": "지원 문의와 해결 과정에서 확인이 필요한 신호가 관측되었습니다.", "steps": ("티켓 상태 확인", "Support 담당 연결", "문제 해결", "해결 후 고객 재확인")},
    {"key": "technical", "category": "지원", "label": "장애·기술 문제", "keywords": ("장애", "기술오류", "technical", "friction"), "summary": "기술 경험과 관련해 확인이 필요한 신호가 관측되었습니다.", "steps": ("영향 범위 확인", "기술지원 우선 검토", "복구", "재발 여부 점검")},
    {"key": "payment", "category": "결제", "label": "결제 실패·지연", "keywords": ("결제실패", "결제 실패", "재시도", "연체", "payment"), "summary": "결제 과정에서 확인이 필요한 신호가 관측되었습니다.", "steps": ("실제 청구 상태 확인", "결제수단 / 청구 오류 안내", "정상화 여부 확인")},
    {"key": "subscription", "category": "구독", "label": "Downgrade·비용 신호", "keywords": ("다운그레이드", "요금", "비용", "유료 구독"), "summary": "현재 이용량과 요금제 적합성을 함께 확인할 필요가 있습니다.", "steps": ("현재 사용량 확인", "현재 요금제 적합성 확인", "비용 부담 여부 확인", "필요 시 적절한 조건/요금제 안내", "혜택은 내부 승인 기준에 따라 검토")},
    {"key": "renewal", "category": "갱신", "label": "Auto-renew OFF·만료 임박", "keywords": ("자동갱신", "갱신", "만료", "renew"), "summary": "갱신 설정이나 시점과 관련해 확인이 필요한 신호가 관측되었습니다.", "steps": ("현재 설정 확인", "갱신일 확인", "갱신 의사 확인", "갱신을 방해하는 요소 확인")},
    {"key": "device", "category": "이용 환경", "label": "등록 기기·이용 환경 변화", "keywords": ("기기", "device", "os 종류"), "summary": "가입 기간과 비교해 등록 기기 또는 이용 환경을 확인할 필요가 있습니다.", "steps": ("최근 활성 기기 확인", "사용 환경 변화 확인", "정상 이용 여부 재확인")},
)

FEATURE_LABEL_MAP = {
    "가입기간 대비 기기 수": ("가입 기간 대비 등록 기기 수", "등록 기기 수가 가입 기간과 비교해 모델의 주요 신호로 포착되었습니다."),
    "연차 대비 기기 수": ("이용 기간 대비 등록 기기 수", "등록 기기와 이용 기간의 관계를 실제 이용 환경과 함께 확인하세요."),
    "계정연령 대비 기기 수": ("계정 이용기간 대비 등록 기기 수", "계정 이용기간에 비해 등록된 기기 구성이 달라졌는지 확인하세요."),
    "계정 가입 기간": ("계정 이용 기간", "최근 이용 패턴을 가입 기간과 함께 확인할 필요가 있습니다."),
    "최소 가입기간": ("가장 짧은 구독 유지기간", "최근 구독의 유지기간이 모델 예측 신호로 포착되었습니다."),
    "갱신까지 남은 일수": ("갱신 예정 시점", "실제 갱신 예정일과 자동 갱신 설정을 확인하세요."),
    "자동갱신 해제 여부": ("자동 갱신 설정", "자동 갱신이 꺼져 있는지 실제 구독 설정을 확인하세요."),
    "활동시간 변화율": ("최근 활동시간 변화", "이전 기간과 비교한 활동시간 변화를 확인하세요."),
    "스토리지 변화율(3개월)": ("최근 3개월 저장소 사용 변화", "최근 저장소 사용량이 이전 기간과 달라졌는지 확인하세요."),
    "문의 증가율": ("최근 지원 문의 변화", "최근 문의 건수와 미해결 문의가 늘었는지 확인하세요."),
    "최근 30일 결제실패 횟수": ("최근 결제 실패", "최근 청구 및 결제수단 상태를 확인하세요."),
}

ACTION_ITEMS = {
    "usage": {"now": "최근 사용량·활동 변화 확인", "customer": "기능 이용을 방해한 불편 확인", "action": "온보딩 또는 활용 지원", "follow": "대응 후 재사용 여부 확인"},
    "storage": {"now": "최근 저장소 사용 변화 확인", "customer": "업무 패턴 변화 확인", "action": "적합한 활용 사례와 기능 안내", "follow": "저장소 사용 회복 여부 확인"},
    "support": {"now": "최근 문의와 미해결 티켓 확인", "customer": "해결되지 않은 불편 확인", "action": "Support 담당 연결 및 문제 해결", "follow": "추가 문의 발생 여부 확인"},
    "technical": {"now": "장애·기술 문제의 영향 범위 확인", "customer": "현재도 문제가 지속되는지 확인", "action": "기술지원 우선 연결", "follow": "복구와 재발 여부 확인"},
    "payment": {"now": "실제 청구·결제 상태 확인", "customer": "결제수단 또는 청구 문제 확인", "action": "결제 오류 안내 및 정상화 지원", "follow": "결제 정상화 여부 확인"},
    "subscription": {"now": "현재 사용량과 요금제 적합성 확인", "customer": "비용 부담과 변경 배경 확인", "action": "적절한 요금제 검토", "follow": "요금제 변경 후 이용 변화 확인"},
    "renewal": {"now": "자동 갱신 설정과 갱신일 확인", "customer": "갱신 의사와 방해 요소 확인", "action": "갱신 절차 안내", "follow": "갱신 상태 재확인"},
    "device": {"now": "등록 기기와 최근 활성도 확인", "customer": "사용 환경 변화 여부 확인", "action": "기기·접속 환경 이용 지원", "follow": "활성 기기와 활동 회복 확인"},
    "review": {"now": "관련 고객 데이터 확인", "customer": "실제 고객 상황 확인", "action": "필요한 지원 결정", "follow": "다음 예측과 이용 변화 확인"},
}

FALLBACK_CHECKS = ("최근 사용 변화 확인", "현재 구독 상태 확인", "지원문의/미해결 티켓 확인", "결제 상태 확인", "갱신일/Auto-renew 확인")


def get_customer_priority(value_score: float | None) -> str:
    score = float(value_score or 0)
    if score >= CUSTOMER_PRIORITY_POLICY["p1_min_score"]:
        return "P1"
    if score >= CUSTOMER_PRIORITY_POLICY["p2_min_score"]:
        return "P2"
    return "P3"


def get_action_level(risk_level: str | None, customer_priority: str) -> str:
    return ACTION_MATRIX.get(str(risk_level or "").upper(), {}).get(customer_priority, "A0")


def get_action_policy(action_level: str) -> dict[str, str]:
    return {"level": action_level, **ACTION_POLICIES.get(action_level, ACTION_POLICIES["A0"])}


def map_risk_factor_to_playbook(factor: str) -> dict[str, Any]:
    normalized = str(factor or "").strip()
    lowered = normalized.lower().replace(" ", "")
    for playbook in PLAYBOOKS:
        if any(keyword.lower().replace(" ", "") in lowered for keyword in playbook["keywords"]):
            label, description = FEATURE_LABEL_MAP.get(normalized, (playbook["label"], playbook["summary"]))
            return {**playbook, "label": label, "summary": description, "source_factor": normalized, "steps": list(playbook["steps"])}
    label, description = FEATURE_LABEL_MAP.get(normalized, (normalized or "개별 위험 신호", "실제 고객 데이터와 함께 확인이 필요한 모델 예측 신호입니다."))
    return {
        "key": "review",
        "category": "추가 확인",
        "label": label,
        "source_factor": normalized,
        "summary": description,
        "steps": ["관련 고객 데이터 확인", "고객 상황 확인", "후속 변화 재확인"],
    }


def _days_to_renewal(value: Any, today: date | None = None) -> int | None:
    if value in (None, ""):
        return None
    try:
        renewal = datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None
    return (renewal - (today or date.today())).days


def build_customer_strategy(customer: dict[str, Any], risk_factors: list[str]) -> dict[str, Any]:
    priority = customer.get("customer_priority") or get_customer_priority(customer.get("customer_value_score"))
    action_level = get_action_level(customer.get("risk_level"), priority)
    policy = get_action_policy(action_level)
    playbooks = [map_risk_factor_to_playbook(factor) for factor in risk_factors if str(factor).strip()]
    unique_groups = {item["key"] for item in playbooks if item["key"] != "review"}
    days = _days_to_renewal(customer.get("next_billing_date"))
    renewal_review = days is not None and 0 <= days <= 60 and customer.get("risk_level") in {"HIGH", "VERY HIGH"}
    execution_steps = ["현재 위험 신호 확인", "최근 고객 사용/지원/결제 상태 확인"]
    execution_steps.extend(item["steps"][0] for item in playbooks[:2])
    execution_steps.extend([policy["contact"], "3~7일 후 회복 여부 확인"])
    action_plan = {"now": [], "customer": [], "action": [], "follow": []}
    for item in playbooks or [{"key": "review"}]:
        actions = ACTION_ITEMS[item["key"]]
        for phase in action_plan:
            if actions[phase] not in action_plan[phase]:
                action_plan[phase].append(actions[phase])
    return {
        **customer,
        "customer_priority": priority,
        "customer_priority_label": PRIORITY_LABELS[priority],
        "action_level": action_level,
        "action_label": policy["label"],
        "action_policy": policy,
        "response_deadline": policy["deadline"],
        "risk_factors": risk_factors,
        "playbooks": playbooks,
        "fallback_checks": list(FALLBACK_CHECKS) if not playbooks else [],
        "multiple_signal_groups": len(unique_groups) >= 2,
        "renewal_escalation_review": renewal_review,
        "days_to_renewal": days,
        "execution_steps": list(dict.fromkeys(execution_steps)),
        "action_plan": action_plan,
        "signal_disclaimer": "모델이 포착한 신호이며 실제 원인으로 확정된 것은 아닙니다. 고객 이용 데이터·문의 이력과 함께 확인해주세요.",
    }
