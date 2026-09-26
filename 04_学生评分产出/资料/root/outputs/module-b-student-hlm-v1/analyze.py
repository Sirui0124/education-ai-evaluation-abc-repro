"""Student-level projections of the frozen descriptive Bayesian HLM.

Reconstruct the joint conjugate posterior; never infer AI causal effects.
"""
from pathlib import Path
import json, hashlib, collections
import numpy as np
import pandas as pd
from scipy.linalg import cho_factor, cho_solve
from scipy.stats import t

ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
SRC=ROOT/'outputs/01a0dda3-15fd-7a03-87b0-c2f5fdc4eb14/calculation.json'
REFERENCE=ROOT/'outputs/module-b-causal-original-domain-v1/results.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
data=json.loads(SRC.read_text());reference=json.loads(REFERENCE.read_text())
source_hashes={str(p):sha(p) for p in [SRC,REFERENCE]}
rows=[r for r in data['records'] if r['scale']=='s3'];students=sorted({r['student_key'] for r in rows});domains=sorted({r['domain'] for r in rows})
counts=collections.Counter(r['student_key'] for r in rows);w=np.array([1/counts[r['student_key']] for r in rows]);n=len(rows)
before=np.array([r['before_score'] for r in rows]);spring=np.array([r['semester']=='2026春' for r in rows],float)
bc=float(np.average(before,weights=w));sc=float(np.average(spring,weights=w));y=np.array([r['delta_l'] for r in rows]);remaining=np.array([r['remaining'] for r in rows])
X=np.column_stack([np.ones(n),before-bc,spring-sc]+[np.array([r['domain']==d for r in rows],float) for d in domains]+[np.array([r['student_key']==s for r in rows],float) for s in students])
selectors=[np.array([j for j,r in enumerate(rows) if r['student_key']==s]) for s in students]
assert len(rows)==147 and len(students)==139
fits=[];records=[];components=[];population=[];maximum_reference_error=0
for domain_sd in [.25,.5,1.]:
 for student_sd in [0.,.5,1.]:
  active=np.arange(X.shape[1]) if student_sd else np.arange(3+len(domains));xx=X[:,active]
  sd=np.array([10,2,2]+[domain_sd]*len(domains)+([student_sd]*len(students) if student_sd else []))
  K=np.einsum('ni,n,nj->ij',xx,w,xx)+np.diag(1/sd**2);V=cho_solve(cho_factor(K),np.eye(len(active)));assert np.isfinite(V).all()
  common=np.average(xx,axis=0,weights=w);common[3+len(domains):]=0
  own=np.array([xx[ix].mean(axis=0) for ix in selectors])
  deviations=np.zeros_like(own)
  if student_sd:
   for i in range(len(students)):deviations[i,3+len(domains)+i]=1
  standard=np.repeat(common[None,:],len(students),axis=0)+deviations
  for q in [0.,.23,.48]:
   yy=y-q*remaining;mean=np.einsum('ij,j->i',V,np.einsum('ni,n,n->i',xx,w,yy));a=2+n/2;b=1+.5*(float(np.sum(w*yy*yy))-float(np.einsum('i,ij,j->',mean,K,mean)));df=2*a;assert b>0 and np.isfinite(mean).all()
   def stats(z):
    mu=float(np.sum(z*mean));var=max(float(np.einsum('i,ij,j->',z,V,z)),0)*b/a;se=np.sqrt(var)
    if not se:return dict(mean=mu,low=mu,high=mu,p_positive=None)
    half=t.ppf(.975,df)*se
    return dict(mean=mu,low=float(mu-half),high=float(mu+half),p_positive=float(t.sf(-mu/se,df)))
   pop=stats(common);expected=next(f for f in reference['fits'] if f['q']==q and f['domain_prior_sd_ratio']==domain_sd and f['student_prior_sd_ratio']==student_sd)['standardized_remaining']
   error=max(abs(pop['mean']-expected['mean']),abs(pop['low']-expected['ci95'][0]),abs(pop['high']-expected['ci95'][1]));maximum_reference_error=max(error,maximum_reference_error);assert error<1e-8
   population.append(dict(q=q,domain_sd=domain_sd,student_sd=student_sd,**pop))
   for i,(s,ix) in enumerate(zip(students,selectors)):
    d=dict(student_key=s,term=s.split(':')[0],n_domains=len(ix),domains='；'.join(rows[j]['domain'] for j in ix),q=q,domain_sd=domain_sd,student_sd=student_sd,
           observed_gain=float(y[ix].mean()),external_baseline=float(q*remaining[ix].mean()),raw_remaining=float(yy[ix].mean()),
           baseline_mean=float(before[ix].mean()),source_ids='|'.join(sorted({c for j in ix for c in rows[j]['dialogue_short_ids']})))
    for label,z in [('conditional',own[i]),('standardized',standard[i]),('student_deviation',deviations[i])]:
     d.update({label+'_'+k:v for k,v in stats(z).items()})
    records.append(d)
    if domain_sd==student_sd==.5:
     intercept=float(mean[0]);baseline=float(own[i,1]*mean[1]);term=float(own[i,2]*mean[2]);domain=float(np.sum(own[i,3:3+len(domains)]*mean[3:3+len(domains)]));student=d['student_deviation_mean'];noise=d['raw_remaining']-d['conditional_mean']
     assert abs(intercept+baseline+term+domain+student+noise-d['raw_remaining'])<1e-10
     components.append(dict(student_key=s,q=q,intercept=intercept,baseline_association=baseline,semester_association=term,domain_association=domain,student_deviation=student,unexplained_observation=noise,
                            observed_gain=d['observed_gain'],external_baseline=d['external_baseline'],raw_remaining=d['raw_remaining'],fitted_remaining=d['conditional_mean']))
f=pd.DataFrame(records);main=f[(f.domain_sd==.5)&(f.student_sd==.5)].copy()
envelopes=[]
for (s,q),g in f.groupby(['student_key','q']):
 envelopes.append(dict(student_key=s,q=q,posterior_mean_min=float(g.standardized_mean.min()),posterior_mean_max=float(g.standardized_mean.max()),
                      sensitivity_interval_low=float(g.standardized_low.min()),sensitivity_interval_high=float(g.standardized_high.max()),
                      positive_probability_min=float(g.standardized_p_positive.min()),positive_probability_max=float(g.standardized_p_positive.max()),
                      mean_sign_stable=bool((g.standardized_mean>0).all() or (g.standardized_mean<0).all()),
                      all_intervals_positive=bool((g.standardized_low>0).all()),all_intervals_negative=bool((g.standardized_high<0).all())))
env=pd.DataFrame(envelopes);main=main.merge(env,on=['student_key','q'],validate='one_to_one')
main.to_csv(OUT/'student_posteriors.csv',index=False);f.to_csv(OUT/'prior_sensitivity.csv',index=False)
pd.DataFrame(components).to_csv(OUT/'student_components.csv',index=False);pd.DataFrame(population).to_csv(OUT/'population_posteriors.csv',index=False)
summary=[]
for q,g in main.groupby('q'):
 summary.append(dict(q=float(q),n_students=len(g),conditional_positive_ci=int((g.conditional_low>0).sum()),standardized_positive_ci=int((g.standardized_low>0).sum()),standardized_negative_ci=int((g.standardized_high<0).sum()),student_deviation_ci_excludes_zero=int(((g.student_deviation_low>0)|(g.student_deviation_high<0)).sum()),
                     standardized_positive_all_priors=int(g.all_intervals_positive.sum()),standardized_negative_all_priors=int(g.all_intervals_negative.sum()),mean_sign_changes_with_prior=int((~g.mean_sign_stable).sum())))
manifest=dict(version='student-descriptive-hlm-v1',identified_causal_effect=False,source_hashes=source_hashes,code_sha256=sha(Path(__file__)),
              n_pairs=n,n_students=len(students),student_multiplicity=dict(collections.Counter(counts.values())),n_s6_excluded_from_model=9,
              main_prior=dict(domain_sd_ratio=.5,student_sd_ratio=.5,sigma2='IG(2,1)',fixed_sd_ratios=[10,2,2]),
              centers=dict(before=bc,spring=sc),variance='conditional sigma2 times number of domains per student',
              inference='Exact joint Normal-inverse-Gamma posterior. Student-t linear projections, not MCMC.',
              standardization='Set Before and semester to weighted cohort means, domain mixture to observed student-equal cohort mixture, retain student random effect. Population projection sets student random effects to zero.',
              interval_scope='Conditional on fixed labels, mapping, selection, targets, q and prior ratios; latent mean intervals, not future outcome intervals.',
              maximum_reference_error=maximum_reference_error,summary=summary)
assert source_hashes=={str(p):sha(Path(p)) for p in source_hashes}
dump(OUT/'manifest.json',manifest)
payload=dict(manifest=manifest,students=json.loads(main.to_json(orient='records',double_precision=15)),population=population,components=components,s6=[r for r in data['records'] if r['scale']=='s6'])
dump(OUT/'workbook_data.json',payload)
print(json.dumps(summary,ensure_ascii=False));print('joint posterior reconciled max error',maximum_reference_error)
print(main[(main.q==.23)].head(3)[['student_key','observed_gain','raw_remaining','conditional_mean','standardized_mean','standardized_low','standardized_high','standardized_p_positive']].to_string(index=False))
