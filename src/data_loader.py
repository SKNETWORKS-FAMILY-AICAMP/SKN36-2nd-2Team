"""SQL-free DataFrame access. Daily activity can be large."""
import pandas as pd
from src.schema import SPECS

def load_tables(names=None):
    from src.db import engine
    names = list(SPECS) if names is None else list(names)
    unknown = set(names) - SPECS.keys()
    if unknown:
        raise ValueError(f'Unknown tables: {sorted(unknown)}')
    return {name: pd.read_sql_table(name, engine) for name in names}
