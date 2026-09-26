"""Portable QA3 v3.1 semantic gate followed by unchanged QAPro v2.4 retrieval."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from .qa3_contract import schema, validate_batch, session_summary, prompt_text
from .student_retrieval import convert as student_side
from .candidates import convert as candidates
from .frozen_hits import convert as freeze

RULE_DIR = Path(__file__).parent / 'rules'
ROLES = {'user': 'student', 'student': 'student', '学生': 'student',
         'assistant': 'agent', 'agent': 'agent', 'AI': 'agent', '助手': 'agent'}

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def normalize(row):
    if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id'].strip():
        raise ValueError('每场必须有非空字符串 id')
    turns = row.get('turns', row.get('messages'))
    if not isinstance(turns, list):
        raise ValueError('每场必须有 turns 或 messages 数组')
    result = {'id': row['id'], 'session_id': row.get('session_id', row['id']), 'turns': []}
    if not isinstance(result['session_id'], str):
        raise ValueError('session_id 必须为字符串')
    for index, t in enumerate(turns, 1):
        if not isinstance(t, dict):
            raise ValueError('发言必须为对象')
        role, text = ROLES.get(t.get('role')), t.get('text', t.get('content'))
        if role is None or not isinstance(text, str):
            raise ValueError('发言需要明确的 student/user 或 agent/assistant 角色及字符串正文')
        number = t.get('turn_index', index)
        if type(number) is not int:
            raise ValueError('turn_index 必须为整数')
        result['turns'].append({'turn_index': number, 'role': role, 'text': text})
    indices = [t['turn_index'] for t in result['turns']]
    if indices and indices != list(range(indices[0], indices[0] + len(indices))):
        raise ValueError('turn_index 必须按输入顺序连续递增且无重复；可省略后自动从 1 编号')
    return result

def check_schema(value, spec):
    """Validate the small, bundled response schema without third-party dependencies."""
    types = {'object': dict, 'array': list, 'string': str, 'integer': int}
    if type(value) is not types[spec['type']]:
        raise ValueError('模型返回字段类型不符合 schema')
    if 'enum' in spec and value not in spec['enum']:
        raise ValueError('模型返回枚举无效')
    if 'const' in spec and value != spec['const']:
        raise ValueError('模型返回常量无效')
    if isinstance(value, dict):
        if set(spec.get('required', [])) - value.keys():
            raise ValueError('模型返回缺少必要字段')
        props = spec.get('properties', {})
        if spec.get('additionalProperties') is False and value.keys() - props.keys():
            raise ValueError('模型返回额外字段')
        for k, v in value.items():
            if k in props:
                check_schema(v, props[k])
    if isinstance(value, list):
        if len(value) < spec.get('minItems', 0):
            raise ValueError('模型返回数组为空')
        for v in value:
            check_schema(v, spec['items'])
    if isinstance(value, str) and len(value) < spec.get('minLength', 0):
        raise ValueError('模型返回文本为空')

def validate_qa3(record, annotation):
    payload = {'results': [annotation]}
    check_schema(payload, schema())
    validate_batch({'sessions': [record], 'session_count': 1}, payload)
    return annotation

def annotate_qapro(record):
    hits = freeze(candidates(student_side(record)))
    primary = next((name for key, name in [('r1_hits', 'R1_METHOD_MODEL_VARIABLE'),
                   ('r2_hits', 'R2_EFFECTIVE_ANSWER'), ('r3_hits', 'R3_DIFFERENTIATED_QUESTION')]
                   if hits[key]), None)
    return {'label': 'ENTER' if primary else 'NOT_ENTER', 'primary_type': primary,
            'reason': None if primary else 'NO_COGNITIVE_CHANGE',
            'r1': hits['r1_hits'], 'r2': hits['r2_hits'], 'r3': hits['r3_hits']}

def label_one(row, annotate):
    """annotate(record) returns one validated QA3 annotation; no API assumptions."""
    result = {'id': row.get('id'), 'input_sha256': digest(row), 'status': 'DONE',
              'exclusion': '不剔除', 'qa3': None, 'qapro': None, 'tier': None,
              'qa3_version': '3.1', 'qapro_version': '2.4', 'segments': [],
              'qa3_reason': None, 'qapro_details': None, 'error': None,
              'metadata': {k: v for k, v in row.items() if k not in {'turns', 'messages'}}}
    if row.get('identity_role') == 'teacher':
        result['exclusion'] = '疑似老师剔除'
        return result
    try:
        record = normalize(row)
    except ValueError as exc:
        result.update(status='DATA_REVIEW', qa3_reason='DATA_REVIEW', error=str(exc))
        return result
    result['turns'] = record['turns']
    if not record['turns'] or not any(t['text'].strip() for t in record['turns']):
        result['exclusion'] = '空对话'
        return result
    if {t['role'] for t in record['turns'] if t['text'].strip()} != {'student', 'agent'} or any(not t['text'].strip() for t in record['turns']):
        result.update(status='DATA_REVIEW', qa3_reason='DATA_REVIEW', error='缺一方发言或存在空正文回合')
        return result
    try:
        annotation = validate_qa3(record, annotate(record))
    except Exception as exc:
        # Never turn an API / validation failure into a negative learning label.
        result.update(status='ERROR', error='标注或证据校验失败：' + type(exc).__name__)
        return result
    segments = annotation['segments']
    result['segments'] = segments
    result['qa3_reason'] = session_summary(segments)
    has_qa3 = any(s['label'] == 'QA3' for s in segments)
    if any(s['label'] == 'REVIEW' for s in segments):
        result['status'] = 'REVIEW'
    result['qa3'] = True if has_qa3 else None if result['status'] == 'REVIEW' else False
    if has_qa3:
        details = annotate_qapro(record)
        result.update(qapro=details['label'] == 'ENTER', qapro_details=details,
                      tier='QA Pro' if details['label'] == 'ENTER' else '仅QA3')
    elif result['qa3'] is False:
        result['tier'] = '仅QA'
    return result

def label_conversations(rows, annotate):
    ids = [r.get('id') if isinstance(r, dict) else None for r in rows]
    if any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('输入 id 必须为非空字符串且全局唯一')
    return [label_one(row, annotate) for row in rows]

def model_prompt(record):
    rules = (RULE_DIR / 'qa3_v3.1.md').read_text(encoding='utf-8')
    return prompt_text(rules) + json.dumps({'sessions': [record], 'session_count': 1}, ensure_ascii=False)
