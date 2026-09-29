"""Point-in-time features for the frozen CloudCare synthetic source contract.

No labels, future ends, or mutable latest-state fields are read by this module.
Notebook displays this source so calculations remain inspectable for beginners.
"""
import numpy as np
import pandas as pd


def clean_sources(tables, specs):
    """Work on copies. Only documented injected exact payload duplicates removed."""
    cleaned, audit = {}, []
    injected = {'storage_usage_monthly', 'user_activity_daily', 'payment_history', 'support_ticket'}
    for name, spec in specs.items():
        frame = tables[name].copy()
        payload = [c for c in frame if c != spec['pk']]
        full = int(frame.duplicated().sum())
        same_payload = int(frame.duplicated(payload).sum())
        # DATA_GENERATION.md and inject_quality_issues explicitly document these
        # copies. All non-PK fields must agree; merely sharing a user is not enough.
        if name in injected:
            frame = frame.drop_duplicates(payload).copy()
        else:
            frame = frame.drop_duplicates().copy()
        audit.append(dict(table=name, exact_rows=full, same_payload_new_id=same_payload,
                          removed=len(tables[name])-len(frame),
                          reason='생성 문서의 주입 중복 + PK 외 전체 값 일치' if name in injected else '전체 컬럼 동일 행만'))
        if name == 'user_activity_daily':
            # Negative counts are documented measurement errors, not inactivity.
            frame.loc[frame.login_count < 0, 'login_count'] = np.nan
        cleaned[name] = frame
    return cleaned, pd.DataFrame(audit)


def build_features(keys, tables):
    """keys contains ONLY user_id/snapshot_date. Return features and time audit.

    Snapshot boundary is midnight. A daily total becomes available next midnight.
    Monthly measurements become available at max(month end, created_at).
    Every event selector records and asserts its effective availability time.
    """
    assert list(keys.columns) == ['user_id', 'snapshot_date']
    user = tables['user'].set_index('user_id')
    plan = tables['plan'].set_index('plan_id')
    sub = tables['subscription']
    payment = tables['payment_history'].merge(sub[['subscription_id', 'user_id']],
                                             on='subscription_id', validate='many_to_one')
    activity = tables['user_activity_daily'].copy()
    activity['_available'] = activity.activity_date + pd.Timedelta(days=1)
    storage = tables['storage_usage_monthly'].copy()
    month_end = storage.usage_month + pd.offsets.MonthEnd(0)
    storage['_available'] = pd.concat([month_end, storage.created_at], axis=1).max(axis=1)
    records, audits = [], []
    for snapshot, part in keys.groupby('snapshot_date', sort=True):
        ids = pd.Index(part.user_id, name='user_id')
        out = pd.DataFrame(index=ids)

        def history(frame, date_col, source, days=None):
            # Both an event's occurrence and its availability must be in the past.
            selected = frame.loc[frame[date_col].le(snapshot) & frame.user_id.isin(ids)].copy()
            if days is not None:
                selected = selected.loc[selected[date_col].gt(snapshot-pd.Timedelta(days=days))]
            assert selected[date_col].le(snapshot).all()
            audits.append({'snapshot_date': snapshot, 'source': source,
                           'window_days': days, 'rows': len(selected),
                           'max_available_at': selected[date_col].max()})
            return selected

        def put(name, values, fill=None):
            out[name] = values.reindex(ids)
            if fill is not None:
                out[name] = out[name].fillna(fill)

        out['tenure_days'] = (snapshot-user.signup_date.reindex(ids)).dt.days
        assert out.tenure_days.ge(0).all()
        # Generator creates these once at signup; no updates occur in this frozen
        # synthetic version. Real customer data needs historical attribute tables.
        for col in ['age_group', 'region', 'signup_channel']:
            out[col] = user[col].reindex(ids)
        known_sub = history(sub, 'start_date', 'subscription')
        latest_sub = known_sub.sort_values(['start_date', 'subscription_id']).groupby('user_id').tail(1).set_index('user_id')
        # A subscription row is a continuous fixed-plan period. Eligible target
        # rows are already an active risk set; no future end_date is consulted.
        out['plan_name'] = latest_sub.plan_id.map(plan.plan_name).reindex(ids)
        for col in ['storage_limit_gb', 'monthly_price']:
            out[col] = latest_sub.plan_id.map(plan[col]).reindex(ids)
        out['billing_cycle'] = latest_sub.plan_id.map(plan.billing_cycle).reindex(ids)
        out['current_plan_tenure_days'] = (snapshot-latest_sub.start_date.reindex(ids)).dt.days

        all_activity = history(activity, '_available', 'activity')
        # A recorded event date proves activity; missing entire daily records do
        # not prove zero true activity. Count fields below are observed counts.
        put('days_since_activity', (snapshot-all_activity.groupby('user_id').activity_date.max()).dt.days)
        for days in [7, 30, 60, 90]:
            recent = history(activity, '_available', 'activity', days)
            grouped = recent.groupby('user_id')
            put(f'active_days_{days}d', grouped.activity_date.nunique(), 0)
            put(f'login_count_{days}d', grouped.login_count.sum(min_count=1))
            # Absent rows -> zero observed events; all-null measurements stay NULL.
            out.loc[~out.index.isin(recent.user_id), f'login_count_{days}d'] = 0
            if days == 30:
                put('active_minutes_30d', grouped.active_minutes.sum(min_count=1))
                out.loc[~out.index.isin(recent.user_id), 'active_minutes_30d'] = 0
                put('login_missing_records_30d', recent.assign(missing=recent.login_count.isna()).groupby('user_id').missing.sum(), 0)
        out['activity_trend_30d'] = out.login_count_30d-(out.login_count_60d-out.login_count_30d)

        known_storage = history(storage, '_available', 'storage')
        # After documented duplicate cleaning, one user-month must be unique.
        assert not known_storage.duplicated(['user_id', 'usage_month']).any()
        last_storage = known_storage.sort_values('usage_month').groupby('user_id').tail(1).set_index('user_id')
        put('storage_latest_gb', last_storage.storage_used_gb)
        put('storage_age_days', (snapshot-last_storage._available).dt.total_seconds()/86400)
        out['storage_utilization'] = out.storage_latest_gb/out.storage_limit_gb.replace(0, np.nan)
        # Exact previous completed calendar months, not arbitrary 90-day proxies.
        monthly = known_storage.loc[known_storage.usage_month.ge(snapshot.to_period('M').start_time-pd.DateOffset(months=3))]
        put('storage_mean_3m', monthly.groupby('user_id').storage_used_gb.mean())
        put('storage_observed_months_3m', monthly.groupby('user_id').storage_used_gb.count(), 0)
        months = known_storage.set_index(['user_id', 'usage_month']).storage_used_gb
        def month_values(offset):
            month = snapshot.to_period('M').start_time-pd.DateOffset(months=offset)
            return months.xs(month, level='usage_month').reindex(ids) if month in months.index.get_level_values('usage_month') else pd.Series(np.nan, index=ids)
        one, two, three = month_values(1), month_values(2), month_values(3)
        out['storage_change_1m'] = (one-two)/two.replace(0, np.nan)
        out['storage_change_3m'] = (one-three)/three.replace(0, np.nan)

        known_payment = history(payment, 'payment_date', 'payment')
        last_payment = known_payment.sort_values(['payment_date', 'payment_id']).groupby('user_id').tail(1).set_index('user_id')
        put('last_payment_amount', last_payment.amount)
        put('mean_payment_amount', known_payment.groupby('user_id').amount.mean())
        for days in [30, 90]:
            recent = history(payment, 'payment_date', 'payment', days)
            put(f'payment_records_{days}d', recent.groupby('user_id').size(), 0)
        # Status, refunds and retries lack their own state-change timestamps.
        # Do not infer that their final values were known at payment_date.

        tickets = history(tables['support_ticket'], 'created_at', 'ticket')
        for days in [30, 60, 90]:
            recent = history(tables['support_ticket'], 'created_at', 'ticket', days)
            put(f'ticket_count_{days}d', recent.groupby('user_id').size(), 0)
        put('days_since_ticket', (snapshot-tickets.groupby('user_id').created_at.max()).dt.total_seconds()/86400)
        # Synthetic generator has one resolution timestamp and no reopen timeline.
        # 'unresolved' is explicitly 'no recorded resolution by cutoff', not final status.
        resolved = history(tickets, 'resolved_at', 'ticket_resolution')
        unresolved = tickets.loc[~tickets.ticket_id.isin(resolved.ticket_id)]
        put('tickets_without_resolution_asof', unresolved.groupby('user_id').size(), 0)
        resolved['hours'] = (resolved.resolved_at-resolved.created_at).dt.total_seconds()/3600
        put('mean_resolution_hours_asof', resolved.groupby('user_id').hours.mean())

        events = history(tables['subscription_event'], 'event_date', 'subscription_event')
        changes = events.loc[events.event_type.isin(['UPGRADE', 'DOWNGRADE'])]
        put('plan_change_count', changes.groupby('user_id').size(), 0)
        put('downgrade_count', changes.loc[changes.event_type.eq('DOWNGRADE')].groupby('user_id').size(), 0)
        put('days_since_plan_change', (snapshot-changes.groupby('user_id').event_date.max()).dt.total_seconds()/86400)
        devices = history(tables['device'], 'registered_at', 'device')
        put('registered_device_count', devices.groupby('user_id').size(), 0)
        put('device_type_diversity', devices.groupby('user_id').device_type.nunique(), 0)
        out['snapshot_date'] = snapshot
        records.append(out.reset_index())
    result = pd.concat(records, ignore_index=True)
    assert not result.duplicated(['user_id', 'snapshot_date']).any()
    return result, pd.DataFrame(audits)
