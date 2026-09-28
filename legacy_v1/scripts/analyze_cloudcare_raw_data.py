"""Read existing Excel only; write a new, non-overwriting Markdown report.

All row examples are selected from pd.read_excel results. No generation module
is imported, no Excel is saved, and no model features or labels are persisted.
"""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/raw/cloudcare_20260831_seed42'
REF = pd.Timestamp('2026-08-31')
NAMES = ['user','plan','subscription','storage_usage_monthly','user_activity_daily',
         'device','payment_history','support_ticket','subscription_event']
ROLES = ['사용자 기본정보 Master','클라우드 요금제 Master','사용자별 구독 이력',
         '사용자별 월별 저장공간 로그','사용자별 일별 서비스 이용 로그',
         '등록 기기 및 동기화 상태','유료 구독 결제 처리 이력','고객 문의 및 해결 이력','구독 Lifecycle 이벤트']
FK = [('user','subscription','user_id'),('plan','subscription','plan_id'),
      ('user','storage_usage_monthly','user_id'),('user','user_activity_daily','user_id'),
      ('user','device','user_id'),('subscription','payment_history','subscription_id'),
      ('user','support_ticket','user_id'),('user','subscription_event','user_id'),
      ('subscription','subscription_event','subscription_id'),
      ('plan','subscription_event','old_plan_id'),('plan','subscription_event','new_plan_id')]
KEYS = {'user':['user_id'],'plan':['plan_name'],
 'subscription':['user_id','plan_id','start_date'],
 'storage_usage_monthly':['user_id','usage_month'],
 'user_activity_daily':['user_id','activity_date'],
 'device':['user_id','device_type','os_type','registered_at'],
 'payment_history':['subscription_id','payment_date'],
 'support_ticket':['user_id','category','created_at'],
 'subscription_event':['subscription_id','event_type','event_date','old_plan_id','new_plan_id']}
INFO = {
 'user_id':'익명 사용자 ID. 사용자별 기록을 연결하는 기준이다.',
 'signup_date':'서비스 가입일. 가입 코호트 및 관측 가능 기간의 시작이다.',
 'age_group':'연령 구간. 사용자 집단별 이용 차이를 비교한다.',
 'region':'대한민국 시·도 수준 지역. 지역별 차이 확인에 사용한다.',
 'signup_channel':'최초 가입 경로. 유입 채널과 결제수단 관계를 살핀다.',
 'status':'현재 상태. 의미와 값은 아래 분포 및 NULL 분석을 참고한다.',
 'created_at':'레코드 생성 시각. 해당 기록의 발생 시점을 파악한다.',
 'updated_at':'레코드의 마지막 갱신 시각. 상태의 갱신 기준을 파악한다.',
 'plan_id':'요금제 ID. 저장 한도·가격·결제주기를 연결한다.',
 'plan_name':'요금제 이름. 용량과 월간/연간 상품을 구별한다.',
 'storage_limit_gb':'요금제 저장 한도(GB). 사용량의 비교 기준이다.',
 'monthly_price':'월 환산 가격(원). 연간 상품 결제액은 이 값의 12배로 비교한다.',
 'billing_cycle':'MONTHLY/YEARLY 결제주기. 청구 일정과 금액 해석에 필요하다.',
 'is_paid':'유료 요금제 여부. 무료 상품의 청구 유무를 검증한다.',
 'is_active':'요금제 판매/사용 가능 상태. 사용자 구독 상태와 구별한다.',
 'subscription_id':'구독 기간 고유 ID. 한 사용자의 여러 구독 및 그 결제를 구별한다.',
 'start_date':'해당 요금제 구독 시작일. 당시 요금제와 결제 유효기간을 정한다.',
 'next_billing_date':'다음 청구 예정일. 실제 결제일이 아니며 기준일 이후가 가능하다.',
 'end_date':'구독 종료일(포함). 진행 중인 ACTIVE 구독은 NULL일 수 있다.',
 'auto_renewal':'저장된 자동갱신 설정. 종료 상태와 함께 해석해야 한다.',
 'subscription_status':'구독 상태. 진행·취소·만료 이력을 구분한다.',
 'usage_id':'월 사용량 로그 고유 ID. 같은 사용자·월의 별도 로그를 구별한다.',
 'usage_month':'월 단위 집계 키(월 1일). 해당 월 스냅샷을 연결한다.',
 'storage_used_gb':'월 스냅샷에서 사용 중인 저장공간(GB). 보관량 변화의 원천이다.',
 'file_count':'전체 보관 파일 수. 저장용량과 파일 구성의 관계를 살핀다.',
 'photo_count':'사진 파일 수. 전체 파일의 일부로 해석한다.',
 'video_count':'영상 파일 수. 사진과 합해 전체 파일 수 이하여야 한다.',
 'upload_size_gb':'해당 월 업로드 전송량(GB). 저장량 자체와는 다른 흐름 값이다.',
 'download_size_gb':'해당 월 다운로드 전송량(GB). 반복 다운로드로 저장량보다 클 수 있다.',
 'activity_id':'일별 활동 로그 고유 ID. 중복 사용자·날짜 로그를 식별한다.',
 'activity_date':'활동 발생 날짜. 관측된 활동일이며 모든 날짜가 있는 것은 아니다.',
 'login_count':'해당 날짜 로그인 횟수. 접속 빈도 확인에 사용한다.',
 'upload_count':'해당 날짜 업로드 횟수. GB 단위 전송량과 구분한다.',
 'download_count':'해당 날짜 다운로드 횟수. 이용 행동의 빈도이다.',
 'share_count':'해당 날짜 공유 횟수. 공유 기능의 이용 수준이다.',
 'preview_count':'해당 날짜 미리보기 횟수. 파일 탐색 행동을 나타낸다.',
 'active_minutes':'해당 날짜 활동시간(분). 이용 강도와 긴 세션 후보를 살핀다.',
 'device_id':'등록 기기 고유 ID. 사용자와 기기의 1:N 관계를 표현한다.',
 'device_type':'기기 형태(MOBILE/PC/TABLET). 기기별 이용 환경을 구분한다.',
 'os_type':'운영체제. 기기 형태와의 조합 및 동기화 문제를 살핀다.',
 'sync_enabled':'동기화 활성 설정. 최근 동기화 성공 여부와는 별개이다.',
 'last_sync_at':'마지막 동기화 시각. 미동기화 기기는 NULL일 수 있다.',
 'registered_at':'기기 등록 시각. 동기화 날짜 유효성과 기기 보유 기간의 기준이다.',
 'payment_id':'결제 처리 기록 고유 ID. 결제 논리적 중복과 PK를 구분한다.',
 'payment_date':'결제 처리 시각. 구독 기간·청구주기와 대조한다.',
 'amount':'결제 처리 금액(원). 상태가 FAILED/REFUNDED이면 매출로 단순 합산하면 안 된다.',
 'payment_status':'결제 처리 결과. 성공·실패·환불을 구분한다.',
 'payment_method':'결제수단. 가입 채널과 일치 여부를 확률적 관계로 살핀다.',
 'retry_count':'해당 결제 처리 과정의 재시도 횟수. 실패 반복과 처리 마찰을 살핀다.',
 'ticket_id':'고객문의 고유 ID. 새 문의와 동일 문의 로그 중복을 구분한다.',
 'category':'문의 분류. 결제·동기화·저장공간·오류 문제를 구별한다.',
 'priority':'문의 우선순위. 처리 긴급도와 해결시간 비교의 기준이다.',
 'resolved_at':'문의 해결 시각. OPEN 문의의 NULL은 정상일 수 있다.',
 'reopened':'문의 재개 여부. 동일 고객의 새 문의 건수와 구별한다.',
 'event_id':'구독 이벤트 고유 ID. 각 Lifecycle 변경을 식별한다.',
 'event_type':'구독 이벤트 유형. 업그레이드·다운그레이드·취소·갱신을 구분한다.',
 'old_plan_id':'이벤트 전 요금제 ID. 변경 방향과 이전 한도를 확인한다.',
 'new_plan_id':'이벤트 후 요금제 ID. 취소 이벤트에서는 NULL일 수 있다.',
 'event_date':'구독 이벤트 발생 시각. 구독 기간 및 결제일과 비교한다.'}
EDA = {
 'user':['가입 시점별 관측기간 차이와 신규 가입자 편향','연령·지역·가입 채널 결측의 집단별 편중','상태와 최근 활동·현재 구독의 일치 정도','유입 채널과 결제수단의 교차분포'],
 'plan':['월 환산 가격과 실제 연간 청구액의 구분','무료·유료 및 용량별 사용자 구성','동일 용량의 월간/연간 상품 비교','한도·가격 변경 이력을 담을 별도 구조의 필요성'],
 'subscription':['사용자별 구독 기간 중첩 및 전환 순서','ACTIVE 구독과 종료 이력의 분모 구분','종료 상태의 auto_renewal 해석','예정 청구일과 실제 청구의 차이','종료 이후 무료 접근 가정의 적용 범위'],
 'storage_usage_monthly':['사용자·월 중복을 먼저 확인하고 집계 규칙 결정','월 로그 부재와 셀 결측을 별도로 처리','스냅샷 날짜에 유효한 요금제와 조인','요금제 전환 전후 저장량 급변','사진·영상·전체 파일 수의 완전한 행만 관계 검사','큰 다운로드량을 반복 전송과 수집 오류 관점에서 구별'],
 'user_activity_daily':['사용자·날짜 중복으로 인한 활동량 과대 합산','로그가 없는 날의 비활동과 수집 누락 구별','음수 로그인 횟수 처리 정책','300분 이상 활동시간의 분포 및 지속성','동일 관측 길이의 최근/이전 기간 비교','업로드·공유의 0과 NULL 구별'],
 'device':['기기 유형과 OS 조합','미동기화 NULL과 수집 결측의 구분 한계','등록 기간을 고려한 오래된 동기화','활성 설정과 최근 성공 동기화의 차이','사용자당 여러 기기 집계 시 중복 조인 방지'],
 'payment_history':['동일 구독·결제일 중복의 실제 중복 여부','월간/연간 요금제별 금액 대조','FAILED·REFUNDED 금액을 매출과 분리','실패 사용자 및 구독별 반복성','결제수단 결측의 채널 편향','재시도 0인 실패 및 재시도 있는 성공 해석'],
 'support_ticket':['동일 고객의 새 문의와 로그 중복 분리','OPEN 해결일 NULL은 정상으로 보존','문의 없는 사용자를 LEFT JOIN으로 유지','재문의 여부와 새 문의 횟수를 분리','해결시간 긴 문의의 우선순위·분류 비교','반복문의 극단 고객의 관측기간 확인'],
 'subscription_event':['이벤트 유형별 old/new 요금제 방향 검증','취소 이벤트와 구독 종료 상태 일치','갱신 이벤트를 결제 성공 라벨로 사용하지 않기','변경 이벤트가 새 구독을 참조하는 방식 확인','시점 조인 및 미래 이벤트 누수 방지']}

def fmt(v):
    if v is None or pd.isna(v): return 'NULL'
    if isinstance(v,(pd.Timestamp,datetime)):
        return v.isoformat(sep=' ',timespec='milliseconds') if v.microsecond else v.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(v,(bool,np.bool_)): return 'TRUE' if v else 'FALSE'
    if isinstance(v,(int,np.integer)): return f'{int(v):,}'
    if isinstance(v,(float,np.floating)): return f'{v:,.4f}'.rstrip('0').rstrip('.')
    return str(v).replace('|','\\|').replace('\n',' ')

def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+
                     ['| '+' | '.join(fmt(x) for x in row)+' |' for row in rows])+'\n'

def fingerprint(path):
    stat=path.stat()
    return {'bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def unique_path(folder,stem,suffix):
    path=folder/(stem+suffix); i=2
    while path.exists(): path=folder/f'{stem}_{i}{suffix}'; i+=1
    return path

def main():
    paths={n:SOURCE/f'5.{i}_{n}.xlsx' for i,n in enumerate(NAMES,1)}
    assert all(p.is_file() for p in paths.values()), 'Missing source workbook'
    before={n:fingerprint(p) for n,p in paths.items()}
    t={}; sheets={}
    for n,path in paths.items():
        with pd.ExcelFile(path,engine='openpyxl') as book:
            sheets[n]=book.sheet_names
            assert len(book.sheet_names)==1 and book.sheet_names[0]==n
            t[n]=pd.read_excel(book,sheet_name=n)
        print(f'[READ] {path.name}: {len(t[n]):,} rows, {len(t[n].columns)} columns',flush=True)
    print('[ANALYZE] actual distributions, examples, temporal joins and business rules',flush=True)
    u=t['user']; s=t['subscription']; pl=t['plan']; st=t['storage_usage_monthly']; a=t['user_activity_daily']
    d=t['device']; p=t['payment_history']; q=t['support_ticket']; e=t['subscription_event']
    users=u.set_index('user_id'); plans=pl.set_index('plan_id')
    duplicates={}
    for n,df in t.items():
        keys=KEYS[n]
        duplicates[n]={'pk_null':int(df.iloc[:,0].isna().sum()),'pk_extra':int(df.iloc[:,0].duplicated().sum()),
            'full_extra':int(df.duplicated().sum()),'logical_extra':int(df.duplicated(keys).sum()),
            'logical_involved':int(df.duplicated(keys,keep=False).sum()),
            'payload_extra':int(df.duplicated(list(df.columns[1:])).sum())}
    fkrows=[]
    for parent,child,col in FK:
        target=t[parent].iloc[:,0]
        fkrows.append([parent,child,col,int((t[child][col].notna()&~t[child][col].isin(target)).sum()),int(t[child][col].isna().sum())])
    checks=[]; suspects=[]
    def check(name,bad,valid=None):
        count=int(bad.sum()) if isinstance(bad,pd.Series) else int(bad)
        checks.append([name,count,'전체 적용 행' if valid is None else int(valid)])
        return count
    check('구독 시작일 < 가입일',s.start_date<s.user_id.map(users.signup_date),len(s))
    check('구독 종료일 < 시작일',s.end_date<s.start_date,s.end_date.notna().sum())
    check('ACTIVE 구독에 종료일 존재',(s.subscription_status=='ACTIVE')&s.end_date.notna())
    check('종료 구독에 종료일 없음',(s.subscription_status!='ACTIVE')&s.end_date.isna())
    check('유료 ACTIVE 구독의 다음 결제일 없음',(s.subscription_status=='ACTIVE')&(s.plan_id!=1)&s.next_billing_date.isna())
    check('기기 마지막 동기화 < 등록',d.last_sync_at<d.registered_at,d.last_sync_at.notna().sum())
    check('기기 등록 < 가입',d.registered_at<d.user_id.map(users.signup_date))
    check('문의 해결 < 생성',q.resolved_at<q.created_at,q.resolved_at.notna().sum())
    check('OPEN 문의에 해결일 존재',(q.status=='OPEN')&q.resolved_at.notna())
    check('RESOLVED 문의 해결일 없음',(q.status=='RESOLVED')&q.resolved_at.isna())
    check('문의 생성 < 가입',q.created_at<q.user_id.map(users.signup_date))
    check('활동일 < 가입일',a.activity_date<a.user_id.map(users.signup_date))
    check('월 로그 생성 < 가입일',st.created_at<st.user_id.map(users.signup_date))
    validcounts=st[['photo_count','video_count','file_count']].notna().all(axis=1)
    check('사진+영상 > 전체 파일',validcounts&(st.photo_count+st.video_count>st.file_count),validcounts.sum())
    check('월 키가 해당 월 1일이 아님',st.usage_month.dt.day!=1)
    allowed={'MOBILE':['IOS','ANDROID'],'TABLET':['IOS','ANDROID'],'PC':['WINDOWS','MACOS']}
    bad_os=d.os_type.notna()&pd.Series([os not in allowed.get(kind,[]) for kind,os in zip(d.device_type,d.os_type)],index=d.index)
    check('기기 유형과 OS 조합 불일치',bad_os,d.os_type.notna().sum())
    seq=s.sort_values(['user_id','start_date'])
    prevend=seq.groupby('user_id').end_date.shift(); prevstart=seq.groupby('user_id').start_date.shift()
    check('사용자별 구독 기간 중첩',prevstart.notna()&(prevend.isna()|(prevend>=seq.start_date)))
    pj=p.merge(s[['subscription_id','user_id','plan_id','start_date','end_date']],on='subscription_id',how='left',validate='many_to_one')
    expected=pj.plan_id.map(plans.monthly_price)*pj.plan_id.map(plans.billing_cycle).map({'MONTHLY':1,'YEARLY':12})
    mismatch=(pj.amount-expected).abs()>.005
    check('FREE 요금제에 결제 존재',pj.plan_id.map(plans.is_paid)==False)
    check('결제일이 구독 기간 밖', (pj.payment_date.dt.normalize()<pj.start_date)|(pj.payment_date.dt.normalize()>pj.end_date.fillna(REF)))
    ej=e.merge(s[['subscription_id','user_id','plan_id','start_date','end_date','subscription_status']],on='subscription_id',how='left',suffixes=('','_sub'),validate='many_to_one')
    check('이벤트 사용자와 구독 사용자 불일치',ej.user_id!=ej.user_id_sub)
    check('이벤트가 구독 기간 밖',(ej.event_date.dt.normalize()<ej.start_date)|(ej.event_date.dt.normalize()>ej.end_date.fillna(REF)))
    oldcap=ej.old_plan_id.map(plans.storage_limit_gb); newcap=ej.new_plan_id.map(plans.storage_limit_gb)
    check('UPGRADE 용량 증가 아님',(ej.event_type=='UPGRADE')&~(newcap>oldcap))
    check('DOWNGRADE 용량 감소 아님',(ej.event_type=='DOWNGRADE')&~(newcap<oldcap))
    check('CANCEL이 CANCELLED 구독과 불일치',(ej.event_type=='CANCEL')&(ej.subscription_status!='CANCELLED'))
    check('CANCEL 이벤트의 new_plan_id 존재',(ej.event_type=='CANCEL')&ej.new_plan_id.notna())
    check('RENEW의 old/new 요금제 불일치',(ej.event_type=='RENEW')&(ej.old_plan_id!=ej.new_plan_id))
    check('변경 이벤트 new_plan_id와 구독 plan_id 불일치',ej.event_type.isin(['UPGRADE','DOWNGRADE'])&(ej.new_plan_id!=ej.plan_id))
    check('CANCELLED 구독의 CANCEL 이벤트 없음',((s.subscription_status=='CANCELLED')&~s.subscription_id.isin(e.loc[e.event_type=='CANCEL','subscription_id'])))
    for n,df in t.items():
        for col in df.select_dtypes(include=['datetime']).columns:
            if col!='next_billing_date': check(f'{n}.{col} 관측기간 밖', (df[col]<pd.Timestamp('2024-01-01'))|(df[col]>=REF+pd.Timedelta(days=1)),df[col].notna().sum())
    # Temporal match uses each monthly snapshot date, never the final current plan.
    left=st.assign(snapshot_date=st.created_at.dt.normalize()).sort_values('snapshot_date')
    sj=pd.merge_asof(left,s[['user_id','plan_id','start_date','end_date']].sort_values('start_date'),
                     left_on='snapshot_date',right_on='start_date',by='user_id',direction='backward')
    within=sj.start_date.notna()&(sj.end_date.isna()|(sj.snapshot_date<=sj.end_date))
    caps=sj.plan_id.map(plans.storage_limit_gb).where(within,15)
    capbad=sj.storage_used_gb>caps+.005
    check('월 저장량 < 0',st.storage_used_gb<0,st.storage_used_gb.notna().sum())
    check('월 저장량 > 시점별 한도(종료 후 무료 가정)',capbad,sj.storage_used_gb.notna().sum())
    suspects.extend([
       ['일 활동 login_count < 0',int((a.login_count<0).sum()),'횟수의 의미와 맞지 않는 오류값. 원본은 그대로 보존.'],
       ['일 활동 active_minutes >= 300',int((a.active_minutes>=300).sum()),'긴 활동시간 후보. Heavy User/세션 집계 방식 확인.'],
       ['결제액과 요금제 기대액 불일치',int(mismatch.sum()),'월 가격 또는 연간 12배와 비교. 할인/환불 정책이 없으므로 검토 필요.'],
       ['retry_count < 0 또는 > 3',int(((p.retry_count<0)|(p.retry_count>3)).sum()),'3은 관측 점검 기준이며 서비스 정책의 절대 상한은 아님.'],
       ['월 다운로드 > 저장량',int((st.download_size_gb>st.storage_used_gb).sum()),'반복 다운로드가 가능하므로 업무 규칙 위반으로 단정하지 않음.'],
       ['전체 파일 수 > 관측 99% 분위수',int((st.file_count>st.file_count.quantile(.99)).sum()),f'임계값 {fmt(st.file_count.quantile(.99))}; 요금제·파일 크기 구성 확인.']])
    # Diagnostic-only copies; original DataFrames are never corrected or overwritten.
    sm=st.drop_duplicates(KEYS['storage_usage_monthly']).sort_values(['user_id','usage_month'])
    prevval=sm.groupby('user_id').storage_used_gb.shift(); prevmonth=sm.groupby('user_id').usage_month.shift()
    adjacent=(sm.usage_month.dt.year*12+sm.usage_month.dt.month)-(prevmonth.dt.year*12+prevmonth.dt.month)==1
    pair=adjacent&sm.storage_used_gb.notna()&prevval.notna()
    delta=sm.storage_used_gb-prevval
    expected_months=int(((REF.year-u.signup_date.dt.year)*12+REF.month-u.signup_date.dt.month+1).sum())
    missing_months=expected_months-len(sm)
    ad=a.drop_duplicates(KEYS['user_activity_daily'])
    recent_start=REF-pd.Timedelta(days=89); prior_start=recent_start-pd.Timedelta(days=90)
    eligible=set(u.loc[u.signup_date<=prior_start,'user_id'])
    recent=ad[(ad.activity_date>=recent_start)&(ad.activity_date<=REF)]
    prior=ad[(ad.activity_date>=prior_start)&(ad.activity_date<recent_start)]
    rc=recent.groupby('user_id').size(); pc=prior.groupby('user_id').size()
    base=pc.index[(pc>=5)&pc.index.isin(eligible)]
    declines=base[rc.reindex(base,fill_value=0).to_numpy()<=pc.loc[base].to_numpy()*.5]
    activeusers=set(s.loc[s.subscription_status=='ACTIVE','user_id'])
    pded=pj.drop_duplicates(['subscription_id','payment_date'])
    failures=pded[pded.payment_status=='FAILED'].groupby('user_id').size()
    qded=q.drop_duplicates(KEYS['support_ticket']); tickets=qded.groupby('user_id').size()
    resolution=(q.resolved_at-q.created_at).dt.total_seconds()/3600
    lag=(REF-d.last_sync_at.dt.normalize()).dt.days
    histories={uid:h for uid,h in sm.groupby('user_id')}
    trend=None
    for uid,h in histories.items():
        for start in range(max(0,len(h)-5)):
            candidate=h.iloc[start:start+6]
            months=candidate.usage_month.dt.year*12+candidate.usage_month.dt.month
            if len(candidate)==6 and months.diff().dropna().eq(1).all() and candidate.storage_used_gb.notna().all():
                trend=st.loc[candidate.index]; break
        if trend is not None: break
    assert trend is not None
    selected={}; reasons={}; evidence=[]
    def choose(n,mask,label,ids):
        pool=t[n].loc[mask].drop(index=ids,errors='ignore')
        if not pool.empty:
            idx=pool.sample(n=1,random_state=42).index[0]; ids.append(idx); reasons[(n,idx)]=label
    for n,df in t.items():
        ids=[]
        if n=='plan': ids=list(df.index)
        elif n=='subscription_event':
            for kind in ['UPGRADE','DOWNGRADE','CANCEL','RENEW']: choose(n,df.event_type==kind,kind,ids)
        else:
            dupe=df.duplicated(KEYS[n],keep=False)
            if dupe.any():
                first=df.loc[dupe].sample(n=1,random_state=42).iloc[0]
                same=pd.Series(True,index=df.index)
                for col in KEYS[n]: same &= df[col].isna() if pd.isna(first[col]) else df[col].eq(first[col])
                for idx in df.index[same][:2]: ids.append(idx); reasons[(n,idx)]='동일 논리 키의 실제 행'
            if n=='support_ticket':
                choose(n,df.status=='OPEN','OPEN·해결일 NULL',ids)
                choose(n,df.status=='RESOLVED','RESOLVED·해결일 존재',ids)
            if n=='user_activity_daily':
                choose(n,df.login_count<0,'음수 로그인 횟수',ids)
                choose(n,df.active_minutes>=300,'긴 활동시간',ids)
            if n=='payment_history':
                choose(n,df.payment_id.isin(pj.loc[mismatch,'payment_id']),'요금제 기대액과 불일치',ids)
                choose(n,df.payment_status=='FAILED','FAILED 결제',ids)
                choose(n,df.payment_status=='REFUNDED','REFUNDED 결제',ids)
            choose(n,df.isna().any(axis=1),'NULL 포함',ids)
        size=7 if n=='payment_history' else (len(df) if n=='plan' else max(5,len(ids)))
        rest=df.drop(index=ids).sample(n=max(0,size-len(ids)),random_state=42)
        for idx in rest.index: ids.append(idx); reasons[(n,idx)]='df.sample(random_state=42)'
        selected[n]=df.loc[ids].copy()
        pd.testing.assert_frame_equal(selected[n],df.loc[ids])

    lines=['# CloudCare AI Raw Dataset 분석 보고서','',
      '## 1. 전체 데이터 개요','',
      f'- 분석 시각: {datetime.now().astimezone().isoformat(timespec="seconds")}',
      f'- 실제 입력 폴더: `{SOURCE}`',
      f'- 실제 Excel: {len(t)}개, 총 데이터 {sum(map(len,t.values())):,}행(헤더 제외).',
      '- 통계는 이번 실행에서 pandas.read_excel(engine="openpyxl")로 직접 읽은 값으로 계산했다. 과거 생성 보고서의 수치를 복사하지 않았다.',
      '- 원본 Excel 수정·삭제·덮어쓰기·재생성을 수행하지 않았다. 읽기 전후 SHA-256·크기·수정 시각을 비교했다.',
      '- 설계 의도는 DATA_GENERATION.md를 참고했지만, 실제 관측 결과와 구분해서 표시했다. 실제 서비스의 실측 데이터가 아닌 합성 원천 데이터이다.',
      '- NULL은 일관되게 `NULL`로 표기한다. UNIQUE는 NULL을 제외한 nunique(dropna=True)이다.',
      '- 실제 타입은 pandas가 Excel을 읽고 추론한 dtype이다. Excel에 SQL 타입 선언이 있는 것은 아니다. 결측이 있는 정수 컬럼이 float64가 되는 것은 읽기 과정의 표현이다.',
      '- 범주형 비율의 분모는 해당 파일 전체 행 수이며 NULL도 분포에 포함한다. 수치 통계는 NULL 제외, 기본 집계는 중복 포함 Raw 행 기준이다.',
      '- 논리적 중복 추가 행 수는 duplicated(keys).sum(), 관련 전체 행 수는 duplicated(keys, keep=False).sum()이다. 같은 논리 키라도 모든 값이 같은지 별도 검사한다.',
      '- 모든 예시 행은 df.sample(random_state=42) 또는 명시된 조건 검색으로 원본에서 선택했다. Excel 행 번호는 헤더가 1행일 때의 실제 행 번호(index+2)이다.',
      '- 시계열 비교만 논리 키의 첫 행을 선택한 메모리 내 진단용 뷰를 사용하며 이를 명시한다. 정제 데이터·모델 피처·이탈 라벨은 만들거나 저장하지 않았다.',
      '- 월 로그 누락은 가입월부터 기준월까지 월별 스냅샷이 있어야 한다는 가정 아래 계산한다. 일 로그 부재는 비활동과 수집 누락을 원천 파일만으로 구별할 수 없다.','',
      '## 2. 테이블 구조 요약','']
    lines.append(table(['No','Excel / Sheet','역할','실제 행 수','컬럼 수','PK','주요 FK'],[
        [f'5.{i}',f'{paths[n].name} / {sheets[n][0]}',ROLES[i-1],len(t[n]),len(t[n].columns),t[n].columns[0],', '.join(c for _,ch,c in FK if ch==n) or '-'] for i,n in enumerate(NAMES,1)]))
    notes={
     'user':[f'가입일 실제 범위는 {fmt(u.signup_date.min())}~{fmt(u.signup_date.max())}이다. update 시각의 UNIQUE 수는 {u.updated_at.nunique():,}개로 운영 중 다양한 갱신 시각을 재현했는지 확인할 합성 특성이다.',
             f'일별 활동이 한 번도 관측되지 않은 사용자는 {len(u)-a.user_id.nunique():,}명, 문의가 없는 사용자는 {len(u)-q.user_id.nunique():,}명이다. 로그 부재를 즉시 이탈로 해석할 수 없다.'],
     'plan':[f'실제 {len(pl)}개 상품이며 전체 NULL {int(pl.isna().sum().sum())}개, PK 중복 {duplicates["plan"]["pk_extra"]}개다.',
             '설계상 YEARLY monthly_price는 월 환산 가격이다. 따라서 amount 비교 시 12배로 환산했다. 요금제 Master에는 가격 변경 이력 컬럼이 없다.'],
     'subscription':[f'사용자당 구독 수 분포: '+', '.join(f'{k}개 보유 {v:,}명' for k,v in s.groupby('user_id').size().value_counts().sort_index().items())+'.',
             f'ACTIVE 구독 행은 {(s.subscription_status=="ACTIVE").sum():,}개/{len(s):,}개, ACTIVE 구독을 가진 사용자는 {len(activeusers):,}명/{len(u):,}명이다. 행 기준과 사용자 기준 비율을 혼동하면 안 된다.',
             f'종료 구독이면서 auto_renewal=TRUE인 행은 {((s.subscription_status!="ACTIVE")&s.auto_renewal.eq(True)).sum():,}개다. 설계 문서는 마지막 저장 설정이며 종료 상태가 우선한다고 정의한다.',
             f'기준일 이후 예정 결제일은 {(s.next_billing_date>REF).sum():,}개다. 예정 정보이므로 실제 관측기간 초과 오류와 분리했다.'],
     'storage_usage_monthly':[f'중복 월 첫 행만 사용했을 때 인접한 두 달 모두 저장량이 있는 비교 쌍 {pair.sum():,}개 중 증가 {(pair&(delta>0)).sum():,}개, 감소 {(pair&(delta<0)).sum():,}개, 동일 {(pair&(delta==0)).sum():,}개다. 전월·당월 상관계수는 {prevval[pair].corr(sm.loc[pair,"storage_used_gb"]):.4f}다.',
             f'원본 유효 쌍에서 저장량과 파일 수의 Pearson 상관계수는 {st.storage_used_gb.corr(st.file_count):.4f}다. 상관은 인과를 뜻하지 않는다.',
             f'가입월~2026-08 기대 사용자·월 {expected_months:,}개, 관측 고유 사용자·월 {len(sm):,}개, 부재 {missing_months:,}개({missing_months/expected_months:.2%})다. 월별 관측 의무 가정의 결과이다.',
             f'스냅샷 당시 유효 구독이 없는 월 로그 {int((~within).sum()):,}행은 설계 문서의 무료 15GB 접근 가정으로 비교했다. 이를 적용한 한도 초과 {capbad.sum():,}행이다. 이 가정은 Excel FK만으로 증명되는 사실은 아니다.'],
     'user_activity_daily':[f'원본에서 300분 이상 활동 {int((a.active_minutes>=300).sum()):,}행, 이 값을 가진 사용자 {a.loc[a.active_minutes>=300,"user_id"].nunique():,}명이 관측된다. 최대 {fmt(a.active_minutes.max())}분이다.',
             f'중복 일 첫 행만 선택하고 가입일이 {prior_start.date()} 이전/당일인 사용자 중 직전 90일({prior_start.date()}~{(recent_start-pd.Timedelta(days=1)).date()})에 활동일 5일 이상인 {len(base):,}명을 비교했다. 최근 90일({recent_start.date()}~{REF.date()}) 활동일이 절반 이하인 사용자는 {len(declines):,}명({len(declines)/len(base):.2%})이다.',
             f'이 활동 감소 집단 중 기준일 ACTIVE 구독을 가진 사용자는 {len(set(declines)&activeusers):,}명이다. 관측상 활동 감소가 항상 구독 종료와 같지는 않다.',
             f'업로드 0은 {int(a.upload_count.eq(0).sum()):,}행, 공유 0은 {int(a.share_count.eq(0).sum()):,}행이다. 0은 관측된 무발생이며 NULL과 다르다. 누락된 일 로그 수는 이 파일만으로 확정하지 않는다.'],
     'device':[f'사용자당 기기 수 분포: '+', '.join(f'{k}개 {v:,}명' for k,v in d.groupby('user_id').size().value_counts().sort_index().items())+'.',
             f'마지막 동기화가 기준일보다 90일 넘게 오래된 기기는 {int((lag>90).sum()):,}개(날짜 존재 {lag.notna().sum():,}개 중)이며, 그중 sync_enabled=TRUE는 {int(((lag>90)&d.sync_enabled.eq(True)).sum()):,}개다.',
             'sync_enabled는 설정값이므로 최근 성공 동기화를 보장하지 않는다. last_sync_at NULL은 한 번도 동기화하지 않았다는 해석이 가능하지만 원천 데이터만으로 수집 누락과 완전히 구별할 수 없다.'],
     'payment_history':[f'구독·결제일 중복 첫 행 기준 실패 결제가 있는 사용자는 {len(failures):,}명, 실패 2회 이상 {int((failures>=2).sum()):,}명, 한 사용자 최대 실패 {int(failures.max()):,}회다.',
             f'Raw 금액 불일치 {mismatch.sum():,}행; 논리 중복 제외 불일치 {pj.loc[mismatch].drop_duplicates(["subscription_id","payment_date"]).shape[0]:,}건이다. 비교식은 MONTHLY=monthly_price, YEARLY=monthly_price×12이다.',
             f'FAILED인데 retry_count=0은 {int(((p.payment_status=="FAILED")&p.retry_count.eq(0)).sum()):,}행, SUCCESS인데 재시도가 있는 경우는 {int(((p.payment_status=="SUCCESS")&(p.retry_count>0)).sum()):,}행이다. 실패·재시도를 동일 의미로 보면 안 된다.'],
     'support_ticket':[f'문의 사용자 {len(tickets):,}명, 문의 없음 {len(u)-len(tickets):,}명({(len(u)-len(tickets))/len(u):.2%}). 논리 중복 첫 행 기준 문의 2건 이상 {int((tickets>=2).sum()):,}명, 20건 이상 {int((tickets>=20).sum()):,}명, 최대 {tickets.max():,}건이다.',
             f'해결일이 존재하는 Raw 문의 {resolution.notna().sum():,}행의 해결시간은 중앙값 {resolution.median():.2f}시간, 최대 {resolution.max():.2f}시간이다. OPEN 문의를 해결시간 0으로 대체하지 않았다.',
             f'reopened=TRUE는 {int(q.reopened.eq(True).sum()):,}행이다. 기존 문의 재개와 동일 사용자의 별도 문의를 구분해야 한다.'],
     'subscription_event':['이벤트는 subscription_id로 구독에, user_id로 사용자에, old/new_plan_id로 요금제에 연결된다. 취소 new_plan_id NULL은 변경 후 유료 요금제 부재라는 설계 의미다.',
             '설계 문서는 월간 상품 RENEW 3개월, 연간 상품 12개월 주기를 정의한다. 결제 성공과의 실제 대응 여부는 아래 추가 관측에서 별도로 계산한다.']}
    notes['user'].append(f'ID를 제외한 속성이 완전히 같은 추가 행은 {duplicates["user"]["payload_extra"]:,}행이다. 연령대·지역·가입일 등 거친 속성이 같은 서로 다른 사용자일 수 있으므로 이 값으로 사용자 중복을 판정하지 않는다.')
    notes['device'].append(f'선택한 기기 논리 키 중복 추가 행 {duplicates["device"]["logical_extra"]:,}행과 PK 제외 모든 값 일치 {duplicates["device"]["payload_extra"]:,}행은 다르다. 하드웨어 식별자가 없어 같은 날 등록된 동종 기기가 실제로 다른 기기인지 확인할 수 없다.')
    notes['support_ticket'].append(f'선택한 문의 논리 키 중복 추가 행 {duplicates["support_ticket"]["logical_extra"]:,}행, PK 제외 모든 값 일치 {duplicates["support_ticket"]["payload_extra"]:,}행이다. 같은 고객·분류·시각이라도 우선순위나 해결 정보가 다른 행은 별개 문의일 수 있다. 진단용 첫 행 집계는 최종 삭제 정책이 아니다.')
    extra={}
    extra['device']=table(['device_type','os_type','행 수'],[[x,y,v] for (x,y),v in d.groupby(['device_type','os_type'],dropna=False).size().items()])
    extra['subscription']=table(['plan_name','구독 행 수'],[[name,count] for name,count in s.plan_id.map(plans.plan_name).value_counts().items()])
    extra['payment_history']=table(['가입 채널','결제수단','Raw 행 수'],[[x,y,v] for (x,y),v in pj.assign(channel=pj.user_id.map(users.signup_channel)).groupby(['channel','payment_method'],dropna=False).size().items()])
    renew=ej[ej.event_type=='RENEW'].copy()
    renewpairs=pd.MultiIndex.from_arrays([renew.subscription_id,renew.event_date.dt.normalize()])
    success=pj[pj.payment_status=='SUCCESS']; successpairs=pd.MultiIndex.from_arrays([success.subscription_id,success.payment_date.dt.normalize()])
    renewmonth=(renew.event_date.dt.year-renew.start_date.dt.year)*12+renew.event_date.dt.month-renew.start_date.dt.month
    cycle=renew.plan_id.map(plans.billing_cycle)
    notes['subscription_event'] += [f'실제 RENEW {len(renew):,}행 중 동일 구독·동일 날짜의 SUCCESS 결제가 없는 이벤트 {int((~renewpairs.isin(successpairs)).sum()):,}행이다. SUCCESS 결제 중 동일 날짜 RENEW가 없는 Raw 결제 {int((~successpairs.isin(renewpairs)).sum()):,}행이다. 두 테이블은 같은 사건 목록이 아니다.',
      f'구독 시작월 대비 RENEW 월 차이를 확인했을 때 월간 상품의 3개월 배수 위반 {int(((cycle=="MONTHLY")&(renewmonth%3!=0)).sum()):,}행, 연간 상품의 12개월 배수 위반 {int(((cycle=="YEARLY")&(renewmonth%12!=0)).sum()):,}행이다. 이는 월 간격 검증이며 날짜의 기념일 일치까지 뜻하지 않는다.']
    example_count=0
    def raw_examples(n,df,label):
        nonlocal example_count
        original=t[n].loc[df.index,df.columns]
        pd.testing.assert_frame_equal(df,original)
        example_count+=len(df)
        for idx,row in df.iterrows(): evidence.append({'table':n,'sheet':n,'excel_row':int(idx)+2,'pk':fmt(row.iloc[0]),'selection':label})
        return table(['Excel 행']+list(df.columns),[[int(idx)+2]+row.tolist() for idx,row in df.iterrows()])

    for i,n in enumerate(NAMES,1):
        df=t[n]; pk=df.columns[0]
        lines += [f'## {i+2}. 5.{i} {n}','', '### 1. 기본 정보와 목적','',
          f'- 파일: `{paths[n]}`',f'- Sheet: `{sheets[n][0]}`',f'- 역할: {ROLES[i-1]}.',
          f'- 실제 크기: **{len(df):,}행 × {len(df.columns)}컬럼**. PK: `{pk}`.',
          '- 전체 컬럼: '+', '.join(f'`{c}`' for c in df.columns),
          '- 주요 FK: '+(', '.join(f'`{col}` → `{parent}.{t[parent].columns[0]}`' for parent,child,col in FK if child==n) or '없음(Master 부모 테이블).'),'',
          '### 2. 컬럼 구성과 실제 값 예시','']
        columnrows=[]
        for col in df:
            valid=df.loc[df[col].notna()]
            sample=valid.sample(n=min(1,len(valid)),random_state=42)
            example='NULL(비결측값 없음)' if sample.empty else f'{fmt(sample.iloc[0][col])} (Excel {int(sample.index[0])+2}행, {pk}={fmt(sample.iloc[0][pk])})'
            role='PK' if col==pk else ', '.join(f'FK → {pa}.{t[pa].columns[0]}' for pa,ch,c in FK if ch==n and c==col) or '-'
            desc=INFO[col]
            if col=='status': desc={'user':'사용자 계정의 ACTIVE/INACTIVE 상태. 구독 상태와 별도인 계정 상태이다.','support_ticket':'문의 OPEN/RESOLVED 상태. 미해결 문의와 해결 완료를 구분한다.'}.get(n,desc)
            if n=='storage_usage_monthly' and col=='created_at': desc='월말 스냅샷 기록 생성 시각. 해당 시점의 요금제를 찾는 기준이다.'
            columnrows.append([col,str(df[col].dtype),desc,example,int(df[col].isna().sum()),int(df[col].nunique()),role])
        lines += [table(['컬럼명','실제 타입','들어가는 정보 / 필요한 이유','실제 데이터 예시','NULL 수','UNIQUE 수','PK/FK'],columnrows),
          '### 3. 실제 값 분포·수치 범위·날짜 범위','']
        categoricals=[c for c in df if pd.api.types.is_string_dtype(df[c].dtype) or pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_bool_dtype(df[c])]
        for col in categoricals:
            vals=df[col].value_counts(dropna=False)
            lines += [f'**{col}** — '+('상위 10개' if len(vals)>10 else '실제 전체 값')+'; 분모는 Raw 전체 행.',
                table(['실제 값','건수','비율'],[[v,int(count),f'{count/len(df):.2%}'] for v,count in vals.head(10).items()])]
            if len(vals)>10: lines.append('실제 존재하는 비결측 값 전체: '+', '.join(map(str,df[col].dropna().unique()))+'.\n')
        nums=[c for c in df.select_dtypes(include='number') if not c.endswith('_id')]
        if nums:
            lines.append(table(['수치 컬럼','유효 수','평균','중앙값','최소','25%','75%','최대'],[
               [c,int(df[c].count()),df[c].mean(),df[c].median(),df[c].min(),df[c].quantile(.25),df[c].quantile(.75),df[c].max()] for c in nums]))
        ids=[c for c in df if c.endswith('_id')]
        if ids: lines.append(table(['ID 컬럼','관측 최소','관측 최대'],[[c,df[c].min(),df[c].max()] for c in ids]))
        dates=list(df.select_dtypes(include=['datetime']).columns)
        if dates: lines.append(table(['날짜 컬럼','비결측 행','최소 날짜/시간','최대 날짜/시간'],[[c,int(df[c].count()),df[c].min(),df[c].max()] for c in dates]))
        if n in extra: lines += ['**테이블별 추가 교차분포**',extra[n]]
        lines += ['### 4. 실제 데이터 행 예시','',
                  '아래 값은 원본 행 전체를 그대로 선택했다. NULL을 대체하지 않았다. plan은 전체 행을 제시한다.' if n=='plan' else '아래는 샘플링·조건 검색으로 선택한 원본 행 전체이다. NULL을 대체하지 않았다.',
                  raw_examples(n,selected[n],'기본 예시: sample/조건 검색'),
                  table(['Excel 행','PK','선택 이유'],[[int(idx)+2,df.loc[idx,pk],reasons.get((n,idx),'전체 Master 행')] for idx in selected[n].index])]
        if n=='subscription_event':
            for kind in ['UPGRADE','DOWNGRADE','CANCEL','RENEW']:
                if not df.event_type.eq(kind).any(): lines.append(f'{kind}: 현재 데이터에는 해당 event 없음.')
        if n=='storage_usage_monthly':
            lines += [f'**한 사용자의 실제 연속 6개월: user_id={int(trend.iloc[0].user_id)}**',
               raw_examples(n,trend,'조건 검색: 실제 연속 6개월'),
               f'관측 저장량은 {fmt(trend.iloc[0].storage_used_gb)}GB → {fmt(trend.iloc[-1].storage_used_gb)}GB로 변했다. 다른 사용자의 일반적 패턴을 대표한다고 단정하지 않는다.']
        if n=='user_activity_daily' and len(declines):
            uid=int(sorted(declines)[0]); ids=ad.loc[(ad.user_id==uid)&(ad.activity_date>=prior_start)].sort_values('activity_date').index
            sampleids=list(ids[:3])+list(ids[-3:]); sampleids=list(dict.fromkeys(sampleids))
            lines += [f'**활동 감소 조건에 해당하는 실제 사용자 {uid}의 관측 행**',
                f'직전 기간 활동 {int(pc.get(uid,0))}일, 최근 기간 {int(rc.get(uid,0))}일. 아래는 해당 사용자 실제 관측 행 중 시기 앞/뒤를 선택한 예시이다.',
                raw_examples(n,a.loc[sampleids],'활동 감소 조건 사용자: 실제 관측 앞/뒤 행')]
        lines += ['### 5. 실제 관측 패턴과 설계 해석','']+['- '+v for v in notes[n]]+['',
                  '### 6. 결측치: 정상 NULL과 확인할 결측','']
        nullrows=[]
        for col in df:
            count=int(df[col].isna().sum())
            if not count: continue
            meaning='EDA에서 확인할 관측값 결측. 원본만으로 개별 셀의 누락 원인을 확정할 수 없다.'
            if n=='subscription' and col=='end_date': meaning=f'NULL 중 ACTIVE {(df[col].isna()&df.subscription_status.eq("ACTIVE")).sum():,}행: 정상 Business NULL. 그 외 {(df[col].isna()&df.subscription_status.ne("ACTIVE")).sum():,}행은 검토 대상.'
            if n=='subscription' and col=='next_billing_date': meaning=f'NULL 중 무료 또는 종료 구독 {(df[col].isna()&((df.plan_id==1)|(df.subscription_status!="ACTIVE"))).sum():,}행: 예정 청구 없음으로 해석. 유료 ACTIVE의 NULL {(df[col].isna()&(df.plan_id!=1)&df.subscription_status.eq("ACTIVE")).sum():,}행.'
            if n=='device' and col=='last_sync_at': meaning='정상 NULL 가능: 등록 이후 한 번도 동기화하지 않은 기기. 별도 동기화 이력이 없어 수집 누락과 구별은 불가능.'
            if n=='support_ticket' and col=='resolved_at': meaning=f'NULL 중 OPEN {(df[col].isna()&df.status.eq("OPEN")).sum():,}행: 정상. RESOLVED {(df[col].isna()&df.status.eq("RESOLVED")).sum():,}행: 확인 필요.'
            if n=='subscription_event' and col=='new_plan_id': meaning=f'NULL 중 CANCEL {(df[col].isna()&df.event_type.eq("CANCEL")).sum():,}행: 정상. 그 외 {(df[col].isna()&df.event_type.ne("CANCEL")).sum():,}행: 확인 필요.'
            nullrows.append([col,count,f'{count/len(df):.2%}',meaning])
        lines.append(table(['컬럼','NULL 수','비율','해석'],nullrows) if nullrows else '실제 NULL이 없다.\n')
        dp=duplicates[n]
        lines += ['### 7. PK 중복과 논리적 중복','',
            f'- PK NULL {dp["pk_null"]:,}행, PK 중복 추가 행 {dp["pk_extra"]:,}행. 전체 컬럼 완전 동일 중복 {dp["full_extra"]:,}행.',
            f'- 논리 키: `{", ".join(KEYS[n])}`. 중복 추가 행 **{dp["logical_extra"]:,}행**, 관련 전체 행 {dp["logical_involved"]:,}행.',
            f'- PK를 제외한 나머지 모든 값이 같은 중복 추가 행: {dp["payload_extra"]:,}행.',
            '- 논리 키는 분석용 후보 정의이다. 결제의 같은 시각 처리나 같은 고객의 문의는 실제 운영 정책에 따라 별개 사건일 수 있어 검토 없이 삭제하지 않는다.' if n in ['device','payment_history','support_ticket','subscription_event'] else '- 사용자·월 또는 사용자·날짜를 유일 사건으로 집계할 때 중복으로 인한 과대 합산을 주의한다.' if n in ['storage_usage_monthly','user_activity_daily'] else '- 사용자나 요금제의 반복 참조는 FK의 정상적인 1:N 관계이며 PK 중복과 다르다.','',
            '### 8. 이상치·특이값 및 검토할 관계','']
        special={
          'user':f'updated_at 값 {u.updated_at.nunique():,}종류, 가입 전 생성 {(u.created_at<u.signup_date).sum():,}행. 일괄 갱신은 합성 데이터의 특성일 수 있다.',
          'plan':f'음수 가격 {(pl.monthly_price<0).sum():,}행, 0 이하 저장 한도 {(pl.storage_limit_gb<=0).sum():,}행. Master 결측·중복과 함께 검토했다.',
          'subscription':f'예정 결제일은 최대 {fmt(s.next_billing_date.max())}로 관측 기준일 이후일 수 있다. 종료 구독의 자동갱신 TRUE는 위 설계 해석을 확인해야 한다.',
          'storage_usage_monthly':f'최대 전체 파일 수 {fmt(st.file_count.max())}, 최대 다운로드 {fmt(st.download_size_gb.max())}GB. 전체 파일 수 99% 분위수 {fmt(st.file_count.quantile(.99))}. 큰 값만으로 오류로 단정하지 않는다. 사진+영상 관계 검증 불가(NULL 포함) {int((~validcounts).sum()):,}행.',
          'user_activity_daily':f'login_count 범위 {fmt(a.login_count.min())}~{fmt(a.login_count.max())}, upload_count {fmt(a.upload_count.min())}~{fmt(a.upload_count.max())}, active_minutes {fmt(a.active_minutes.min())}~{fmt(a.active_minutes.max())}. 음수 로그인 {int((a.login_count<0).sum()):,}행은 횟수 의미에 맞지 않는다.',
          'device':f'등록 이전 동기화 {int((d.last_sync_at<d.registered_at).sum()):,}행, OS 조합 위반 {int(bad_os.sum()):,}행. 동기화 시각 NULL은 오래된 동기화와 분리한다.',
          'payment_history':f'금액 범위 {fmt(p.amount.min())}~{fmt(p.amount.max())}원, 재시도 {fmt(p.retry_count.min())}~{fmt(p.retry_count.max())}회. 금액 불일치 {int(mismatch.sum()):,}행은 중복 포함 Raw 기준이다.',
          'support_ticket':f'논리 중복 제외 최대 문의 사용자 {int(tickets.idxmax())}: {int(tickets.max())}건. 해결시간 7일 초과 Raw 문의 {int((resolution>168).sum()):,}행. 문의 수 자체를 기술 문제의 원인으로 단정할 수 없다.',
          'subscription_event':f'UPGRADE 증가 위반 {int(((ej.event_type=="UPGRADE")&~(newcap>oldcap)).sum()):,}행, DOWNGRADE 감소 위반 {int(((ej.event_type=="DOWNGRADE")&~(newcap<oldcap)).sum()):,}행. new_plan_id의 float dtype은 NULL을 포함한 pandas 추론이며 FK 실수 오류를 뜻하지 않는다.'}
        lines += [special[n],'','### 9. 다른 테이블과 연결·FK 검증','']
        relations=[r for r in fkrows if r[0]==n or r[1]==n]
        lines.append(table(['부모','자식','FK','비결측 참조 불일치','FK NULL'],relations) if relations else '관계 없음.')
        lines += ['### 10. 이후 EDA에서 확인할 항목','']+[f'- {v}' for v in EDA[n]]+['']
    lines += ['## 12. 테이블 간 관계 및 FK 검증','',
      '```text\nuser\n ├─ subscription ── plan\n │    ├─ payment_history\n │    └─ subscription_event ── plan(old/new)\n ├─ storage_usage_monthly\n ├─ user_activity_daily\n ├─ device\n └─ support_ticket\n```',
      'subscription_event.user_id도 user에 직접 연결된다. FK의 NULL은 참조 미일치와 별도로 집계한다. CANCEL의 new_plan_id NULL은 허용 가능한 Business NULL이다.',
      table(['부모 테이블','자식 테이블','FK','미일치 건수','NULL 건수'],fkrows),
      f'모든 FK 비결측 참조 미일치 합계: {sum(r[3] for r in fkrows):,}행. 이벤트와 구독의 user_id 일치도 별도 검사했다.',
      '월 사용량은 user_id만 있으므로 단순 사용자 JOIN으로 구독 이력 전체를 붙이면 행이 불어난다. 스냅샷 시점과 구독 유효기간을 함께 조건으로 사용해야 한다.',
      '', '## 13. 전체 결측치 현황','',
      table(['테이블','NULL 셀 수','전체 셀 수','셀 기준 NULL 비율','NULL 있는 행'],[
        [n,int(df.isna().sum().sum()),df.size,f'{df.isna().sum().sum()/df.size:.2%}',int(df.isna().any(axis=1).sum())] for n,df in t.items()]),
      '종료일·청구예정일·미해결 문의 해결일·취소 후 요금제·미동기화 시각의 NULL을 관측값 누락과 구분한다. 표는 의도적으로 삽입한 개수가 아니라 실제 Excel에 존재하는 모든 NULL 셀을 집계한다.',
      '', '## 14. 전체 중복 현황','',
      table(['테이블','논리 키','PK 추가 중복','논리 추가 중복','관련 전체 행','PK 제외 완전 일치 추가 중복'],[
        [n,', '.join(KEYS[n]),v['pk_extra'],v['logical_extra'],v['logical_involved'],v['payload_extra']] for n,v in duplicates.items()]),
      '중복 추가 행은 첫 행을 제외한 개수이다. 테이블 간 같은 user_id가 반복되는 것은 중복 오류가 아니다. 분석 코드는 어떠한 중복도 원본에서 삭제하지 않았다.',
      '', '## 15. 이상치 및 Business Rule 위반 후보','',
      '### 검토 후보(원본 값 보존)',table(['판정 기준','Raw 해당 행 수','해석'],suspects),
      '### 날짜·관계·업무 규칙 실제 검증',table(['검사','위반/후보 행 수','평가 범위 또는 비결측 행 수'],checks),
      'NULL이 필요한 입력을 가리는 관계는 비교 가능한 행만 평가한다. 위반 0은 모든 데이터 품질 문제 부재를 뜻하지 않는다.',
      '### 설계 의도와 관측 결과의 구분',
      '- DATA_GENERATION.md는 로그 누락, 측정값 결측, 새 PK의 논리적 중복, 긴 활동시간, 일부 금액 불일치 및 음수 로그인을 의도한 Raw 문제로 설명한다. 위 실제 건수는 Excel에서 새로 계산한 것이며 삽입 당시 개수와 같다고 가정하지 않았다.',
      '- 날짜/FK 위반, 요금제 방향 모순, ACTIVE 종료일 등 문서화되지 않은 모순이 발견되면 생성 코드 오류 가능성을 우선 점검해야 한다. 현재 실제 검사 결과는 위 표의 값으로 판단한다.',
      '- 종료 후 무료 15GB 접근, 종료 구독의 자동갱신 설정 유지, 월간 상품의 3개월 단위 Lifecycle 갱신은 설계 선택이다. 실제 서비스 도입 전 업무 정의를 확정해야 한다.',
      '- 원천 파일만으로 잠재변수의 영향이나 개별 결측·이상치의 발생 원인을 증명할 수 없다. 관측된 상관·반복·감소만 기술했다.',
      '', '## 16. 향후 EDA 포인트','',
      '1. 최우선: 음수 횟수, 금액 불일치, 논리적 중복의 처리 원칙을 문서화한다. 원본 보존 후 별도 분석 계층에서 처리한다.',
      '2. 정상 Business NULL을 일괄 보간하지 않는다. 측정값 결측, 월 로그 부재, 비활동일을 구분한다.',
      '3. 요금제는 관측 시점의 구독 기간으로 연결하고, 유료 구독 종료 후 무료 접근 가정의 타당성을 확인한다.',
      '4. 사용자별 관측기간, 가입 코호트, 월간/연간 결제주기를 통제하여 활동·문의·실패 횟수를 비교한다.',
      '5. Heavy User와 긴 세션 오류, 반복문의와 로그 중복, 청구 실패와 갱신을 각각 구분한다.',
      '6. 모델링 전 예측 기준일·관측창·미래 라벨창을 확정한다. 종료 상태/종료일/미래 이벤트로 과거를 예측하는 누수를 방지한다.',
      '', '## 17. 향후 Feature Engineering 후보','',
      '아래는 설계 후보 목록이다. 실제 피처 테이블이나 이탈 라벨은 생성하지 않았다.',
      table(['후보','원천 테이블·컬럼','향후 정의 시 주의'],[
       ['storage_usage_ratio','storage_usage_monthly.storage_used_gb; subscription 기간·plan_id; plan.storage_limit_gb','관측 시점 한도, 종료 후 무료 접근 가정, 결측·중복 처리'],
       ['usage_change_3m','storage_usage_monthly.user_id, usage_month, storage_used_gb','연속 월 여부와 요금제 전환을 확인'],
       ['active_days_30d / login_count_30d','user_activity_daily.user_id, activity_date, login_count','고유 활동일, 음수/NULL, 활동일 부재 해석'],
       ['upload_count_30d / activity_change','user_activity_daily.upload_count, active_minutes, activity_date','같은 길이의 관측창과 중복 제거 정책'],
       ['sync_device_count / days_since_last_sync','device.user_id, sync_enabled, last_sync_at, registered_at','설정과 실제 동기화 구분, 미동기화 NULL 별도'],
       ['payment_failure_count_3m / retry_count_3m','payment_history.payment_status, retry_count, payment_date, subscription_id; subscription.user_id','동일 결제 중복 및 월간/연간 노출 차이'],
       ['unresolved_ticket_count / support_issue_count_3m','support_ticket.user_id, created_at, resolved_at, status','예측 기준일 당시의 미해결 상태 재구성 필요'],
       ['reopened_ticket_count','support_ticket.reopened, user_id, created_at','재개 시각 컬럼이 없어 과거 시점 재구성 한계'],
       ['subscription_months','subscription.user_id, start_date, end_date','가입기간과 유료 구독기간 구별, 기간 중첩 및 기준일 절단'],
       ['upgrade / downgrade 횟수','subscription_event.event_type, event_date, user_id','관측창 이후 이벤트를 포함하지 않기']]),
      '', '## 18. 최종 요약','',
      f'- 실제 9개 파일에서 총 {sum(map(len,t.values())):,}행을 읽었다. 원본 셀 수·NULL·UNIQUE·분포·범위·예시를 각 테이블에 제시했다.',
      f'- PK NULL {sum(v["pk_null"] for v in duplicates.values()):,}행, PK 중복 추가 행 {sum(v["pk_extra"] for v in duplicates.values()):,}행, FK 비결측 참조 미일치 {sum(r[3] for r in fkrows):,}행.',
      f'- 전체 NULL {sum(int(df.isna().sum().sum()) for df in t.values()):,}셀, 정의한 논리 키의 중복 추가 행 {sum(v["logical_extra"] for v in duplicates.values()):,}행.',
      f'- 음수 로그인 {int((a.login_count<0).sum()):,}행, 300분 이상 활동 {int((a.active_minutes>=300).sum()):,}행, 요금제 금액 불일치 {int(mismatch.sum()):,}행은 우선 확인할 실제 관측값이다.',
      f'- 조건 검색·샘플링으로 제시한 원본 행 예시는 총 {example_count:,}행(본문 중복 제시 포함). 모든 행을 원본 DataFrame의 같은 인덱스와 assert_frame_equal로 대조했다.',
      '- 신규 원천 데이터·정제 Excel·ML 피처·이탈 라벨은 생성하지 않았다. 다음 단계는 원본을 보존한 상태에서 EDA 처리 기준을 확정하는 것이다.',
      '', '### 원본 보존 확인용 파일 지문','']
    after={n:fingerprint(path) for n,path in paths.items()}
    assert before==after, 'Source file changed during read-only analysis'
    lines.append(table(['파일','바이트','SHA-256','전후 크기·수정 시각·해시'],[[paths[n].name,before[n]['bytes'],before[n]['sha256'],'동일'] for n in NAMES]))
    folder=ROOT/'docs' if (ROOT/'docs').is_dir() else ROOT
    dest=unique_path(folder,'CloudCare_Raw_Dataset_Analysis','.md')
    with dest.open('x',encoding='utf-8') as handle: handle.write('\n\n'.join(part.strip() for part in lines if part.strip())+'\n')
    print('[REPORT] '+str(dest),flush=True)
    print(json.dumps({'total_rows':sum(map(len,t.values())),'null_cells':sum(int(df.isna().sum().sum()) for df in t.values()),
      'duplicates':duplicates,'fk_mismatches':sum(r[3] for r in fkrows),'rule_violations':sum(r[1] for r in checks),
      'outlier_candidates':suspects,'missing_months_assuming_monthly_snapshot':missing_months,
      'declining_activity_users':len(declines),'declining_with_active_subscription':len(set(declines)&activeusers),
      'examples_verified':example_count,'source_fingerprints_unchanged':True},ensure_ascii=True,indent=2),flush=True)

if __name__=='__main__': main()
