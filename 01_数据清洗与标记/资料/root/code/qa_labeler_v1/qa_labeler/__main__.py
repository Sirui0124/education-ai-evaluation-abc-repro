from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from .core import digest, normalize, label_one
from .backend import APIAnnotator


def read_rows(path):
    if path.is_dir():
        files = sorted(p for p in path.iterdir() if p.suffix.lower() in {'.json', '.jsonl'})
        if not files:
            raise ValueError('目录中没有 JSON/JSONL 文件')
        return [r for p in files for r in read_rows(p)]
    text = path.read_text(encoding='utf-8-sig')
    if path.suffix.lower() == '.jsonl':
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    value = json.loads(text)
    return value if isinstance(value, list) else [value]


def save_json(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def rules_code_hash():
    base = Path(__file__).parent
    return digest({str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(base.rglob('*')) if p.suffix in {'.py', '.md'}})


def imported_annotator(path):
    rows = read_rows(path)
    if any(not isinstance(r, dict) or not isinstance(r.get('id'), str) for r in rows):
        raise ValueError('QA3 导入记录缺少字符串 id')
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('QA3 导入记录 id 重复')
    index = {r['id']: r for r in rows}
    def annotate(record):
        source = index[record['id']]
        if normalize(source)['turns'] != record['turns']:
            raise ValueError('导入 QA3 与当前正文、角色或回合不一致')
        return {'id': record['id'], 'session_id': record['session_id'],
                'qa_pro': 'PENDING', 'segments': [{k: v for k, v in segment.items() if k in
                    {'topic', 'turn_start', 'turn_end', 'label', 'reason', 'evidence',
                     'effective_student_turns', 'deferred_student_turns', 'closure',
                     'agent_uptake', 'review_reason'}} for segment in source['segments']]}
    return annotate, digest(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description='独立批量打标：有效 QA3 v3.1 → QAPro v2.4')
    parser.add_argument('--input', type=Path, required=True, help='JSON、JSONL 或含这些文件的目录')
    parser.add_argument('--output', type=Path, required=True, help='独立输出目录；支持相同配置断点续跑')
    parser.add_argument('--qa3-annotations', type=Path, help='可选：含原文 turns 的既有 QA3 标注，不调用 API')
    parser.add_argument('--model', default=os.getenv('QA_MODEL'))
    parser.add_argument('--base-url', default=os.getenv('QA_BASE_URL'), help='API 基址，含 /v1（如果供应商要求）')
    parser.add_argument('--api-key-env', default='QA_API_KEY', help='存放 API Key 的环境变量名，勿直接传 Key')
    parser.add_argument('--json-mode', choices=['schema', 'object'], default='schema')
    parser.add_argument('--reasoning-effort', choices=['omit', 'low', 'medium', 'high'], default='medium')
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--retries', type=int, default=2)
    args = parser.parse_args(argv)
    try:
        if args.timeout <= 0 or not 0 <= args.retries <= 10:
            raise ValueError('timeout 必须 >0，retries 为 0–10')
        rows = read_rows(args.input)
        ids = [r.get('id') if isinstance(r, dict) else None for r in rows]
        if not rows or any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
            raise ValueError('输入不能为空，且每场 id 必须为非空字符串、全局唯一')
        if args.qa3_annotations:
            annotate, imported_hash = imported_annotator(args.qa3_annotations)
            backend = {'mode': 'import', 'annotations_sha256': imported_hash}
        else:
            key = os.getenv(args.api_key_env)
            if not args.model or not args.base_url or not key:
                raise ValueError('配置 QA_MODEL、QA_BASE_URL、QA_API_KEY，或提供 --qa3-annotations')
            from urllib.parse import urlsplit
            url = urlsplit(args.base_url)
            if url.scheme not in {'http', 'https'} or not url.netloc or url.username or url.password or url.query or url.fragment:
                raise ValueError('base-url 需为不含凭据、查询参数的 HTTP(S) 基址')
            if url.scheme == 'http' and url.hostname not in {'localhost', '127.0.0.1', '::1'}:
                raise ValueError('远程 API 必须使用 HTTPS')
            annotate = APIAnnotator(args.base_url, key, args.model, args.timeout, args.retries, args.json_mode, args.reasoning_effort)
            backend = {'mode': 'api', 'model': args.model, 'endpoint_sha256': digest(args.base_url),
                       'json_mode': args.json_mode, 'reasoning_effort': args.reasoning_effort, 'timeout': args.timeout, 'retries': args.retries}
        config = {'package_version': '1.0.0', 'input_sha256': digest(rows),
                  'code_rules_sha256': rules_code_hash(), 'backend': backend}
        out = args.output
        out.mkdir(parents=True, exist_ok=True)
        manifest = out / 'manifest.json'
        if manifest.exists():
            if json.loads(manifest.read_text(encoding='utf-8')) != config:
                raise ValueError('输入、规则或配置变化，请使用新的输出目录')
        else:
            if any(out.iterdir()):
                raise ValueError('输出目录已有其他文件，请使用空目录')
            save_json(manifest, config)
        cache = out / 'cache'
        cache.mkdir(exist_ok=True)
        results = []
        for index, row in enumerate(rows, 1):
            cached = cache / (digest(row['id']) + '.json')
            if cached.exists():
                result = json.loads(cached.read_text(encoding='utf-8'))
                if result.get('input_sha256') != digest(row):
                    raise ValueError('缓存正文校验失败')
            else:
                result = None
            if result is None or result['status'] == 'ERROR':
                result = label_one(row, annotate)
                save_json(cached, result)
            results.append(result)
            print(f'{index}/{len(rows)} {result["status"]}', flush=True)
        (out / 'labels.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in results), encoding='utf-8')
        fields = ['id', 'status', 'exclusion', 'tier', 'qa3', 'qapro', 'qa3_reason', 'primary_type', 'r1_count', 'r2_count', 'r3_count', 'error']
        with (out / 'labels.csv').open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for r in results:
                value = {k: r.get(k) for k in fields}
                detail = r['qapro_details'] or {}
                value.update(primary_type=detail.get('primary_type'), **{f'{k}_count': len(detail.get(k, [])) for k in ('r1', 'r2', 'r3')})
                # Prevent source identifiers from being executed as spreadsheet formulas.
                value = {k: "'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v for k, v in value.items()}
                writer.writerow(value)
        summary = {'total': len(results), 'status_counts': dict(Counter(r['status'] for r in results)),
                   'tier_counts': dict(Counter(r['tier'] or '未定级/剔除' for r in results)),
                   'qa3_true': sum(r['qa3'] is True for r in results),
                   'qapro_true': sum(r['qapro'] is True for r in results),
                   'excluded': sum(r['exclusion'] != '不剔除' for r in results),
                   'semantic_accuracy': 'NOT_ESTABLISHED_BY_MECHANICAL_TESTS'}
        save_json(out / 'summary.json', summary)
        print(json.dumps(summary, ensure_ascii=False))
        return 2 if any(r['status'] == 'ERROR' for r in results) else 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f'输入/配置错误：{exc}\n')

if __name__ == '__main__':
    raise SystemExit(main())
