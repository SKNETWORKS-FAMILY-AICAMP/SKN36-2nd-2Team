"""Failure-path coverage without pretending SQLite verifies MySQL deployment."""
import contextlib
import io
import unittest
from unittest.mock import patch
from decimal import Decimal
import pandas as pd
from sqlalchemy import create_engine, select, func, event
from src.schema import SPECS, ORDER, metadata
from src.validation import validate_frame
from scripts.load_raw_data import load

def sample(name):
    row = {}
    for col, info in SPECS[name]['columns'].items():
        kind = info['type']
        if kind == 'DATE' or kind.startswith('DATETIME'):
            row[col] = pd.Timestamp('2026-01-01')
        elif kind.startswith('VARCHAR'):
            row[col] = 'sample'
        elif kind.startswith('DECIMAL'):
            row[col] = Decimal('1.00')
        else:
            row[col] = 1
    return validate_frame(name, pd.DataFrame([row]))

class ValidationTests(unittest.TestCase):
    def test_invalid_values(self):
        cases = [('user', 'user_id', None), ('user', 'signup_date', 'bad date'),
                 ('user', 'signup_date', 123), ('user', 'signup_date', '2026-01-01 01:00:00'),
                 ('plan', 'monthly_price', '1.001'), ('plan', 'storage_limit_gb', 'bad number'),
                 ('plan', 'is_paid', 2), ('plan', 'storage_limit_gb', 1.5),
                 ('user', 'region', 'x'*65)]
        for name, col, value in cases:
            with self.subTest(name=name, col=col, value=value):
                frame = sample(name).astype(object)
                frame.loc[0, col] = value
                with self.assertRaises(ValueError):
                    validate_frame(name, frame)

    def test_duplicate_and_unexpected_column(self):
        frame = sample('user')
        with self.assertRaisesRegex(ValueError, 'duplicate PK'):
            validate_frame('user', pd.concat([frame,frame],ignore_index=True))
        with self.assertRaisesRegex(ValueError, 'columns'):
            validate_frame('user', frame.assign(unexpected=1))

    def test_raw_anomalies_preserved(self):
        frame = sample('user_activity_daily').astype(object)
        frame.loc[0, 'login_count'] = -1
        frame.loc[0, 'active_minutes'] = None
        output = validate_frame('user_activity_daily', frame)
        self.assertEqual(output.loc[0, 'login_count'], -1)
        self.assertTrue(pd.isna(output.loc[0, 'active_minutes']))

    def test_fractional_timestamp_preserved(self):
        frame = sample('support_ticket')
        frame.loc[0, 'resolved_at'] = pd.Timestamp('2026-01-01 01:18:07.310000')
        self.assertEqual(validate_frame('support_ticket', frame).loc[0, 'resolved_at'].microsecond, 310000)

class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        @event.listens_for(self.engine, 'connect')
        def enable_fk(dbapi, _):
            dbapi.execute('PRAGMA foreign_keys=ON')
        metadata.create_all(self.engine)
        self.frames = {name: sample(name) for name in ORDER}

    def tearDown(self):
        self.engine.dispose()

    def test_repeat_load_skips(self):
        with patch('scripts.load_raw_data.validate_db_schema'), contextlib.redirect_stdout(io.StringIO()):
            with self.engine.connect() as conn:
                load(conn, self.frames)
                load(conn, self.frames)
                for table in metadata.sorted_tables:
                    self.assertEqual(conn.scalar(select(func.count()).select_from(table)), 1)

    def test_late_failure_rolls_back(self):
        self.frames['payment_history'].loc[0,'subscription_id'] = 999
        with patch('scripts.load_raw_data.validate_db_schema'), contextlib.redirect_stdout(io.StringIO()):
            with self.engine.connect() as conn:
                with self.assertRaisesRegex(ValueError, 'parent DB keys missing'):
                    load(conn, self.frames)
                for table in metadata.sorted_tables:
                    self.assertEqual(conn.scalar(select(func.count()).select_from(table)), 0)

if __name__ == '__main__':
    unittest.main()
