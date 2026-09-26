"""Course-specific bounded proxies. Original cognition and targets are never edited."""
from pathlib import Path
from collections import Counter,defaultdict
import csv,json,hashlib

ROOT=Path('/Users/sirui/Documents/ChatGPT/数学建模')
OUT=Path(__file__).resolve().parent
D=ROOT/'workspace/data_clean/module_b_cognitive_full_v5'
C=ROOT/'results/module_b_decomposition_v4'
def read(p):return [json.loads(l) for l in p.read_text().splitlines() if l]
def write(p,data):p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
COURSE=ROOT/'workspace/data_clean/module_b_topic_domain_unified_v1/taxonomy.jsonl'
targets=read(COURSE)
raw={r['id']:r for r in read(D/'final_rows.jsonl')}
lineage={(r['id'],r['stream']):r for r in read(D/'evidence_lineage.jsonl')}
POINTS=ROOT/'workspace/data_clean/module_b_topic_domain_unified_v1/point_domains.jsonl'
points={(r['id'],r['stream']):r for r in read(POINTS)}
global_pairs=list(csv.DictReader((C/'calibration_pairs.csv').open()))
assert len(global_pairs)==519
accepted=[];excluded=[]
for p in global_pairs:
    p['L']=int(p['L']);p['fold']=int(p['fold'])
    rid=p['id'];stage=p['stage']
    c3,c6=('qa3_three','qa3_l') if stage=='baseline' else ('highest_three','highest_l')
    assert raw[rid][c3]==p['s3'] and raw[rid][c6]=='L'+str(p['L'])
    a,b=points[rid,stage+'_s3'],points[rid,stage+'_s6']
    shared=set(a['task_ids'])&set(b['task_ids'])
    if a['domain_id'] and a['domain_id']==b['domain_id'] and shared and next(t for t in targets if t['id']==a['domain_id'])['target_level'] is not None:
        accepted.append(dict(p,module_id=a['domain_id'],domain_id=a['domain_id'],task_ids=sorted(shared),course_mapping_status='ORIGINAL_TOPIC_EVIDENCE'))
    else:excluded.append(dict(p,reason='NO_UNIQUE_SAME_TOPIC_DOMAIN_EVIDENCE'))
assert len({(p['id'],p['stage']) for p in accepted})==len(accepted)
labels=['低','中','高']
def pava(values,weights):
    blocks=[]
    for i,(value,weight) in enumerate(zip(values,weights)):
        blocks.append(([i],value*weight,weight))
        while len(blocks)>1 and blocks[-2][1]/blocks[-2][2]>blocks[-1][1]/blocks[-1][2]:
            b=blocks.pop();a=blocks.pop();blocks.append((a[0]+b[0],a[1]+b[1],a[2]+b[2]))
    result=[None]*len(values)
    for ids,total,n in blocks:
        for i in ids:result[i]=total/n
    return result
def calculate(t,heldout=None,strength=10):
    if t['target_level'] is None:
        return [dict(label=l,n_pairs=0,n_students=0,raw_s6_counts={},raw_mean=None,above_target_count=0,capped_mean=None,parent_n=0,parent_capped_mean=None,unconstrained_proxy=None,weight=0,estimate_status='TARGET_UNDEFINED',proxy=None,isotonic_adjusted=False) for l in labels]
    T=int(t['target_level'][1:]);local=[p for p in accepted if p['module_id']==t['id'] and (heldout is None or p['fold']!=heldout)]
    rows=[]
    for label in labels:
        pp=[p for p in local if p['s3']==label]
        # Parent prior excludes this module to avoid counting the local cells twice.
        local_keys={(p['id'],p['stage']) for p in local}
        parent=[p for p in global_pairs if p['s3']==label and (heldout is None or p['fold']!=heldout) and (p['id'],p['stage']) not in local_keys]
        prior=sum(min(p['L'],T) for p in parent)/len(parent)
        n=len(pp);mean=sum(min(p['L'],T) for p in pp)/n if n else None
        proxy=(sum(min(p['L'],T) for p in pp)+strength*prior)/(n+strength) if n+strength else prior
        rows.append(dict(label=label,n_pairs=n,n_students=len({p['student_key'] for p in pp}),raw_s6_counts={f'L{k}':sum(p['L']==k for p in pp) for k in range(1,7)},raw_mean=sum(p['L'] for p in pp)/n if n else None,above_target_count=sum(p['L']>T for p in pp),capped_mean=mean,parent_n=len(parent),parent_capped_mean=prior,unconstrained_proxy=proxy,weight=n+strength if n+strength else 1,estimate_status='NO_LOCAL_SAMPLE_PARENT_FALLBACK' if n==0 else ('SPARSE_LOCAL_SHRINKAGE' if n<10 else 'LOCAL_SHRINKAGE')))
    adjusted=pava([r['unconstrained_proxy'] for r in rows],[r['weight'] for r in rows])
    for r,value in zip(rows,adjusted):
        r['proxy']=value;r['isotonic_adjusted']=abs(value-r['unconstrained_proxy'])>1e-12
        assert 1<=value<=T
    assert adjusted==sorted(adjusted)
    return rows
modules=[]
for t in targets:
    records=[p for p in accepted if p['module_id']==t['id']]
    maps=calculate(t)
    modules.append(dict(module_id=t['id'],name=t['name'],definition=t['definition'],initial_level=t['initial_level'],target_level=t['target_level'],target_requirement=next((r['standard'] for r in t['rubric'] if r['level']==t['target_level']), '待具体主题和目标确认'),scale=t['scale'],teacher_target=None,target_status=t['target_status'],rubric=t['rubric'],n_pairs=len(records),n_conversations=len({p['id'] for p in records}),n_students=len({p['student_key'] for p in records}),mapping=maps,heldout_mappings=[dict(heldout_fold=f,mapping=calculate(t,f)) for f in range(5)],sensitivity={str(k):calculate(t,strength=k) for k in [5,20]}))
payload=dict(version='course-module-bounded-proxy-v1-proposed',status='COURSE_CONFIGURATION_ONLY_NOT_APPLIED_TO_STUDENTS',direct_six_source_domains=['数学建模综合与案例','数学基础'],method='Per-module E[min(L,target)|independent_s3], local sums + 10 leave-module-out parent pseudo-observations, then weighted isotonic projection; raw L is never capped.',strength=10,source_counts=dict(global_pairs=len(global_pairs),accepted_module_pairs=len(accepted),excluded_module_pairs=len(excluded),global_students=len({p['student_key'] for p in global_pairs})),sources={str(p):sha(p) for p in [D/'final_rows.jsonl',D/'evidence_lineage.jsonl',POINTS,COURSE,C/'calibration_pairs.csv']},modules=modules)
payload['version']='original-topic-domain-bounded-proxy-v1'
payload['status']='CONFIGURATION_APPLICATION_TRACKED_IN_MANIFEST'
payload['taxonomy']='original-topic-domain-v1'
payload['sources'][str(COURSE)]=sha(COURSE)
write(OUT/'模块映射配置.json',payload)
write(OUT/'模块映射配对依据.json',accepted)
write(OUT/'未用于模块拟合的配对.json',excluded)
print(json.dumps(payload['source_counts'],ensure_ascii=False))
for m in modules:print(m['module_id'],m['name'],m['target_level'],m['n_pairs'],[(r['label'],r['n_pairs'],round(r['proxy'],3) if r['proxy'] is not None else None) for r in m['mapping']])
