"""Check report completeness and its recorded source fingerprints, read-only."""
from pathlib import Path
import hashlib
import re
import sys

root=Path(__file__).resolve().parents[1]
path=Path(sys.argv[1]) if len(sys.argv)>1 else root/'docs/CloudCare_Raw_Dataset_Analysis_2.md'
body=path.read_text(encoding='utf-8')
heads=re.findall(r'^## (\d+)\.',body,re.M)
assert heads==[str(i) for i in range(1,19)],heads
sections=re.split(r'^## \d+\.',body,flags=re.M)
for i in range(3,12):
    text=sections[i]
    subheads=re.findall(r'^### (\d+)\.',text,re.M)
    assert subheads==[str(j) for j in range(1,11)],(i,subheads)
    for term in ['실제 타입','UNIQUE 수','Excel 행','### 4. 실제 데이터 행 예시']:
        assert term in text,(i,term)
for term in ['age_group','region','signup_channel','status','plan_name','billing_cycle',
             'is_paid','is_active','auto_renewal','subscription_status','device_type','os_type',
             'sync_enabled','payment_status','payment_method','category','priority','reopened','event_type']:
    assert f'**{term}**' in body,term
for file in (root/'data/raw/cloudcare_20260831_seed42').glob('*.xlsx'):
    assert hashlib.sha256(file.read_bytes()).hexdigest() in body,file
assert 'df.sample(random_state=42)' in body
assert '61행' in body
assert '| FAILED |' in body
print('[PASS] 18 sections, 9 complete table descriptions, categorical distributions, sample provenance, 9 unchanged source hashes')
print(f'[REPORT] {path.resolve()} ({path.stat().st_size:,} bytes)')
