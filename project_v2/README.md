# CloudCare 어딜가

클라우드 서비스 고객의 이탈 위험을 조기에 확인하고, 관리자 화면에서 위험 고객 목록, 고객 상세, 대응 전략, 모델/데이터 정보를 확인하는 Flask 기반 프로젝트입니다.

## 필요한 프로그램

- Git
- Python 3.12
- uv
- Docker Desktop: MySQL 모드에서만 필요

## 방법 A - 가장 빠른 실행: Excel

MySQL과 Docker 없이 포함된 Excel/CSV 파일만으로 실행합니다.

```powershell
git clone https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN36-2nd-2Team.git
cd SKN36-2nd-2Team
cd project_v2

uv sync
uv run python app.py
```

`.env`를 만들지 않아도 앱 기본값은 `DATA_SOURCE=excel`입니다. 명시하고 싶다면 `.env`에 아래처럼 둡니다.

```env
DATA_SOURCE=excel
```

브라우저에서 `http://127.0.0.1:5000`으로 접속합니다.

관리자 테스트 계정:

```text
ID: admin
PW: 1234
```

## 방법 B - 팀 공통 DB 환경: Docker + MySQL

MySQL을 직접 설치하지 않고 Docker Desktop으로 동일한 로컬 DB를 실행합니다.

```powershell
git clone https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN36-2nd-2Team.git
cd SKN36-2nd-2Team
cd project_v2

Copy-Item .env.example .env

docker compose up -d

uv sync

uv run python scripts/setup_mysql.py

uv run python app.py
```

`.env.example`의 기본값은 로컬 개발용 Docker MySQL 계정입니다. 실제 서비스 비밀번호나 개인 비밀번호를 넣지 마세요.

Docker MySQL 기본 정보:

```text
Container: cloudcare-mysql
Host: 127.0.0.1
Port: 3306
Database: cloud_churn
User: cloudcare
Password: cloudcare_local_pw
```

MySQL 모드에서 `.env`는 아래 값을 사용합니다.

```env
DATA_SOURCE=mysql
MYSQL_DATABASE=cloud_churn
MYSQL_USER=cloudcare
MYSQL_PASSWORD=cloudcare_local_pw
MYSQL_ROOT_PASSWORD=cloudcare_root_pw
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=cloudcare
DB_PASSWORD=cloudcare_local_pw
```

`scripts/setup_mysql.py`는 다음 작업을 한 번에 처리합니다.

- Docker MySQL ready 대기
- 앱 보조 테이블 생성: `admin`, `inquiry`
- V3 원천 Excel 검증
- V3 raw 테이블 생성 및 적재
- V3 prediction CSV 적재
- V3 risk factor CSV 적재
- 주요 테이블 row count 출력

다시 실행해도 V3 raw/prediction 데이터는 현재 산출물 기준으로 재적재되어 중복 누적되지 않습니다.

## Docker 종료

컨테이너만 종료하고 DB volume은 유지합니다.

```powershell
docker compose down
```

DB 데이터까지 완전히 초기화합니다. 다음 실행 시 `scripts/setup_mysql.py`로 다시 적재해야 합니다.

```powershell
docker compose down -v
```

## 주요 화면

- 메인 페이지: 서비스 소개, 이탈률 계산, FAQ, 문의하기
- 관리자 대시보드: 전체 현황과 위험 고객 요약
- 전체 고객: 고객 목록, 검색, 필터, 고객 상세 이동
- 위험 고객: 이탈 위험 고객 우선순위 목록과 대응 전략 연결
- 대응 전략: 고객별 대응 전략과 대응 기록 관리
- 모델 / 데이터: 모델 성능, 위험 기준, feature, 학습 데이터 정보

## 프로젝트 구조

```text
project_v2/
  app.py
  docker-compose.yml
  frontend/
    index.html
    admin.html
    animated-hero-exact.html
    logo.png
  data/
    admin.xlsx
    inquiry.xlsx
    raw/cloudcare_v3_20260926_seed42/
    processed/v3/
  db/init/
  models/v3/
  scripts/
    setup_mysql.py
    load_raw_data.py
    load_predictions.py
  src/
  tests/
  pyproject.toml
  uv.lock
  .env.example
```

## 데이터와 모델 산출물

현재 앱은 V3 산출물을 기본으로 사용합니다.

- 원천 Excel 데이터: `data/raw/cloudcare_v3_20260926_seed42/`
- 예측 결과: `data/processed/v3/customer_churn_predictions_v3_5tier.csv`
- 위험 요인: `data/processed/v3/customer_risk_factors_v3.csv`
- Feature importance: `data/processed/v3/feature_importance_v3.csv`
- 모델 파일: `models/v3/final_model_v3.joblib`

모델 재학습 없이 현재 포함된 산출물을 그대로 읽거나 MySQL에 적재해 화면에 표시합니다.

## 개발 확인

```powershell
uv run pytest
```

앱 실행 확인:

```powershell
uv run python app.py
```

## 보안 메모

- `.env`와 로컬 비밀번호는 Git에서 제외합니다.
- `.env.example`의 비밀번호는 Docker 로컬 개발용 예시입니다.
- 운영 배포 전에는 강한 `FLASK_SECRET_KEY`, 해시된 관리자 비밀번호, 운영용 DB 계정, CSRF 보호 등을 별도로 적용해야 합니다.
