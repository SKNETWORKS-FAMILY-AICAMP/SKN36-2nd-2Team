# CloudCare AI 이탈예측 — v3 데이터 최종 모델 평가 리포트

## 0. reopened_count_90d 제외 효과 (요청하신 검증)
                           포함                     제외            
                   test_prauc test_rocauc test_prauc test_rocauc
model                                                           
LightGBM               0.3836      0.9494     0.3972      0.9516
LogisticRegression     0.3665      0.9559     0.3642      0.9557
XGBoost                0.3414      0.9380     0.3011      0.9376
CatBoost               0.3390      0.9399     0.3449      0.9376
GradientBoosting       0.3225      0.9185     0.3227      0.9186
RandomForest           0.2983      0.8803     0.2971      0.8691
ExtraTrees             0.2485      0.8671     0.2422      0.8665

reopened_count_90d를 빼도 성능에 거의 영향이 없어 최종 feature에서 제외함
(타입 혼재 데이터 품질 이슈도 있었던 컬럼이라 제외가 더 안전함).

## 1. 최종 모델
- 모델명: LightGBM
- 전처리: 결측치 median 대체 -> StandardScaler (Train 기준 fit), 카테고리(age_group/region/signup_channel) 원-핫 인코딩
- 최종 사용 feature 개수: 77개 (reopened_count_90d 제외)

## 2. Classification Threshold
- 참고용(기본값) threshold = 0.5
- **최종 채택 threshold = 0.4320** (Validation Recall >= 0.7 만족 기준)

## 3. Test 최종 평가 지표

### (A) threshold = 0.5 (참고용)
{
  "threshold": 0.5,
  "accuracy": 0.9576,
  "balanced_accuracy": 0.8147,
  "precision": 0.2404,
  "recall": 0.6667,
  "f1": 0.3534,
  "roc_auc": 0.9516,
  "pr_auc": 0.3972,
  "TN": 3592,
  "FP": 139,
  "FN": 22,
  "TP": 44
}

### (B) threshold = 0.4320 (최종 채택)
{
  "threshold": 0.432,
  "accuracy": 0.9544,
  "balanced_accuracy": 0.8429,
  "precision": 0.2365,
  "recall": 0.7273,
  "f1": 0.3569,
  "roc_auc": 0.9516,
  "pr_auc": 0.3972,
  "TN": 3576,
  "FP": 155,
  "FN": 18,
  "TP": 48
}

Confusion Matrix (최종 채택 threshold 기준):
|              | 예측 유지 | 예측 이탈 |
|---|---|---|
| 실제 유지 | TN=3576 | FP=155 |
| 실제 이탈 | FN=18 | TP=48 |

## 4. risk_level 기준 (전체 데이터 확률분포 percentile 기준)
- HIGH: churn_probability >= 0.6321 (상위 5%)
- MEDIUM: churn_probability >= 0.0554 (상위 5~20%)
- LOW: 나머지 80%
- 주의: 팀장님 별도 기준 미확인 상태라 확률분포 기반으로 임의 설정함(민혁님 재량).

## 5. 중요 caveat
v3는 v2 대비 성능이 매우 크게 향상됨(Test PR-AUC 0.04대 -> 0.3대, ROC-AUC 0.62 -> 0.95).
직접 검증한 결과 데이터 중복/리크는 발견되지 않았으나, 이 향상은 지인님 V3 생성기의 파라미터 변경
(risk_persistence, behavior_signal_strength 등 - 이탈 위험이 행동 데이터에 더 강하고 오래 지속되도록 설계)에서
기인한 것으로 보임. 실제 서비스에서도 이 정도로 강한 관계가 성립하는지는 별도 확인이 필요함.
