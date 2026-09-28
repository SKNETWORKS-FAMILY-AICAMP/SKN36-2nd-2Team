"""User-level retrospective targets, never a feature table; Excel is read-only."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from src.schema import ROOT, SPECS
from src.validation import validate_frame

CSV_PATH = ROOT / 'data/processed/user_snapshot_target.csv'
COLUMNS = ['snapshot_id','user_id','snapshot_date','label_window_end','churn_date',
           'churn_60d','active_subscription_count','eligible','created_at']
DATE_COLUMNS = ['snapshot_date','label_window_end','churn_date']

def read_inputs():
    frames = {}
    for name in ['user','subscription']:
        spec = SPECS[name]
        path = ROOT / spec['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != spec['sha256']:
            raise ValueError(f'{name}: source differs from frozen raw inventory')
        frames[name] = validate_frame(name, pd.read_excel(path, sheet_name=spec['sheet'],
                         engine='openpyxl', keep_default_na=False, na_values=['']))
    report = ROOT / Path(SPECS['user']['file']).parent / 'generation_report.json'
    observation_end = pd.Timestamp(json.loads(report.read_text(encoding='utf-8'))['reference_date'])
    # The generation manifest defines completeness, not scheduled next_billing_date.
    # Verify its cutoff is also present in the actual source metadata.
    if frames['user'].updated_at.max().normalize() != observation_end:
        raise ValueError('Manifest reference_date and user.updated_at observation endpoint disagree')
    return frames['user'], frames['subscription'], observation_end

def generate(users, subscriptions, observation_end, created_at=None):
    cutoff = pd.Timestamp(observation_end).normalize()
    u = users.copy(); s = subscriptions.copy()
    u['signup_date'] = pd.to_datetime(u.signup_date)
    for col in ['start_date','end_date']: s[col] = pd.to_datetime(s[col])
    if u.user_id.isna().any() or u.user_id.duplicated().any(): raise ValueError('Invalid user PK')
    if s.subscription_id.isna().any() or s.subscription_id.duplicated().any(): raise ValueError('Invalid subscription PK')
    if not s.user_id.isin(u.user_id).all(): raise ValueError('Subscription user FK missing')
    signup = u.set_index('user_id').signup_date
    if s.start_date.isna().any() or (s.start_date<s.user_id.map(signup)).any() or (s.end_date<s.start_date).any():
        raise ValueError('Invalid subscription dates')
    if (s.start_date>cutoff).any(): raise ValueError('Future subscription start beyond observation endpoint')
    if ((s.subscription_status.eq('ACTIVE') & s.end_date.notna()) |
        (~s.subscription_status.eq('ACTIVE') & s.end_date.isna())).any():
        raise ValueError('Subscription status/end_date contradiction')
    dates = pd.date_range(u.signup_date.min().to_period('M').start_time, cutoff, freq='ME')
    churn = {}
    for uid, history in s.groupby('user_id'):
        # Inspect ALL observed history, not a single ended period or only a snapshot.
        if history.end_date.notna().all() and history.end_date.max() <= cutoff:
            churn[uid] = history.end_date.max()
    rows=[]
    for snapshot in dates:
        active=s[(s.start_date<=snapshot)&(s.end_date.isna()|(s.end_date>=snapshot))]
        counts=active.groupby('user_id').size()
        window=snapshot+pd.Timedelta(days=60)
        eligible=int(window<=cutoff)
        for uid,count in counts.items():
            end=churn.get(uid,pd.NaT)
            # End dates are inclusive. Final exit on this month-end is already
            # complete at the snapshot boundary, so it is not a future risk row.
            if pd.notna(end) and end<=snapshot: continue
            label=int(pd.notna(end) and snapshot<end<=window) if eligible else pd.NA
            rows.append([len(rows)+1,int(uid),snapshot,window,end,label,int(count),eligible,
                         created_at or datetime.now(timezone.utc).replace(tzinfo=None,microsecond=0)])
    df=pd.DataFrame(rows,columns=COLUMNS)
    for col in DATE_COLUMNS+['created_at']: df[col]=pd.to_datetime(df[col])
    df['churn_60d']=df.churn_60d.astype('Int64')
    return validate_target(df,cutoff)

def validate_target(frame, cutoff):
    df=frame.copy()
    if list(df.columns)!=COLUMNS: raise ValueError('Unexpected snapshot CSV columns')
    for col in DATE_COLUMNS+['created_at']:
        df[col]=pd.to_datetime(df[col],errors='raise')
    required=[c for c in COLUMNS if c not in ['churn_date','churn_60d']]
    if df[required].isna().any().any(): raise ValueError('Required target NULL')
    for col in ['snapshot_id','user_id','active_subscription_count','eligible','churn_60d']:
        n=pd.to_numeric(df[col],errors='raise')
        if (n.dropna()%1!=0).any(): raise ValueError(f'{col}: non-integral value')
        df[col]=n.astype('Int64')
    if df.snapshot_id.duplicated().any() or df.duplicated(['user_id','snapshot_date']).any():
        raise ValueError('Duplicate snapshot PK or user/month')
    if (df.snapshot_id<=0).any() or (df.active_subscription_count<=0).any(): raise ValueError('Invalid target count/ID')
    if not df.snapshot_date.dt.is_month_end.all(): raise ValueError('Snapshot not month-end')
    for col in DATE_COLUMNS:
        if (df[col].dropna()!=df[col].dropna().dt.normalize()).any(): raise ValueError(f'{col}: DATE contains time')
    if not df.label_window_end.eq(df.snapshot_date+pd.Timedelta(days=60)).all(): raise ValueError('Invalid 60-day window')
    if (df.snapshot_date>cutoff).any() or (df.churn_date.dropna()>cutoff).any(): raise ValueError('Beyond observed period')
    if not df.eligible.eq((df.label_window_end<=cutoff).astype(int)).all(): raise ValueError('Invalid eligibility')
    if (df.churn_date.notna()&(df.churn_date<=df.snapshot_date)).any(): raise ValueError('Already churned snapshot')
    known=df.eligible.eq(1)
    expected=(df.churn_date>df.snapshot_date)&(df.churn_date<=df.label_window_end)
    if df.loc[~known,'churn_60d'].notna().any() or df.loc[known,'churn_60d'].isna().any(): raise ValueError('Censored label must be NULL; eligible label required')
    if not df.loc[known,'churn_60d'].eq(expected.loc[known].astype(int)).all(): raise ValueError('Incorrect label')
    return df

def read_csv(path, cutoff):
    return validate_target(pd.read_csv(path,encoding='utf-8-sig'),cutoff)

def same_data(actual, expected):
    cols=[c for c in COLUMNS if c!='created_at']
    try:
        pd.testing.assert_frame_equal(actual[cols].sort_values('snapshot_id').reset_index(drop=True),
            expected[cols].sort_values('snapshot_id').reset_index(drop=True),check_dtype=False)
    except AssertionError as exc: raise ValueError('CSV/DB content differs from current source-derived target') from exc

def create_csv(path=CSV_PATH):
    path=Path(path)
    if path.exists():
        print(f'[SKIP] {path.name} already exists.',flush=True)
        return path
    users,subs,cutoff=read_inputs()
    now=datetime.now(timezone.utc).replace(tzinfo=None,microsecond=0)
    df=generate(users,subs,cutoff,now)
    output=df.copy()
    for col in DATE_COLUMNS: output[col]=output[col].dt.strftime('%Y-%m-%d').where(output[col].notna(),'')
    output.created_at=output.created_at.dt.strftime('%Y-%m-%d %H:%M:%S')
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists(): print(f'[SKIP] {path.name} already exists.'); return path
    try:
        with path.open('x',encoding='utf-8-sig',newline='') as handle:
            output.to_csv(handle,index=False)
    except FileExistsError:
        print(f'[SKIP] {path.name} already exists.'); return path
    same_data(read_csv(path,cutoff),df)
    print(f'[CREATED] {path} - {len(df):,} rows; observation_end={cutoff.date()}',flush=True)
    return path
