import json,collections,hashlib,datetime
from pathlib import Path
import tiktoken
D=Path('workspace/data_clean/module_b_cognitive_full_v5'); O=Path('outputs/annotation-resource-model')
def read(p): return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
enc=tiktoken.get_encoding('cl100k_base')
base=read(D/'baseline/all.jsonl'); high=read(D/'highest/all.jsonl')
stats={}; hashes={}
for scale in ['s6','s3']:
    maps=[]
    for who in ['terra','sol']:
        path=D/f'{who}_baseline_{scale}.jsonl'; rows=read(path)
        assert len(rows)==len({r['id'] for r in rows})==708
        maps.append({r['id']:r['label'] for r in rows});hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    counts=collections.Counter(list(maps[0].values())+list(maps[1].values())); n=sum(counts.values())
    de=sum(c*(n-c) for c in counts.values())/(n*(n-1));do=sum(maps[0][i]!=maps[1][i] for i in maps[0])/708
    stats[scale]={'De':de,'alpha':1-do/de,'disagreements':round(do*708),'n':708}
domains=collections.Counter((r.get('domain') or ['领域待补'])[0] for r in base)
tokens={}
for key,rows in [('baseline',base),('highest',high)]:
    sizes=[len(enc.encode(json.dumps(r,ensure_ascii=False))) for r in rows]
    tokens[key]={'n':len(rows),'mean':sum(sizes)/len(sizes)}
result={'as_of':datetime.datetime.now().isoformat(),'spring_sessions':482,'spring_students':109,'spring_turns':1384,'raw_total':1299,'qa3':708,'qapro':425,'stats':stats,'domains':dict(sorted(domains.items(),key=lambda kv:-kv[1])),'tokens':tokens,'hashes':hashes,'sampling_sources':['https://www.itl.nist.gov/div898/handbook/pmc/section2/pmc232.htm','https://www.asc.upenn.edu/sites/default/files/2021-03/Computing%20Krippendorff%27s%20Alpha-Reliability.pdf']}
(O/'latest_sources.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
