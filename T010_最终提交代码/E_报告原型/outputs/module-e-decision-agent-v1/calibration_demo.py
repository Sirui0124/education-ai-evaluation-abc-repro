"""Synthetic module E calibration demo. No real student records or external calls."""
import csv, json, random, hashlib
from pathlib import Path
from collections import defaultdict
ROOT=Path(__file__).resolve().parent
STRATA=['low_easy','low_hard','high_easy','high_hard']

def calibrate(rows, weights=None, minimum=10):
    weights=weights or dict.fromkeys(STRATA,.25)
    if abs(sum(weights.values())-1)>1e-9 or any(w<0 for w in weights.values()):
        raise ValueError('invalid reference weights')
    groups=defaultdict(list)
    for r in rows:
        if r['outcome'] not in (None,0,1): raise ValueError('invalid outcome')
        if r['outcome'] is not None: groups[r['stratum']].append(r['outcome'])
    observed=[r['outcome'] for r in rows if r['outcome'] is not None]
    result={'n':len(rows),'observed':len(observed),'coverage':len(observed)/len(rows) if rows else 0,
      'raw':sum(observed)/len(observed) if observed else None,
      'status':'COMPARABLE','adjusted':None,'ci_low':None,'ci_high':None}
    if result['coverage']<.8 or any(len(groups[k])<minimum for k,w in weights.items() if w>0):
        result['status']='INSUFFICIENT_SUPPORT'; return result
    result['adjusted']=sum(weights[k]*sum(groups[k])/len(groups[k]) for k in weights if weights[k]>0)
    rng=random.Random(20260926)
    boots=sorted(sum(weights[k]*sum(rng.choices(groups[k],k=len(groups[k])))/len(groups[k]) for k in weights if weights[k]>0) for _ in range(1000))
    result['ci_low'],result['ci_high']=boots[24],boots[974]
    return result

def main():
    specs=[('A','autumn',[20,20,80,80],[.4,.2,.8,.6]),('B','autumn',[80,80,20,20],[.5,.3,.9,.7]),
           ('A','spring',[50]*4,[.5,.3,.9,.7]),('B','spring',[50]*4,[.6,.4,.9,.7])]
    rows=[]
    for cls,term,ns,ps in specs:
        for stratum,n,prob in zip(STRATA,ns,ps):
            for j in range(n):
                rows.append(dict(synthetic=True,student_id=f'SIM-{len(rows)+1:04}',class_id=cls,term=term,
                    domain='common-anchor-domain',rubric_version='sim-v1',stratum=stratum,outcome=int(j<round(n*prob))))
    with (ROOT/'synthetic_students.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summaries=[]
    for cls,term,_,_ in specs:
        summaries.append(dict(synthetic=True,class_id=cls,term=term,**calibrate([r for r in rows if r['class_id']==cls and r['term']==term])))
    with (ROOT/'comparison.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(summaries[0]));w.writeheader();w.writerows(summaries)
    checks={
      'composition_reversal': summaries[0]['raw']>summaries[1]['raw'] and summaries[0]['adjusted']<summaries[1]['adjusted'],
      'balanced_reference_identity':abs(summaries[2]['raw']-summaries[2]['adjusted'])<1e-9,
      'sparse_refused':calibrate(rows[:5])['adjusted'] is None,
      'missing_not_zero':calibrate([{**r,'outcome':None} for r in rows[:200]])['raw'] is None,
      'no_overlap_refused':calibrate([r for r in rows[:200] if r['stratum']!='low_hard'])['status']=='INSUFFICIENT_SUPPORT',
      'unique_students':len({r['student_id'] for r in rows})==800}
    assert all(checks.values()), checks
    (ROOT/'verification.json').write_text(json.dumps(checks,indent=2))
    (ROOT/'simulation_manifest.json').write_text(json.dumps({'synthetic':True,'n':800,'seed':20260926,'bootstrap':1000,
       'reference_weights':dict.fromkeys(STRATA,.25),'data_design':'fixed constructed stratum counts; bootstrap is illustrative only',
       'unit':'one independent fictional student per row; spring and autumn are different cohorts',
       'thresholds':'minimum observed cell 10; coverage .8; demonstration policy, not validated standard',
       'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2))
    print(json.dumps(summaries,indent=2))
if __name__=='__main__': main()
