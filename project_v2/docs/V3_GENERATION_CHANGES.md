# V3 Generation Changes

## Frozen State

`V3_GENERATOR_FROZEN` was declared after pilot generation and one conservative design pass. The frozen parameters are saved at `artifacts/v3_generator_frozen_config.json`.

## V2 Issues Addressed

- V2 allowed hidden pressure to influence churn more strongly than observable behavior, so future random innovation could dominate the 60-day label.
- V2 payment retry/failure and support timing were not fully point-in-time safe for model features.
- V2 `device_count_asof` could drift with account age and create an unstable calendar relationship.

## V3 Structure

- Persistent risk path: AR(1)-style latent risk with 30/90-day rolling risk and high-risk duration.
- Observable deterioration: activity, usage, payment, support, and subscription signals are generated from the same sustained risk before churn is sampled.
- Future shock reduction: churn hazard still has random noise, but sustained risk, observable warnings, accumulated friction, and renewal timing carry more weight.
- Persona diversity: engagement, technical, financial, price-sensitive, and silent churn patterns are mixed per customer. These hidden personas are never exported.
- Device drift mitigation: device count depends on tenure, plan, customer size, and engagement; normalized device features are included.

## Pilot

```json
[
  {
    "seed": 42,
    "churn_ratio": 0.16133333333333333,
    "valid_roc_auc": 0.9735028437604549,
    "valid_pr_auc": 0.5948997772289155,
    "strong_signal_count": 16,
    "median_abs_effect": 0.1759699586502272
  },
  {
    "seed": 123,
    "churn_ratio": 0.16266666666666665,
    "valid_roc_auc": 0.9512951308380257,
    "valid_pr_auc": 0.4006129321482117,
    "strong_signal_count": 19,
    "median_abs_effect": 0.15794810361347994
  },
  {
    "seed": 2026,
    "churn_ratio": 0.16133333333333333,
    "valid_roc_auc": 0.9591915707541434,
    "valid_pr_auc": 0.4429336841570095,
    "strong_signal_count": 14,
    "median_abs_effect": 0.20258212380830276
  }
]
```

## Official Generation

- Customers: 5,000
- Churn customers: 810
- Retained customers: 4,190
- Overall churn ratio: 0.1620
- Snapshot known-label positive ratio: 0.0253
