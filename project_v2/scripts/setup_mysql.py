"""Prepare the local Docker MySQL database for CloudCare V3.

This script is intentionally idempotent for local development:
raw V3 tables are reset and reloaded, prediction tables are replaced for
the current model/dataset version, and app support tables are created if
missing.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import OperationalError

from scripts.load_predictions import (
    load_predictions,
    load_risk_factors,
    read_risk_factor_csv,
)
from scripts.load_raw_data import RAW_TABLES, load as load_raw_v3
from src.prediction_schema import prediction_table, risk_factor_table
from src.predictions import DEFAULT_PREDICTION_CSV, read_prediction_csv
from src.validation import read_sources

ROOT = Path(__file__).resolve().parents[1]
ADMIN_XLSX = ROOT / "data/admin.xlsx"
INQUIRY_XLSX = ROOT / "data/inquiry.xlsx"


def wait_for_mysql(engine, timeout_seconds: int) -> None:
    print("[MYSQL] Waiting for MySQL to become ready...", flush=True)
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                conn.commit()
            print("[MYSQL] Ready", flush=True)
            return
        except OperationalError as exc:
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"MySQL is not ready after {timeout_seconds}s: {last_error}")


def ensure_app_tables(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS admin (
            admin_id BIGINT NOT NULL PRIMARY KEY,
            username VARCHAR(64) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL
        ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS inquiry (
            inquiry_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(255) NOT NULL,
            topic VARCHAR(100) NOT NULL,
            message TEXT NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'RECEIVED',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_ai_ci
    """))
    if ADMIN_XLSX.exists():
        admins = pd.read_excel(ADMIN_XLSX)
        for row in admins.astype(object).where(admins.notna(), None).to_dict("records"):
            conn.execute(text("""
                INSERT INTO admin (admin_id, username, password)
                VALUES (:admin_id, :username, :password)
                ON DUPLICATE KEY UPDATE
                    username = VALUES(username),
                    password = VALUES(password)
            """), row)
    if INQUIRY_XLSX.exists():
        inquiries = pd.read_excel(INQUIRY_XLSX)
        if not inquiries.empty:
            records = inquiries.astype(object).where(inquiries.notna(), None).to_dict("records")
            conn.execute(text("DELETE FROM inquiry"))
            for row in records:
                conn.execute(text("""
                    INSERT INTO inquiry (inquiry_id, name, email, topic, message, status, created_at)
                    VALUES (:inquiry_id, :name, :email, :topic, :message, :status, :created_at)
                """), row)
    conn.commit()
    print("[APP] admin/inquiry tables are ready", flush=True)


def print_row_counts(conn) -> None:
    names = [*RAW_TABLES, prediction_table.name, risk_factor_table.name, "admin", "inquiry"]
    existing = set(inspect(conn).get_table_names())
    print("\n[ROW COUNTS]", flush=True)
    for name in names:
        if name not in existing:
            print(f"- {name}: MISSING", flush=True)
            continue
        count = conn.execute(text(f"SELECT COUNT(*) FROM `{name}`")).scalar_one()
        print(f"- {name}: {count:,}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait-timeout", type=int, default=120, help="Seconds to wait for Docker MySQL")
    parser.add_argument("--skip-raw-reset", action="store_true", help="Do not reset/reload raw V3 tables")
    args = parser.parse_args()

    from src.db import engine

    wait_for_mysql(engine, args.wait_timeout)

    print("[SOURCE] Validating V3 Excel files", flush=True)
    frames = read_sources()

    with engine.connect() as conn:
        ensure_app_tables(conn)
        if args.skip_raw_reset:
            load_raw_v3(conn, frames, reset_v3=False)
        else:
            load_raw_v3(conn, frames, reset_v3=True)

        prediction_frame = read_prediction_csv(DEFAULT_PREDICTION_CSV)
        load_predictions(conn, prediction_frame)
        risk_factor_path = DEFAULT_PREDICTION_CSV.with_name("customer_risk_factors_v3.csv")
        if risk_factor_path.exists():
            load_risk_factors(conn, read_risk_factor_csv(risk_factor_path), prediction_frame)
        print_row_counts(conn)

    print("\n[DONE] CloudCare Docker MySQL setup completed", flush=True)


if __name__ == "__main__":
    from src.cli import run

    run(main)
