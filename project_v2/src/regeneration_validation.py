"""Independent acceptance checks for the ten-table synthetic refresh."""
import calendar
import numpy as np
import pandas as pd
from src.snapshot_target import generate, same_data, validate_target

HIDDEN = {'satisfaction','satisfaction_score','engagement','engagement_score',
          'financial_risk','technical_friction','competitor_intent','churn_probability',
          'pressure','response','hazard','price_sensitivity','usage_growth','declining'}

def validate_dataset(t, cutoff):
    from scripts.generate_cloudcare_raw_data import validate_primary_keys, validate_foreign_keys, validate_business_rules
    raw={n:f for n,f in t.items() if n!='user_snapshot_target'}
    validate_primary_keys(t); validate_foreign_keys(t); validate_business_rules(raw)
    assert len(t)==10 and len(t['user'])==5000
    for name,df in t.items():
        assert not (set(df)&HIDDEN), name
        for col in df.select_dtypes(include='number'):
            assert df[col].dropna().ge(0).all(), (name,col,'negative')
    users=t['user'].set_index('user_id'); subs=t['subscription']
    final=subs.sort_values('start_date').groupby('user_id').tail(1).set_index('user_id')
    churn=final.end_date.dropna()
    limit=final.end_date.fillna(cutoff)
    assert set(final.index)==set(users.index)
    assert users.status.eq('INACTIVE').equals(users.index.to_series().isin(churn.index).rename('status'))
    for name,col in [('user_activity_daily','activity_date'),('storage_usage_monthly','created_at'),
                     ('device','registered_at'),('device','last_sync_at'),('support_ticket','created_at')]:
        df=t[name]; valid=df[col].notna()
        assert df.loc[valid,col].dt.normalize().le(df.loc[valid,'user_id'].map(limit)).all(), (name,col,'post churn')
        assert df.loc[valid,col].ge(df.loc[valid,'user_id'].map(users.signup_date)).all(), (name,col,'pre signup')
    snap=validate_target(t['user_snapshot_target'],cutoff)
    same_data(snap,generate(t['user'],subs,cutoff,cutoff))
    annual=[]
    for year in range(users.signup_date.min().year,cutoff.year+1):
        start=pd.Timestamp(year,1,1); end=min(pd.Timestamp(year,12,31),cutoff)
        entry=users.signup_date.clip(lower=start)
        finish=limit.reindex(users.index).clip(upper=end)
        exposure=((finish-entry).dt.days+1).clip(lower=0).sum()/(366 if calendar.isleap(year) else 365)
        count=int(churn.dt.year.eq(year).sum()); rate=float(-np.expm1(-count/exposure))
        opening=users.index[(users.signup_date<start)&limit.reindex(users.index).ge(start)]
        opening_lost=int(churn.reindex(opening).between(start,end).sum())
        annual.append(dict(year=year,churn_customers=count,customer_years=float(exposure),
                           annual_rate=rate,opening_customers=len(opening),opening_churn=opening_lost,
                           opening_observed_rate=opening_lost/len(opening) if len(opening) else None,
                           status='PASS' if .12<=rate<=.15 else 'FAIL'))
    assert all(r['status']=='PASS' for r in annual), annual
    monthly=churn.dt.to_period('M').value_counts().sort_index()
    assert (churn-users.signup_date.reindex(churn.index)).dt.days.lt(7).mean()<.05
    assert churn.value_counts().max()/len(churn)<.02, 'Churn date concentration'
    for year in monthly.index.year.unique():
        assert monthly[monthly.index.year==year].max()/monthly[monthly.index.year==year].sum()<.3
    known=snap[snap.eligible.eq(1)]
    by_date=[]
    for date,group in snap.groupby('snapshot_date'):
        labels=group.churn_60d.dropna()
        by_date.append(dict(snapshot_date=str(date.date()),rows=len(group),negative=int(labels.eq(0).sum()),
                            positive=int(labels.eq(1).sum()),censored=int(group.churn_60d.isna().sum()),
                            positive_ratio=float(labels.mean()) if len(labels) else None))
    # Diagnostic only: a 60-day label naturally has much lower prevalence than annual churn.
    return dict(customers=len(users),churn_customers=len(churn),non_churn_customers=len(users)-len(churn),
                overall_churn_ratio=len(churn)/len(users),annual=annual,
                churn_by_month={str(k):int(v) for k,v in monthly.items()},
                snapshots=dict(total=len(snap),negative=int(known.churn_60d.eq(0).sum()),
                               positive=int(known.churn_60d.eq(1).sum()),censored=int(snap.eligible.eq(0).sum()),
                               positive_ratio=float(known.churn_60d.mean()),
                               positive_ratio_all=float(snap.churn_60d.eq(1).fillna(False).mean()),by_date=by_date))

def temporal_feature_check(t):
    """Validate existing feature code only; no EDA, fitting, or feature export."""
    from src.eda_features import build_features, clean_sources
    from src.schema import SPECS
    raw,_=clean_sources({n:t[n] for n in SPECS},SPECS)
    keys=t['user_snapshot_target'].loc[lambda f:f.eligible.eq(1),['user_id','snapshot_date']]
    keys=keys.groupby('snapshot_date',group_keys=False).head(4).reset_index(drop=True)
    features,audit=build_features(keys,raw)
    activity=raw['user_activity_daily']
    for row in features.itertuples(index=False):
        for days in (30,60,90):
            available=activity.activity_date+pd.Timedelta(days=1)
            chosen=activity[(activity.user_id==row.user_id)&available.le(row.snapshot_date)&
                            available.gt(row.snapshot_date-pd.Timedelta(days=days))]
            assert getattr(row,f'active_days_{days}d')==chosen.activity_date.nunique()
    assert not (set(features)&(HIDDEN|{'churn_date','churn_60d','eligible','label_window_end','status'}))
    return {'keys_checked':len(keys),'window_checks':len(keys)*3,'availability_checks':len(audit),'status':'PASS'}

def behavior_check(t,cutoff):
    """Generation acceptance diagnostics only; no EDA or statistical tests.

    Controls are survivors matched with replacement to calendar exit dates. Only users
    with 90 days of prior observation enter this diagnostic (no rows deleted).
    """
    from src.eda_features import clean_sources
    from src.schema import SPECS
    raw,_=clean_sources({n:t[n] for n in SPECS},SPECS)
    users=raw['user'].set_index('user_id')
    final=raw['subscription'].sort_values('start_date').groupby('user_id').tail(1).set_index('user_id')
    exits=final.end_date.dropna()
    activity={uid:g for uid,g in raw['user_activity_daily'].groupby('user_id')}
    payment=raw['payment_history'].merge(raw['subscription'][['subscription_id','user_id']],on='subscription_id')
    payments={uid:g for uid,g in payment.groupby('user_id')}
    support={uid:g for uid,g in raw['support_ticket'].groupby('user_id')}
    events={uid:g for uid,g in raw['subscription_event'].groupby('user_id')}
    values={'churn':[],'retained':[]}; survivors=final.index[final.end_date.isna()]
    for uid,end in exits.items():
        if (end-users.loc[uid,'signup_date']).days<90: continue
        possible=survivors[users.signup_date.reindex(survivors).le(end-pd.Timedelta(days=90))]
        if not len(possible): continue
        control=possible[int(uid)%len(possible)]
        for group,who in [('churn',uid),('retained',control)]:
            a=activity.get(who)
            def count(frame,col,days=30,offset=0):
                if frame is None: return frame
                right=end-pd.Timedelta(days=offset); left=right-pd.Timedelta(days=days)
                return frame[frame[col].gt(left)&frame[col].le(right)]
            recent=count(a,'activity_date'); previous=count(a,'activity_date',60,30)
            now=0 if recent is None else float(recent.login_count.sum())
            before=0 if previous is None else float(previous.login_count.sum())/2
            p=count(payments.get(who),'payment_date',90)
            s=count(support.get(who),'created_at',90)
            e=count(events.get(who),'event_date',90)
            values[group].append(dict(login_recent=now,login_prior_month=before,declining=now<before,
                                      failed_payment=p is not None and p.payment_status.eq('FAILED').any(),
                                      support=s is not None and len(s)>0,
                                      downgrade=e is not None and e.event_type.eq('DOWNGRADE').any()))
    output={}
    for group,rows in values.items():
        frame=pd.DataFrame(rows)
        output[group]={'matched_observations':len(frame),**{c:float(frame[c].mean()) for c in frame}}
        assert 0<output[group]['declining']<1, 'Behavior groups must overlap'
        assert 0<output[group]['failed_payment']<1
        assert 0<output[group]['support']<1
        assert 0<output[group]['downgrade']<1
    output['status']='PASS'
    return output
