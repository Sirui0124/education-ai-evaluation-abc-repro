#!/usr/bin/env python3
"""Validate two QA Pro label files and calculate agreement statistics."""

from __future__ import annotations

import json
import argparse
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "workspace/data_clean/module_b_qapro_agreement200"
SAMPLE = DATA_DIR / "sample_full_dialogues.jsonl"
VALID_LABELS = {"ENTER", "NOT_ENTER"}


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"{path}:{number}: invalid JSON: {exc}") from exc
    return rows


def index_labels(path: Path, sample_ids: set[str]) -> dict[str, dict]:
    rows = load_jsonl(path)
    by_id = {row["id"]: row for row in rows}
    if len(rows) != 200 or len(by_id) != 200:
        raise RuntimeError(f"{path} must contain 200 unique ids")
    if set(by_id) != sample_ids:
        missing = sorted(sample_ids - set(by_id))
        extra = sorted(set(by_id) - sample_ids)
        raise RuntimeError(f"{path} id mismatch; missing={missing}, extra={extra}")
    bad = {row["label"] for row in rows} - VALID_LABELS
    if bad:
        raise RuntimeError(f"{path} contains invalid labels: {sorted(bad)}")
    return by_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--terra", default="labels_terra.jsonl")
    parser.add_argument("--sol", default="labels_sol.jsonl")
    parser.add_argument("--out-prefix", default="agreement_report")
    args = parser.parse_args()
    terra_path = DATA_DIR / args.terra
    sol_path = DATA_DIR / args.sol
    out_json = DATA_DIR / f"{args.out_prefix}.json"
    out_md = DATA_DIR / f"{args.out_prefix}.md"

    sample_rows = load_jsonl(SAMPLE)
    sample_by_id = {row["id"]: row for row in sample_rows}
    sample_ids = set(sample_by_id)
    if len(sample_rows) != 200 or len(sample_by_id) != 200:
        raise RuntimeError("sample must contain 200 unique ids")

    terra = index_labels(terra_path, sample_ids)
    sol = index_labels(sol_path, sample_ids)

    confusion = Counter()
    disagreements = []
    domain_totals = Counter()
    domain_agree = Counter()
    for sid in sorted(sample_ids):
        left = terra[sid]["label"]
        right = sol[sid]["label"]
        confusion[(left, right)] += 1
        domain = sample_by_id[sid]["primary_domain"]
        domain_totals[domain] += 1
        if left == right:
            domain_agree[domain] += 1
        else:
            disagreements.append(
                {
                    "id": sid,
                    "domain": domain,
                    "terra_label": left,
                    "sol_label": right,
                    "terra_rule_codes": terra[sid].get("rule_codes", []),
                    "sol_rule_codes": sol[sid].get("rule_codes", []),
                    "terra_delta": terra[sid].get("delta", ""),
                    "sol_delta": sol[sid].get("delta", ""),
                }
            )

    agree = sum(value for (left, right), value in confusion.items() if left == right)
    observed = agree / 200
    terra_counts = Counter(row["label"] for row in terra.values())
    sol_counts = Counter(row["label"] for row in sol.values())
    expected = sum((terra_counts[label] / 200) * (sol_counts[label] / 200) for label in VALID_LABELS)
    kappa = (observed - expected) / (1 - expected) if expected < 1 else 1.0

    per_domain = {
        domain: {
            "n": domain_totals[domain],
            "agreed": domain_agree[domain],
            "agreement": domain_agree[domain] / domain_totals[domain],
        }
        for domain in sorted(domain_totals)
    }
    report = {
        "sample_size": 200,
        "labels": sorted(VALID_LABELS),
        "terra_counts": dict(sorted(terra_counts.items())),
        "sol_counts": dict(sorted(sol_counts.items())),
        "confusion": {
            f"terra={left}|sol={right}": confusion[(left, right)]
            for left in sorted(VALID_LABELS)
            for right in sorted(VALID_LABELS)
        },
        "agreements": agree,
        "disagreements": len(disagreements),
        "percent_agreement": observed,
        "cohen_kappa": kappa,
        "agreement_gate": 0.9,
        "gate_passed": observed >= 0.9,
        "per_domain": per_domain,
        "disagreement_cases": disagreements,
    }
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# QA Pro 双标一致性报告",
        "",
        f"- 样本：200场完整有效QA3会话",
        f"- 完全一致：{agree}/200（{observed:.1%}）",
        f"- Cohen's κ：{kappa:.3f}",
        f"- 90%门槛：{'PASSED' if observed >= 0.9 else 'FAILED'}",
        f"- Terra标签：ENTER {terra_counts['ENTER']}，NOT_ENTER {terra_counts['NOT_ENTER']}",
        f"- Sol标签：ENTER {sol_counts['ENTER']}，NOT_ENTER {sol_counts['NOT_ENTER']}",
        "",
        "## 分领域一致率",
        "",
        "| 领域 | 一致/样本 | 一致率 |",
        "|---|---:|---:|",
    ]
    for domain, stats in per_domain.items():
        lines.append(f"| {domain} | {stats['agreed']}/{stats['n']} | {stats['agreement']:.1%} |")
    lines.extend(["", "## 分歧案例", "", "| ID | 领域 | Terra | Sol |", "|---|---|---|---|"])
    for row in disagreements:
        lines.append(f"| {row['id']} | {row['domain']} | {row['terra_label']} | {row['sol_label']} |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({key: report[key] for key in ["agreements", "disagreements", "percent_agreement", "cohen_kappa", "gate_passed"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
