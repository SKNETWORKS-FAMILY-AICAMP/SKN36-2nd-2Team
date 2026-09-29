"""Derived targets are separate from the frozen nine-table raw contract."""
from sqlalchemy import (MetaData, Table, Column, BigInteger, Integer, Date,
                        DateTime, ForeignKey, UniqueConstraint, CheckConstraint, text)
from sqlalchemy.dialects.mysql import TINYINT
from src.schema import metadata as raw_metadata

metadata = MetaData()
raw_metadata.tables['user'].to_metadata(metadata)
target = Table('user_snapshot_target', metadata,
    Column('snapshot_id', BigInteger, primary_key=True, autoincrement=True),
    Column('user_id', BigInteger, ForeignKey('user.user_id'), nullable=False),
    Column('snapshot_date', Date, nullable=False),
    Column('label_window_end', Date, nullable=False),
    Column('churn_date', Date),
    Column('churn_60d', Integer().with_variant(TINYINT(), 'mysql'), nullable=True),
    Column('active_subscription_count', Integer, nullable=False),
    Column('eligible', Integer().with_variant(TINYINT(), 'mysql'), nullable=False),
    Column('created_at', DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP')),
    UniqueConstraint('user_id', 'snapshot_date', name='uq_snapshot_user_date'),
    CheckConstraint('active_subscription_count > 0', name='ck_snapshot_active'),
    CheckConstraint('(eligible = 0 AND churn_60d IS NULL) OR '
                    '(eligible = 1 AND churn_60d IS NOT NULL AND churn_60d IN (0,1))',
                    name='ck_snapshot_label'),
    mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_0900_ai_ci')
