"""Read every source cell and record schema evidence; never modify Excel."""
from pathlib import Path
from decimal import Decimal
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

def main():
    tables = {}
    frames = {}
    for path in sorted((ROOT / 'data/raw').rglob('*.xlsx')):
        name = path.stem.split('_', 1)[1]
        book = pd.ExcelFile(path, engine='openpyxl')
        if len(book.sheet_names) != 1 or name in tables:
            raise ValueError(f'Ambiguous source: {path}, {book.sheet_names}')
        df = pd.read_excel(book, keep_default_na=False, na_values=[''])
        frames[name] = df
        columns = {}
        for col in df:
            values = df[col].dropna()
            if pd.api.types.is_datetime64_any_dtype(values):
                kind = 'DATE' if col in {'signup_date','start_date','end_date','next_billing_date','usage_month','activity_date'} else 'DATETIME(6)'
                if kind == 'DATE' and (values != values.dt.normalize()).any():
                    raise ValueError(f'Time loss: {name}.{col}')
            elif pd.api.types.is_bool_dtype(values):
                kind = 'BOOLEAN'
            elif pd.api.types.is_numeric_dtype(values):
                if col in {'monthly_price', 'amount'}:
                    scale = max(max(0, -Decimal(str(v)).as_tuple().exponent) for v in values)
                    kind = f'DECIMAL(18,{max(2, scale)})'
                elif (values % 1 == 0).all():
                    kind = 'BIGINT' if col.endswith('_id') else 'INT'
                else:
                    kind = 'DOUBLE'
            else:
                kind = f'VARCHAR({max(64, int(values.astype(str).str.len().max()))})'
            columns[col] = {'type': kind, 'nullable': bool(df[col].isna().any()), 'nulls': int(df[col].isna().sum())}
        pk = df.columns[0]
        if df[pk].isna().any() or df[pk].duplicated().any():
            raise ValueError(f'Invalid PK: {name}.{pk}')
        tables[name] = {'file': path.relative_to(ROOT).as_posix(), 'sheet': book.sheet_names[0],
                        'rows': len(df), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'pk': pk, 'columns': columns, 'fk': {}}
        print(f'[SCAN] {name}: {len(df):,} rows, {len(df.columns)} columns, sheet={book.sheet_names}', flush=True)
        book.close()
    for name, spec in tables.items():
        for col in spec['columns']:
            parent = {'user_id':'user', 'plan_id':'plan', 'subscription_id':'subscription',
                      'old_plan_id':'plan', 'new_plan_id':'plan'}.get(col)
            if parent and parent != name:
                pk = tables[parent]['pk']
                bad = frames[name][col].notna() & ~frames[name][col].isin(frames[parent][pk])
                if bad.any():
                    raise ValueError(f'Invalid FK {name}.{col}: {frames[name].loc[bad].head().to_dict("records")}')
                spec['fk'][col] = [parent, pk]
    (ROOT/'docs/raw_inventory.json').write_text(json.dumps(tables, ensure_ascii=False, indent=2), encoding='utf-8')
    print('[PASS] All source PK/FK values verified')

if __name__ == '__main__':
    main()
