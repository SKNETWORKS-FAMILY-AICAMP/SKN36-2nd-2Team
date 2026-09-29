"""Prediction table contract for the LightGBM V3 five-tier output."""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    func,
)

PREDICTION_TABLE_NAME = "customer_churn_prediction"
RISK_FACTOR_TABLE_NAME = "customer_risk_factor"
DATASET_VERSION = "v3"
MODEL_VERSION = "LightGBM_V3_5tier"
RISK_LEVELS = ["VERY HIGH", "HIGH", "MEDIUM", "LOW", "VERY LOW"]
RISK_LABELS_KO = {
    "VERY HIGH": "매우 높음",
    "HIGH": "높음",
    "MEDIUM": "보통",
    "LOW": "낮음",
    "VERY LOW": "매우 낮음",
}
RISK_BANDS = {
    "VERY HIGH": ">= 0.9745",
    "HIGH": "0.6321 ~ 0.9745",
    "MEDIUM": "0.0554 ~ 0.6321",
    "LOW": "0.0033 ~ 0.0554",
    "VERY LOW": "< 0.0033",
}
RISK_CUTOFFS = {
    "very_high": 0.9745,
    "high": 0.6321,
    "medium": 0.0554,
    "low": 0.0033,
}

metadata = MetaData()

prediction_table = Table(
    PREDICTION_TABLE_NAME,
    metadata,
    Column("user_id", BigInteger, nullable=False),
    Column("snapshot_date", Date, nullable=False),
    Column("churn_probability", Float, nullable=False),
    Column("prediction", Integer, nullable=False),
    Column("risk_level", String(16), nullable=False),
    Column("split", String(32), nullable=False),
    Column("actual_churn_60d", Integer, nullable=False),
    Column("model_version", String(64), nullable=False),
    Column("dataset_version", String(16), nullable=False),
    Column("loaded_at", DateTime, nullable=False, server_default=func.now()),
    UniqueConstraint("user_id", "snapshot_date", name="uq_prediction_user_snapshot"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_0900_ai_ci",
)

Index("ix_prediction_snapshot_date", prediction_table.c.snapshot_date)
Index("ix_prediction_user_snapshot", prediction_table.c.user_id, prediction_table.c.snapshot_date)
Index("ix_prediction_prediction", prediction_table.c.prediction)
Index("ix_prediction_risk_level", prediction_table.c.risk_level)

risk_factor_table = Table(
    RISK_FACTOR_TABLE_NAME,
    metadata,
    Column("user_id", BigInteger, nullable=False),
    Column("snapshot_date", Date, nullable=False),
    Column("churn_probability", Float, nullable=False),
    Column("risk_factor_1", String(255), nullable=True),
    Column("risk_factor_2", String(255), nullable=True),
    Column("risk_factor_3", String(255), nullable=True),
    Column("risk_factor_4", String(255), nullable=True),
    Column("risk_factor_5", String(255), nullable=True),
    Column("model_version", String(64), nullable=False),
    Column("dataset_version", String(16), nullable=False),
    Column("loaded_at", DateTime, nullable=False, server_default=func.now()),
    UniqueConstraint("user_id", "snapshot_date", name="uq_risk_factor_user_snapshot"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_0900_ai_ci",
)

Index("ix_risk_factor_user_snapshot", risk_factor_table.c.user_id, risk_factor_table.c.snapshot_date)
Index("ix_risk_factor_snapshot_date", risk_factor_table.c.snapshot_date)
