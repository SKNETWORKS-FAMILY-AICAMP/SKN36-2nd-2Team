"""Explicitly regenerate DDL from the reviewed frozen source contract."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects import mysql
from src.schema import metadata, ROOT

def main():
    dialect = mysql.dialect()
    chunks = ['-- Source columns only. No DROP/REPLACE. Select the database before execution.\nSET NAMES utf8mb4;']
    for table in metadata.sorted_tables:
        chunks.append(str(CreateTable(table, if_not_exists=True).compile(dialect=dialect)).strip() + ';')
        for index in sorted(table.indexes, key=lambda index: index.name):
            chunks.append(str(CreateIndex(index).compile(dialect=dialect)) + ';')
    (ROOT/'db/init/01_schema.sql').write_text('\n\n'.join(chunks)+'\n', encoding='utf-8')

if __name__ == '__main__':
    main()
