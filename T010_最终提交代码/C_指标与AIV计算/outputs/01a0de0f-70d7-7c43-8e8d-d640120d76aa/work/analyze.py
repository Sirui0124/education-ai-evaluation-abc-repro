from pathlib import Path
import json, hashlib, itertools, math
from collections import Counter, defaultdict
import numpy as np
import pandas as pd
from types import SimpleNamespace
def spearmanr(a,b):
 return SimpleNamespace(statistic=pd.Series(np.asarray(a)).rank().corr(pd.Series(np.asarray(b)).rank()))
def rankdata(a,method='average'):return pd.Series(a).rank(method=method).to_numpy()

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parents[1]
sources={
 'domains':'outputs/module-b-q3-adopted-v1/学生领域采纳版.jsonl',
 'students':'outputs/module-b-q3-adopted-v1/学生指标采纳版.jsonl',
 'mapping':'outputs/module-b-course-mapping/模块映射配置.json',
 'summary':'outputs/module-b-q3-adopted-v1/summary.json',
 'discussion':'outputs/module-c-student-discussion-20260926/学生学期汇总.jsonl'}
data={};manifest={}
for k,p in sources.items():
 suffix=Path(p).suffix; snap=OUT/'snapshot'/f'{k}{suffix}'
 b=snap.read_bytes() if snap.exists() else (ROOT/p).read_bytes()
 if not snap.exists():snap.write_bytes(b)
 manifest[k]={'source':p,'sha256':hashlib.sha256(b).hexdigest()}
 data[k]=[json.loads(l) for l in b.decode().splitlines()] if suffix=='.jsonl' else json.loads(b)
modules={m['name']:m for m in data['mapping']['modules'] if m['target_level'] is not None}
M=len(modules);Q=.6
students={r['student_key']:r for r in data['students']}
discuss={r['student_key']:r for r in data['discussion']}
components=[];bad=Counter();students_bad=defaultdict(Counter)
for d in data['domains']:
 reason=d['pair_status']
 if not d['domain_pair_valid'] or reason!='COMPARABLE':
  bad[reason]+=1;students_bad[d['student_key']][reason]+=1;continue
 if d['domain'] not in modules:
  bad['NO_TARGET']+=1;students_bad[d['student_key']]['NO_TARGET']+=1;continue
 m=modules[d['domain']]
 if d['before_module']!=d['after_module']:
  bad['MODULE_MISMATCH']+=1;students_bad[d['student_key']]['MODULE_MISMATCH']+=1;continue
 b,a=d['before_score'],d['after_score'];t=int(m['target_level'][1:])
 assert 1<=b<=6 and 1<=a<=6
 ctq=max(0,(a-b)/5);base=Q*max(t-b,0)/5
 components.append(dict(student_key=d['student_key'],term=d['student_key'].split(':')[0],scale=d['scale'],domain=d['domain'],module=m['module_id'],before=b,after=a,target=t,importance=1.,ctq=ctq,baseline=base,net=ctq-base,signed=(a-b)/5,same_task=d['same_task'],evidence=';'.join(d['dialogue_short_ids']),before_evidence=d['before_evidence'],after_evidence=d['after_evidence']))
C=pd.DataFrame(components)
assert not C.duplicated(['student_key','domain']).any()
rows=[]
for (key,scale),g in C.groupby(['student_key','scale'],sort=True):
 s=students[key];den=s['ab3_inclusive_count'];num=s['abpro_count']
 if den<=0: bad['QA3_ZERO']+=1;continue
 assert 0<=num<=den
 zsum=(g.net.sum()/M+1)/2;zmean=(g.net.mean()+1)/2;zpeak=(g.net.max()+1)/2
 mab=s['observed_agent_category_count']
 rows.append(dict(student_key=key,term=key.split(':')[0],scale=scale,group=key.split(':')[0]+' / '+scale,n=len(g),sum=float(g.net.sum()),mean=float(g.net.mean()),peak=float(g.net.max()),actual=float(g.ctq.mean()),baseline=float(g.baseline.mean()),z=[zsum,zmean,zpeak,num/den],qa3=den,qapro=num,mab=mab,mab_coverage=s['agent_observation_coverage'],mab_sat=None if mab is None else 1-math.exp(-max(mab-1,0)/2),self=discuss.get(key,{}).get('autonomy_evidence','未匹配'),sessions=s['included_session_count']))
R=pd.DataFrame(rows); primary=R[R.scale=='s3'].copy(); Z=np.array(primary.z.tolist())
def entropy(z):
 sums=z.sum(axis=0);p=np.divide(z,sums,where=sums>0,out=np.zeros_like(z));logs=np.zeros_like(p);np.log(p,out=logs,where=p>0)
 e=-(p*logs).sum(axis=0)/np.log(len(z));d=np.maximum(0,1-e);d[np.ptp(z,axis=0)<1e-12]=0
 return (d/d.sum() if d.sum()>0 else np.ones(z.shape[1])/z.shape[1]),d
ew,div=entropy(Z);ec,_=entropy(Z[:,:3]);prior=np.array([.30,.45,.25]);w=np.r_[.8*(.75*prior+.25*ec),.2]
schemes={'推荐':w,'均衡发展':np.array([.30,.30,.20,.20]),'高阶突破':np.array([.20,.20,.40,.20]),'纯熵权':ew}
def ranks(v):return rankdata(-np.round(v,10),method='average')
def tops(v):
 k=math.ceil(len(v)*.2);th=sorted(np.round(v,10),reverse=True)[k-1];return set(np.flatnonzero(np.round(v,10)>=th))
def compare(v,ref):
 a,b=tops(v),tops(ref)
 return {'rho':float(spearmanr(v,ref).statistic),'max_rank_change':float(np.max(np.abs(ranks(v)-ranks(ref)))),'top_intersection':len(a&b),'top_base':len(b),'top_other':len(a),'jaccard':len(a&b)/len(a|b),'max_score_change':float(np.max(np.abs(v-ref)))}
ref=100*Z@w
comparisons=[]
for name,wt in schemes.items():
 v=100*Z@wt;d=compare(v,ref);d.update(name=name,weights=wt.tolist(),score_min=float(v.min()),score_max=float(v.max()),top_mean_net=float(primary.iloc[list(tops(v))]['mean'].mean()),top_mean_quality=float(primary.iloc[list(tops(v))].qapro.div(primary.iloc[list(tops(v))].qa3).mean()));comparisons.append(d)
corners=[];rankarrays=[];scorearrays=[]
for bits in itertools.product([.9,1.1],repeat=4):
 wt=w*np.array(bits);wt/=wt.sum();v=100*Z@wt
 corners.append(dict(factors=list(bits),weights=wt.tolist(),**compare(v,ref)));rankarrays.append(ranks(v));scorearrays.append(v)
sens=[]
for q in [.4,.5,.6,.7,.8]:
 z=[];net=[]
 for r in primary.to_dict('records'):
  g=C[(C.student_key==r['student_key'])&(C.scale==r['scale'])];v=g.ctq-g.baseline*q/Q
  z.append([(v.sum()/M+1)/2,(v.mean()+1)/2,(v.max()+1)/2,r['qapro']/r['qa3']]);net.append(float(v.mean()))
 v=100*np.array(z)@w;sens.append(dict(name=f'自然完成率q={q}',q=q,positive_net=sum(x>1e-12 for x in net),**compare(v,ref)))
nonlinear=100*((1-np.exp(-2*Z))/(1-np.exp(-2)))@w
sens.append(dict(name='边际递减（所有正向评分）',**compare(nonlinear,ref)))
for j,n in enumerate(['总量','均值','峰值','质量']):
 wt=w.copy();wt[j]=0;wt/=wt.sum();sens.append(dict(name='删去'+n,**compare(100*Z@wt,ref)))
mask=primary.mab.notna().to_numpy();weak=.95*ref[mask]+5*primary.mab_sat.to_numpy()[mask];sens.append(dict(name='MAB额外占5%（完整子样本）',n=int(mask.sum()),**compare(weak,ref[mask])))
# Freeze fitted weights for ranking and perturbations; do not refit for each student.
for r in rows:
 r['scores']={k:float(100*np.dot(r['z'],v)) for k,v in schemes.items()}
 r['contributions']=(100*np.array(r['z'])*w).tolist()
 r['net_positive_all_q']=r['actual']-r['baseline']*.8/.6>1e-12
 r['net_negative_all_q']=r['actual']-r['baseline']*.4/.6< -1e-12
 r['diagnosis']='基线范围内均为正' if r['net_positive_all_q'] else ('基线范围内均为负' if r['net_negative_all_q'] else '正负依赖自然基线')
for group in sorted({r['group'] for r in rows}):
 ids=[i for i,r in enumerate(rows) if r['group']==group]
 for scheme in schemes:
  rr=ranks(np.array([rows[i]['scores'][scheme] for i in ids]))
  for i,rank in zip(ids,rr):rows[i].setdefault('ranks',{})[scheme]=float(rank)
for j,i in enumerate(primary.index):
 rows[i]['perturb_rank_min']=float(np.array(rankarrays)[:,j].min());rows[i]['perturb_rank_max']=float(np.array(rankarrays)[:,j].max())
 rows[i]['perturb_score_min']=float(np.array(scorearrays)[:,j].min());rows[i]['perturb_score_max']=float(np.array(scorearrays)[:,j].max())
# Leave-one-out entropy influence (data-driven component only).
loo=[]
for i in range(len(Z)):
 e,_=entropy(np.delete(Z[:,:3],i,axis=0));wi=np.r_[.8*(.75*prior+.25*e),.2];loo.append(np.max(np.abs(wi-w)))
roster=[]
for key,s in students.items():
 own=[r for r in rows if r['student_key']==key]
 roster.append([key,s['included_session_count'],s['ab3_inclusive_count'],s['abpro_count'],s['observed_agent_category_count'],'、'.join(r['scale'] for r in own) or '不可评分','；'.join(f'{k}:{v}' for k,v in students_bad[key].items()) or '无无效领域',discuss.get(key,{}).get('autonomy_evidence','未匹配')])
payload={'version':data['summary']['version'],'manifest':manifest,'M':M,'q':Q,'modules':[dict(module=m['module_id'],domain=m['name'],target=int(m['target_level'][1:]),importance=1.) for m in modules.values()], 'weights':w.tolist(),'entropy_weights':ew.tolist(),'cognition_entropy':ec.tolist(),'entropy_divergence':div.tolist(),'prior':prior.tolist(),'rows':rows,'components':components,'roster':roster,'comparisons':comparisons,'corners':corners,'sensitivity':sens,'pearson':np.corrcoef(Z,rowvar=False).tolist(),'spearman':pd.DataFrame(Z).corr(method='spearman').values.tolist(),'counts':{'students':len(students),'scored_students':len({r['student_key'] for r in rows}),'score_rows':len(rows),'domains':len(data['domains']),'valid_domains':len(C),'scales':dict(Counter(r['scale'] for r in rows)),'groups':dict(Counter(r['group'] for r in rows)),'domain_n':dict(Counter(r['n'] for r in rows)),'bad':dict(bad),'qaden_small':sum(r['qa3']<3 for r in rows),'same_task_false':int((~C.same_task).sum()),'negative_signed':int((C.signed<0).sum()),'positive_s3':int((primary['mean']>1e-12).sum()),'zero_s3':int((primary['mean'].abs()<=1e-12).sum()),'negative_s3':int((primary['mean']< -1e-12).sum()),'diagnoses':dict(Counter(r['diagnosis'] for r in rows if r['scale']=='s3'))},'mab_spearman_net':float(spearmanr(primary.mab,primary['mean']).statistic),'mab_spearman_sessions':float(spearmanr(primary.mab,primary.sessions).statistic),'loo_max_weight_change':max(loo),'main_score_min':float(ref.min()),'main_score_max':float(ref.max())}
rng=np.random.default_rng(20260926);boot=[]
for _ in range(500):
 e,_=entropy(Z[rng.integers(0,len(Z),len(Z)),:3]);boot.append(np.r_[.8*(.75*prior+.25*e),.2])
payload['bootstrap_weight_interval']=np.quantile(np.array(boot),[.025,.975],axis=0).tolist()
payload['main_one_domain']=int((primary.n==1).sum())
payload['perturb_summary']={'min_rho':min(x['rho'] for x in corners),'max_rank_change':max(x['max_rank_change'] for x in corners),'max_score_change':max(x['max_score_change'] for x in corners),'min_top_intersection':min(x['top_intersection'] for x in corners)}
payload['examples']=sorted([r for r in rows if r['scale']=='s3'],key=lambda r:abs(r['ranks']['推荐']-r['ranks']['纯熵权']),reverse=True)[:5]
payload['stratum_comparison']=[]
for group,g in R.groupby('group'):
 zz=np.array(g.z.tolist());v=100*zz@w
 for name,wt in schemes.items():payload['stratum_comparison'].append(dict(group=group,n=len(g),scheme=name,**compare(100*zz@wt,v)))
assert len(rows)>0 and np.allclose(sum(w),1) and min(w)>=0
assert all(0<=x<=1 for r in rows for x in r['z'])
assert all(0<=r['scores']['推荐']<=100 for r in rows)
(OUT/'work'/'analysis.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:payload[k] for k in ['version','counts','weights','entropy_weights','comparisons','sensitivity','mab_spearman_net','mab_spearman_sessions','loo_max_weight_change']},ensure_ascii=False,indent=2))
