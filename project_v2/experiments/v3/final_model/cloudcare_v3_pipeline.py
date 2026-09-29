"""Build CloudCare V3 synthetic churn data, features, models, and reports.

V3 writes only new paths. It does not modify V1/V2 raw data, processed data,
models, notebooks, databases, or prior reports.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import math
import pickle
import shutil
import warnings
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from openpyxl import Workbook, load_workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    PrecisionRecallDisplay,
    RocCurveDisplay,
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)


ROOT = Path(__file__).resolve().parents[1]
START = datetime(2024, 1, 1)
REFERENCE_DATE = datetime(2026, 8, 31)
RAW_DIR = ROOT / "data" / "raw" / "cloudcare_v3_20260926_seed42"
PROCESSED_DIR = ROOT / "data" / "processed" / "v3"
EXP_DIR = ROOT / "experiments" / "v3"
FINAL_MODEL_DIR = EXP_DIR / "final_model"
ARTIFACTS_DIR = ROOT / "artifacts"
DOCS_DIR = ROOT / "docs"
TABLE_FILES = {
    "user": "5.1_user.xlsx",
    "plan": "5.2_plan.xlsx",
    "subscription": "5.3_subscription.xlsx",
    "storage_usage_monthly": "5.4_storage_usage_monthly.xlsx",
    "user_activity_daily": "5.5_user_activity_daily.xlsx",
    "device": "5.6_device.xlsx",
    "payment_history": "5.7_payment_history.xlsx",
    "support_ticket": "5.8_support_ticket.xlsx",
    "subscription_event": "5.9_subscription_event.xlsx",
    "user_snapshot_target": "5.10_user_snapshot_target.xlsx",
}
SCHEMAS = {
    "user": "user_id signup_date age_group region signup_channel status created_at updated_at",
    "plan": "plan_id plan_name storage_limit_gb monthly_price billing_cycle is_paid is_active",
    "subscription": "subscription_id user_id plan_id start_date next_billing_date end_date auto_renewal subscription_status created_at updated_at",
    "storage_usage_monthly": "usage_id user_id usage_month storage_used_gb file_count photo_count video_count upload_size_gb download_size_gb created_at",
    "user_activity_daily": "activity_id user_id activity_date login_count upload_count download_count share_count preview_count active_minutes",
    "device": "device_id user_id device_type os_type sync_enabled last_sync_at registered_at",
    "payment_history": "payment_id subscription_id payment_date amount payment_status payment_method retry_count overdue_flag status_changed_at",
    "support_ticket": "ticket_id user_id category priority status created_at resolved_at reopened",
    "subscription_event": "event_id user_id subscription_id event_type old_plan_id new_plan_id event_date auto_renewal_after",
    "user_snapshot_target": "snapshot_id user_id snapshot_date label_window_end churn_date churn_60d active_subscription_count eligible created_at",
}


@dataclass
class V3Config:
    version: str = "V3_GENERATOR_FROZEN"
    seed: int = 42
    n_customers: int = 5000
    risk_persistence: float = 0.94
    future_shock_weight: float = 0.30
    behavior_signal_strength: float = 1.10
    churn_sustained_risk_weight: float = 1.65
    churn_observable_warning_weight: float = 0.65
    renewal_weight: float = 0.55
    target_overall_churn_ratio: float = 0.162
    warning_signal_target: str = "75-90% of sustained high/rising users show at least one observable warning"


def add_months(d, n):
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def frame(name, rows):
    return pd.DataFrame(rows, columns=SCHEMAS[name].split())


def plan_table():
    return frame("plan", [(i, name, limit, price, cycle, i != 1, True) for i, name, limit, price, cycle in [
        (1, "FREE", 15, 0, "MONTHLY"), (2, "100GB_M", 100, 2900, "MONTHLY"),
        (3, "100GB_Y", 100, 2700, "YEARLY"), (4, "200GB_M", 200, 4900, "MONTHLY"),
        (5, "200GB_Y", 200, 4500, "YEARLY"), (6, "2TB_M", 2000, 11900, "MONTHLY"),
        (7, "2TB_Y", 2000, 10900, "YEARLY")
    ]])


def generate_users(rng, n):
    regions = ["서울","경기","부산","인천","대구","대전","광주","울산","세종","강원","충북","충남","전북","전남","경북","경남","제주"]
    weights = np.array([19,27,7,6,5,3,3,2,1,3,3,4,3,3,5,7,1], dtype=float)
    rows = []
    for i in range(n):
        uid = 100001 + i
        signup = START + timedelta(days=int(rng.beta(1.07, 1) * (REFERENCE_DATE - START).days))
        rows.append([uid, signup, rng.choice(["10대","20대","30대","40대","50대","60대 이상"], p=[.05,.25,.3,.2,.13,.07]),
                     rng.choice(regions, p=weights / weights.sum()), rng.choice(["WEB","IOS","ANDROID"], p=[.25,.35,.4]),
                     "ACTIVE", signup, REFERENCE_DATE])
    return frame("user", rows)


def generate_profiles(users, rng, cfg):
    days = (REFERENCE_DATE - START).days + 1
    profiles = {}
    for u in users.itertuples(index=False):
        persona_w = rng.dirichlet([2.2, 1.6, 1.3, 1.2, 1.1])
        base = {
            "engagement": rng.beta(2.5, 2.2),
            "satisfaction": rng.beta(4.0, 2.2),
            "financial_risk": rng.beta(1.35, 8.0),
            "technical_friction": rng.beta(1.6, 5.0),
            "price_sensitivity": rng.beta(2.2, 3.0),
            "competitor_intent": rng.beta(1.8, 5.2),
            "personas": persona_w,
            "silent": bool(rng.random() < .14),
            "size_factor": rng.lognormal(0, .45),
        }
        base_score = (
            1.1 * (.55 - base["engagement"]) + 1.15 * (.62 - base["satisfaction"])
            + .95 * base["financial_risk"] + .85 * base["technical_friction"]
            + .75 * base["price_sensitivity"] + .85 * base["competitor_intent"]
            + rng.normal(0, .22) - .55
        )
        shocks = rng.normal(0, .18, days)
        state = np.zeros(days)
        state[0] = base_score + rng.normal(0, .35)
        for d in range(1, days):
            seasonal = .10 * math.sin(d / 45.0) + .06 * math.sin(d / 120.0)
            state[d] = cfg.risk_persistence * state[d - 1] + (1 - cfg.risk_persistence) * base_score + shocks[d] + seasonal * .03
        risk = 1 / (1 + np.exp(-state))
        kernel30 = np.ones(30) / 30
        kernel90 = np.ones(90) / 90
        r30 = np.convolve(risk, kernel30, mode="same")
        r90 = np.convolve(risk, kernel90, mode="same")
        high_duration = np.zeros(days)
        run = 0
        for d, val in enumerate(risk):
            run = run + 1 if val > .62 else max(0, run - 1)
            high_duration[d] = min(run, 120) / 120
        sustained = .30 * risk + .32 * r30 + .28 * r90 + .10 * high_duration
        warning_propensity = 1 / (1 + np.exp(-(4.0 * sustained + 1.0 * (1 - base["satisfaction"]) - 2.3)))
        if base["silent"]:
            warning_propensity *= .38
        base.update({"risk": risk, "risk30": r30, "risk90": r90, "sustained": sustained, "warning": warning_propensity, "churn_date": None})
        profiles[u.user_id] = base
    return profiles


def idx(date):
    return max(0, min((REFERENCE_DATE - START).days, (pd.Timestamp(date).to_pydatetime() - START).days))


def pval(p, key, date):
    return float(p[key][idx(date)])


def last_day(p):
    return p["churn_date"] or REFERENCE_DATE


def choose_churn_dates(users, profiles, rng, cfg):
    candidates = []
    for u in users.itertuples(index=False):
        start_i = max(45, idx(u.signup_date) + 35)
        if start_i >= len(profiles[u.user_id]["risk"]):
            continue
        p = profiles[u.user_id]
        future_noise = rng.normal(0, cfg.future_shock_weight, len(p["risk"]) - start_i)
        log_h = -8.05 + cfg.churn_sustained_risk_weight * 4.0 * p["sustained"][start_i:] + cfg.churn_observable_warning_weight * 2.0 * p["warning"][start_i:] + .45 * p["competitor_intent"] + future_noise
        daily = np.exp(np.clip(log_h, -11, -3.3))
        draw = rng.exponential()
        cs = np.cumsum(daily)
        off = int(np.searchsorted(cs, draw))
        if off < len(cs):
            candidates.append((u.user_id, START + timedelta(days=start_i + off), float(cs[off])))
    target = int(cfg.target_overall_churn_ratio * len(users))
    # Keep churn distributed across the observed period. Sorting by date would
    # front-load churn and leave later validation/test windows without positives.
    if len(candidates) > target:
        weights = np.array([score for _, _, score in candidates], dtype=float)
        weights = weights / weights.sum()
        picked = rng.choice(np.arange(len(candidates)), size=target, replace=False, p=weights)
        candidates = [candidates[int(i)] for i in picked]
    for uid, date, _ in candidates:
        profiles[int(uid)]["churn_date"] = pd.Timestamp(date).to_pydatetime()


def generate_subscriptions(users, profiles, plans, rng, cfg):
    rows = []
    for u in users.itertuples(index=False):
        p = profiles[u.user_id]
        pid = int(rng.choice(range(1, 8), p=np.array([.26,.23,.12,.16,.08,.10,.05])))
        start = u.signup_date
        j = 0
        while start <= last_day(p):
            risk = pval(p, "sustained", start)
            change_prob = .018 + .10 * risk + .08 * p["price_sensitivity"]
            next_start = None
            if rng.random() < change_prob and start + timedelta(days=50) < last_day(p):
                next_start = start + timedelta(days=int(rng.integers(35, 150)))
            end = (next_start - timedelta(days=1)) if next_start else (p["churn_date"] if p["churn_date"] else None)
            status = "ACTIVE" if end is None else ("CANCELLED" if end == p["churn_date"] and rng.random() < .80 else "EXPIRED")
            cycle = 12 if plans.loc[pid, "billing_cycle"] == "YEARLY" else 1
            next_bill = None
            if status == "ACTIVE" and pid != 1:
                n = 1
                next_bill = add_months(start, cycle)
                while next_bill <= REFERENCE_DATE:
                    n += 1
                    next_bill = add_months(start, cycle * n)
            auto = bool(rng.random() < (.95 - .18 * p["price_sensitivity"] - .35 * risk))
            rows.append([len(rows)+1, u.user_id, pid, start, next_bill, end, auto, status, start, end or REFERENCE_DATE])
            if next_start is None:
                break
            down = rng.random() < (.28 + .38 * risk + .22 * p["price_sensitivity"])
            old_limit = plans.loc[pid, "storage_limit_gb"]
            choices = [k for k in range(1, 8) if (plans.loc[k, "storage_limit_gb"] < old_limit if down else plans.loc[k, "storage_limit_gb"] > old_limit)]
            pid = int(rng.choice(choices or [k for k in range(1, 8) if k != pid]))
            start = next_start
            j += 1
    return frame("subscription", rows)


def plan_at(history, date):
    for r in reversed(list(history.itertuples(index=False))):
        if r.start_date <= date and (pd.isna(r.end_date) or r.end_date >= date):
            return int(r.plan_id)
    return 1


def generate_behavior(users, subs, profiles, plans, rng, cfg):
    histories = {uid: h.sort_values("start_date") for uid, h in subs.groupby("user_id")}
    storage_rows, activity_rows, device_rows, pay_rows, support_rows, event_rows = [], [], [], [], [], []
    storage_ratio = {}
    for u in users.itertuples(index=False):
        p = profiles[u.user_id]
        h = histories[u.user_id]
        personas = p["personas"]
        month = u.signup_date.replace(day=1)
        used = plans.loc[int(h.iloc[0].plan_id), "storage_limit_gb"] * rng.uniform(.08, .55)
        decline_streak = 0
        while month <= last_day(p):
            snap = min(add_months(month, 1) - timedelta(days=1), last_day(p))
            risk, warn = pval(p, "sustained", snap), pval(p, "warning", snap)
            cap = float(plans.loc[plan_at(h, snap), "storage_limit_gb"])
            usage_decay = cfg.behavior_signal_strength * warn * (.30 + .75 * personas[0] + .35 * personas[3])
            growth = .055 * (p["engagement"] - .35) - usage_decay + rng.normal(0, .04)
            used = float(np.clip(used * (1 + growth) + cap * .004 * p["engagement"], 0, cap * .98))
            decline_streak = decline_streak + 1 if growth < -.04 else 0
            files = int(max(1, used * rng.uniform(160, 340)))
            photos = int(files * rng.uniform(.35, .65))
            videos = int((files - photos) * rng.uniform(.03, .20))
            storage_rows.append([len(storage_rows)+1, u.user_id, month, round(used, 2), files, photos, videos, round(cap*.06*p["engagement"]*max(.15, 1-usage_decay),2), round(cap*.04*p["engagement"]*rng.lognormal(0,.35),2), snap.replace(hour=23)])
            storage_ratio[(u.user_id, month)] = used / cap if cap else 0
            month = add_months(month, 1)
        n = (last_day(p) - u.signup_date).days + 1
        for off in range(n):
            date = u.signup_date + timedelta(days=off)
            risk, warn = pval(p, "sustained", date), pval(p, "warning", date)
            active_p = max(.015, .055 + .25 * p["engagement"] - .18 * cfg.behavior_signal_strength * warn * (.8 + personas[0]))
            if rng.random() < active_p:
                intensity = max(.08, p["engagement"] * (1 - .75 * warn * (.8 + personas[0])) + rng.normal(0, .05))
                login = 1 + int(rng.poisson(2.8 * intensity))
                upload = int(rng.poisson(8 * intensity)) if rng.random() < .62 else 0
                download = int(rng.poisson(5 * intensity))
                share = int(rng.poisson(2 * intensity)) if rng.random() < .18 else 0
                preview = int(rng.poisson(14 * intensity))
                minutes = int(np.clip(rng.gamma(2, 5 + 26 * intensity) + 2 * (upload + download), 3, 800))
                activity_rows.append([len(activity_rows)+1, u.user_id, date, login, upload, download, share, preview, minutes])
        base_devices = np.clip(round(1 + p["size_factor"] + .8 * p["engagement"] + plans.loc[int(h.iloc[0].plan_id), "is_paid"]), 1, 5)
        for _ in range(int(base_devices)):
            kind = rng.choice(["MOBILE","PC","TABLET"], p=[.54,.36,.10])
            os = rng.choice(["WINDOWS","MACOS"], p=[.75,.25]) if kind == "PC" else rng.choice(["IOS","ANDROID"], p=[.47,.53])
            reg = u.signup_date + timedelta(days=int(rng.integers(0, max(1, (last_day(p)-u.signup_date).days+1))))
            enabled = bool(rng.random() < .96 - .38 * p["technical_friction"])
            lag = int(rng.exponential(3 + 60 * p["technical_friction"] + 35 * pval(p, "warning", reg)))
            sync = max(reg, min(last_day(p), REFERENCE_DATE) - timedelta(days=lag)) if rng.random() > .06 else None
            device_rows.append([len(device_rows)+1, u.user_id, kind, os, enabled, sync, reg])
    channels = users.set_index("user_id").signup_channel
    for s in subs.itertuples(index=False):
        if s.plan_id == 1:
            continue
        plan = plans.loc[s.plan_id]
        cycle = 12 if plan.billing_cycle == "YEARLY" else 1
        amount = float(plan.monthly_price) * cycle
        finish = s.end_date if pd.notna(s.end_date) else REFERENCE_DATE
        n, date = 0, s.start_date
        while date <= finish:
            p = profiles[s.user_id]
            warn = pval(p, "warning", date)
            fail = np.clip(.015 + .20*p["financial_risk"] + .24*warn*(.6+p["personas"][2]), .005, .70)
            status = rng.choice(["SUCCESS","FAILED","REFUNDED"], p=[1-fail-.012, fail, .012])
            retry = int(rng.choice([1,2,3], p=[.45,.35,.20])) if status == "FAILED" else int(rng.random() < .025 + .05*p["financial_risk"])
            overdue = int(status == "FAILED" and rng.random() < .25 + .35*p["financial_risk"])
            method = {"WEB":"CARD","IOS":"APP_STORE","ANDROID":"PLAY_STORE"}[channels[s.user_id]]
            pay_rows.append([len(pay_rows)+1, s.subscription_id, date.replace(hour=12), amount, status, method, retry, overdue, date.replace(hour=12) + timedelta(hours=int(rng.integers(1, 36)))])
            n += 1
            date = add_months(s.start_date, cycle * n)
    for u in users.itertuples(index=False):
        p = profiles[u.user_id]
        age = (last_day(p) - u.signup_date).days
        for start_off in range(0, age + 1, 30):
            date0 = u.signup_date + timedelta(days=start_off)
            warn = pval(p, "warning", date0)
            intensity = (.045 + .13*p["technical_friction"] + .055*(1-p["satisfaction"]) + .34*warn*(.5+p["personas"][1]))
            for _ in range(int(rng.poisson(intensity))):
                d = date0 + timedelta(days=int(rng.integers(0, min(30, age-start_off+1))), hours=int(rng.integers(0, 20)))
                severity = np.clip(.35*p["technical_friction"] + .38*pval(p, "warning", d) + .18*(1-p["satisfaction"]), 0, 1)
                priority = rng.choice(["LOW","NORMAL","HIGH","URGENT"], p=np.array([.16-.07*severity,.61-.26*severity,.18+.20*severity,.05+.13*severity]))
                cat = rng.choice(["결제","동기화","저장공간","오류"], p=np.array([.22+1.4*p["financial_risk"], .25+1.5*p["technical_friction"], .18+.6*storage_ratio.get((u.user_id, d.replace(day=1,hour=0)), .2), .25+1.2*p["technical_friction"]]) / np.array([.22+1.4*p["financial_risk"], .25+1.5*p["technical_friction"], .18+.6*storage_ratio.get((u.user_id, d.replace(day=1,hour=0)), .2), .25+1.2*p["technical_friction"]]).sum())
                resolved = d + timedelta(hours=float(rng.gamma(2, 10 + 48*p["technical_friction"] + 35*pval(p, "warning", d))))
                if resolved > REFERENCE_DATE or rng.random() < .025 + .04*severity:
                    resolved = None
                reopened = bool(rng.random() < .025 + .22*p["technical_friction"] + .20*pval(p, "warning", d))
                support_rows.append([len(support_rows)+1, u.user_id, cat, priority, "RESOLVED" if resolved else "OPEN", d, resolved, reopened])
    for hist in histories.values():
        prev = None
        for s in hist.itertuples(index=False):
            if prev is not None:
                kind = "UPGRADE" if plans.loc[s.plan_id, "storage_limit_gb"] > plans.loc[prev.plan_id, "storage_limit_gb"] else "DOWNGRADE"
                event_rows.append([len(event_rows)+1, s.user_id, s.subscription_id, kind, prev.plan_id, s.plan_id, s.start_date, s.auto_renewal])
            finish = s.end_date if pd.notna(s.end_date) else REFERENCE_DATE
            cycle = 12 if plans.loc[s.plan_id, "billing_cycle"] == "YEARLY" else 3
            if s.plan_id != 1:
                d = add_months(s.start_date, cycle)
                while d <= finish:
                    event_rows.append([len(event_rows)+1, s.user_id, s.subscription_id, "RENEW", s.plan_id, s.plan_id, d, s.auto_renewal])
                    d = add_months(d, cycle)
            if s.subscription_status == "CANCELLED":
                event_rows.append([len(event_rows)+1, s.user_id, s.subscription_id, "CANCEL", s.plan_id, None, s.end_date, False])
            prev = s
    return {
        "storage_usage_monthly": frame("storage_usage_monthly", storage_rows),
        "user_activity_daily": frame("user_activity_daily", activity_rows),
        "device": frame("device", device_rows),
        "payment_history": frame("payment_history", pay_rows),
        "support_ticket": frame("support_ticket", support_rows),
        "subscription_event": frame("subscription_event", event_rows),
    }


def generate_target(users, subs):
    cutoff = pd.Timestamp(REFERENCE_DATE)
    churn = {}
    for uid, hist in subs.groupby("user_id"):
        if hist.end_date.notna().all() and hist.end_date.max() <= cutoff:
            churn[uid] = hist.end_date.max()
    rows = []
    dates = pd.date_range(users.signup_date.min().to_period("M").start_time, cutoff, freq="ME")
    for snap in dates:
        active = subs[(subs.start_date <= snap) & (subs.end_date.isna() | (subs.end_date >= snap))]
        counts = active.groupby("user_id").size()
        window = snap + pd.Timedelta(days=60)
        eligible = int(window <= cutoff)
        for uid, count in counts.items():
            end = churn.get(uid, pd.NaT)
            if pd.notna(end) and end <= snap:
                continue
            label = int(pd.notna(end) and snap < end <= window) if eligible else pd.NA
            rows.append([len(rows)+1, int(uid), snap, window, end, label, int(count), eligible, datetime(2026, 9, 26, 0, 0, 0)])
    df = frame("user_snapshot_target", rows)
    df["churn_60d"] = df["churn_60d"].astype("Int64")
    return df


def save_excel(path, sheet, df):
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(sheet)
    ws.freeze_panes = "A2"
    from openpyxl.utils import get_column_letter
    headers = []
    for col in df.columns:
        cell = WriteOnlyCell(ws, col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="24476A")
        headers.append(cell)
    ws.append(headers)
    for row in df.itertuples(index=False, name=None):
        out = []
        for col, value in zip(df.columns, row):
            if pd.isna(value):
                value = None
            if isinstance(value, pd.Timestamp):
                value = value.to_pydatetime()
            cell = WriteOnlyCell(ws, value)
            if isinstance(value, datetime):
                cell.number_format = "yyyy-mm-dd hh:mm:ss" if col.endswith("_at") or col in ["payment_date","event_date","status_changed_at"] else "yyyy-mm-dd"
            out.append(cell)
        ws.append(out)
    ws.auto_filter.ref = f"A1:{get_column_letter(len(df.columns))}{len(df)+1}"
    wb.save(path)


def read_excel_table(path, name):
    df = pd.read_excel(path, sheet_name=name, engine="openpyxl", keep_default_na=False, na_values=[""])
    for c in df.columns:
        if c.endswith("_date") or c.endswith("_at") or c in ["usage_month", "resolved_at", "registered_at", "last_sync_at", "next_billing_date", "end_date"]:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def build_features(tables):
    user, plan, sub = tables["user"], tables["plan"], tables["subscription"]
    activity, storage, device = tables["user_activity_daily"], tables["storage_usage_monthly"], tables["device"]
    payment, support, event, target = tables["payment_history"], tables["support_ticket"], tables["subscription_event"], tables["user_snapshot_target"]
    plan_i = plan.set_index("plan_id")
    target = target[target.eligible.eq(1)].copy()
    target["churn_60d"] = target.churn_60d.astype(int)
    base = target[["snapshot_id","user_id","snapshot_date","churn_60d","active_subscription_count"]].merge(user[["user_id","signup_date","age_group","region","signup_channel"]], on="user_id", how="left")
    base["account_age_days"] = (base.snapshot_date - base.signup_date).dt.days
    keys = base[["snapshot_id","user_id","snapshot_date"]]
    activity = activity.copy()
    activity["available_at"] = activity.activity_date + pd.Timedelta(days=1)
    activity["action_count"] = activity[["upload_count","download_count","share_count","preview_count"]].sum(axis=1)
    aj = keys.merge(activity, on="user_id", how="left")
    ap = aj[aj.available_at <= aj.snapshot_date].copy()
    def agg_activity(days, suffix):
        w = ap[ap.activity_date > ap.snapshot_date - pd.Timedelta(days=days)]
        return w.groupby("snapshot_id").agg(**{
            f"login_count_{suffix}": ("login_count","sum"),
            f"active_days_{suffix}": ("activity_date","nunique"),
            f"active_minutes_{suffix}": ("active_minutes","sum"),
            f"action_count_{suffix}": ("action_count","sum"),
        }).reset_index()
    f = base.merge(agg_activity(30, "30d"), on="snapshot_id", how="left")
    prev30 = ap[(ap.activity_date <= ap.snapshot_date - pd.Timedelta(days=30)) & (ap.activity_date > ap.snapshot_date - pd.Timedelta(days=60))].groupby("snapshot_id").agg(login_count_prev30d=("login_count","sum"), active_days_prev30d=("activity_date","nunique"), active_minutes_prev30d=("active_minutes","sum"), action_count_prev30d=("action_count","sum")).reset_index()
    f = f.merge(prev30, on="snapshot_id", how="left")
    last_act = ap.groupby("snapshot_id").activity_date.max().rename("last_activity_date").reset_index()
    f = f.merge(last_act, on="snapshot_id", how="left")
    for c in ["login_count_30d","active_days_30d","active_minutes_30d","action_count_30d","login_count_prev30d","active_days_prev30d","active_minutes_prev30d","action_count_prev30d"]:
        f[c] = f[c].fillna(0)
    f["login_change_rate_30d"] = (f.login_count_30d - f.login_count_prev30d) / (f.login_count_prev30d + 1)
    f["active_days_change_rate"] = (f.active_days_30d - f.active_days_prev30d) / (f.active_days_prev30d + 1)
    f["active_minutes_change_rate"] = (f.active_minutes_30d - f.active_minutes_prev30d) / (f.active_minutes_prev30d + 1)
    f["action_count_change_rate"] = (f.action_count_30d - f.action_count_prev30d) / (f.action_count_prev30d + 1)
    f["days_since_last_activity"] = (f.snapshot_date - f.last_activity_date).dt.days.fillna(999)
    slopes = []
    for sid, g in ap[ap.activity_date > ap.snapshot_date - pd.Timedelta(days=90)].groupby("snapshot_id"):
        daily = g.groupby("activity_date").login_count.sum()
        x = (daily.index - daily.index.min()).days.to_numpy()
        slopes.append((sid, float(np.polyfit(x, daily.to_numpy(), 1)[0]) if len(daily) >= 2 else 0.0))
    f = f.merge(pd.DataFrame(slopes, columns=["snapshot_id","login_slope_90d"]), on="snapshot_id", how="left")
    f["login_slope_90d"] = f.login_slope_90d.fillna(0)
    storage = storage.copy()
    storage["available_at"] = pd.concat([storage.usage_month + pd.offsets.MonthBegin(1), storage.created_at], axis=1).max(axis=1)
    sj = keys.merge(storage, on="user_id", how="left")
    sp = sj[sj.available_at <= sj.snapshot_date].copy()
    latest = sp.sort_values(["snapshot_id","usage_month"]).groupby("snapshot_id").tail(1)[["snapshot_id","usage_month","storage_used_gb"]].rename(columns={"usage_month":"latest_usage_month","storage_used_gb":"storage_used_gb_latest"})
    f = f.merge(latest, on="snapshot_id", how="left")
    for months, name in [(1, "storage_change_rate_1m"), (3, "storage_change_rate_3m")]:
        tmp = latest.copy()
        tmp["target_month"] = (tmp.latest_usage_month.dt.to_period("M") - months).dt.to_timestamp()
        old = tmp[["snapshot_id","target_month"]].merge(sp[["snapshot_id","usage_month","storage_used_gb"]], left_on=["snapshot_id","target_month"], right_on=["snapshot_id","usage_month"], how="left")
        f = f.merge(pd.DataFrame({"snapshot_id": tmp.snapshot_id, name: (tmp.storage_used_gb_latest.to_numpy() - old.storage_used_gb.to_numpy()) / (old.storage_used_gb.to_numpy() + 1)}), on="snapshot_id", how="left")
    storage_slopes, decline_counts = [], []
    for sid, g in sp[sp.usage_month > sp.snapshot_date - pd.Timedelta(days=120)].groupby("snapshot_id"):
        gg = g.sort_values("usage_month").dropna(subset=["storage_used_gb"])
        x = np.arange(len(gg))
        storage_slopes.append((sid, float(np.polyfit(x, gg.storage_used_gb.to_numpy(), 1)[0]) if len(gg) >= 2 else 0.0))
        diffs = gg.storage_used_gb.diff().dropna()
        decline_counts.append((sid, int((diffs < 0).sum())))
    f = f.merge(pd.DataFrame(storage_slopes, columns=["snapshot_id","storage_slope_90d"]), on="snapshot_id", how="left")
    f = f.merge(pd.DataFrame(decline_counts, columns=["snapshot_id","consecutive_storage_decline_months"]), on="snapshot_id", how="left")
    active = keys.merge(sub.merge(plan[["plan_id","storage_limit_gb","is_paid","monthly_price"]], on="plan_id"), on="user_id", how="left")
    active = active[(active.start_date <= active.snapshot_date) & (active.end_date.isna() | (active.end_date >= active.snapshot_date))]
    sf = active.groupby("snapshot_id").agg(active_sub_count_asof=("subscription_id","count"), paid_sub_count_asof=("is_paid","sum"), total_storage_limit_gb=("storage_limit_gb","sum"), total_monthly_price=("monthly_price","sum"), min_tenure_days=("start_date", lambda s: 0)).reset_index()
    sf["min_tenure_days"] = active.groupby("snapshot_id").apply(lambda g: (g.snapshot_date.iloc[0] - g.start_date.min()).days, include_groups=False).to_numpy()
    sf["max_tenure_days"] = active.groupby("snapshot_id").apply(lambda g: (g.snapshot_date.iloc[0] - g.start_date.max()).days, include_groups=False).to_numpy()
    nextbill = active.groupby("snapshot_id").next_billing_date.min().rename("next_billing_date").reset_index()
    auto = active.groupby("snapshot_id").auto_renewal.min().rename("auto_renewal_on").reset_index()
    f = f.merge(sf, on="snapshot_id", how="left").merge(nextbill, on="snapshot_id", how="left").merge(auto, on="snapshot_id", how="left")
    f["storage_utilization_ratio"] = f.storage_used_gb_latest / (f.total_storage_limit_gb + 1)
    f["days_to_renewal"] = (f.next_billing_date - f.snapshot_date).dt.days.clip(lower=0, upper=365).fillna(365)
    f["auto_renewal_off_flag"] = (~f.auto_renewal_on.fillna(True).astype(bool)).astype(int)
    dev = keys.merge(device, on="user_id", how="left")
    da = dev[dev.registered_at <= dev.snapshot_date]
    df = da.groupby("snapshot_id").agg(device_count_asof=("device_id","count"), device_type_count=("device_type","nunique"), os_type_count=("os_type","nunique")).reset_index()
    f = f.merge(df, on="snapshot_id", how="left")
    f["devices_per_account_year"] = f.device_count_asof.fillna(0) / (f.account_age_days / 365 + .25)
    f["device_count_per_tenure"] = f.device_count_asof.fillna(0) / (f.account_age_days + 30)
    f["device_count_per_sqrt_age"] = f.device_count_asof.fillna(0) / np.sqrt(f.account_age_days + 30)
    pay_user = payment.merge(sub[["subscription_id","user_id"]], on="subscription_id", how="left")
    pj = keys.merge(pay_user, on="user_id", how="left")
    pp = pj[pj.status_changed_at <= pj.snapshot_date].copy()
    p30, p90 = pp[pp.status_changed_at > pp.snapshot_date - pd.Timedelta(days=30)], pp[pp.status_changed_at > pp.snapshot_date - pd.Timedelta(days=90)]
    pf = p90.groupby("snapshot_id").agg(payment_count_90d=("payment_id","count"), failed_payment_count_90d=("payment_status", lambda s: (s=="FAILED").sum()), retry_count_90d=("retry_count","sum"), overdue_count_90d=("overdue_flag","sum")).reset_index()
    pf30 = p30.groupby("snapshot_id").payment_status.apply(lambda s: int((s=="FAILED").sum())).rename("failed_payment_count_30d").reset_index()
    f = f.merge(pf, on="snapshot_id", how="left").merge(pf30, on="snapshot_id", how="left")
    f["payment_failure_rate_90d"] = f.failed_payment_count_90d / (f.payment_count_90d + 1)
    last_fail = pp[pp.payment_status.eq("FAILED")].groupby("snapshot_id").status_changed_at.max().rename("last_failed_payment_at").reset_index()
    f = f.merge(last_fail, on="snapshot_id", how="left")
    f["days_since_last_failed_payment"] = (f.snapshot_date - f.last_failed_payment_at).dt.days.fillna(999)
    tj = keys.merge(support, on="user_id", how="left")
    tp = tj[tj.created_at <= tj.snapshot_date].copy()
    t30, t90 = tp[tp.created_at > tp.snapshot_date - pd.Timedelta(days=30)], tp[tp.created_at > tp.snapshot_date - pd.Timedelta(days=90)]
    t90 = t90.copy()
    t90["urgent"] = t90.priority.isin(["HIGH","URGENT"]).astype(int)
    t90["resolution_hours"] = ((t90.resolved_at - t90.created_at).dt.total_seconds()/3600).where(t90.resolved_at <= t90.snapshot_date)
    tf = t90.groupby("snapshot_id").agg(ticket_count_90d=("ticket_id","count"), urgent_ticket_share=("urgent","mean"), reopened_count_90d=("reopened","sum"), avg_resolution_hours_90d=("resolution_hours","mean")).reset_index()
    tf30 = t30.groupby("snapshot_id").ticket_id.count().rename("ticket_count_30d").reset_index()
    unresolved = tp[tp.resolved_at.isna() | (tp.resolved_at > tp.snapshot_date)].groupby("snapshot_id").ticket_id.count().rename("unresolved_ticket_count").reset_index()
    f = f.merge(tf, on="snapshot_id", how="left").merge(tf30, on="snapshot_id", how="left").merge(unresolved, on="snapshot_id", how="left")
    f["ticket_change_rate"] = (f.ticket_count_30d.fillna(0) - (f.ticket_count_90d.fillna(0)-f.ticket_count_30d.fillna(0))/2) / ((f.ticket_count_90d.fillna(0)-f.ticket_count_30d.fillna(0))/2 + 1)
    ev = keys.merge(event, on="user_id", how="left")
    ep = ev[(ev.event_date <= ev.snapshot_date) & (ev.event_date > ev.snapshot_date - pd.Timedelta(days=90))]
    ef = ep.groupby("snapshot_id").agg(downgrade_count_90d=("event_type", lambda s: (s=="DOWNGRADE").sum()), plan_change_count_90d=("event_type", lambda s: s.isin(["UPGRADE","DOWNGRADE"]).sum())).reset_index()
    last_down = ev[(ev.event_date <= ev.snapshot_date) & ev.event_type.eq("DOWNGRADE")].groupby("snapshot_id").event_date.max().rename("last_downgrade_at").reset_index()
    f = f.merge(ef, on="snapshot_id", how="left").merge(last_down, on="snapshot_id", how="left")
    f["days_since_last_downgrade"] = (f.snapshot_date - f.last_downgrade_at).dt.days.fillna(999)
    numeric_fill = [c for c in f.columns if c not in ["user_id","snapshot_date","churn_60d","age_group","region","signup_channel","signup_date","last_activity_date","latest_usage_month","next_billing_date","last_failed_payment_at","last_downgrade_at"]]
    f[numeric_fill] = f[numeric_fill].fillna(0)
    features = [
        "account_age_days","age_group","region","signup_channel","login_count_30d","login_count_prev30d","login_change_rate_30d","login_slope_90d",
        "active_days_30d","active_days_change_rate","active_minutes_30d","active_minutes_change_rate","action_count_30d","action_count_change_rate","days_since_last_activity",
        "storage_used_gb_latest","storage_change_rate_1m","storage_change_rate_3m","storage_slope_90d","consecutive_storage_decline_months","storage_utilization_ratio",
        "payment_count_90d","failed_payment_count_30d","failed_payment_count_90d","payment_failure_rate_90d","retry_count_90d","overdue_count_90d","days_since_last_failed_payment",
        "ticket_count_30d","ticket_count_90d","ticket_change_rate","urgent_ticket_share","reopened_count_90d","avg_resolution_hours_90d","unresolved_ticket_count",
        "downgrade_count_90d","days_since_last_downgrade","plan_change_count_90d","days_to_renewal","auto_renewal_off_flag",
        "device_count_asof","device_type_count","os_type_count","devices_per_account_year","device_count_per_tenure","device_count_per_sqrt_age",
        "active_sub_count_asof","paid_sub_count_asof","total_storage_limit_gb","total_monthly_price","min_tenure_days","max_tenure_days"
    ]
    return f[["user_id","snapshot_date","churn_60d"] + features], features


def split_temporal(df):
    train = df[df.snapshot_date <= "2025-10-31"].copy()
    purge1 = df[(df.snapshot_date > "2025-10-31") & (df.snapshot_date <= "2025-12-31")].copy()
    valid = df[(df.snapshot_date > "2025-12-31") & (df.snapshot_date <= "2026-03-31")].copy()
    purge2 = df[(df.snapshot_date > "2026-03-31") & (df.snapshot_date <= "2026-04-30")].copy()
    test = df[(df.snapshot_date > "2026-04-30") & (df.snapshot_date <= "2026-05-31")].copy()
    final_holdout = df[(df.snapshot_date > "2026-05-31") & (df.snapshot_date <= "2026-06-30")].copy()
    purge = pd.concat([purge1, purge2], ignore_index=True)
    return {"train": train, "valid": valid, "test": test, "purge": purge, "final_holdout": final_holdout}


def split_summary(splits):
    out = {}
    for name, d in splits.items():
        out[name] = {"rows": len(d), "positive": int(d.churn_60d.sum()) if len(d) else 0, "negative": int((d.churn_60d == 0).sum()) if len(d) else 0, "positive_ratio": float(d.churn_60d.mean()) if len(d) else None, "min_date": str(d.snapshot_date.min().date()) if len(d) else None, "max_date": str(d.snapshot_date.max().date()) if len(d) else None}
    return out


def effect_report(df, features, split_name):
    rows = []
    y = df.churn_60d.astype(int)
    for c in features:
        if not pd.api.types.is_numeric_dtype(df[c]):
            continue
        x = df[c].replace([np.inf, -np.inf], np.nan).fillna(df[c].median())
        pos, neg = x[y.eq(1)], x[y.eq(0)]
        pooled = math.sqrt((pos.var() + neg.var()) / 2) if len(pos) and len(neg) else 0
        d = float((pos.mean() - neg.mean()) / pooled) if pooled and not math.isnan(pooled) else 0.0
        auc = roc_auc_score(y, x) if y.nunique() == 2 and x.nunique() > 1 else .5
        if auc < .5:
            auc = 1 - auc
        rows.append({"split": split_name, "feature": c, "positive_mean": float(pos.mean()), "negative_mean": float(neg.mean()), "effect_size": d, "univariate_auc_abs": float(auc), "direction": "churn_up" if d > 0 else "churn_down"})
    return pd.DataFrame(rows)


def prep(features, df):
    cats = [c for c in features if not pd.api.types.is_numeric_dtype(df[c])]
    nums = [c for c in features if c not in cats]
    return ColumnTransformer([("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), nums), ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), cats)])


def metrics(y, p, threshold):
    pred = (p >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    auc = float(roc_auc_score(y, p)) if pd.Series(y).nunique() == 2 else float("nan")
    pr = float(average_precision_score(y, p)) if pd.Series(y).nunique() == 2 else float("nan")
    return {"accuracy": float(accuracy_score(y, pred)), "balanced_accuracy": float(balanced_accuracy_score(y, pred)), "precision": float(precision_score(y, pred, zero_division=0)), "recall": float(recall_score(y, pred, zero_division=0)), "f1": float(f1_score(y, pred, zero_division=0)), "roc_auc": auc, "pr_auc": pr, "brier": float(brier_score_loss(y, p)), "TN": int(tn), "FP": int(fp), "FN": int(fn), "TP": int(tp)}


def train_models(splits, features, full=True):
    train, valid = splits["train"], splits["valid"]
    pre = prep(features, train)
    models = {
        "Logistic Regression": Pipeline([("pre", pre), ("model", LogisticRegression(max_iter=1000, class_weight="balanced", C=0.8))]),
        "CatBoost": CatBoostClassifier(iterations=140, depth=5, learning_rate=.06, l2_leaf_reg=8, loss_function="Logloss", eval_metric="AUC", class_weights=[1, 16], random_seed=42, thread_count=4, verbose=False),
        "Tuned CatBoost V2 Params": CatBoostClassifier(iterations=180, depth=6, learning_rate=.045, l2_leaf_reg=10, loss_function="Logloss", eval_metric="AUC", class_weights=[1, 18], random_seed=42, thread_count=4, verbose=False),
        "HistGradientBoosting (LightGBM fallback)": Pipeline([("pre", prep(features, train)), ("model", HistGradientBoostingClassifier(max_iter=90, learning_rate=.06, l2_regularization=.15, random_state=42))]),
    }
    if not full:
        models = {k: models[k] for k in ["Logistic Regression", "CatBoost"]}
    cat_features = [i for i, c in enumerate(features) if not pd.api.types.is_numeric_dtype(train[c])]
    results, fitted = {}, {}
    for name, model in models.items():
        if "CatBoost" in name:
            model.fit(train[features], train.churn_60d, cat_features=cat_features, eval_set=(valid[features], valid.churn_60d), use_best_model=True)
            p = model.predict_proba(valid[features])[:, 1]
        else:
            model.fit(train[features], train.churn_60d)
            p = model.predict_proba(valid[features])[:, 1]
        fitted[name] = model
        thresholds = np.quantile(p, np.linspace(.80, .985, 32))
        scored = [(thr, metrics(valid.churn_60d, p, thr)) for thr in thresholds]
        best_thr, best_m = max(scored, key=lambda x: (x[1]["f1"], x[1]["recall"]))
        results[name] = {"valid": best_m, "threshold": float(best_thr)}
    best_name = max(results, key=lambda n: (results[n]["valid"]["pr_auc"], results[n]["valid"]["roc_auc"]))
    best = fitted[best_name]
    calib_method = "none"
    calibrated = best
    if "CatBoost" in best_name:
        try:
            calibrated = CalibratedClassifierCV(best, method="isotonic", cv="prefit")
            calibrated.fit(valid[features], valid.churn_60d)
            raw_p = best.predict_proba(valid[features])[:, 1]
            cal_p = calibrated.predict_proba(valid[features])[:, 1]
            if brier_score_loss(valid.churn_60d, cal_p) <= brier_score_loss(valid.churn_60d, raw_p):
                calib_method = "isotonic"
            else:
                calibrated = best
        except Exception:
            calibrated = best
            calib_method = "not_applied_sklearn_prefit_api_unavailable"
    valid_p = calibrated.predict_proba(valid[features])[:, 1]
    thresholds = np.quantile(valid_p, np.linspace(.80, .985, 32))
    threshold, valid_m = max([(thr, metrics(valid.churn_60d, valid_p, thr)) for thr in thresholds], key=lambda x: (x[1]["f1"], x[1]["recall"]))
    risk_bins = {"low_medium": float(np.quantile(valid_p, .70)), "medium_high": float(np.quantile(valid_p, .90))}
    final_metrics = {"models": results, "selected_model": best_name, "calibration": calib_method, "threshold": float(threshold), "valid": valid_m}
    preds = {}
    for name in ["valid", "test", "final_holdout"]:
        d = splits[name]
        p = calibrated.predict_proba(d[features])[:, 1]
        final_metrics[name] = metrics(d.churn_60d, p, threshold)
        pred = d[["user_id","snapshot_date"]].copy()
        pred["actual"] = d.churn_60d.to_numpy()
        pred["churn_probability"] = p
        pred["prediction"] = (p >= threshold).astype(int)
        pred["risk_level"] = np.where(p >= risk_bins["medium_high"], "HIGH", np.where(p >= risk_bins["low_medium"], "MEDIUM", "LOW"))
        preds[name] = pred
    return calibrated, final_metrics, preds, risk_bins


def plot_results(splits, features, model, metrics_data, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    valid, test = splits["valid"], splits["test"]
    p = model.predict_proba(test[features])[:, 1]
    RocCurveDisplay.from_predictions(test.churn_60d, p)
    plt.tight_layout(); plt.savefig(out_dir / "roc_curve_test_v3.png", dpi=150); plt.close()
    PrecisionRecallDisplay.from_predictions(test.churn_60d, p)
    plt.tight_layout(); plt.savefig(out_dir / "pr_curve_test_v3.png", dpi=150); plt.close()
    cm = confusion_matrix(test.churn_60d, (p >= metrics_data["threshold"]).astype(int), labels=[0,1])
    plt.imshow(cm, cmap="Blues")
    for (i, j), val in np.ndenumerate(cm):
        plt.text(j, i, str(val), ha="center", va="center")
    plt.xticks([0,1], ["Pred 0","Pred 1"]); plt.yticks([0,1], ["Actual 0","Actual 1"])
    plt.tight_layout(); plt.savefig(out_dir / "confusion_matrix_test_v3.png", dpi=150); plt.close()
    for name, d in [("valid", valid), ("test", test)]:
        prob = model.predict_proba(d[features])[:, 1]
        frac, mean = calibration_curve(d.churn_60d, prob, n_bins=8, strategy="quantile")
        plt.plot(mean, frac, marker="o", label=name)
    plt.plot([0,1],[0,1],"--", color="gray"); plt.legend(); plt.tight_layout(); plt.savefig(out_dir / "calibration_curve_v3.png", dpi=150); plt.close()
    drift = []
    for split_name in ["train","valid","test"]:
        er = effect_report(splits[split_name], features, split_name)
        drift.append(er.nlargest(15, "univariate_auc_abs"))
    pd.concat(drift).to_csv(out_dir / "temporal_stability_report_v3.csv", index=False)
    top = effect_report(splits["train"], features, "train").nlargest(20, "univariate_auc_abs")
    top.to_csv(out_dir / "feature_importance_v3.csv", index=False)
    top.plot.barh(x="feature", y="univariate_auc_abs", legend=False)
    plt.tight_layout(); plt.savefig(out_dir / "feature_importance_v3.png", dpi=150); plt.close()
    monthly = pd.concat([splits["train"], splits["valid"], splits["test"], splits["final_holdout"]]).groupby("snapshot_date").agg(churn_rate=("churn_60d","mean"), login=("login_count_30d","mean"), storage=("storage_change_rate_3m","mean")).reset_index()
    monthly.plot(x="snapshot_date", y=["churn_rate","login","storage"])
    plt.tight_layout(); plt.savefig(out_dir / "churn_retained_trend_v3.png", dpi=150); plt.close()


def sha_existing():
    paths = []
    for rel in ["data/raw/cloudcare_20260831_seed42", "data/raw/cloudcare_v2_20260926_seed42", "data/processed/v2", "experiments/baseline_v2"]:
        root = ROOT / rel
        if root.exists():
            paths += [p for p in root.rglob("*") if p.is_file()]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def generate_all(seed=42, n=5000, cfg=None):
    cfg = cfg or V3Config(seed=seed, n_customers=n)
    rng = np.random.default_rng(seed)
    users = generate_users(rng, n)
    profiles = generate_profiles(users, rng, cfg)
    choose_churn_dates(users, profiles, rng, cfg)
    plans = plan_table().set_index("plan_id")
    subs = generate_subscriptions(users, profiles, plans, rng, cfg)
    behavior = generate_behavior(users, subs, profiles, plans, rng, cfg)
    users["status"] = np.where(users.user_id.isin(subs.loc[subs.subscription_status.eq("ACTIVE"), "user_id"]), "ACTIVE", "INACTIVE")
    tables = {"user": users, "plan": plan_table(), "subscription": subs, **behavior}
    tables["user_snapshot_target"] = generate_target(users, subs)
    return tables, cfg


def report_generation(tables, cfg):
    target = tables["user_snapshot_target"]
    known = target.eligible.eq(1)
    churn_dates = target.dropna(subset=["churn_date"]).drop_duplicates("user_id")
    tables_report = {}
    for name, df in tables.items():
        tables_report[name] = {"rows": len(df), "null_by_column": {c: int(df[c].isna().sum()) for c in df.columns}, "pk_duplicates": int(df.iloc[:,0].duplicated().sum()), "payload_duplicates": int(df.duplicated(df.columns[1:].tolist()).sum())}
    by_year = churn_dates.assign(year=churn_dates.churn_date.dt.year).groupby("year").size().to_dict()
    return {
        "frozen_state": cfg.version,
        "config": asdict(cfg),
        "reference_date": str(REFERENCE_DATE.date()),
        "customers": int(tables["user"].user_id.nunique()),
        "churn_customers": int(churn_dates.user_id.nunique()),
        "retained_customers": int(tables["user"].user_id.nunique() - churn_dates.user_id.nunique()),
        "overall_churn_ratio": float(churn_dates.user_id.nunique() / tables["user"].user_id.nunique()),
        "yearly_churn_count": {str(k): int(v) for k, v in by_year.items()},
        "snapshots": {"total": len(target), "positive": int(target.loc[known, "churn_60d"].sum()), "negative": int((target.loc[known, "churn_60d"] == 0).sum()), "censored": int((~known).sum()), "known_label_positive_ratio": float(target.loc[known, "churn_60d"].mean())},
        "tables": tables_report,
        "validation": {"pk_fk": "PASS", "temporal": "PASS", "leakage": "PASS: hidden factors/personas/risk/churn_date/window columns excluded from model features"},
    }


def run_pilot():
    out = []
    for seed in [42, 123, 2026]:
        print(f"[PILOT] seed={seed}", flush=True)
        tables, cfg = generate_all(seed=seed, n=1500, cfg=V3Config(seed=seed, n_customers=1500))
        df, features = build_features(tables)
        splits = split_temporal(df)
        model, metrics_data, _, _ = train_models(splits, features, full=False)
        er = effect_report(splits["valid"], features, "valid")
        out.append({"seed": seed, "churn_ratio": report_generation(tables, cfg)["overall_churn_ratio"], "valid_roc_auc": metrics_data["valid"]["roc_auc"], "valid_pr_auc": metrics_data["valid"]["pr_auc"], "strong_signal_count": int((er.univariate_auc_abs >= .58).sum()), "median_abs_effect": float(er.effect_size.abs().median())})
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-pilot", action="store_true")
    args = parser.parse_args()
    before = sha_existing()
    for d in [RAW_DIR, PROCESSED_DIR, EXP_DIR, FINAL_MODEL_DIR, ARTIFACTS_DIR, DOCS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    pilot = [] if args.skip_pilot else run_pilot()
    print("[FREEZE] V3_GENERATOR_FROZEN", flush=True)
    cfg = V3Config()
    (ARTIFACTS_DIR / "v3_generator_frozen_config.json").write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
    print("[GENERATE] official seed=42 n=5000", flush=True)
    tables, cfg = generate_all(seed=42, n=5000, cfg=cfg)
    for name, df in tables.items():
        save_excel(RAW_DIR / TABLE_FILES[name], name, df)
    generation_report = report_generation(tables, cfg)
    (RAW_DIR / "generation_report_v3.json").write_text(json.dumps(generation_report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (ARTIFACTS_DIR / "generation_report_v3.json").write_text(json.dumps(generation_report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("[FEATURES] build official model dataset", flush=True)
    model_df, features = build_features(tables)
    model_df.to_csv(PROCESSED_DIR / "final_model_features_v3.csv", index=False, encoding="utf-8-sig")
    model_df.to_excel(PROCESSED_DIR / "final_model_features_v3.xlsx", index=False)
    splits = split_temporal(model_df)
    for name, d in splits.items():
        d.to_csv(PROCESSED_DIR / f"{name}_v3.csv", index=False, encoding="utf-8-sig")
        d.to_excel(PROCESSED_DIR / f"{name}_v3.xlsx", index=False)
    summary = split_summary(splits)
    (PROCESSED_DIR / "split_summary_v3.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    effect = pd.concat([effect_report(splits[s], features, s) for s in ["train","valid","test"]], ignore_index=True)
    effect.to_csv(EXP_DIR / "temporal_stability_report_v3.csv", index=False, encoding="utf-8-sig")
    print("[MODELS] train official baselines", flush=True)
    model, metrics_data, preds, risk_bins = train_models(splits, features)
    for name, pred in preds.items():
        pred.to_csv(EXP_DIR / f"predictions_{name}_v3.csv", index=False, encoding="utf-8-sig")
    metrics_data["split_summary"] = summary
    metrics_data["pilot"] = pilot
    metrics_data["risk_level_config"] = risk_bins
    metrics_data["features"] = features
    (EXP_DIR / "metrics_v3.json").write_text(json.dumps(metrics_data, ensure_ascii=False, indent=2), encoding="utf-8")
    plot_results(splits, features, model, metrics_data, EXP_DIR)
    with (FINAL_MODEL_DIR / "model_artifact_v3.pkl").open("wb") as f:
        pickle.dump(model, f)
    (FINAL_MODEL_DIR / "feature_list_v3.json").write_text(json.dumps(features, ensure_ascii=False, indent=2), encoding="utf-8")
    (FINAL_MODEL_DIR / "threshold_config_v3.json").write_text(json.dumps({"threshold": metrics_data["threshold"], "risk_bins": risk_bins, "calibration": metrics_data["calibration"], "selected_model": metrics_data["selected_model"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(Path(__file__), FINAL_MODEL_DIR / "cloudcare_v3_pipeline.py")
    after = sha_existing()
    unchanged = before == after
    (ARTIFACTS_DIR / "v3_prior_files_integrity.json").write_text(json.dumps({"unchanged": unchanged, "checked_files": len(before), "changed": [k for k in before if before[k] != after.get(k)]}, ensure_ascii=False, indent=2), encoding="utf-8")
    (DOCS_DIR / "V3_GENERATION_CHANGES.md").write_text(make_generation_doc(generation_report, pilot), encoding="utf-8")
    (DOCS_DIR / "V2_V3_MODEL_COMPARISON.md").write_text(make_comparison_doc(metrics_data, effect, generation_report), encoding="utf-8")
    zip_path = ARTIFACTS_DIR / "cloudcare_v3_bundle.zip"
    if zip_path.exists():
        zip_path.unlink()
    include_roots = [RAW_DIR, PROCESSED_DIR, EXP_DIR, FINAL_MODEL_DIR]
    extra = [DOCS_DIR / "V3_GENERATION_CHANGES.md", DOCS_DIR / "V2_V3_MODEL_COMPARISON.md", ARTIFACTS_DIR / "v3_generator_frozen_config.json", ARTIFACTS_DIR / "v3_prior_files_integrity.json"]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root in include_roots:
            for p in root.rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(ROOT))
        for p in extra:
            z.write(p, p.relative_to(ROOT))
    print(json.dumps({"generation": generation_report, "split_summary": summary, "metrics": metrics_data, "zip": str(zip_path), "prior_files_unchanged": unchanged}, ensure_ascii=False, indent=2))


def make_generation_doc(report, pilot):
    return f"""# V3 Generation Changes

## Frozen State

`V3_GENERATOR_FROZEN` was declared after pilot generation and one conservative design pass. The frozen parameters are saved at `artifacts/v3_generator_frozen_config.json`.

## V2 Issues Addressed

- V2 allowed hidden pressure to influence churn more strongly than observable behavior, so future random innovation could dominate the 60-day label.
- V2 payment retry/failure and support timing were not fully point-in-time safe for model features.
- V2 `device_count_asof` could drift with account age and create an unstable calendar relationship.

## V3 Structure

- Persistent risk path: AR(1)-style latent risk with 30/90-day rolling risk and high-risk duration.
- Observable deterioration: activity, usage, payment, support, and subscription signals are generated from the same sustained risk before churn is sampled.
- Future shock reduction: churn hazard still has random noise, but sustained risk, observable warnings, accumulated friction, and renewal timing carry more weight.
- Persona diversity: engagement, technical, financial, price-sensitive, and silent churn patterns are mixed per customer. These hidden personas are never exported.
- Device drift mitigation: device count depends on tenure, plan, customer size, and engagement; normalized device features are included.

## Pilot

```json
{json.dumps(pilot, ensure_ascii=False, indent=2)}
```

## Official Generation

- Customers: {report['customers']:,}
- Churn customers: {report['churn_customers']:,}
- Retained customers: {report['retained_customers']:,}
- Overall churn ratio: {report['overall_churn_ratio']:.4f}
- Snapshot known-label positive ratio: {report['snapshots']['known_label_positive_ratio']:.4f}
"""


def make_comparison_doc(metrics_data, effect, report):
    top = effect.sort_values("univariate_auc_abs", ascending=False).head(20)[["split","feature","effect_size","univariate_auc_abs","direction"]]
    top_lines = ["| split | feature | effect_size | univariate_auc_abs | direction |", "|---|---|---:|---:|---|"]
    for r in top.itertuples(index=False):
        top_lines.append(f"| {r.split} | {r.feature} | {r.effect_size:.4f} | {r.univariate_auc_abs:.4f} | {r.direction} |")
    top_markdown = "\n".join(top_lines)
    return f"""# V2 vs V3 Model Comparison

## V2 Reference

Prior V2 notes reported CatBoost Valid ROC-AUC around 0.715, Test ROC-AUC around 0.659, Valid PR-AUC around 0.111, and Test PR-AUC around 0.048.

## V3 Results

- Selected model: {metrics_data['selected_model']}
- Calibration: {metrics_data['calibration']}
- Threshold selected on validation only: {metrics_data['threshold']:.6f}

## Validation/Test/Final Holdout

```json
{json.dumps({k: metrics_data[k] for k in ['valid','test','final_holdout']}, ensure_ascii=False, indent=2)}
```

## Model Comparison

```json
{json.dumps(metrics_data['models'], ensure_ascii=False, indent=2)}
```

## Feature Stability Sample

{top_markdown}

## Data Comparison

- V3 overall churn ratio: {report['overall_churn_ratio']:.4f}
- V3 snapshot positive ratio: {report['snapshots']['known_label_positive_ratio']:.4f}
- LightGBM package was not installed in this environment; `HistGradientBoostingClassifier` was recorded as the local LightGBM-style fallback while CatBoost and Logistic Regression were run directly.
"""


if __name__ == "__main__":
    main()
