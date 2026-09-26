"""Audit application and regenerate descriptive summary, not raw ratings."""
from pathlib import Path
import json, hashlib
from collections import Counter
P=Path(__file__).resolve().parent
def read(p):return [json.loads(x) for x in p.read_text().splitlines() if x]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
c=read(P/'逐对话采纳版.jsonl');a=read(P/'学生领域采纳版.jsonl');s=read(P/'学生指标采纳版.jsonl')
cfg=json.loads((P/'冻结映射.json').read_text());summary=json.loads((P/'summary.json').read_text())
mods={m['module_id']:m for m in cfg['modules']}
all_pairs=read(P/'映射训练成员.jsonl')
accepted=json.loads((P.parent/'module-b-course-mapping/模块映射配对依据.json').read_text())
for mm in mods.values():
 if mm['target_level'] is None:
  assert all(cell['proxy'] is None for fm in mm['heldout_mappings'] for cell in fm['mapping']);continue
 T=int(mm['target_level'][1:])
 for fm in mm['heldout_mappings']:
  f=fm['heldout_fold'];local=[p for p in accepted if p['module_id']==mm['module_id'] and p['fold']!=f]
  keys={(p['id'],p['stage']) for p in local}
  for cell in fm['mapping']:
   pp=[p for p in local if p['s3']==cell['label']]
   parent=[p for p in all_pairs if p['fold']!=f and p['label']==cell['label'] and (p['id'],p['stage']) not in keys]
   prior=sum(min(p['L'],T) for p in parent)/len(parent)
   value=(sum(min(p['L'],T) for p in pp)+10*prior)/(len(pp)+10)
   assert len(pp)==cell['n_pairs'] and len(parent)==cell['parent_n']
   assert abs(value-cell['unconstrained_proxy'])<1e-12
   if not cell['isotonic_adjusted']:assert abs(value-cell['proxy'])<1e-12
for r in c:
 for stage in ['before','after']:
  q=r[stage]
  if q['score'] is None:continue
  if q['scale']=='s6':assert q['score']==int(q['label'][1:])
  else:
   mm=mods[q['module_id']];fm=next(x for x in mm['heldout_mappings'] if x['heldout_fold']==q['fold'])
   expected=next(x['proxy'] for x in fm['mapping'] if x['label']==q['label'])
   assert q['score']==expected and 1<=expected<=int(mm['target_level'][1:])
 if r['delta'] is not None:
  assert abs(r['delta']-(r['after_score']-r['before_score']))<1e-12
  assert r['scale']=='s6' or r['before']['module_id']==r['after']['module_id']
assert len(a)==621 and sum(r['delta_l'] is not None for r in a)==156
assert all(r['before_module']==r['after_module'] for r in a if r['delta_l'] is not None)
assert sum(mm['n_pairs'] for mm in mods.values())==488
assert all(not r.get('before_module') or r['before_module'].startswith('topic-') for r in a)
audit={'version':summary['version'],'student_domain_rows':len(a),'comparable_pairs':156,'fit_pairs':488,'heldout_coefficient_checks':'PASS','point_application_checks':'PASS','taxonomy':'original-topic-domain-v1'}
(P/'module-application-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
manifest={'status':'APPLIED_TO_ADOPTED_STUDENT_SCORES','mapping_version':cfg['version'],'mapping_sha256':sha(P/'冻结映射.json'),'outputs':{str(P/f):sha(P/f) for f in ['逐对话采纳版.jsonl','学生领域采纳版.jsonl','学生指标采纳版.jsonl','逐对话采纳及学生指标.xlsx']},'effect_decomposition_recomputed':True}
(P.parent/'module-b-course-mapping/评分应用状态.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps(audit,ensure_ascii=False))
