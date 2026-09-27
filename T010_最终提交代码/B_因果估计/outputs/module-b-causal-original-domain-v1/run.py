from pathlib import Path
import json,hashlib,csv,collections
import numpy as np
from scipy.linalg import cho_factor,cho_solve
from scipy.stats import t
R=Path(__file__).resolve().parents[2];O=Path(__file__).parent
src=R/'outputs/01a0dda3-15fd-7a03-87b0-c2f5fdc4eb14/calculation.json'
data=json.loads(src.read_text()); allrows=data['records']; rows=[r for r in allrows if r['scale']=='s3']; students=sorted({r['student_key'] for r in rows}); domains=sorted({r['domain'] for r in rows})
ns=collections.Counter(r['student_key'] for r in rows); w=np.array([1/ns[r['student_key']] for r in rows]); n=len(rows)
before=np.array([r['before_score'] for r in rows]);semester=np.array([r['semester']=='2026春' for r in rows],float); center=float(np.average(before,weights=w)); scenter=float(np.average(semester,weights=w))
X=np.column_stack([np.ones(n),before-center,semester-scenter]+[np.array([r['domain']==d for r in rows],float) for d in domains]+[np.array([r['student_key']==s for r in rows],float) for s in students]);p=X.shape[1]
y=np.array([r['delta_l'] for r in rows]);remaining=np.array([r['remaining'] for r in rows]); names=['intercept','baseline_centered','spring_vs_fall']+['domain:'+d for d in domains]+['student:'+s for s in students]
# Proper Normal-inverse-Gamma hierarchical model. Conditional random-effect SDs scale with residual sigma.
# y | beta,sigma2 ~ N(X beta, sigma2 diag(1/w)). beta | sigma2 ~ N(0, sigma2 D).
# sigma2 ~ IG(2,1). Student/domain variances fixed on a declared sensitivity grid, not learned from sparse repeats.
fits=[]
for domain_sd in [.25,.5,1.]:
 for student_sd in [0.,.5,1.]:
  active=np.arange(p) if student_sd else np.arange(3+len(domains)); xx=X[:,active]
  sd=np.array([10,2,2]+[domain_sd]*len(domains)+([student_sd]*len(students) if student_sd else [])); V=cho_solve(cho_factor(xx.T@(w[:,None]*xx)+np.diag(1/sd**2)),np.eye(len(active)))
  target=np.average(xx,axis=0,weights=w); target[3+len(domains):]=0 # marginalize student random effects, retain target cohort's observed domain mix
  for q in [0.,.23,.48]:
   yy=y-q*remaining; mean=V@(xx.T@(w*yy)); a=2+n/2; b=1+.5*(float(yy@(w*yy))-float(mean@np.linalg.solve(V,mean))); assert b>0
   def stat(z):
    m=float(z@mean);se=float(np.sqrt(b/a*(z@V@z)));return {'mean':m,'ci95':[m-t.ppf(.975,2*a)*se,m+t.ppf(.975,2*a)*se]}
   fit={'q':q,'domain_prior_sd_ratio':domain_sd,'student_prior_sd_ratio':student_sd,'standardized_remaining':stat(target),'baseline_coefficient':stat(np.eye(len(active))[1]),'spring_association':stat(np.eye(len(active))[2]),'residual_variance_posterior_mean':b/(a-1)}
   if domain_sd==.5 and student_sd==.5:
    fit['domain_deviations']={d:stat(np.eye(len(active))[3+j]) for j,d in enumerate(domains)}
   fits.append(fit)
# Empirical student-equal summary with student cluster bootstrap; mappings and targets remain frozen.
rng=np.random.default_rng(20260926); sm=np.array([[np.mean([r[k] for r in rows if r['student_key']==s]) for k in ['delta_l','remaining']] for s in students]); boot=np.mean(sm[rng.integers(0,len(students),(10000,len(students)))],axis=1)
scenarios=[]
for q in [0,.23,.48]:
 vals=boot[:,0]-q*boot[:,1];scenarios.append({'q':q,'student_equal_mean':float(np.mean(sm[:,0]-q*sm[:,1])),'conditional_cluster_bootstrap_ci95':np.quantile(vals,[.025,.975]).tolist()})
trans=collections.Counter((r['before_raw_label'],r['after_raw_label']) for r in rows)
# All observed outcome pairs come from AI dialogue; there is no observed untreated treatment arm.
treatment=np.ones(n);rank=np.linalg.matrix_rank(np.column_stack([np.ones(n),treatment]));assert rank==1
result={'version':'causal-original-domain-v1','source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'scope':{'all_pairs':len(allrows),'s3_pairs':n,'s3_students':len(students),'s3_domains':len(domains),'s6_pairs_reported_separately':len(allrows)-n,'student_repeats':dict(collections.Counter(ns.values())),'spring_pairs':int(semester.sum()),'spring_students':len({r['student_key'] for r in rows if r['semester']=='2026春'})},'identification':{'ai_effect':'NOT_IDENTIFIED','verified_no_ai_controls':0,'true_pre_ai_baseline':'UNVERIFIED','intercept_plus_ai_indicator_rank':int(rank),'n_columns':2,'psm':'NOT_ESTIMABLE_NO_CONTROL_ARM','did':'NOT_ESTIMABLE_NO_CONTROL_PREPOST_PANEL','hlm':'FITTED_DESCRIPTIVE_BAYESIAN_HIERARCHY'},'priors':{'sigma2':'InverseGamma(shape=2,scale=1)','fixed_effect_sd_ratios':[10,2,2],'domain_sd_ratios':[.25,.5,1],'student_sd_ratios':[0,.5,1],'conditional_noise_variance':'sigma2 * number_of_comparable_domains_for_this_student','before_weighted_center':center,'semester_weighted_center':scenter},'scenarios':scenarios,'critical_q':float(sm[:,0].mean()/sm[:,1].mean()),'transition_counts':[{'before':a,'after':b,'n':c} for (a,b),c in sorted(trans.items())],'fits':fits,'limitations':['Empirical index, not equal-interval Bloom levels','Highest after is opportunity-sensitive and not a final independent test','Baseline may be post-treatment; current adjustment is descriptive','Intervals condition on frozen mapping, targets and selected observable sample','Fixed variance-ratio priors sensitivity, not data-estimated heterogeneity variances','No independent pretreatment achievement, socioeconomic mix, or validated control arm']}
(O/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
with (O/'analysis_rows.csv').open('w') as f:
 wr=csv.DictWriter(f,fieldnames=['student_key','domain','semester','scale','before_score','after_score','delta_l','target','remaining']);wr.writeheader();wr.writerows({k:r[k] for k in wr.fieldnames} for r in rows)
print(json.dumps({k:result[k] for k in ['scope','identification','scenarios','critical_q']},ensure_ascii=False));print(json.dumps([f for f in fits if f['domain_prior_sd_ratio']==.5 and f['student_prior_sd_ratio']==.5],ensure_ascii=False))
