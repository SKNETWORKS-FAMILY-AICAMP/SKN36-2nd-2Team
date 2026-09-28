"""Frozen source contract shared by SQL generation, validation, and loading."""
from pathlib import Path
import json
from sqlalchemy import (MetaData, Table, Column, BigInteger, Integer, Boolean,
                        Date, DateTime, Float, Numeric, String, ForeignKey, Index)
from sqlalchemy.dialects.mysql import DOUBLE, DATETIME

ROOT = Path(__file__).resolve().parents[1]
SPECS = json.loads((ROOT/'docs/raw_inventory.json').read_text(encoding='utf-8'))
metadata = MetaData()

def column_type(value):
    if value.startswith('VARCHAR'):
        return String(int(value.split('(')[1][:-1]))
    if value.startswith('DECIMAL'):
        return Numeric(*map(int, value.split('(')[1][:-1].split(',')))
    if value == 'DOUBLE':
        return DOUBLE()
    if value == 'DATETIME(6)':
        return DATETIME(fsp=6)
    return {'BIGINT': BigInteger, 'INT': Integer, 'BOOLEAN': Boolean,
            'DATE': Date, 'DATETIME': DateTime}[value]()

for name, spec in SPECS.items():
    columns = []
    for col, info in spec['columns'].items():
        args = [ForeignKey('.'.join(spec['fk'][col]))] if col in spec['fk'] else []
        columns.append(Column(col, column_type(info['type']), *args,
                              primary_key=col == spec['pk'], nullable=info['nullable'],
                              unique=name == 'plan' and col == 'plan_name',
                              autoincrement=False))
    table = Table(name, metadata, *columns, mysql_engine='InnoDB',
                  mysql_charset='utf8mb4', mysql_collate='utf8mb4_0900_ai_ci')
    for col in spec['fk']:
        Index(f'ix_{name}_{col}', table.c[col])
    for col, info in spec['columns'].items():
        if info['type'] == 'DATE' or info['type'].startswith('DATETIME'):
            Index(f'ix_{name}_{col}', table.c[col])

ORDER = [table.name for table in metadata.sorted_tables]
