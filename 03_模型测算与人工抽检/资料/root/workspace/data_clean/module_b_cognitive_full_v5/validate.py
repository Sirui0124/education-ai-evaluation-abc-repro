"""Mechanical checks only; never assigns semantic labels."""
import json
import sys
from pathlib import Path

D = Path(__file__).resolve().parent

def read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def validate(path, partial=False):
    stage = 'baseline' if 'baseline' in path.name else 'highest'
    scale = 's6' if 's6' in path.name else 's3'
    sources = read(D / stage / 'all.jsonl')
    inputs = {r['id']: r for r in sources}
    rows = read(path)
    errors = []
    ids = [r['id'] for r in rows]
    if len(ids) != len(set(ids)):
        errors.append('duplicate IDs')
    expected = [r['id'] for r in sources]
    if not partial and ids != expected:
        errors.append('missing / extra / reordered IDs')
    labels = {'U','L1','L2','L3','L4','L5','L6'} if scale == 's6' else {'U','低','中','高'}
    for row in rows:
        rid = row['id']
        src = inputs.get(rid)
        if not src:
            errors.append([rid,'unknown ID']); continue
        if row.get('label') not in labels:
            errors.append([rid,'invalid label'])
        if row.get('raw_label') not in labels:
            errors.append([rid,'invalid raw label'])
        if row.get('support') not in {'独立表达','经提示后表达','复述AI','复述 AI','无法判断'}:
            errors.append([rid,'invalid support'])
        if row.get('confidence') not in {'high','medium','low'}:
            errors.append([rid,'invalid confidence'])
        turns = {t['i']:t for t in src['turns']}
        ev = row.get('evidence_turn_ids',[])
        quote = row.get('evidence_quote','')
        if row.get('label') == 'U':
            if ev or quote:
                errors.append([rid,'U has evidence'])
            if row.get('u_reason') not in {'NO_DEMONSTRATED_KNOWLEDGE','COPY_ONLY','NO_CORRECT_COMPONENT','MISSING_CONTEXT','DOMAIN_MISMATCH'}:
                errors.append([rid,'missing/invalid U reason'])
        else:
            if not ev or any(i not in turns or turns[i]['role']!='student' for i in ev):
                errors.append([rid,'missing/nonstudent evidence'])
            if not quote or not any(quote in turns[i]['text'] for i in ev if i in turns):
                errors.append([rid,'quote not exact'])
            if stage == 'baseline' and ev != [src['target_student_turn']]:
                errors.append([rid,'baseline evidence outside target'])
            if stage == 'highest' and any(not any(t['turn_start'] <= i <= t['turn_end'] for t in src['tasks']) for i in ev):
                errors.append([rid,'highest evidence outside eligible tasks'])
            if row.get('u_reason') is not None:
                errors.append([rid,'concrete label has U reason'])
        if stage=='baseline' and scale=='s6' and src['classification']=='QA3' and row.get('label') not in {'U','L1','L2'}:
            errors.append([rid,'QA3 exceeds L2'])
    return {'file':path.name,'count':len(rows),'expected':len(sources),'errors':errors}

if __name__=='__main__':
    paths = [D/x for x in sys.argv[1:] if not x.startswith('--')]
    if not paths:
        paths = sorted(D.glob('*_s[36].jsonl'))
    for p in paths:
        print(json.dumps(validate(p, '--partial' in sys.argv),ensure_ascii=False))
