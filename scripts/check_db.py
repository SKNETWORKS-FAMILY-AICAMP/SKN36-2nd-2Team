"""Read-only DB reconciliation against validated Excel sources."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import inspect, select, func
from src.schema import SPECS, ORDER, metadata
from src.validation import read_sources, validate_db_schema

def main():
    from src.db import engine
    with engine.connect() as conn:
        print('[OK] Database connected')
        print('Tables:', ', '.join(inspect(conn).get_table_names()))
        validate_db_schema(conn)
    frames = read_sources()
    errors = []
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn, conn.begin():
        for name in ORDER:
            spec = SPECS[name]
            table = metadata.tables[name]
            source = frames[name]
            count = conn.scalar(select(func.count()).select_from(table))
            before = len(errors)
            if count != len(source):
                errors.append(f'{name}: row count {count} != {len(source)}')
            duplicates = conn.execute(select(table.c[spec['pk']], func.count()).group_by(table.c[spec['pk']]).having(func.count() > 1).limit(5)).all()
            if duplicates:
                errors.append(f'{name}: duplicate PK {duplicates}')
            null_counts = {}
            for col, info in spec['columns'].items():
                nulls = conn.scalar(select(func.count()).select_from(table).where(table.c[col].is_(None)))
                null_counts[col] = nulls
                expected = int(source[col].isna().sum())
                if nulls != expected or (not info['nullable'] and nulls):
                    errors.append(f'{name}.{col}: DB NULL={nulls}, Excel NULL={expected}')
            for col, (parent_name, pk) in spec['fk'].items():
                parent = metadata.tables[parent_name]
                orphans = conn.scalar(select(func.count()).select_from(table.outerjoin(parent, table.c[col] == parent.c[pk])).where(table.c[col].is_not(None), parent.c[pk].is_(None)))
                if orphans:
                    errors.append(f'{name}.{col}: orphan FK={orphans}')
            db_keys = set(conn.scalars(select(table.c[spec['pk']])))
            excel_keys = set(source[spec['pk']])
            if db_keys != excel_keys:
                errors.append(f'{name}: PK set mismatch; missing={list(excel_keys-db_keys)[:5]}, extra={list(db_keys-excel_keys)[:5]}')
            print(f'\n{name}\nExcel rows : {len(source):,}\nDB rows    : {count:,}\nNULLs      : {null_counts}\nStatus     : {"OK" if len(errors) == before else "FAIL"}', flush=True)
    if errors:
        raise ValueError('\n'.join(errors))
    print('\nALL CHECKS PASSED')

if __name__ == '__main__':
    from src.cli import run
    run(main)
