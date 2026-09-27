#!/usr/bin/env python3
"""Freeze v2.4 retrieval hits; label is intentionally left to independent auditors."""

import argparse
import json
import re
from pathlib import Path


R1_ADOPTION = re.compile(r"(我|我们).{0,8}(想用|计划|准备|选择|采用|使用|设为|设置|取值|调整|组合|结合|验证|检验)|(^|[，。；;])\s*(采用|设为|设置|令|选择|使用)")
AGENT_META = re.compile(r"了解|熟悉|感兴趣|学习阶段|研究方向|专业|希望|准备好|掌握|选择|哪个|情况|基础|偏好|方向|想要|重点")
R3_MARKERS = ["为什么", "如何", "怎么", "条件", "局限", "区别", "关系", "影响", "适用", "场景", "验证", "比较", "能否", "是否", "机制", "原理", "边界", "参数", "变量", "负权", "应用", "具体", "约束", "优缺点"]


def read(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def convert(row):
    r1 = [c for c in row["r1_candidates"] if R1_ADOPTION.search(c["text"])]
    r2 = [c for c in row["r2_candidates"] if c["agent_questions"] and all(not AGENT_META.search(q) for q in c["agent_questions"])]
    r3 = []
    for c in row["r3_candidates"]:
        markers = [m for m in R3_MARKERS if m in c["new_text"]]
        if len(markers) >= 2 and len(c["new_text"]) > len(c["shared_anchor_candidate"]) + 2:
            item = dict(c)
            item["direction_markers"] = markers
            r3.append(item)
    return {
        "id": row["id"],
        "session_id": row.get("session_id"),
        "primary_domain": row.get("primary_domain"),
        "student_utterances": row["student_utterances"],
        "r1_hits": r1,
        "r2_hits": r2,
        "r3_hits": r3,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = [convert(row) for row in read(args.input)]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"n": len(rows), "r1": sum(bool(x['r1_hits']) for x in rows), "r2": sum(bool(x['r2_hits']) for x in rows), "r3": sum(bool(x['r3_hits']) for x in rows), "or": sum(bool(x['r1_hits'] or x['r2_hits'] or x['r3_hits']) for x in rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
