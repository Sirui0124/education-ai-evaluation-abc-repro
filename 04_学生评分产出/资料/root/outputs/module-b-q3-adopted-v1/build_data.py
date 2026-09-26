"""Adopt existing ratings; do not create new cognitive labels."""
from pathlib import Path
from collections import defaultdict, Counter
import json, hashlib, shutil, csv, statistics

ROOT=Path('/Users/sirui/Documents/ChatGPT/数学建模')
OUT=Path(__file__).resolve().parent
D=ROOT/'workspace/data_clean/module_b_cognitive_full_v5'
KEY=ROOT/'outputs/01a0dced-dc37-7133-824b-3061277eee78/模块B问题3_学生领域认知层级明细.xlsx'
BACKUP=OUT/'backup/模块B问题3_学生领域认知层级明细_原六级.xlsx'
MODEL='数学建模综合与案例'
DIRECT_SIX_DOMAINS={MODEL,'数学基础'}
def read(p):return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
def dump(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2))
def jl(p,rows):p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def scale(d):return 's6' if d in DIRECT_SIX_DOMAINS else 's3'
def fold(s):return int(hashlib.sha256(s.encode()).hexdigest()[:8],16)%5

BACKUP.parent.mkdir(parents=True,exist_ok=True)
if not BACKUP.exists():shutil.copy2(KEY,BACKUP)
source_hash=digest(BACKUP)
rows=read(D/'final_rows.jsonl');meta={r['id']:r for r in rows}
inputs={r['id']:r for r in read(D/'baseline/all.jsonl')}
for r in rows:r['domains']=['其他与待判定' if d=='其他领域' else d for d in r['domains']]
for r in inputs.values():r['domain']=['其他与待判定' if d=='其他领域' else d for d in r['domain']]
aligned={r['id']:r for r in read(ROOT/'workspace/data_clean/module_b_domain_qa3_calibrated/aligned_sessions.jsonl')}
labels={f'{st}_{sc}':{r['id']:r for r in read(D/f'final_{st}_{sc}.jsonl')} for st in ['baseline','highest'] for sc in ['s6','s3']}
lineage={(r['id'],r['stream']):r for r in read(D/'evidence_lineage.jsonl')}
mapping=json.loads((ROOT/'outputs/module-b-course-mapping/模块映射配置.json').read_text())
for path,expected in mapping['sources'].items():assert digest(Path(path))==expected,(path,'source drift')
modules={m['module_id']:m for m in mapping['modules']}
maps={m['module_id']:{f['heldout_fold']:{v['label']:v['proxy'] for v in f['mapping']} for f in m['heldout_mappings']} for m in mapping['modules']}
point_domains={(r['id'],r['stream']):r for r in read(ROOT/'workspace/data_clean/module_b_topic_domain_unified_v1/point_domains.jsonl')}
domain_ids={m['name']:m['module_id'] for m in mapping['modules']}
pairs=[]
for r in rows:
 for st,c3,c6 in [('baseline','qa3_three','qa3_l'),('highest','highest_three','highest_l')]:
  if r[c3] in ['低','中','高'] and r[c6] in ['L1','L2','L3','L4','L5','L6']:
   pairs.append({'student_key':r['student_key'],'id':r['id'],'stage':st,'label':r[c3],'L':int(r[c6][1:]),'fold':fold(r['student_key'])})
assert len(pairs)==mapping['source_counts']['global_pairs']==519
for mm in maps.values():
 for v in mm.values():
  if v['低'] is not None:assert v['低']<=v['中']<=v['高']
dump(OUT/'冻结映射.json',mapping)
jl(OUT/'映射训练成员.jsonl',pairs)

def module_for(rid,stream):
 p=point_domains.get((rid,stream),{})
 candidates=[domain_ids[d] for d in p.get('domains',[])]
 return p.get('domain_id'),candidates

def pair_status(b,a):
 if b['score'] is None or a['score'] is None:return 'BEFORE_'+b['status'] if b['score'] is None else 'AFTER_'+a['status']
 if b['scale']=='s3' and b['module_id']!=a['module_id']:return 'MODULE_MISMATCH'
 return 'COMPARABLE'

def domains_for(rid,stream):
 l=lineage[rid,stream]; turns=set(l['evidence_turn_ids'])
 # Match the selected literal quote, not unrelated turns from a broader task.
 lab=labels[stream][rid]
 actual={t['turn_index'] for t in aligned[rid]['turns'] if t['role']=='student' and t['turn_index'] in turns and lab['evidence_quote'] and lab['evidence_quote'] in t['text']}
 if lab['label']!='U':assert actual,(rid,stream,'quote mismatch')
 units={u['domain'] for u in l.get('domain_units',[]) if set(u.get('matched_student_turn_ids',[])) & actual and u.get('domain')}
 if units:return sorted(units)
 tasks=[t for t in aligned[rid]['tasks'] if t.get('is_qa3') and any(t['turn_start']<=i<=t['turn_end'] for i in actual)]
 return sorted({d for t in tasks for d in t.get('domains',[])})

def point(rid,st,sc,d):
 r=meta[rid];stream=st+'_'+sc; lab=labels[stream].get(rid)
 out={'id':rid,'session_id':r['session_id'],'domain':d,'stage':st,'scale':sc,'time':r['time'],'label':None,'score':None,'display':'NA','status':'NOT_ASSESSED','turn_ids':[],'quote':'','mapped_domains':[],'fold':fold(r['student_key']),'module_id':None,'module_candidates':[]}
 if not lab:return out
 if lab['label']=='U':
  candidates=sorted(set(inputs[rid]['domain'])) if st=='baseline' else sorted(set(r['domains']))
 else:candidates=domains_for(rid,stream)
 out['mapped_domains']=candidates
 if candidates!=[d]:out['status']='DOMAIN_UNVERIFIED';return out
 if st=='baseline' and sorted(set(inputs[rid]['domain']))!=[d]:out['status']='DOMAIN_UNVERIFIED';return out
 out.update(label=lab['label'],turn_ids=lab['evidence_turn_ids'],quote=lab['evidence_quote'],status='U' if lab['label']=='U' else 'OBSERVED',decision_source=lab['decision_source'])
 if lab['label']=='U':out['display']='U';return out
 if sc=='s6':out.update(module_id=domain_ids[d],module_candidates=[domain_ids[d]]);out['score']=int(lab['label'][1:]);out['display']=lab['label']
 else:
  mid,candidates=module_for(rid,stream);out.update(module_id=mid,module_candidates=candidates)
  if mid is None:out['status']='MODULE_UNVERIFIED';return out
  out.update(module_name=modules[mid]['name'],module_target=modules[mid]['target_level'],module_mapping_status='ORIGINAL_TOPIC_EVIDENCE')
  fm=next(x for x in modules[mid]['heldout_mappings'] if x['heldout_fold']==out['fold'])
  cell=next(x for x in fm['mapping'] if x['label']==lab['label'])
  out.update(mapping_version=mapping['version'],estimate_status=cell['estimate_status'])
  out['score']=maps[mid][out['fold']][lab['label']]
  if out['score'] is None:out['status']='TARGET_UNDEFINED';return out
  out['display']=f"{out['score']:.3f}（{lab['label']}·{mid}折算）"
 return out

def evidence(p):
 return [{'dialogue_id':p['session_id'],'conversation_id':p['id'],'turn_ids':p['turn_ids'],'module_id':p['module_id'],'status':p['status']}] if p['turn_ids'] else []

conv=[];detail=[];groups=defaultdict(list)
for r in rows:
 rid=r['id'];bdomains=sorted(set(inputs[rid]['domain']));primary=bdomains[0] if len(bdomains)==1 else None
 sc=scale(primary);b=point(rid,'baseline',sc,primary);a=point(rid,'highest',sc,primary)
 valid=pair_status(b,a)=='COMPARABLE'
 # At conversation level, retain task comparability separately from domain comparability.
 bt=set(lineage[rid,'baseline_'+sc]['task_ids']);at=set(lineage.get((rid,'highest_'+sc),{}).get('task_ids',[]))
 same_task=bool(bt&at)
 conv.append({'id':rid,'session_id':r['session_id'],'student_key':r['student_key'],'term':r['term'],'time':r['time'],'classification':r['classification'],'domain':primary,'scale':sc,'scale_status':'探索性直接六级' if sc=='s6' else '独立三级经验折算','before':b,'after':a,'before_score':b['score'],'after_score':a['score'],'delta':a['score']-b['score'] if valid else None,'same_task':same_task,'comparable_task_delta':a['score']-b['score'] if valid and same_task else None,'raw_s6_before':r['qa3_l'],'raw_s6_after':r['highest_l'],'raw_s3_before':r['qa3_three'],'raw_s3_after':r['highest_three'],'all_qa3_domains':r['domains']})
 conv[-1]['pair_status']=pair_status(b,a)
 for d in r['domains']:
  item={'id':rid,'session_id':r['session_id'],'student_key':r['student_key'],'domain':d,'time':r['time'],'scale':scale(d),'before':point(rid,'baseline',scale(d),d),'after':point(rid,'highest',scale(d),d)}
  detail.append(item);groups[r['student_key'],d].append(item)

aggregated=[]
for (student,d),items in sorted(groups.items()):
 items.sort(key=lambda i:(i['time'] or '',i['id']))
 # First relevant conversation is authoritative. Never skip U/unavailable to use a later baseline.
 b=items[0]['before'];numeric=[i['after'] for i in items if i['after']['score'] is not None]
 if numeric:
  best=max(p['score'] for p in numeric);peaks=[p for p in numeric if p['score']==best];a=peaks[0]
 else:
  peaks=[];a=next((i['after'] for i in items if i['after']['status']=='U'),items[0]['after'])
 valid=pair_status(b,a)=='COMPARABLE'
 delta=a['score']-b['score'] if valid else None
 category_high=valid and (delta>=3 if scale(d)=='s6' else b['label']=='低' and a['label']=='高')
 category_low=valid and (delta<=1 if scale(d)=='s6' else b['label']==a['label'])
 aggregated.append({'student_key':student,'domain':d,'scale':scale(d),'before_l':b['display'],'after_l':a['display'],'before_raw_label':b['label'],'after_raw_label':a['label'],'before_score':b['score'],'after_score':a['score'],'delta_l':delta,'before_evidence':evidence(b),'after_evidence':[loc for p in peaks for loc in evidence(p)],'dialogue_ids':[i['session_id'] for i in items],'dialogue_short_ids':[i['id'] for i in items],'before_status':b['status'],'after_status':a['status'],'domain_pair_valid':valid,'same_task': bool(valid and any(p['id']==b['id'] and set(lineage[b['id'],'baseline_'+scale(d)]['task_ids'])&set(lineage[p['id'],'highest_'+scale(d)]['task_ids']) for p in peaks)),'after_unobserved_conversations':sum(i['after']['score'] is None for i in items),'high_progress_literal':valid and delta>=3,'low_progress_literal':valid and delta<=1,'high_progress_category':bool(category_high),'low_progress_category':bool(category_low),'fold':fold(student)})
 aggregated[-1].update(pair_status=pair_status(b,a),before_module=b['module_id'],after_module=a['module_id'])
assert len(aggregated)==621 and len(conv)==708
assert len({(r['student_key'],r['domain']) for r in aggregated})==621
for r in aggregated:
 for loc in r['before_evidence']+r['after_evidence']:assert loc['dialogue_id'] in r['dialogue_ids']
 if r['delta_l'] is not None:assert abs(r['delta_l']-(r['after_score']-r['before_score']))<1e-12
jl(OUT/'逐对话采纳版.jsonl',conv)
jl(OUT/'逐对话领域证据.jsonl',detail)
jl(OUT/'学生领域采纳版.jsonl',aggregated)
jl(OUT/'领域不可核对清单.jsonl',[r for r in detail if 'DOMAIN_UNVERIFIED' in (r['before']['status'],r['after']['status'])])

# Recompute the user's individual metrics from all included conversations, not the scored subset.
sessions=read(ROOT/'workspace/data_clean/module_a_student_panel/conversation_sessions.jsonl')
hier={r['session_id']:r for r in read(ROOT/'workspace/data_clean/module_b_full_hierarchy_v1/conversation_labels.jsonl')}
sessions_by=defaultdict(list)
for r in sessions:sessions_by[r['student_key']].append(r)
conv_by={r['session_id']:r for r in conv};agg_by=defaultdict(list)
for r in aggregated:agg_by[r['student_key']].append(r)
def ratio(n,d):return n/d if d else None
metrics=[]
for student,dr in sorted(agg_by.items()):
 raw=sessions_by[student];inc=[s for s in raw if hier.get(s['session_id'],{}).get('exclusion_status')=='不剔除']
 agents=[hier[s['session_id']].get('agent_type') or s.get('agent_type') for s in inc];known=[a for a in agents if a]
 counts=Counter(hier[s['session_id']]['interaction_tier'] for s in inc);pro=[s for s in inc if hier[s['session_id']]['interaction_tier']=='QA Pro']
 # Highest performance is a whole-conversation indicator; use the selected scale by unique first domain.
 vals=[];unknown=Counter();scs=Counter();rawhi=0
 for s in pro:
  c=conv_by.get(s['session_id'])
  if not c:unknown['missing']+=1;continue
  sc=c['scale'];lab=labels['highest_'+sc][c['id']]['label'];scs[sc]+=1
  if lab=='U':unknown['U']+=1;continue
  if sc=='s6':v=int(lab[1:])
  else:
   mid,_=module_for(c['id'],'highest_s3')
   if mid is None:unknown['missing']+=1;continue
   v=maps[mid][fold(student)][lab]
   if v is None:unknown['missing']+=1;continue
  vals.append(v)
  if c['raw_s6_after'] in ['L3','L4','L5','L6']:rawhi+=1
 numeric=[r for r in dr if r['delta_l'] is not None]
 nh=[r for r in numeric if r['high_progress_literal']];ch=[r for r in numeric if r['high_progress_category']]
 metrics.append({'student_key':student,'raw_session_count':len(raw),'included_session_count':len(inc),'excluded_session_count':len(raw)-len(inc),'observed_agent_distribution':dict(Counter(known)) if known else None,'observed_agent_category_count':len(set(known)) if known else None,'agent_observation_coverage':ratio(len(known),len(inc)),'observed_cross_agent_indicator':len(set(known))>=2 if known else None,'ab3_inclusive_count':counts['仅QA3']+counts['QA Pro'],'ab3_inclusive_share_all_included':ratio(counts['仅QA3']+counts['QA Pro'],len(inc)),'abpro_count':len(pro),'abpro_share_all_included':ratio(len(pro),len(inc)),'abpro_share_ab3_inclusive':ratio(len(pro),counts['仅QA3']+counts['QA Pro']),'ability_adopted_ge3_count':sum(v>=3 for v in vals),'ability_adopted_ge3_share_all_abpro':ratio(sum(v>=3 for v in vals),len(pro)),'ability_adopted_ge3_share_scorable':ratio(sum(v>=3 for v in vals),len(vals)),'ability_scorable_count':len(vals),'ability_u_count':unknown['U'],'ability_missing_count':unknown['missing'],'ability_scale_counts':dict(scs),'computable_domain_count':len(numeric),'na_domain_count':len(dr)-len(numeric),'high_literal':bool(nh),'low_literal':bool(numeric) and all(r['low_progress_literal'] for r in numeric),'high_category':bool(ch),'low_category':bool(numeric) and all(r['low_progress_category'] for r in numeric),'high_domain_count_literal':len(nh),'high_domain_count_category':len(ch),'high_delta_sum_literal':sum(r['delta_l'] for r in nh),'high_delta_sum_category':sum(r['delta_l'] for r in ch)})
jl(OUT/'学生指标采纳版.jsonl',metrics)
summary={'version':'adopted-v1','backup_sha256':source_hash,'raw_labels_sha256':digest(D/'final_rows.jsonl'),'mapping_sha256':digest(OUT/'冻结映射.json'),'n_calibration_pairs':len(pairs),'students':len(metrics),'conversations':len(conv),'student_domains':len(aggregated),'conversation_scales':dict(Counter(r['scale'] for r in conv)),'student_domain_scales':dict(Counter(r['scale'] for r in aggregated)),'computable_conversation_pairs':sum(r['delta'] is not None for r in conv),'computable_student_domain_pairs':sum(r['delta_l'] is not None for r in aggregated),'na_student_domain_pairs':sum(r['delta_l'] is None for r in aggregated),'literal_high_students':sum(r['high_literal'] for r in metrics),'literal_low_students':sum(r['low_literal'] for r in metrics),'category_high_students':sum(r['high_category'] for r in metrics),'category_low_students':sum(r['low_category'] for r in metrics),'group_medians':{}}
for definition in ['literal','category']:
 for side in ['high','low']:
  group=[r for r in metrics if r[f'{side}_{definition}']]
  summary['group_medians'][f'{side}_{definition}']={'n':len(group),**{k:statistics.median(v) if (v:=[r[k] for r in group if r[k] is not None]) else None for k in ['included_session_count','ab3_inclusive_share_all_included','abpro_share_all_included','observed_agent_category_count','ability_adopted_ge3_share_all_abpro']}}
old={r['student_key']:r for r in read(ROOT/'outputs/module-b-q3-student-progress-analysis/学生指标与候选清单.jsonl')}
unchanged=['raw_session_count','included_session_count','ab3_inclusive_share_all_included','abpro_share_all_included','observed_agent_category_count','observed_agent_distribution']
for r in metrics:
 if r['student_key'] in old:
  for k in unchanged:assert r.get(k)==old[r['student_key']].get(k),(r['student_key'],k)
summary['old_136_students_willingness_unchanged']=True
summary['version']='adopted-v4-original-topic-domain'
summary['pair_status_counts']=dict(Counter(r['pair_status'] for r in aggregated))
summary['conversation_point_status_counts']={st:dict(Counter(r[st]['status'] for r in conv)) for st in ['before','after']}
summary['module_mapping_version']=mapping['version']
summary['module_fit_pairs']=mapping['source_counts']['accepted_module_pairs']
previous=OUT/'backup/before-course-module-mapping'
old_agg={(r['student_key'],r['domain']):r for r in read(previous/'学生领域采纳版.jsonl')}
for r in aggregated:
 if r['scale']=='s6':
  for k in ['before_score','after_score','delta_l']:assert r[k]==old_agg[r['student_key'],r['domain']][k]
old_metrics={r['student_key']:r for r in read(previous/'学生指标采纳版.jsonl')}
for r in metrics:
 for k in unchanged:assert r[k]==old_metrics[r['student_key']][k]
summary['all_369_willingness_unchanged']=True
summary['all_direct_six_scores_unchanged']=True
summary['direct_six_domains']=sorted(DIRECT_SIX_DOMAINS)
first_basic=[r for r in rows if (inputs[r['id']].get('domain') or r['domains'] or ['领域待补'])[0]=='数学基础']
any_basic=[r for r in rows if '数学基础' in r['domains']]
summary['math_basic_scope']={'first_domain_conversations':len(first_basic),'first_domain_tiers':dict(Counter(r['classification'] for r in first_basic)),'any_domain_conversations':len(any_basic),'any_domain_tiers':dict(Counter(r['classification'] for r in any_basic)),'first_domain_ids':[r['id'] for r in first_basic],'any_domain_ids':[r['id'] for r in any_basic]}
dump(OUT/'summary.json',summary)
dump(OUT/'workbook-data.json',{'domains':aggregated,'conversations':conv,'students':metrics,'summary':summary})
print(json.dumps(summary,ensure_ascii=False,indent=2))
