"""Agreement from two independent raters, never from adjudicated labels."""
import importlib.util
import json
import random
from collections import Counter
from pathlib import Path
from validate import read,validate

D=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('legacy_alpha',D.parents[1]/'code/scripts/analyze_cognitive_qapro_v4.py')
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
MAP=legacy.MAP
ORDERS=legacy.ORDERS

def measure(pairs,scheme,bootstrap=False):
    n=len(pairs)
    if not n:return {'n':0}
    nominal,_=legacy.alpha(pairs)
    concrete=[[None if v=='U' else v for v in pair] for pair in pairs]
    ordinal,pairable=legacy.alpha(concrete,'ordinal',ORDERS[scheme])
    gate,_=legacy.alpha([['U' if v=='U' else 'G' for v in p] for p in pairs])
    counts=[Counter(p[i] for p in pairs) for i in range(2)]
    exact=sum(a==b for a,b in pairs)
    result={'n':n,'exact':exact,'agreement_rate':exact/n,'disagreements':n-exact,
        'nominal_alpha_with_u':nominal,'cohen_kappa_with_u':legacy.kappa(pairs,0,1),
        'u_gradable_alpha':gate,'ordinal_alpha_u_missing':ordinal,'both_gradable_n':pairable,
        'both_u':sum(a==b=='U' for a,b in pairs),'concrete_agree':sum(a==b and a!='U' for a,b in pairs),
        'u_rates':{'terra':counts[0]['U']/n,'sol':counts[1]['U']/n},
        'counts':dict(zip(['terra','sol'],[dict(c) for c in counts])),
        'pooled_u_rate':sum(c['U'] for c in counts)/(2*n)}
    if bootstrap:
        rng=random.Random(20260926)
        values=[legacy.alpha([pairs[rng.randrange(n)] for _ in range(n)])[0] for _ in range(2000)]
        result['nominal_alpha_ci95']=legacy.ci(values)
    return result

def main():
    meta={r['id']:r for r in read(D/'metadata.jsonl')}
    baseline={r['id']:r for r in read(D/'baseline/all.jsonl')}
    result={'schema':'two-independent-raters-full-v5','raters':['gpt-5.6-terra','gpt-5.6-sol'],
        'reasoning_effort':'medium','adjudication_excluded':True,
        'protocol':{'primary':'nominal Krippendorff alpha, U as separate category','secondary':'Cohen kappa including U; U/gradable alpha; ordinal alpha with U missing','bootstrap':'2000 paired conversation resamples, seed 20260926; percentile 95% CI','domain_grouping':'first QA3 task domain; conversation maximum can belong to another task, no per-concept gain claim'},'stages':{}}
    for stage in ('baseline','highest'):
        ids=[r['id'] for r in read(D/stage/'all.jsonl')]
        ratings={}
        for scale in ('s6','s3'):
            ratings[scale]=[]
            maps=[]
            for rater in ('terra','sol'):
                path=D/f'{rater}_{stage}_{scale}.jsonl'
                checked=validate(path);assert not checked['errors'],checked
                maps.append({r['id']:r['label'] for r in read(path)})
            ratings[scale]=[[m[i] for m in maps] for i in ids]
        ratings['mapped3']=[[MAP[v] for v in pair] for pair in ratings['s6']]
        groups={'overall':list(range(len(ids)))}
        for term in sorted({meta[i]['term'] for i in ids}):groups['学期:'+term]=[k for k,i in enumerate(ids) if meta[i]['term']==term]
        primary={i:(baseline[i]['domain'] or meta[i]['domains'] or ['领域待补'])[0] for i in ids}
        for domain in sorted(set(primary.values())):groups['首QA3领域:'+domain]=[k for k,i in enumerate(ids) if primary[i]==domain]
        result['stages'][stage]={name:{scheme:measure([pairs[k] for k in indices],scheme,bootstrap=name=='overall') for scheme,pairs in ratings.items()} for name,indices in groups.items()}
    (D/'metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({stage:data['overall'] for stage,data in result['stages'].items()},ensure_ascii=False))

if __name__=='__main__':main()
