# V3 Data Migration Report

## 1. 기존 DB 상태

- MySQL에는 V2가 아니라 legacy raw data, 즉 기존 원천 데이터와 legacy schema가 들어 있었습니다.
- 기존 원천 Excel/CSV 파일과 V2/V3 산출물 파일은 삭제하거나 덮어쓰지 않았습니다.
- 운영용 테이블인 `admin`, `inquiry`는 V3 raw reset 대상에서 제외되도록 설계했습니다.

## 2. 기존 Migration 실패 원인

`db/migrations/05_v3_dataset_schema.sql`은 기존 row를 보존한 채 schema만 V3로 바꾸려는 in-place migration입니다.

실행 결과:

```text
ERROR 1138 (22004): Invalid use of NULL value
```

원인은 legacy raw data의 일부 컬럼에 NULL이 있는데, V3 schema에서는 해당 컬럼들이 `NOT NULL`이기 때문입니다. 예를 들어 `user.age_group`은 legacy schema에서는 nullable이었지만 V3에서는 nullable이 아닙니다. 이 프로젝트에서는 legacy raw row를 V3 schema로 변환해 보존할 필요가 없으므로, in-place migration 대신 raw 10개 테이블 재생성 방식을 사용합니다.

`db/migrations/05_v3_dataset_schema.sql`은 삭제하지 않고 deprecated 참고용으로 유지했습니다. 개발 DB 교체에는 아래 명령을 사용합니다.

```powershell
uv run python scripts/load_raw_data.py --reset-v3
```

## 3. Reset 대상과 보호 대상

Reset 대상 raw 테이블:

```text
plan
user
device
storage_usage_monthly
subscription
support_ticket
user_activity_daily
payment_history
subscription_event
user_snapshot_target
```

보호 대상:

```text
admin
inquiry
기타 raw table 목록에 없는 웹 서비스용 테이블
```

`--reset-v3`는 `DROP DATABASE`를 사용하지 않습니다. 위 raw 10개 테이블만 FK 순서를 고려해 drop 후 재생성합니다.

## 4. 새 Reset-V3 방식

`scripts/load_raw_data.py --reset-v3` 실행 순서:

1. MySQL 연결 및 lock 획득
2. V3 source Excel 전체 validation
3. DB명, reset 대상 테이블, 보호 테이블, V3 source 경로 로그 출력
4. `FOREIGN_KEY_CHECKS=0`
5. raw 10개 테이블만 drop
6. `FOREIGN_KEY_CHECKS=1`
7. `src/schema.py`, `src/snapshot_schema.py` 기준 V3 schema 재생성
8. schema type/nullability/PK/FK 검증
9. V3 데이터 적재
10. table별 SOURCE/DB row count 비교
11. commit

일반 실행인 `uv run python scripts/load_raw_data.py`는 자동 삭제를 하지 않습니다. schema mismatch 또는 기존 data mismatch가 있으면 명확히 실패합니다.

## 5. V3 Schema 생성 방식

- raw 9개 테이블: `docs/raw_inventory.json` + `src/schema.py`
- snapshot target: `src/snapshot_schema.py`
- 신규 Docker volume 초기 schema: `db/init/01_schema.sql`
- 최종 검증: `scripts/check_db.py`

V3 추가 컬럼:

- `payment_history.overdue_flag`
- `payment_history.status_changed_at`
- `subscription_event.auto_renewal_after`

## 6. V3 Row Count

| table | source rows | DB rows | result |
|---|---:|---:|---|
| plan | 7 | 7 | PASS |
| user | 5,000 | 5,000 | PASS |
| device | 16,197 | 16,197 | PASS |
| storage_usage_monthly | 69,377 | 69,377 | PASS |
| subscription | 5,462 | 5,462 | PASS |
| support_ticket | 15,246 | 15,246 | PASS |
| user_activity_daily | 181,956 | 181,956 | PASS |
| payment_history | 34,318 | 34,318 | PASS |
| subscription_event | 10,941 | 10,941 | PASS |
| user_snapshot_target | 68,600 | 68,600 | PASS |

## 7. 테스트 결과

| test | result | note |
|---|---|---|
| `uv run python scripts/load_raw_data.py --validate-only` | PASS | V3 source 10개 파일 검증 통과 |
| `uv run python scripts/load_raw_data.py --reset-v3` | PASS | legacy raw tables drop/recreate/load, row count PASS |
| `uv run python scripts/check_db.py` | PASS | schema, row count, NULL count, PK, FK 검증 통과 |
| `uv run python scripts/load_raw_data.py --reset-v3` 재실행 | PASS | 중복 없이 동일 row count로 재적재 |
| `DATA_SOURCE=excel DATA_VERSION=v3` 앱 import | PASS | V3 Excel raw dir, customer frame 5,000명 |
| `DATA_SOURCE=mysql DATA_VERSION=v3` 앱 import | PASS | MySQL customer frame 5,000명 |
| `uv run python -m unittest tests.test_ingestion` | PASS | loader repeat/rollback test 통과 |

## 8. 팀원 실행 명령어

```powershell
uv sync
Copy-Item .env.example .env
docker compose up -d

uv run python scripts/load_raw_data.py --validate-only
uv run python scripts/load_raw_data.py --reset-v3
uv run python scripts/check_db.py
uv run python app.py
```

Excel 모드:

```env
DATA_SOURCE=excel
DATA_VERSION=v3
```

MySQL 모드:

```env
DATA_SOURCE=mysql
DATA_VERSION=v3
```

## 9. 남아 있는 문제

- 브라우저를 직접 열어 관리자 화면 UI를 수동 클릭 검증하지는 않았습니다. 대신 Excel/MySQL 양쪽에서 앱 import와 customer frame 5,000명 로딩을 확인했습니다.
- 모델 prediction/risk 결과와 관리자 화면 연결은 이번 작업 범위가 아니므로 건드리지 않았습니다.
