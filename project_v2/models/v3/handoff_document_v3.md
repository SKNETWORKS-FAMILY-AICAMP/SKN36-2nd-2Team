# CloudCare AI 이탈예측 — 최종 모델 인수인계 문서 (V3)

추측 없이 실제 사용한 값/파일 기준으로만 작성했습니다. 없는 항목은 명시적으로 "사용하지 않음"이라고 표시했습니다.

---

## 1. 최종 모델 정보

| 항목 | 내용 |
|---|---|
| 최종 모델명 | LightGBM (LGBMClassifier, scikit-learn API) |
| 사용 알고리즘 | LightGBM |
| 모델 저장 파일명 | `final_model_v3.joblib` |
| 모델 파일 확장자 | `.joblib` |
| 최종적으로 사용할 파일 | **`final_model_v3.joblib` 이 파일 하나면 됩니다** (model + imputer + scaler + feature 목록 + category 목록 + threshold가 전부 이 안에 dict로 묶여있음) |

**모델을 저장한 코드** (원본, `final_deliverable_v3.py`에서 발췌):
```python
import joblib

bundle = {
    'model': model,                      # LGBMClassifier
    'imputer': imputer,                  # sklearn SimpleImputer(strategy='median')
    'scaler': scaler,                    # sklearn StandardScaler
    'features': FINAL_FEATURES,          # 77개, 순서 고정 리스트
    'category_levels': CATEGORY_LEVELS,  # {'age_group':[...], 'region':[...], 'signup_channel':[...]}
    'categorical_columns': ['age_group', 'region', 'signup_channel'],
    'sentinel_columns': ['days_since_last_activity', 'days_since_last_failed_payment', 'days_since_last_downgrade'],
    'threshold_recommended': RECOMMENDED_THRESHOLD,  # 0.432
    'model_name': 'LightGBM',
}
joblib.dump(bundle, 'final_model_v3.joblib')
```

**모델을 다시 불러오는 코드**:
```python
import joblib
bundle = joblib.load('final_model_v3.joblib')
model = bundle['model']
imputer = bundle['imputer']
scaler = bundle['scaler']
features = bundle['features']
threshold = bundle['threshold_recommended']  # 0.432
```

---

## 2. 모델 평가 결과

**최종 채택 threshold = 0.432** (Validation 기준 Recall≥0.7을 만족하는 가장 높은 threshold)

| 지표 | Train | Validation | **Test (최종 기준)** |
|---|---|---|---|
| rows | 32,704 | 10,226 | 3,797 |
| positive_rate | 3.14% | 2.00% | 1.74% |
| Accuracy | 0.9412 | 0.9607 | **0.9544** |
| Precision | 0.3483 | 0.2969 | **0.2365** |
| Recall | 0.9981 | 0.7024 | **0.7273** |
| F1-score | 0.5164 | 0.4174 | **0.3569** |
| ROC-AUC | 0.9938 | 0.9650 | **0.9516** |
| TN / FP / FN / TP | 29756/1920/2/1026 | 9680/341/61/144 | **3576/155/18/48** |

Confusion Matrix (Test, threshold=0.432 기준):
|  | 예측 유지 | 예측 이탈 |
|---|---|---|
| 실제 유지 | TN=3576 | FP=155 |
| 실제 이탈 | FN=18 | TP=48 |

- **모든 성능값은 Test 데이터 기준이 최종**입니다. Train 성능(Recall 0.998, PR-AUC 0.81)은 학습에 쓴 데이터라 당연히 과도하게 높게 나오는 것이니 참고만 하세요.
- PR-AUC(참고): Train 0.8122 / Validation 0.5184 / Test 0.3972
- ROC-AUC는 높은데 Precision이 낮아 보이는 건 이탈률 자체가 1.7~2%로 극단적 불균형이기 때문입니다(자세한 설명은 팀 내부에서 이미 공유함). Test 기준 baseline(무작위) 대비 PR-AUC lift는 약 **22.8배**입니다.

---

## 3. Train / Validation / Test 분리 방식

| Split | 기간 | Row 수 |
|---|---|---|
| Train | 2024-01-31 ~ 2025-10-31 | 32,704 |
| (Purge, 미사용 구간) | 2025-11-30 ~ 2026-04-30 | 9,733 |
| Validation | 2026-01-31 ~ 2026-03-31 | 10,226 |
| Test | 2026-05-31 (단일월) | 3,797 |
| Final Holdout (모델링에 전혀 미사용, 최종 검증용) | 2026-06-30 (단일월) | 3,911 |

- **분할 기준**: **Time-based split**입니다 (random split 아님). snapshot_date 기준으로 시간순으로 잘랐습니다.
- **Purge 구간의 존재 이유**: Validation(2026-01~03) 직전에 label window(churn_60d = 60일 이내 이탈 여부)가 겹치는 구간을 일부러 비워서, 미래 정보가 과거 label에 섞여 들어가는 걸 방지했습니다.
- **동일 user가 Train과 Test에 동시에 들어갈 수 있는 구조인지**: **예, 들어갈 수 있습니다.** 이 데이터는 `user_id + snapshot_date` 조합의 패널 데이터라서, 같은 고객이 여러 달에 걸쳐 반복 관측됩니다. 다만 **같은 (user_id, snapshot_date) 조합이 두 split에 동시에 존재하지는 않습니다** — 시점 자체가 겹치지 않게 시간으로 잘랐기 때문입니다. 직접 중복 검증(exact row duplication check)도 했고 0건이었습니다.
- **데이터 누수 방지 처리**: (1) 시간순 분할 + Purge gap, (2) Feature 계산 시점이 각 snapshot_date 시점까지의 정보만 쓰도록 이미 원본 데이터 설계 단계에서 point-in-time으로 생성됨, (3) 완전 중복 행 여부 직접 검증.

---

## 4. 최종 모델 Feature 목록 (총 77개, 아래 순서 그대로 모델에 입력됨)

**feature 순서가 중요합니다** — `final_model_v3.joblib`의 `bundle['features']` 리스트 순서와 반드시 동일해야 합니다. (아래는 발췌, 전체는 `feature_list_dtypes_v3.csv` 참고)

| 순서 | feature명 | 의미 | dtype | 전처리 |
|---|---|---|---|---|
| 1 | account_age_days | 계정 생성 후 경과일 | int64 | 결측치 median 대체 + Scaling |
| 2 | login_count_30d | 최근 30일 로그인 횟수 | float64 | 동일 |
| ... | (원본 raw feature 46개: 로그인/활동/스토리지/결제/티켓/다운그레이드/구독/기기 관련) | | float64/int64 | 동일 |
| 33,39,42 | `days_since_last_activity_never` 등 (`_never` 3개) | 999(이벤트 없음) sentinel을 대체한 결측 플래그 | int64 | 그대로 사용(스케일링만) |
| 53~76 | `age_group_*`(6) / `region_*`(17) / `signup_channel_*`(3) | 원-핫 인코딩된 범주형 | bool(0/1) | One-hot만, Scaling 대상 아님(imputer/scaler 파이프라인엔 같이 들어가지만 median/평균 영향 거의 없음) |

- **target 컬럼**: `churn_60d` (0/1)
- **학습에서 제외한 컬럼**: `user_id`, `snapshot_date`, `reopened_count_90d` (타입 혼재 데이터품질 버그 + 성능 기여 없어서 제외)
- **ID 성격 컬럼**: `user_id`
- **날짜 컬럼**: `snapshot_date`

전체 77개 리스트는 `feature_list_dtypes_v3.csv` 파일 그대로 참고하시면 됩니다.

---

## 5. 전처리 정보

| 항목 | 내용 |
|---|---|
| 결측치 처리 | `SimpleImputer(strategy='median')` — Train 기준으로만 fit |
| 이상치 처리 | 별도 이상치 제거/클리핑 **없음**. 다만 `reopened_count_90d`의 타입 혼재 버그(숫자 0~4 / 문자열 'True','False' 섞임)는 클리닝해서 1/0으로 통일 (최종 모델에서는 이 feature 자체를 제외) |
| Encoding | `age_group`/`region`/`signup_channel` 3개 범주형 → **원-핫 인코딩** (Train에서 관측된 카테고리 목록으로 fit, Valid/Test/Purge/Holdout에 동일 적용) |
| Scaling | `StandardScaler()` — Train 기준으로만 fit, 전체 77개 feature에 적용 |
| Log 변환 | 사용하지 않음 |
| 범주형 처리 | 원-핫 인코딩 (CatBoost 자체 범주형 처리 아님 — LightGBM 모델이라 sklearn 표준 원-핫 사용) |
| 클래스 불균형 처리 | 별도 오버/언더샘플링 **없음**. LightGBM 기본 파라미터로 학습(class_weight 별도 조정 없음) — threshold 조정(0.432)으로 recall 확보 |
| Feature Engineering | sentinel(999) 값을 `_never` 플래그 3개로 분리 + NaN 처리 정도이며, 그 외 복잡한 파생 feature는 원본 `final_model_features_v3.csv`에 이미 계산되어 있던 것을 그대로 사용 |

**Encoder / Scaler / Imputer 파일**: 별도 파일로 분리하지 않았고, **전부 `final_model_v3.joblib` 안에 함께 저장**되어 있습니다 (`bundle['imputer']`, `bundle['scaler']`). Encoder는 별도 객체가 아니라 `bundle['category_levels']`에 저장된 카테고리 목록으로 직접 원-핫을 재현하는 방식입니다.

---

## 6. 전체 고객 추론 결과

**파일: `customer_churn_predictions_v3_5tier.csv`**

요청하신 최소 컬럼(user_id/snapshot_date/churn_probability/prediction/risk_level) 전부 포함되어 있고, 편의상 `split`(train/valid/test/purge/holdout 구분)과 `actual_churn_60d(참고용)`(실제 정답 라벨, 모델 평가용) 컬럼이 추가로 들어있습니다 — **actual_churn_60d는 관리자 화면 로직에는 절대 사용하면 안 되고, 참고/검증용으로만 보관**해주세요.

- 총 60,371행 (고유 고객 4,656명 × 월별 반복 관측)
- `churn_probability`는 0~1 사이 실제 확률값 (LightGBM `predict_proba()` 결과, calibration 별도 적용 안 함)
- **주의**: 5.1_user.xlsx 기준 전체 고객은 5,000명인데, 이 중 344명(2026-07 이후 가입한 신규고객)은 스냅샷 생성 마감일(2026-06-30) 이후 가입이라 예측 자체가 없습니다. 관리자 페이지에서 전체 5,000명 고객 목록에 이 CSV를 LEFT JOIN하고, 매칭 안 되는 344명은 "최근가입-미산출"로 표시해주세요.

---

## 7. Risk Level 5단계 기준

| 등급 | 확률 기준 | 산출 기준 |
|---|---|---|
| VERY HIGH | ≥ 0.9745 | 전체 60,371명 확률분포 상위 1% |
| HIGH | 0.6321 ~ 0.9745 | 상위 1~5% |
| MEDIUM | 0.0554 ~ 0.6321 | 상위 5~20% |
| LOW | 0.0033 ~ 0.0554 | 상위 20~50% |
| VERY LOW | < 0.0033 | 하위 50% |

- **산출 기준**: probability quantile (데이터 분포 기준 percentile) — business rule이나 임의 구간이 아니라, 전체 고객 예측 확률분포에서 percentile을 잘라서 정함.
- **팀장님/회사 지정 기준이 별도로 없어서** 이 percentile 방식을 임의로 채택한 것이며, 실제 각 구간의 이탈률로 검증했을 때 VERY HIGH 80.8% → HIGH 34.0% → MEDIUM 1.8% → LOW 0.24% → VERY LOW 0.03%로 단조 감소하며 등급 간 구분력이 확인됨.
- classification threshold(0.432)와 risk_level 컷오프는 **서로 다른 기준**입니다. threshold는 이진분류(1/0) 판단용이고, risk_level은 5단계 세분화용이라 별도로 산출했습니다.

---

## 8. 고객별 주요 위험요인

**파일: `customer_risk_factors_v3.csv`**

**SHAP 기반입니다.** `shap.TreeExplainer`로 LightGBM 모델의 SHAP value를 고객별로 계산해서, 이탈확률을 **높이는 방향(+)**으로 기여한 feature 중 절댓값이 큰 순서로 TOP5를 뽑았습니다.

컬럼: `user_id`, `snapshot_date`, `churn_probability`, `risk_factor_1`~`risk_factor_5` (한글 라벨로 변환, 예: "최근 30일 로그인 횟수", "결제실패율" 등)

- 전체 60,371행(전체 고객 x 전체 월) 대상으로 계산함
- 이 부분은 원래 요구사항에서 "여유 되면"이라고 우선순위가 낮았던 항목인데, 이번에 요청하셔서 새로 만들었습니다.

---

## 9. 전체 Feature Importance

**파일: `feature_importance_v3.csv`** (전체 77개 feature, LightGBM `.feature_importances_` 기준)

상위 10개:
| feature | importance |
|---|---|
| device_count_per_tenure | 200 |
| devices_per_account_year | 171 |
| storage_utilization_ratio | 168 |
| account_age_days | 166 |
| min_tenure_days | 129 |
| storage_used_gb_latest | 120 |
| action_count_change_rate | 117 |
| days_since_last_activity | 114 |
| active_minutes_30d | 113 |
| active_minutes_change_rate | 112 |

발표/시각화용으로 상위 15개까지는 노트북(`CloudCare_V3_최종_EDA_모델링_실행완료.ipynb`) 15번 섹션에 막대그래프로 이미 그려져 있습니다.

---

## 10. 최종 모델 학습 데이터셋

**파일: `final_model_features_v3.csv`** (60,371행, 지인님이 만들어주신 파일 그대로 사용, 이 위에서 train/valid/test/purge/holdout 5개로 시간 분할)

| 항목 | 값 |
|---|---|
| 총 row 수 | 60,371 |
| 총 원본 컬럼 수 | 55개 (여기서 파생 3개 추가 + 원-핫 24개 전개해서 최종 77개 feature 사용) |
| churn=0 개수 | 58,845 |
| churn=1 개수 | 1,526 |
| 전체 target 비율 | 약 2.53% |
| Train row 수 | 32,704 (positive 1,028) |
| Validation row 수 | 10,226 (positive 205) |
| Test row 수 | 3,797 (positive 66) |
| (참고) Purge row 수 | 9,733 (positive 165) |
| (참고) Final Holdout row 수 | 3,911 (positive 62) |

---

## 11. 실제 추론 코드

**파일: `predict.py`** (아래 흐름 그대로 구현됨)

```text
고객 데이터 불러오기(csv)
→ reopened_count_90d 클리닝, sentinel(999) 처리
→ 원-핫 인코딩 (bundle의 category_levels 기준)
→ imputer.transform → scaler.transform
→ model.predict_proba()
→ churn_probability
→ prediction (threshold=0.432)
→ risk_level 5단계 변환
```

**사용법**:
```bash
python predict.py 고객데이터.csv 결과.csv
```

**고객 1명 예시 추론** (인자 없이 실행하면 샘플 1건으로 자동 테스트):
```bash
python predict.py
```
실행 결과 예시:
```
user_id  snapshot_date  churn_probability  prediction  risk_level
999999   2026-06-30     0.0001             0           VERY LOW
```
(이 샘플은 임의로 만든 값이라 실제로 위험도가 낮게 나온 건 자연스러운 결과이고, 실제 고객 데이터를 넣으면 다르게 나옵니다)

---

## 12. 필요한 Python 라이브러리 버전

**파일: `requirements_model.txt`**
```
python==3.11.15
pandas==3.0.2
numpy==2.4.4
scikit-learn==1.8.0
lightgbm==4.7.0
joblib==1.5.3
```
(catboost/xgboost는 최종 모델(LightGBM)에서 사용하지 않아 제외함)

---

## 13. 최종 전달 파일 체크리스트

- [x] 최종 모델 파일 — `final_model_v3.joblib`
- [x] 최종 학습 데이터셋 — `final_model_features_v3.csv`
- [x] 전체 고객 추론 CSV — `customer_churn_predictions_v3_5tier.csv`
- [x] 고객별 위험요인 CSV — `customer_risk_factors_v3.csv`
- [x] Feature Importance CSV — `feature_importance_v3.csv`
- [ ] Encoder / Scaler 등 전처리 파일 — **별도 파일 없음** (`final_model_v3.joblib` 안에 imputer/scaler/category_levels 전부 포함되어 있어 별도 전달 불필요)
- [x] predict.py
- [x] requirements_model.txt
- [x] 모델 성능 결과 — `model_evaluation_report_v3.md` (본 문서 §2와 동일 내용)
- [x] 5단계 risk 기준 설명 — 본 문서 §7
- [x] Feature 목록/dtype — `feature_list_dtypes_v3.csv`

---

## 지인님 PC에서 모델 연동할 때 실행 순서

1. `final_model_v3.joblib`, `predict.py`, `requirements_model.txt`를 같은 폴더에 둡니다.
2. `pip install -r requirements_model.txt`로 환경을 맞춥니다.
3. 관리자 페이지에 연결할 고객 데이터를 `final_model_features_v3.csv`와 **동일한 컬럼 구조**로 준비합니다 (컬럼명이 다르면 predict.py가 `missing_cols` 에러로 어떤 컬럼이 부족한지 알려줍니다).
4. `python predict.py 고객데이터.csv 결과.csv` 실행 → `결과.csv`에 `user_id, snapshot_date, churn_probability, prediction, risk_level`이 생성됩니다.
5. 필요하면 `customer_risk_factors_v3.csv`를 별도로 조인해서 고객 상세 화면의 "위험요인 TOP5"에 붙입니다.
6. 전체 고객 대량 배치가 필요하면, Test용으로 미리 뽑아둔 `customer_churn_predictions_v3_5tier.csv`를 바로 사용해도 됩니다 (이미 60,371행 전체에 대해 위 파이프라인을 그대로 돌려놓은 결과물입니다).
