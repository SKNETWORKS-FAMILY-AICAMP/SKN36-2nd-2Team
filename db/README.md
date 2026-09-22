# MySQL 원천 데이터베이스

`init/01_schema.sql`은 실제 Excel 9개에서 조사한 컬럼만 정의합니다.
확정된 계약은 `docs/raw_inventory.json`, 공통 SQLAlchemy 정의는 `src/schema.py`입니다.
DDL 재생성: `uv run python scripts/export_schema.py`.
Excel 재조사는 `uv run python scripts/inspect_raw_data.py`로 가능하지만 계약 파일을 갱신하므로 변경 내용을 검토해야 합니다.

- PK: 각 테이블 첫 ID 컬럼, 원천 값을 보존하며 자동 번호를 생성하지 않습니다.
- UNIQUE: `plan.plan_name`. 로그의 사용자+날짜는 의도적 논리 중복이 있으므로 UNIQUE를 걸지 않습니다.
- FK: 사용자, 요금제, 구독을 참조하는 11개 관계. 삭제·갱신 연쇄 작업 없이 참조를 보호합니다.
- ID는 BIGINT, 카운트는 부호 있는 INT, 금액은 DECIMAL(18,2), 연속 측정값은 DOUBLE입니다.
- 날짜는 DATE, 시각은 DATETIME(6), 여부는 BOOLEAN입니다. 시각은 원천의 timezone 없는 값을 보존합니다.
  `support_ticket.resolved_at`에 실제 밀리초가 있어 소수 초를 보존합니다.
- 실제 결측 및 정상적인 미정 날짜는 NULL을 허용합니다. 나머지 컬럼은 NOT NULL입니다.
- FK와 날짜 컬럼에 인덱스를 생성합니다. 한국어 문자열은 utf8mb4입니다.

Compose의 초기화 SQL은 **새 볼륨의 최초 시작 시에만** 실행됩니다.
기존 볼륨의 테이블을 자동 변경하지 않습니다. 기존 DB가 있으면 백업 후 별도 마이그레이션을 검토하세요.
SQL 파일의 CREATE INDEX는 재실행 시 중복 이름 오류가 발생할 수 있으므로 초기화 전체를 기존 DB에 반복 실행하지 마세요.

적재는 전체 Excel 검증 후 하나의 트랜잭션으로 수행합니다. 기존 행이 있는 테이블은 SKIP합니다.
새로 적재할 자식의 FK는 실제 DB 부모 키와 다시 비교합니다. 오류 시 이번 실행의 INSERT 전체가 롤백됩니다.
MySQL advisory lock으로 이 적재기의 동시 실행을 막습니다. 외부 도구의 동시 변경까지 차단하는 잠금은 아닙니다.
기존 데이터가 원천과 다르더라도 자동 수정하지 않습니다. 검증기가 행 수·PK 집합·NULL·FK 차이를 보고합니다.
모든 비키 값의 완전 일치를 검사하는 도구는 아닙니다.
