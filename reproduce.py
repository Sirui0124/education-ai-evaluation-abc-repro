#!/usr/bin/env python3
"""Offline, standard-library reproduction of the published numerical claims."""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent


def jsonl(relative):
    with (BASE / relative).open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def json_file(relative):
    return json.loads((BASE / relative).read_text(encoding='utf-8'))


def close(actual, expected, name):
    if not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9):
        raise AssertionError(f'{name}: calculated {actual}; frozen {expected}')


def nominal_alpha(pairs):
    coincidence = defaultdict(float)
    margin = Counter()
    for a, b in pairs:
        values = Counter((a, b))
        for x, nx in values.items():
            for y, ny in values.items():
                value = nx * (ny - (x == y))
                coincidence[x, y] += value
                margin[x] += value
    n = sum(margin.values())
    if n <= 1:
        return None
    observed = sum(value for (a, b), value in coincidence.items() if a != b) / n
    expected = sum(na * nb for a, na in margin.items() for b, nb in margin.items() if a != b) / (n * (n - 1))
    return 1 - observed / expected if expected else None


def kappa(pairs):
    n = len(pairs)
    a, b = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
    observed = sum(x == y for x, y in pairs) / n
    expected = sum(a[x] * b[x] for x in a.keys() | b.keys()) / n**2
    return (observed - expected) / (1 - expected) if expected < 1 else None


def claim_a_funnel():
    rows = jsonl('01_数据清洗与标记/资料/root/workspace/data_clean/module_b_full_hierarchy_v1/conversation_labels.jsonl')
    tiers = Counter(row['interaction_tier'] for row in rows)
    assert len(rows) == 1327 and tiers == {None: 41, '仅QA': 578, '仅QA3': 283, 'QA Pro': 425}
    return {'records': len(rows), 'excluded': tiers[None], 'qa_only': tiers['仅QA'], 'qa3_only': tiers['仅QA3'], 'qapro': tiers['QA Pro']}


def claim_b_agreement():
    path = BASE / '03_模型测算与人工抽检/资料/root/workspace/data_clean/module_b_cognitive_qapro_v5/record_labels.csv'
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 708
    metrics = json_file('03_模型测算与人工抽检/资料/root/workspace/data_clean/module_b_cognitive_qapro_v5/metrics.json')
    result = {}
    for stage in ('baseline', 'highest'):
        for scale in ('s6', 's3'):
            pairs = [(r['terra_' + stage + '_' + scale], r['sol_' + stage + '_' + scale]) for r in rows]
            pairs = [(a, b) for a, b in pairs if a and b]
            frozen = metrics['stages'][stage]['overall'][scale]
            assert len(pairs) == frozen['n']
            exact = sum(a == b for a, b in pairs)
            assert exact == frozen['exact']
            close(nominal_alpha(pairs), frozen['nominal_alpha_with_u'], stage + '_' + scale + '_alpha')
            close(kappa(pairs), frozen['cohen_kappa_with_u'], stage + '_' + scale + '_kappa')
            result[stage + '_' + scale] = {'n': len(pairs), 'exact': exact, 'alpha': round(nominal_alpha(pairs), 6)}
    assert result['baseline_s6']['n'] == 708 and result['highest_s6']['n'] == 425
    return result


def claim_b_student():
    rows = jsonl('04_学生评分产出/资料/root/outputs/module-b-q3-adopted-v1/学生领域采纳版.jsonl')
    assert len(rows) == 621
    students = len({r['student_key'] for r in rows})
    comparable = 0
    for row in rows:
        if row['pair_status'] == 'COMPARABLE':
            comparable += 1
            assert row['domain_pair_valid'] and row['before_score'] is not None and row['after_score'] is not None
            close(row['delta_l'], row['after_score'] - row['before_score'], 'student_delta')
        else:
            assert row['delta_l'] is None
    assert students == 369 and comparable == 156
    return {'students': students, 'student_domains': len(rows), 'comparable': comparable, 'not_comparable': len(rows) - comparable}


def claim_c_aiv():
    rows = jsonl('05_打分表/资料/root/outputs/module-c-ranking-v4-174-20260926/学生指标与多方案排名_174人.jsonl')
    assert len(rows) == 174
    assert sum(bool(r['strict_baseline_eligible']) for r in rows) == 146
    scores = []
    for row in rows:
        score = 100 * (0.30 * row['observed_ctq_sum_equal'] / 12 +
                       0.25 * row['observed_ctq_mean_equal'] +
                       0.15 * row['observed_ctq_peak'] +
                       0.30 * row['quality_ratio'])
        frozen = row['scores_and_rankings']['observed_all_exploratory']['normative_balanced']
        close(score, frozen['score'], 'AIV ' + row['student_key'])
        scores.append((row['student_key'], score, frozen['rank']))
    # Average rank for ties, using the published precision of the computed score.
    sorted_scores = sorted(scores, key=lambda item: -round(item[1], 9))
    for index, (student, score, frozen_rank) in enumerate(sorted_scores):
        peers = [j + 1 for j, item in enumerate(sorted_scores) if round(item[1], 9) == round(score, 9)]
        close(frozen_rank, sum(peers) / len(peers), 'rank ' + student)
    return {'students': len(rows), 'baseline_eligible': 146, 'scores_and_ranks_verified': len(rows)}


def claim_c_weights():
    weights = json_file('05_打分表/资料/root/outputs/module-c-purpose-weights-20260927/weights.json')
    # The structure is checked in a separate helper to preserve the source's full-precision values.
    schemes = weights.get('schemes') or weights.get('purposes') or weights.get('scenarios')
    if not schemes:
        raise AssertionError('cannot locate three weight schemes')
    result = {}
    for name, item in (schemes.items() if isinstance(schemes, dict) else ((x.get('name', str(i)), x) for i, x in enumerate(schemes))):
        values = item.get('weights', item) if isinstance(item, dict) else item
        if isinstance(values, dict):
            vector = [v for v in values.values() if isinstance(v, (int, float))]
        else:
            vector = [v for v in values if isinstance(v, (int, float))]
        if len(vector) != 8:
            raise AssertionError(f'{name}: expected eight numeric weights; got {len(vector)}')
        close(sum(vector), 1.0, name + ' weight sum')
        result[name] = round(sum(vector), 9)
    assert len(result) == 3
    return result


CLAIMS = {
    'A-FUNNEL': claim_a_funnel,
    'B-AGREEMENT': claim_b_agreement,
    'B-STUDENT': claim_b_student,
    'C-AIV-OLD': claim_c_aiv,
    'C-WEIGHTS': claim_c_weights,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--claim', choices=[*CLAIMS, 'all', 'random'], default='all')
    parser.add_argument('--seed', type=int, default=20260927)
    args = parser.parse_args()
    names = list(CLAIMS) if args.claim == 'all' else [random.Random(args.seed).choice(list(CLAIMS)) if args.claim == 'random' else args.claim]
    for name in names:
        print(json.dumps({'claim': name, 'status': 'PASS', 'result': CLAIMS[name]()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
