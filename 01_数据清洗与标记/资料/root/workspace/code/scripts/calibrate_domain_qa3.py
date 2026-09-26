#!/usr/bin/env python3
"""Join existing domains to v3.1 task stages by source session ID and verified turns."""
import collections
import csv
import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VALIDITY = ROOT / 'workspace/data_clean/module_b_dialogue_validity_v3_1_full'
DOMAIN = Path('/Users/sirui/CC/Sirui/Work/11-AI/5_Hackathon/项目/260927数学建模/模块A思路/教学对话漏斗')
OUT = ROOT / 'workspace/data_clean/module_b_domain_qa3_calibrated'

def read(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')

def main():
    OUT.mkdir(exist_ok=True, parents=True)
    sources = {'validity':VALIDITY/'annotations.jsonl','funnel':DOMAIN/'annotations.jsonl','domains':DOMAIN/'topics_v1/annotations.jsonl'}
    hashes = {k:digest(v) for k,v in sources.items()}
    current, previous, topics = (read(sources[k]) for k in ('validity','funnel','domains'))
    old_by_id = {r['id']:r for r in previous}
    old_by_session = {r['session_id']:r for r in previous}
    domain_by_session = {old_by_id[r['id']]['session_id']:r for r in topics}
    assert len(current)==len(previous)==len(old_by_session)==1299
    assert {r['session_id'] for r in current}==set(old_by_session)
    assert len(domain_by_session)==len(topics)==748
    rows=[]; role_conflicts=[]; gaps=[]; domain_tasks=collections.defaultdict(set); transition=collections.Counter()
    for r in current:
        old=old_by_session[r['session_id']]
        assert old['id']==r['id']
        domain=domain_by_session.get(r['session_id'])
        turns={t['turn_index']:t for t in r['turns']}
        units=[]
        for i,u in enumerate(domain['units'] if domain else [],1):
            # No semantic relabeling; preserve the entire original domain unit.
            good=[t for t in u['student_turn_ids'] if t in turns and turns[t]['role']=='student']
            rejected=[t for t in u['student_turn_ids'] if t not in good]
            for e in u['evidence']:
                assert e['turn_index'] in turns and e['quote'] in turns[e['turn_index']]['text'],(r['id'],i,'quote mismatch')
            if rejected:role_conflicts.append({'id':r['id'],'domain_unit_id':f"{r['id']}-D{i:02d}",'excluded_student_turn_ids':rejected})
            units.append({'domain_unit_id':f"{r['id']}-D{i:02d}",'original':u,'verified_student_turn_ids':good,'excluded_student_turn_ids':rejected})
        tasks=[]
        for i,s in enumerate(r['segments'],1):
            task_id=f"{r['id']}-Q{i:02d}"
            links=[]
            for u in units:
                overlap=[t for t in u['verified_student_turn_ids'] if s['turn_start']<=t<=s['turn_end']]
                if overlap:links.append({'domain_unit_id':u['domain_unit_id'],'domain':u['original']['domain'],'overlap_student_turn_ids':overlap,'matched_effective_turn_ids':sorted(set(overlap)&set(s['effective_student_turns']))})
            domains=sorted({u['domain'] for u in links})
            if s['label']=='QA3':
                if not domains:gaps.append({'id':r['id'],'session_id':r['session_id'],'task_id':task_id,'topic':s['topic']})
                for d in domains:domain_tasks[d].add(task_id)
            tasks.append({**s,'task_id':task_id,'is_qa3':s['label']=='QA3','domains':domains,'domain_links':links,'domain_status':'LINKED' if links else 'NOT_IN_EXISTING_DOMAIN_SET'})
        has_qa3=any(s['is_qa3'] for s in tasks)
        transition[(old['annotation']['branch'],r['session_label'])]+=1
        rows.append({'id':r['id'],'session_id':r['session_id'],'term':r['term'],'sample_index':r['sample_index'],'status':r['status'],'session_label':r['session_label'],'has_qa3':has_qa3,'qa_pro':r['qa_pro'],'previous_funnel_annotation':old['annotation'],'domain_units':units,'tasks':tasks,'turns':r['turns'],'data_review_reason':r['data_review_reason']})
    qa3=[t for r in rows for t in r['tasks'] if t['is_qa3']]
    assert len(qa3)==721 and sum(r['has_qa3'] for r in rows)==708
    assert sum(len(r['domain_units']) for r in rows)==sum(len(r['units']) for r in topics)==835
    assert {k:digest(v) for k,v in sources.items()}==hashes
    # Recovered domain objects must match their source exactly.
    for r in rows:
        expected=domain_by_session.get(r['session_id'],{}).get('units',[])
        assert [u['original'] for u in r['domain_units']]==expected
    with (OUT/'aligned_sessions.jsonl').open('w') as f:
        for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    task_counts=collections.Counter(t['label'] for r in rows for t in r['tasks'])
    summary={'version':'domain-preserved_qa3-v3.1','updated_at':datetime.datetime.now().astimezone().isoformat(),'matched_sessions':len(rows),'annotated_sessions':sum(r['status']=='ANNOTATED' for r in rows),'data_review_sessions':sum(r['status']=='DATA_REVIEW' for r in rows),'task_segments':sum(task_counts.values()),'task_label_counts':dict(task_counts),'qa3_tasks':len(qa3),'qa3_sessions':sum(r['has_qa3'] for r in rows),'existing_domain_sessions':len(topics),'existing_domain_units':835,'qa3_tasks_with_domain':len(qa3)-len(gaps),'qa3_tasks_without_domain':len(gaps),'domain_gap_tasks':gaps,'role_conflict_sessions':len({r['id'] for r in role_conflicts}),'role_conflicts':role_conflicts,'domain_qa3_task_counts':{k:len(v) for k,v in sorted(domain_tasks.items())},'domains_in_previous_effective_but_no_current_qa3':sum(bool(r['domain_units']) and not r['has_qa3'] for r in rows),'source_paths':{k:str(v) for k,v in sources.items()},'source_hashes':hashes,'validation':'PASS','unit_note':'721 is a task count; domain units are retained and may map many-to-many. Domain counts cannot be summed across domains.'}
    dump(OUT/'summary.json',summary)
    with (OUT/'会话阶段对照.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['会话ID','原始session_id','旧版是否继续','旧版质量分支','本轮会话标签','本轮是否含QA3','QA3任务段数','保留领域','角色差异待注意'])
        for r in rows:w.writerow([r['id'],r['session_id'],r['previous_funnel_annotation'].get('continuation'),r['previous_funnel_annotation']['branch'],r['session_label'],'YES' if r['has_qa3'] else 'NO',sum(t['is_qa3'] for t in r['tasks']),' / '.join(sorted({u['original']['domain'] for u in r['domain_units']})),any(u['excluded_student_turn_ids'] for u in r['domain_units'])])
    with (OUT/'任务段领域对照.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['任务段ID','会话ID','起始回合','结束回合','阶段标签','是否QA3','既有领域','关联领域片段ID','有效学生回合'])
        for r in rows:
            for t in r['tasks']:w.writerow([t['task_id'],r['id'],t['turn_start'],t['turn_end'],t['label'],t['is_qa3'],' / '.join(t['domains']) or '领域待补',' / '.join(x['domain_unit_id'] for x in t['domain_links']),str(t['effective_student_turns'])])
    payload=json.dumps({'rows':rows,'summary':summary},ensure_ascii=False).replace('<','\\u003c')
    template=(ROOT/'workbench/static/calibration-template.html').read_text()
    assert template.count('__PAYLOAD__')==1
    html=template.replace('__PAYLOAD__',payload)
    (OUT/'领域与QA3校准.html').write_text(html)
    (ROOT/'workbench/static/calibration.html').write_text(html)
    report=f'''# 领域与QA3逐会话校准

两份结果的1,299个原始session_id全部唯一、一一对应，显示编号也一致。领域名称、话题、概念及原始领域片段均保留；QA3阶段以本轮v3.1任务段结果为准。

- 1,277组可读会话拆为1,382个任务段，其中721段为QA3，涉及708组会话。
- 原领域分类保留748组会话、835个领域片段，不把领域片段数强行改成721。
- 721个QA3任务段中，{len(qa3)-len(gaps)}段关联到既有领域，{len(gaps)}段缺少既有领域记录：{', '.join(x['id'] for x in gaps)}。保持QA3，领域待补。
- 43组有既有领域记录的会话，本轮不含QA3任务段；保留领域分类，退出本轮QA3集合。
- 4组角色解析存在差异：S0128、S0192、S0439、S0598。领域名称保留，关联时排除本轮已确认为AI发言的回合。

关联依据是同一原始session_id、完整原文证据及复核后的学生回合范围。领域与任务段允许多对多；跨领域数量不能相加作为721的分解。领域片段关联到QA3任务段，不等于额外认定了“同领域QA3”或QA Pro。未进入QA3不等于没有学习。

校准只做已有结果对齐，没有重标领域或修改源标注。三份输入哈希、角色差异及缺口详见summary.json。

[查看校准图与明细](领域与QA3校准.html) · [会话阶段对照](会话阶段对照.csv) · [任务段领域对照](任务段领域对照.csv)
'''
    (OUT/'校准说明.md').write_text(report)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('role_conflicts','source_paths','source_hashes','domain_qa3_task_counts')},ensure_ascii=False))

if __name__=='__main__':main()
