"""Build a deterministic human-review queue from the frozen v5 double ratings.

This script only routes records for review. It never changes model or final labels.
"""
import argparse
import csv
import hashlib
from collections import Counter
from pathlib import Path

STREAMS = ("baseline_s6", "baseline_s3", "highest_s6", "highest_s3")


def priority(reasons):
    if "U_VS_GRADED" in reasons or "MISSING_RATING" in reasons:
        return 1
    if "RATER_DISAGREEMENT" in reasons or "FINAL_STAGE_INVERSION" in reasons:
        return 2
    if "AGREEMENT_AUDIT_SAMPLE" in reasons:
        return 3
    return 9


def selected(identifier, stream, sample_percent):
    digest = hashlib.sha256(f"{identifier}|{stream}|agreement-v1".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64 < sample_percent / 100


def build(rows, sample_percent):
    output = []
    for row in rows:
        identifier = row["id"]
        for stream in STREAMS:
            left, right = row.get("terra_" + stream, ""), row.get("sol_" + stream, "")
            final = row.get("final_" + stream, "")
            if not left and not right and not final:
                continue  # highest is intentionally empty for QA3-only sessions
            reasons = []
            if not left or not right:
                reasons.append("MISSING_RATING")
            elif left != right:
                reasons.append("RATER_DISAGREEMENT")
                if "U" in (left, right):
                    reasons.append("U_VS_GRADED")
            elif selected(identifier, stream, sample_percent):
                reasons.append("AGREEMENT_AUDIT_SAMPLE")
            if stream.endswith("s6"):
                before = row.get("final_baseline_s6", "")
                after = row.get("final_highest_s6", "")
                if stream == "highest_s6" and before.startswith("L") and after.startswith("L") and int(after[1:]) < int(before[1:]):
                    reasons.append("FINAL_STAGE_INVERSION")
            if not reasons:
                continue
            output.append({
                "priority": priority(reasons), "id": identifier,
                "student_key": row.get("student_key", ""), "term": row.get("term", ""),
                "domain": row.get("domain", ""), "classification": row.get("classification", ""),
                "stream": stream, "terra": left, "sol": right, "final": final,
                "reasons": ";".join(reasons), "review_status": "PENDING",
                "human_label": "", "human_evidence": "", "reviewer": "", "review_note": "",
            })
    return sorted(output, key=lambda r: (r["priority"], r["id"], r["stream"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--agreement-sample-percent", type=float, default=10)
    args = parser.parse_args()
    if not 0 <= args.agreement_sample_percent <= 100:
        parser.error("agreement sample percent must be within 0..100")
    with args.input.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"id", "terra_baseline_s6", "sol_baseline_s6", "final_baseline_s6"}
    if not rows or not required.issubset(rows[0]):
        parser.error("input is empty or lacks v5 rating columns")
    queue = build(rows, args.agreement_sample_percent)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(queue[0]) if queue else [])
        if queue:
            writer.writeheader()
            writer.writerows(queue)
    counts = Counter(reason for row in queue for reason in row["reasons"].split(";"))
    print(f"sessions={len(rows)} queue_rows={len(queue)} reasons={dict(counts)}")


if __name__ == "__main__":
    main()
