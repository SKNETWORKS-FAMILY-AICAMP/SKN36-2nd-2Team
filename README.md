# CloudCare 클라우드 서비스 이탈 예측

합성 원천 Excel → MySQL 8.4 → Pandas 조회 → EDA/Feature Engineering을 위한 팀 프로젝트입니다.
원천은 9개 파일, 500,271행이며 이탈 라벨이나 학습 피처는 아직 생성하지 않았습니다.

## 프로젝트 환경 구성

Git 저장소를 만든 뒤 팀 저장소 URL로 clone합니다. 현재 작업 폴더는 아직 Git 저장소가 아닙니다.

```powershell
git clone <팀-저장소-URL>
cd SKN36-2nd-2team
uv sync
```

사전 준비: Git, uv, Docker Desktop의 Linux 컨테이너 실행 환경. Python 3.12 및 패키지는 uv로 관리합니다.
`uv.lock`을 공유하고 CI 또는 정확한 잠금 확인에는 `uv sync --locked`를 사용합니다.
이 PC에서는 기본 Python 별칭이 Windows 정책에 차단되어 사용 가능한 Python의 절대 경로를
`uv sync --python <실행-가능한-Python-경로>`에 지정해 최초 환경을 만들었습니다. 이후 `uv sync --locked`는 성공했습니다.

## 환경 변수 생성

`.env`가 없는 경우에만 실행합니다. 기존 파일을 덮어쓰지 마세요.

```powershell
Copy-Item .env.example .env
```

`.env`의 `MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD`를 서로 다른 비밀번호로 변경합니다.
DB명은 `cloud_churn`, 일반 사용자는 `churn_user`, 기본 접속은 `localhost:3306`입니다.
DB명과 사용자명에는 영문·숫자·밑줄을 사용하세요. 환경에 이미 지정한 변수는 `.env`보다 우선합니다.
이 작업 폴더에는 무작위 비밀번호로 `.env`를 생성했습니다. 비밀번호를 문서나 출력에 기록하지 않습니다.

## MySQL 실행

```powershell
docker compose config --quiet
docker compose up -d
docker compose ps
```

`mysql`이 healthy가 된 뒤 적재하세요. `config --quiet`는 검증만 하며 비밀번호가 포함된 구성 출력을 피합니다.
최초 시작 시 `db/init/01_schema.sql`이 자동 실행됩니다. DB는 Docker named volume에 영구 저장됩니다.
기존 볼륨에서는 초기화 SQL이 다시 실행되지 않습니다. 포트 충돌 시 `.env`의 `DB_PORT`를 변경합니다.
호스트 포트는 로컬 PC의 127.0.0.1에만 바인딩합니다.

## 원천 데이터 적재 및 검증

```powershell
uv run python scripts/load_raw_data.py --validate-only
uv run python scripts/load_raw_data.py
uv run python scripts/check_db.py
```

적재기는 파일/시트/컬럼, 필수값, PK, FK, 날짜·숫자·길이·정밀도, DB 스키마를 검증합니다.
예외에는 테이블·컬럼·Excel 행 번호와 문제 값 일부가 출력됩니다.
일별 로그 34만 행을 포함하므로 Excel 전체 읽기에 시간이 걸릴 수 있습니다.

부모 테이블부터 순서대로 적재하며 기존 행이 있으면 SKIP합니다. replace, truncate, delete를 사용하지 않습니다.
다시 실행해도 중복 적재하지 않습니다. 기존 일부 행만 있어도 SKIP하므로 검증 결과가 실패하면
기존 데이터와 원천의 차이를 확인해야 합니다. 자동으로 덮어쓰거나 이어 붙이지 않습니다.
한 실행의 새 INSERT는 하나의 트랜잭션으로 커밋하며 오류 시 롤백됩니다.

검증기는 테이블 목록, 행 수, PK 중복 및 키 집합, 컬럼별 NULL 개수, FK 무결성,
Excel과 DB 행 수 차이를 출력합니다. 실패 시 종료 코드는 1입니다.
의도적으로 삽입된 측정 결측·논리적 중복·음수 로그인 값은 수정하지 않습니다.

## SQL 없이 EDA 시작

```powershell
uv run jupyter lab
```

프로젝트는 `uv sync` 시 editable 설치되어 `notebooks/`에서도 `src`를 import할 수 있습니다.
Jupyter 커널은 이 프로젝트의 `.venv` Python을 사용하세요.

```python
import pandas as pd
from src.db import engine

user = pd.read_sql_table('user', engine)
user.head()
```

```python
from src.data_loader import load_tables

data = load_tables(['user', 'plan', 'subscription'])
user = data['user']
subscription = data['subscription']
# 전체 9개 테이블이 필요하면 data = load_tables()
```

실제 테이블명은 `customer`가 아니라 `user`입니다. 전체 테이블 조회는 메모리 사용량에 유의하세요.
가공 결과는 `data/processed/`에 저장하고 EDA는 `notebooks/`에서 관리합니다.

## DBeaver 접속

```text
Driver: MySQL
Host: localhost
Port: 3306 (변경했다면 .env의 DB_PORT)
Database: .env의 MYSQL_DATABASE
Username: .env의 MYSQL_USER
Password: .env의 MYSQL_PASSWORD
```

## MySQL 종료 및 초기화

```powershell
docker compose down
```

종료 후에도 볼륨의 DB 데이터는 남습니다.

**다음 명령은 DB 볼륨과 모든 DB 데이터를 삭제합니다. 필요한 데이터를 백업한 뒤에만 실행하세요.**

```powershell
docker compose down -v
```

## 폴더 구성

```text
data/raw/cloudcare_20260831_seed42/  # 원천 Excel 9개, generation_report.json
data/processed/                    # 향후 학습 데이터 (Git 제외)
db/init/01_schema.sql               # MySQL 초기화 DDL
db/README.md                       # 스키마·적재 정책
scripts/                           # 적재/검증/기존 생성·분석 코드
src/                               # DB 접속/스키마/검증/Pandas 조회
notebooks/                         # 향후 EDA notebook
docs/                              # 기존 명세·분석 보고서, 원천 목록, 작업 결과
tests/                             # 오류 처리·SKIP·롤백 테스트
docker-compose.yml
pyproject.toml
uv.lock
.python-version
.env.example
.env                               # 로컬 전용, Git 제외
.gitignore
README.md
```

기존 스크립트는 `scripts/`로 이동하고 데이터/문서 경로를 프로젝트 루트 기준으로 수정했습니다.
기존 보고서 두 버전은 이력이므로 모두 보존했습니다. `.verification/`의 과거 검증 산출물도 보존하되 Git에서 제외합니다.

## 기존 데이터 생성·분석 작업

```powershell
uv run python scripts/generate_cloudcare_raw_data.py
uv run python scripts/analyze_cloudcare_raw_data.py
uv run python scripts/verify_cloudcare_analysis_report.py
uv run python -m unittest discover -s tests -v
```

생성기는 기존 원천을 보호하고 분석기는 새 보고서 이름을 사용합니다.
검증기는 기존 `docs/CloudCare_Raw_Dataset_Analysis_2.md`의 완전성과 원천 해시를 검사합니다.
상세 원천 정책은 [DATA_GENERATION](docs/DATA_GENERATION.md), 컬럼·타입·관계는
[원천 목록](docs/raw_inventory.json), 작업 결과는 [SETUP_REPORT](docs/SETUP_REPORT.md)를 참고하세요.

## GitHub 공유

코드, 문서, SQL, Compose, 환경 예시, 잠금 파일, 합성 원천 Excel을 공유 대상으로 준비했습니다.
`.env`, `.venv/`, 캐시, IDE 설정, 검증 임시 산출물, 가공 데이터는 제외합니다.
실제 개인정보는 없는 합성 데이터입니다. 추후 실제 고객 데이터를 사용하면 공유 정책을 다시 정하세요.
현재 Git 저장소를 생성하거나 commit/push하지 않았습니다.

## 현재 실행 상태

Python 환경 구성, 원천 전체 PK/FK 검사, 오류 처리·중복 방지·롤백 테스트는 수행했습니다.
현재 PC에 Docker CLI/표준 설치 경로/서비스가 발견되지 않아 MySQL 컨테이너 생성은 미완료입니다.
실제 적재와 DB 검증 명령은 연결 오류 2003으로 실패했습니다. Docker 실행 환경 준비 후 위 순서를 실행하세요.
SQLite 테스트는 적재 로직 검증용이며 MySQL 8.4 실행 검증을 대신하지 않습니다.
