#!/usr/bin/env python3
"""QA Pro 130: all-state agreement, U coverage, and grade concentration."""
import csv,json,math,random
from collections import Counter,defaultdict
from itertools import combinations
from pathlib import Path
P=Path(__file__).resolve().parents[2]/"data_clean/module_b_cognitive_qapro_v4"
RATERS=("terra","luna","m55")
ORDERS={"s6":["L1","L2","L3","L4","L5","L6"],"mapped3":["低","中","高"],"s3":["低","中","高"]}
MAP={"L1":"低","L2":"低","L3":"中","L4":"高","L5":"高","L6":"高","U":"U"}
U_REASONS={"NO_DEMONSTRATED_KNOWLEDGE","COPY_ONLY","NO_CORRECT_COMPONENT","MISSING_CONTEXT","DOMAIN_MISMATCH"}

def alpha(rows,kind="nominal",order=None):
 coincidence=defaultdict(float);margin=Counter();pairable=0
 for original in rows:
  row=[z for z in original if z is not None]
  if len(row)<2:continue
  pairable+=1;c=Counter(row)
  for a,na in c.items():
   for b,nb in c.items():
    v=na*(nb-(a==b))/(len(row)-1)
    coincidence[a,b]+=v;margin[a]+=v
 n=sum(margin.values())
 if n<=1:return None,pairable
 used=[x for x in order if margin[x]] if order else []
 if kind=="ordinal" and len(used)<2:return None,pairable
 def delta(a,b):
  if a==b:return 0
  if kind=="nominal":return 1
  i,j=sorted((used.index(a),used.index(b)))
  return (margin[used[i]]/2+sum(margin[used[t]] for t in range(i+1,j))+margin[used[j]]/2)**2
 cats=list(margin)
 do=sum(coincidence[a,b]*delta(a,b) for a in cats for b in cats)/n
 de=sum(margin[a]*margin[b]*delta(a,b) for a in cats for b in cats)/(n*(n-1))
 return (1-do/de if de>0 else None),pairable

def kappa(rows,i,j):
 n=len(rows);a=Counter(r[i] for r in rows);b=Counter(r[j] for r in rows)
 po=sum(r[i]==r[j] for r in rows)/n
 pe=sum(a[z]*b[z] for z in a.keys()|b.keys())/(n*n)
 return (po-pe)/(1-pe) if pe<1 else None

def ci(values):
 v=sorted(x for x in values if x is not None and math.isfinite(x))
 if not v:return None
 return [v[int(.025*(len(v)-1))],v[int(.975*(len(v)-1))]]

def measure(rows,scheme):
 n=len(rows)
 full,_=alpha(rows)
 gate,_=alpha([["U" if z=="U" else "G" for z in row] for row in rows])
 concrete=[[None if z=="U" else z for z in row] for row in rows]
 ordinal,pairable=alpha(concrete,"ordinal",ORDERS[scheme])
 nominal,_=alpha(concrete)
 counts=Counter(z for row in rows for z in row if z!="U")
 total=sum(counts.values());props=[v/total for v in counts.values()] if total else []
 us=[sum(row[i]=="U" for row in rows) for i in range(3)]
 pooled=sum(us)/(n*3)
 maximum=max(props) if props else None
 entropy=-sum(p*math.log(p) for p in props)/math.log(len(ORDERS[scheme])) if props else None
 all_u=sum(all(z=="U" for z in r) for r in rows)
 exact=sum(len(set(r))==1 and r[0]!="U" for r in rows)
 target=.70 if scheme=="s6" else .80
 return {"n":n,"full_nominal_alpha":full,"u_gate_alpha":gate,"concrete_ordinal_alpha":ordinal,"concrete_nominal_alpha":nominal,"pairable_records":pairable,"all_three_graded":sum(all(z!="U" for z in r) for r in rows),"all_u_records":all_u,"specific_exact_records":exact,"all_state_exact_records":exact+all_u,"u_counts_by_rater":dict(zip(RATERS,us)),"u_rates_by_rater":dict(zip(RATERS,[v/n for v in us])),"pooled_u_rate":pooled,"concrete_counts":dict(counts),"modal_share_non_u":maximum,"normalized_entropy_non_u":entropy,"pairwise_kappa_all_states":{RATERS[i]+"-"+RATERS[j]:kappa(rows,i,j) for i,j in combinations(range(3),2)},"target_full_alpha":target,"u_target_pass":max(us)/n<=.20,"alpha_target_pass":full is not None and full>=target,"concentration_pass":maximum is not None and maximum<.75,"pilot_pass":bool(n>=20 and full is not None and full>=target and max(us)/n<=.20 and maximum is not None and maximum<.75 and len(counts)>=(3 if scheme=="s6" else 2))}

def main():
 sample=[json.loads(x) for x in (P/"sample_all130.jsonl").open()];ids=[x["id"] for x in sample]
 assert len(ids)==len(set(ids))==130
 data={};audit={}
 for scheme in ('s6','s3'):
  for rater in RATERS:
   key=rater+'_'+scheme
   labels=[json.loads(x) for x in (P/(key+'.jsonl')).open()]
   assert [x['id'] for x in labels]==ids,(key,'ID order')
   issues=[]
   for inp,lab in zip(sample,labels):
    stud={t['i']:t['text'] for t in inp['turns'] if t['role']=='student'}
    q=lab.get('evidence_quote','');ts=lab.get('evidence_turn_ids',[])
    if lab['label'] not in set(ORDERS[scheme])|{'U'}:issues.append((inp['id'],'label'))
    if lab.get('confidence') not in {'high','medium','low'}:issues.append((inp['id'],'confidence'))
    if lab.get('support') not in {'独立表达','经提示后表达','复述AI','无法判断'}:issues.append((inp['id'],'support'))
    if any(t not in stud for t in ts):issues.append((inp['id'],'student turns'))
    if lab['label']=='U':
     if q or ts:issues.append((inp['id'],'U evidence must empty'))
     if lab.get('u_reason') not in U_REASONS:issues.append((inp['id'],'U reason'))
    else:
     if not q or not any(q in stud[t] for t in ts if t in stud):issues.append((inp['id'],'noncontinuous quote'))
     if lab.get('u_reason') is not None:issues.append((inp['id'],'nonU reason'))
    if not lab.get('reason'):issues.append((inp['id'],'empty reason'))
   audit[key]={'n':len(labels),'issues':issues}
   data[key]={z['id']:z for z in labels}
 result={'protocol':json.loads((P/'manifest.json').read_text())['protocol'],'audit':audit,'overall':{},'domains':{},'u_reasons':{}}
 rng=random.Random(20260926)
 for domain in ['ALL']+list(dict.fromkeys(x['domain'] for x in sample)):
  sub=[x for x in sample if domain=='ALL' or x['domain']==domain];target=result['overall'] if domain=='ALL' else result['domains'].setdefault(domain,{})
  for scheme in ('s6','mapped3','s3'):
   rows=[[data[r+'_'+('s6' if scheme=='mapped3' else scheme)][x['id']]['label'] for r in RATERS] for x in sub]
   if scheme=='mapped3':rows=[[MAP[z] for z in row] for row in rows]
   m=measure(rows,scheme)
   if domain=='ALL':
    draws=[]
    for _ in range(2000):
     draw=[rows[rng.randrange(len(rows))] for __ in rows]
     val,_=alpha(draw);draws.append(val)
    m['full_nominal_alpha_ci95']=ci(draws)
   target[scheme]=m
 for scope in [result['overall']]+list(result['domains'].values()):
  for scheme,m in scope.items():
   original='s6' if scheme=='mapped3' else scheme
   m['annotation_audit_pass']=all(not audit[r+'_'+original]['issues'] for r in RATERS)
   m['pilot_pass']=m['pilot_pass'] and m['annotation_audit_pass']
 for key,byid in data.items():result['u_reasons'][key]=dict(Counter(z.get('u_reason') for z in byid.values() if z['label']=='U'))
 (P/'metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 with (P/'record_labels.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['id','session_id','domain','topic']+[r+'_'+s for s in ('s6','mapped3','s3') for r in RATERS])
  for x in sample:
   vals=[]
   for s in ('s6','mapped3','s3'):
    for r in RATERS:
     z=data[r+'_'+('s6' if s=='mapped3' else s)][x['id']]['label'];vals.append(MAP[z] if s=='mapped3' else z)
   w.writerow([x['id'],x['session_id'],x['domain'],x['topic']]+vals)
 print(json.dumps({'audit':{k:len(v['issues']) for k,v in audit.items()},'overall':result['overall']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
