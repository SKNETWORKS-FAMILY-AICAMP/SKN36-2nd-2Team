# 프로젝트 정리 및 MySQL 적재 준비 결과

작업일: 2026-09-22. 실제 Excel을 읽고 기존 생성·분석 코드를 검토했습니다.
현재 환경에서 MySQL 서버는 실행되지 않았으므로 **DB 생성·적재 완료 보고가 아닙니다.**

## 1. 발견한 원천 데이터

모든 파일은 `data/raw/cloudcare_20260831_seed42/`에 있으며 파일마다 시트 하나가 있습니다.
시트명과 대응 테이블명은 같습니다. 실제 컬럼명·NULL 수·타입·SHA-256 전체는
[`raw_inventory.json`](raw_inventory.json)에 기록했습니다.

| 파일 | 시트 / 테이블 | 실제 행 수 | 컬럼 수 |
|---|---|---:|---:|
| 5.1_user.xlsx | user | 5,000 | 8 |
| 5.2_plan.xlsx | plan | 7 | 7 |
| 5.3_subscription.xlsx | subscription | 6,050 | 10 |
| 5.4_storage_usage_monthly.xlsx | storage_usage_monthly | 79,119 | 10 |
| 5.5_user_activity_daily.xlsx | user_activity_daily | 340,173 | 9 |
| 5.6_device.xlsx | device | 9,129 | 7 |
| 5.7_payment_history.xlsx | payment_history | 38,432 | 7 |
| 5.8_support_ticket.xlsx | support_ticket | 9,338 | 8 |
| 5.9_subscription_event.xlsx | subscription_event | 13,023 | 7 |
| 합계 | 9개 | 500,271 | 73 |

## 2. 설계한 DB 테이블

SQL은 생성했지만 실제 DB 테이블 생성 여부 및 DB 행 수는 확인할 수 없었습니다.

| 테이블 | PK | FK → 부모 | DB 행 수 |
|---|---|---|---|
| user | user_id | 없음 | 미확인 |
| plan | plan_id | 없음 | 미확인 |
| subscription | subscription_id | user_id → user; plan_id → plan | 미확인 |
| storage_usage_monthly | usage_id | user_id → user | 미확인 |
| user_activity_daily | activity_id | user_id → user | 미확인 |
| device | device_id | user_id → user | 미확인 |
| payment_history | payment_id | subscription_id → subscription | 미확인 |
| support_ticket | ticket_id | user_id → user | 미확인 |
| subscription_event | event_id | user_id → user; subscription_id → subscription; old_plan_id, new_plan_id → plan | 미확인 |

전체 원천 값에서 PK NULL·중복 0, 11개 FK 관계의 고아 참조 0을 확인했습니다.
적재 순서는 SQLAlchemy FK 의존성 정렬을 사용합니다:
`plan → user → device → storage_usage_monthly → subscription → support_ticket → user_activity_daily → payment_history → subscription_event`.
서로 의존하지 않는 테이블 간 순서는 의미가 없으며 모든 부모가 자식보다 앞섭니다.

금액은 DECIMAL(18,2), 정수 카운트는 부호 있는 INT, ID는 BIGINT,
측정 소수는 DOUBLE, 날짜는 DATE, 시각은 DATETIME(6)입니다.
문의 해결 시각의 9,029건에 소수 초가 발견되어 마이크로초 정밀도를 보존했습니다.
`plan_name`은 UNIQUE이며 로그의 사용자+날짜 등은 의도적 중복을 보존합니다.

## 3. 생성·수정·이동 파일

- 생성: `docker-compose.yml`, `db/init/01_schema.sql`, `db/README.md`.
- 생성: `src/__init__.py`, `src/db.py`, `src/data_loader.py`, `src/schema.py`, `src/validation.py`, `src/cli.py`.
- 생성: `scripts/load_raw_data.py`, `scripts/check_db.py`, `scripts/inspect_raw_data.py`, `scripts/export_schema.py`.
- 생성: `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`, `.gitignore`, `README.md`.
- 생성: 로컬 `.env` (무작위 비밀번호, 값 비공개), `.venv/`.
- 생성: `docs/raw_inventory.json`, 이 보고서, `tests/test_ingestion.py`, 빈 EDA/가공 데이터 폴더 표시 파일.
- 이동 및 경로 수정: 생성·분석·보고서 검증 Python 3개를 루트에서 `scripts/`로 이동.
- 이동: 분석 보고서 2개와 생성 명세를 `docs/`로 이동. 명세의 실행 경로와 과거 파일 현황 문구를 갱신.
- 보존: Excel 9개, 원천 생성 보고서, 과거 `.verification/` 결과, 기존 보고서 내용.

기존 pyproject/uv.lock/.env/.gitignore/Docker/SQL/notebook은 없었습니다.
기존 코드를 새로 대체하지 않고 이동 후 경로만 수정했습니다.

## 4. Docker 상태

- PATH에서 `docker` 명령을 찾을 수 없습니다.
- 표준 설치 경로 `C:\Program Files\Docker\Docker\resources\bin\docker.exe`가 없습니다.
- 이름에 docker가 포함된 Windows 서비스도 발견되지 않았습니다.
- `docker compose config --quiet`는 명령을 찾지 못해 실패했습니다.
- 컨테이너 시작, healthcheck, DB 생성은 실행 불가입니다.
- `load_raw_data.py`, `check_db.py` 실제 실행은 MySQL OperationalError 2003 (서버 연결 실패)입니다.
- 다른 위치의 Docker 설치 여부까지 단정하지 않으며 현재 세션에서 사용 가능한 Docker를 발견하지 못했습니다.

## 5. 검증 및 적재 결과

9개 Excel 읽기와 전체 PK/FK 검사 및 기존 보고서 검증이 통과했습니다.
기존 보고서에 기록된 Excel 9개의 SHA-256이 모두 일치했습니다.
최종 적재 전 검증도 9개 테이블 500,271행 전체에서 `ALL SOURCE CHECKS PASSED`로 완료됐습니다.

오류 입력·PK 중복·잘못된 컬럼·원천 이상값 보존·소수 초 보존·반복 SKIP·트랜잭션 롤백을 포함하는
unittest 6개가 통과했습니다. 트랜잭션 테스트는 SQLite이며 MySQL 반영 결과를 증명하지 않습니다.
실제 DB 행 수와 Excel 행 수의 대조는 **MySQL 실행 후 반드시 수행해야 합니다.**

| 테이블 | Excel 행 수 | DB 행 수 | 적재 상태 |
|---|---:|---|---|
| user | 5,000 | 미확인 | 서버 연결 실패 |
| plan | 7 | 미확인 | 서버 연결 실패 |
| subscription | 6,050 | 미확인 | 서버 연결 실패 |
| storage_usage_monthly | 79,119 | 미확인 | 서버 연결 실패 |
| user_activity_daily | 340,173 | 미확인 | 서버 연결 실패 |
| device | 9,129 | 미확인 | 서버 연결 실패 |
| payment_history | 38,432 | 미확인 | 서버 연결 실패 |
| support_ticket | 9,338 | 미확인 | 서버 연결 실패 |
| subscription_event | 13,023 | 미확인 | 서버 연결 실패 |

## 6. 최종 폴더 구조

```text
project-root/
├─ data/
│  ├─ raw/cloudcare_20260831_seed42/  (Excel 9개 + generation_report.json)
│  └─ processed/
├─ db/
│  ├─ init/01_schema.sql
│  └─ README.md
├─ scripts/                         (기존 3개 + 신규 4개)
├─ src/                             (Python 모듈 6개)
├─ notebooks/
├─ docs/                            (기존 문서 3개 + 목록·결과)
├─ tests/test_ingestion.py
├─ docker-compose.yml
├─ pyproject.toml
├─ uv.lock
├─ .python-version
├─ .env.example
├─ .env                             (비공개)
├─ .gitignore
└─ README.md
```

과거 `.verification/` 및 실행 중 생긴 캐시는 Git 제외 대상으로 보존했습니다.

## 7. GitHub 공유 대상

`data/raw/`의 합성 원천 및 생성 기록, `db/`, `scripts/`, `src/`, `notebooks/`, `docs/`, `tests/`,
Compose, pyproject, uv.lock, Python 버전, `.env.example`, `.gitignore`, README입니다.
현재는 Git 저장소가 아니므로 실제 추적 파일 목록은 없습니다.

## 8. GitHub 제외 대상

`.env`, 기타 `.env.*` (단 `.env.example` 예외), `.venv/`, Python 캐시, notebook 체크포인트,
IDE 설정, OS 잡파일, 과거 `.verification/`, `data/processed/` 내용, 로그, `mysql-data/`입니다.
실제 DB 데이터는 Docker named volume을 사용하므로 프로젝트 폴더에 생성하지 않습니다.
Git 저장소가 없어 `git check-ignore`에 의한 실제 인덱스 검증은 수행하지 않았고 ignore 규칙을 확인했습니다.

## 9. 팀원 최초 실행 명령

Docker 및 uv 준비 후 저장소 루트에서 실행합니다. `.env` 복사는 최초 1회만 합니다.

```powershell
uv sync
Copy-Item .env.example .env
# .env에서 비밀번호 변경
docker compose config --quiet
docker compose up -d
docker compose ps
# healthy 확인 후
uv run python scripts/load_raw_data.py
uv run python scripts/check_db.py
uv run jupyter lab
```

## 10. 문제 및 주의사항

- Docker 부재로 실제 MySQL 8.4 DDL·적재·healthcheck·DB 건수 비교는 미완료입니다.
- Windows 정책이 기본 Python 별칭 실행을 차단해 번들 Python 3.12.14를 명시하여 uv 환경을 만들었습니다.
  이후 `uv sync --locked`는 성공했습니다. 설치 패키지 읽기는 도구 샌드박스 제한 때문에 승인된 실행으로 검증했습니다.
- 의도적 결측·논리 중복·음수 로그인은 EDA 단계에서 처리할 대상이며 적재 과정에서 삭제/수정하지 않습니다.
- 기존 테이블에 한 행이라도 있으면 SKIP합니다. 부분 적재나 다른 데이터셋을 자동 보완하지 않습니다.
- 초기화 SQL은 새 볼륨 최초 생성용입니다. 기존 볼륨은 별도 마이그레이션 검토가 필요합니다.
- `docker compose down -v`는 DB를 삭제합니다. 이번 작업에서 실행하지 않았습니다.
- `git status` 결과는 `fatal: not a git repository`입니다. GitHub 저장소 생성·commit·push를 수행하지 않았습니다.

## 최종 실행 기록

- `uv sync --locked`: 통과.
- `uv run python -m unittest discover -s tests -v`: 6개 통과.
- `uv run python scripts/load_raw_data.py --validate-only`: 전체 500,271행 검증 통과.
- `scripts/verify_cloudcare_analysis_report.py`: 18개 섹션·9개 원천 해시 검증 통과.
- Python 14개 파일 문법 검사 및 Compose YAML 문법 검사: 통과. Docker Compose 자체 구성 검증은 미실행.
- `notebooks/` 작업 경로에서 `src.db`, `src.data_loader` import: 통과.
- DB 연결·적재: MySQL 오류 2003, 미완료.
