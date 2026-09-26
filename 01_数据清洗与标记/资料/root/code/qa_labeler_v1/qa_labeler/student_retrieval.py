#!/usr/bin/env python3
"""Build student-side QA Pro retrieval inputs while preserving every student turn."""

import argparse
import json
import re
from pathlib import Path


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def extract_agent_prompts(text):
    """Keep only question/prompt lines needed for retrieval step 2."""
    lines = []
    for raw in text.splitlines():
        line = raw.strip().strip("#>*- ")
        if line and ("?" in line or "？" in line) and "费曼讲解" not in line:
            lines.append(line)
    return lines[-12:]


def convert(row):
    turns = row["turns"]
    student = []
    for turn in turns:
        if turn["role"] != "student":
            continue
        previous_agent = None
        for prior in reversed(turns):
            if prior["turn_index"] >= turn["turn_index"]:
                continue
            if prior["role"] == "agent":
                previous_agent = {
                    "turn_index": prior["turn_index"],
                    "prompt_lines_only": extract_agent_prompts(prior["text"]),
                }
                break
        student.append({
            "turn_index": turn["turn_index"],
            "text": turn["text"],
            "is_first_student_turn": len(student) == 0,
            "previous_agent_prompts_for_retrieval_2": previous_agent,
        })
    return {
        "id": row["id"],
        "session_id": row.get("session_id"),
        "term": row.get("term"),
        "primary_domain": row.get("primary_domain"),
        "student_utterances": student,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = [convert(row) for row in read_jsonl(args.input)]
    assert len(rows) == len({row["id"] for row in rows})
    assert all(row["student_utterances"] for row in rows)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"n": len(rows), "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
