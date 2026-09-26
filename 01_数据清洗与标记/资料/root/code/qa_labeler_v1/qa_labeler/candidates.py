#!/usr/bin/env python3
"""Generate identical high-precision R1/R2/R3 candidate spans for both annotators."""

import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path


LOW_INFO = re.compile(r"^(都可以|你来定|不知道|不懂|继续|可以|都行|好的|好|是|不是|A|B|C|方法[ABC]|全部了解)[。！!？?\s]*$", re.I)
BACKGROUND = re.compile(r"(我的专业|研究方向|我是.{0,8}(博士|硕士|本科|学生)|熟悉|学过|接触过|全部了解)")
REQUEST = re.compile(r"(如何|怎么|为什么|能否|是否|什么|哪些|哪个|哪种|请|帮我|介绍|讲讲|告诉我|推荐|生成|提出|解释|分析|举例)")
R1_ACTION = re.compile(r"(我想用|我计划|我准备|我选择|采用|使用|设为|设置|取值|调整|组合|结合|验证|检验|定义为|令.{1,12}为)")
QUESTION = re.compile(r"[?？]|(如何|怎么|为什么|能否|是否|什么|哪些|哪个|哪种|吗|请|介绍|讲讲|告诉我|举例)")
ANCHOR_STOP = {"什么", "如何", "为什么", "问题", "模型", "方法", "可以", "这个", "哪些", "怎么", "一下", "详细", "进行", "相关", "知识", "学习"}


def read(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def is_r2_candidate(text, prompts):
    value = text.strip()
    if not prompts or LOW_INFO.fullmatch(value) or BACKGROUND.search(value):
        return False
    questionish = bool(REQUEST.search(value) or "?" in value or "？" in value)
    tentative_short = len(value) <= 12 and (value.endswith("?") or value.endswith("？")) and not REQUEST.search(value)
    return not questionish or tentative_short


def shared_anchor(a, b):
    blocks = sorted(SequenceMatcher(None, a, b).get_matching_blocks(), key=lambda x: x.size, reverse=True)
    for block in blocks:
        if block.size < 2:
            break
        candidate = a[block.a:block.a + min(block.size, 20)].strip(" ，。！？?、：:；;（）()\"'“”")
        if len(candidate) >= 2 and candidate not in ANCHOR_STOP and not all(ch in "的了是在和与及" for ch in candidate):
            return candidate
    return ""


def convert(row):
    student = row["student_utterances"]
    later = [turn for turn in student if not turn["is_first_student_turn"]]
    r1 = [{"turn": t["turn_index"], "text": t["text"]} for t in later if R1_ACTION.search(t["text"])]
    r2 = []
    for t in later:
        ctx = t.get("previous_agent_prompts_for_retrieval_2") or {}
        prompts = ctx.get("prompt_lines_only") or []
        if is_r2_candidate(t["text"], prompts):
            r2.append({"agent_turn": ctx.get("turn_index"), "agent_questions": prompts, "student_turn": t["turn_index"], "student_text": t["text"]})
    r3 = []
    for j, new in enumerate(student[1:], 1):
        if not QUESTION.search(new["text"]):
            continue
        for old in student[:j]:
            if not QUESTION.search(old["text"]):
                continue
            anchor = shared_anchor(old["text"], new["text"])
            if anchor:
                r3.append({"baseline_turn": old["turn_index"], "baseline_text": old["text"], "new_turn": new["turn_index"], "new_text": new["text"], "shared_anchor_candidate": anchor})
    out = dict(row)
    out["r1_candidates"] = r1
    out["r2_candidates"] = r2
    out["r3_candidates"] = r3
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = [convert(row) for row in read(args.input)]
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"n": len(rows), "r1_candidates": sum(len(r['r1_candidates']) for r in rows), "r2_candidates": sum(len(r['r2_candidates']) for r in rows), "r3_candidates": sum(len(r['r3_candidates']) for r in rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
