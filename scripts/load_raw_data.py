"""Validate all Excel sources, then append only to empty existing tables."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text, select, func
from src.schema import ORDER, SPECS, metadata
from src.validation import read_sources, validate_db_schema

def load(connection, frames):
    validate_db_schema(connection)
    connection.commit()
    # A single transaction protects all empty tables; populated tables are untouched.
    with connection.begin():
        for name in ORDER:
            table = metadata.tables[name]
            count = connection.scalar(select(func.count()).select_from(table))
            if count:
                print(f'[SKIP] {name}: already {count:,} rows (Excel {len(frames[name]):,})', flush=True)
                continue
            for col, (parent, pk) in SPECS[name]['fk'].items():
                existing = set(connection.scalars(select(metadata.tables[parent].c[pk])))
                missing = set(frames[name][col].dropna()) - existing
                if missing:
                    raise ValueError(f'{name}.{col}: parent DB keys missing: {sorted(missing)[:5]}')
            print(f'[LOAD] {name}: {len(frames[name]):,} rows', flush=True)
            # SQLAlchemy Core inserts cannot implicitly create/replace tables.
            frame = frames[name].astype(object).where(frames[name].notna(), None)
            for start in range(0, len(frame), 2000):
                connection.execute(table.insert(), frame.iloc[start:start+2000].to_dict('records'))
            after = connection.scalar(select(func.count()).select_from(table))
            if after != len(frame):
                raise ValueError(f'{name}: inserted count mismatch {after} != {len(frame)}')
            print(f'[STAGED] {name}: {after:,} rows', flush=True)
    print('[DONE] Transaction committed. Run scripts/check_db.py for reconciliation.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate-only', action='store_true', help='Validate Excel without connecting to MySQL')
    args = parser.parse_args()
    if args.validate_only:
        read_sources()
        print('ALL SOURCE CHECKS PASSED')
        return
    from src.db import engine
    with engine.connect() as connection:
        locked = connection.scalar(text("SELECT GET_LOCK('cloudcare_raw_load', 0)"))
        connection.commit()
        if locked != 1:
            raise ValueError('Another CloudCare import is running')
        try:
            validate_db_schema(connection)
            connection.commit()
            load(connection, read_sources())
        finally:
            connection.rollback()
            connection.execute(text("SELECT RELEASE_LOCK('cloudcare_raw_load')"))
            connection.commit()

if __name__ == '__main__':
    from src.cli import run
    run(main)
