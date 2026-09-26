"""Build an auditable student-level dialogue and feedback panel.

Raw attachments are read-only. Remote conversation URLs are expanded when
available, but access-bearing URLs are never written to outputs. Cross-term
IDs and prefix aliases are never auto-merged.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import csv
import json
import re
import time
from urllib.request import Request, urlopen

import openpyxl
from docx import Document


ROOT = Path(__file__).resolve().parents[3]
ATTACHMENTS = ROOT / "黑客松赛题-关老师"
OUT = ROOT / "workspace" / "data_clean" / "module_a_student_panel"

AUTUMN_QA = (
    ATTACHMENTS
    / "附件2-2025 年秋季学期脱敏数据"
    / "2025秋-数学模型-问答记录导出20260502导出_已标注_已更新.xlsx"
)
AUTUMN_DUPLICATE = (
    ATTACHMENTS
    / "附件2-2025 年秋季学期脱敏数据"
    / "2025秋-数学模型-问答记录导出20260502导出_已标注.xlsx"
)
SPRING_QA = (
    ATTACHMENTS
    / "附件3-2026年春季学期脱敏数据"
    / "问答记录导出0919_已更新.xlsx"
)
SPRING_ROSTER = (
    ATTACHMENTS
    / "附件3-2026年春季学期脱敏数据"
    / "请大家对本学期线上线下融合授课-参与数据.xlsx"
)

FEEDBACK_DOCS = [
    ("2025秋", ATTACHMENTS / "附件2-2025 年秋季学期脱敏数据" / "2025秋-数学模型-课程反馈详情记录.docx", "课程反馈", None),
    ("2025秋", ATTACHMENTS / "附件2-2025 年秋季学期脱敏数据" / "2025秋-数学模型-课程智能体“探知侠”使用讨论.docx", "智能体反馈", "探知侠"),
    ("2025秋", ATTACHMENTS / "附件2-2025 年秋季学期脱敏数据" / "2025秋-数学模型-课程智能体“数模全才”使用讨论.docx", "智能体反馈", "数模全才"),
    ("2026春", ATTACHMENTS / "附件3-2026年春季学期脱敏数据" / "请大家对本学期线上线下融合授课.docx", "课程反馈", None),
    ("2026春", ATTACHMENTS / "附件3-2026年春季学期脱敏数据" / "课程智能体“探知侠的引导学习空间.docx", "智能体反馈", "探知侠"),
    ("2026春", ATTACHMENTS / "附件3-2026年春季学期脱敏数据" / "课程智能体“数学模型匹配专业知识点.docx", "智能体反馈", "数模匹配知识点"),
    ("2026春", ATTACHMENTS / "附件3-2026年春季学期脱敏数据" / "课程智能体“逆行侠的探索空间”.docx", "智能体反馈", "逆行侠"),
]

MARKER_RE = re.compile(r"^(Q\d*|A\d*)\s*[:：]\s*(.*)$")
URL_RE = re.compile(r"https?://\S+")
FEATURE_KEYS = [
    "total_turns",
    "student_turns",
    "agent_turns",
    "student_character_count",
    "agent_character_count",
    "total_character_count",
]


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def clean_id(value) -> str:
    return "" if value is None else str(value).strip()


def iso(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).isoformat(sep=" ")
        except ValueError:
            pass
    return text


def write_jsonl(path: Path, records) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_csv(path: Path, records: list[dict], fields: list[str] | None = None) -> None:
    if not records and not fields:
        return
    fields = fields or list(records[0])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def fetch_remote_body(url: str, retries: int = 2) -> tuple[str | None, str, str | None]:
    """Return body, fetch status, and content digest; never return the URL."""
    for attempt in range(retries + 1):
        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=20) as response:
                raw = response.read()
            text = raw.decode("utf-8-sig", errors="replace")
            return text, "FETCHED", sha256(raw).hexdigest()
        except Exception as exc:  # URL failures are reviewable data states.
            if attempt == retries:
                return None, f"FAILED:{type(exc).__name__}", None
            time.sleep(0.3 * (attempt + 1))
    return None, "FAILED:Unknown", None


def parse_turns(text: str) -> tuple[list[dict], str | None]:
    turns: list[dict] = []
    current = None
    in_code = False
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.strip().startswith("```"):
            in_code = not in_code
        match = None if in_code else MARKER_RE.match(line.strip())
        if match:
            if current:
                current["text"] = "\n".join(current.pop("lines")).strip()
                turns.append(current)
            marker, first = match.groups()
            current = {
                "turn_index": len(turns) + 1,
                "raw_marker": marker,
                "role": "student" if marker.startswith("Q") else "agent",
                "lines": [first] if first else [],
            }
        elif current:
            current["lines"].append(line)
    if current:
        current["text"] = "\n".join(current.pop("lines")).strip()
        turns.append(current)
    if not turns and text.strip():
        return [], "UNSTRUCTURED_TEXT"
    if any(not turn["text"] for turn in turns):
        return turns, "EMPTY_TURN"
    return turns, None


def infer_agent(text: str, raw_agent: str | None) -> tuple[str | None, str]:
    if raw_agent:
        return str(raw_agent).strip(), "source_field"
    return None, "unlabeled_needs_semantic_review"


def session_features(turns: list[dict]) -> dict:
    student = [turn for turn in turns if turn["role"] == "student"]
    agent = [turn for turn in turns if turn["role"] == "agent"]
    student_text = "\n".join(turn["text"] for turn in student)
    agent_text = "\n".join(turn["text"] for turn in agent)
    return {
        "total_turns": len(turns),
        "student_turns": len(student),
        "agent_turns": len(agent),
        "student_character_count": len(student_text),
        "agent_character_count": len(agent_text),
        "total_character_count": len(student_text) + len(agent_text),
    }


def load_spring_roster() -> set[str]:
    workbook = openpyxl.load_workbook(SPRING_ROSTER, read_only=True, data_only=True)
    sheet = workbook["学生参与情况"]
    rows = list(sheet.iter_rows(values_only=True))
    header_index = next(i for i, row in enumerate(rows) if "学号" in row)
    id_col = rows[header_index].index("学号")
    roster = {clean_id(row[id_col]) for row in rows[header_index + 2 :] if clean_id(row[id_col])}
    workbook.close()
    return roster


def load_sessions(path: Path, term: str, allowed_ids: set[str] | None) -> tuple[list[dict], dict]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook["问答记录"]
    rows = sheet.iter_rows(values_only=True)
    headers = list(next(rows))
    positions = {name: index for index, name in enumerate(headers)}
    sessions = []
    summary = Counter()
    for row_number, row in enumerate(rows, 2):
        student_id = clean_id(row[positions["学号"]])
        if allowed_ids is not None and student_id not in allowed_ids:
            summary["excluded_outside_roster"] += 1
            continue
        body_cell = row[positions["问答记录"]]
        body = "" if body_cell is None else str(body_cell).strip()
        body_source = "cell"
        fetch_status = None
        content_digest = None
        if URL_RE.fullmatch(body):
            body_source = "remote_url"
            body, fetch_status, content_digest = fetch_remote_body(body)
            body = body or ""
            summary["remote_url_rows"] += 1
            summary[f"remote_{fetch_status.split(':', 1)[0].lower()}"] += 1
        turns, parse_warning = parse_turns(body)
        raw_agent = row[positions["智能体类型"]] if "智能体类型" in positions else None
        agent_type, agent_basis = infer_agent(body, raw_agent)
        session_id = f"{term}:{path.name}:问答记录:{row_number}"
        features = session_features(turns)
        status = "PARSED"
        review_reasons = []
        if not body:
            status = "REVIEW_REQUIRED"
            review_reasons.append("NO_BODY")
        if parse_warning:
            status = "REVIEW_REQUIRED"
            review_reasons.append(parse_warning)
        if agent_basis in {"unknown", "conflict"}:
            review_reasons.append("AGENT_TYPE_" + agent_basis.upper())
        session = {
            "session_id": session_id,
            "student_key": f"{term}:{student_id}",
            "term": term,
            "raw_student_id": student_id,
            "source_file": str(path.relative_to(ROOT)),
            "sheet": "问答记录",
            "excel_row": row_number,
            "created_at": iso(row[positions["问题建立时间"]]),
            "qa_source": row[positions["问答来源"]],
            "agent_type": agent_type,
            "agent_type_basis": agent_basis,
            "body_source": body_source,
            "remote_fetch_status": fetch_status,
            "remote_content_sha256": content_digest,
            "parse_status": status,
            "review_reasons": review_reasons,
            "turns": turns,
            "features": features,
        }
        sessions.append(session)
        summary["included_sessions"] += 1
        summary["parsed_sessions"] += status == "PARSED"
        summary["review_sessions"] += status != "PARSED"
    workbook.close()
    return sessions, dict(summary)


def load_feedback_posts(term: str, path: Path, feedback_type: str, agent_type: str | None) -> list[dict]:
    document = Document(path)
    posts = []
    current = None
    id_pattern = re.compile(r"学生学号[：:]\s*([^\s]+)")
    time_pattern = re.compile(r"发布时间[：:]\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})")
    for paragraph_number, paragraph in enumerate(document.paragraphs, 1):
        text = paragraph.text.strip()
        match = id_pattern.search(text)
        if match:
            if current:
                posts.append(current)
            current = {
                "term": term,
                "raw_student_id": clean_id(match.group(1)),
                "source_file": str(path.relative_to(ROOT)),
                "start_paragraph": paragraph_number,
                "feedback_type": feedback_type,
                "agent_type": agent_type,
                "paragraphs": [text],
                "published_at": iso(time_pattern.search(text).group(1)) if time_pattern.search(text) else None,
            }
        elif current:
            current["paragraphs"].append(text)
            if current["published_at"] is None and time_pattern.search(text):
                current["published_at"] = iso(time_pattern.search(text).group(1))
    if current:
        posts.append(current)
    output = []
    for index, post in enumerate(posts, 1):
        body = "\n".join(part for part in post.pop("paragraphs") if part).strip()
        content_parts = re.split(r"学生(?:话题互动内容|话题评论内容|回复)[：:]", body, maxsplit=1)
        content = content_parts[-1].strip() if len(content_parts) > 1 else body
        post_id = f"{term}:{path.name}:P{post['start_paragraph']}"
        output.append(
            {
                **post,
                "post_id": post_id,
                "student_key": f"{term}:{post['raw_student_id']}",
                "post_order_in_document": index,
                "is_reply": "学生回复：" in body[:120],
                "body": body,
                "content": content,
                "body_sha256": sha256(body.encode("utf-8")).hexdigest(),
                "subjective_recognition": "UNLABELED_SEMANTIC_REVIEW_REQUIRED",
            }
        )
    return output


def build_links(sessions: list[dict], posts: list[dict]) -> tuple[list[dict], list[dict]]:
    sessions_by_student = defaultdict(list)
    for session in sessions:
        sessions_by_student[session["student_key"]].append(session)
    links = []
    review = []
    session_ids_by_term_raw = {(session["term"], session["raw_student_id"]): session["student_key"] for session in sessions}
    for post in posts:
        candidates = sessions_by_student.get(post["student_key"], [])
        if not candidates:
            raw = post["raw_student_id"]
            alias = raw[-6:] if len(raw) == 9 and raw.startswith("230") else None
            alias_key = session_ids_by_term_raw.get((post["term"], alias)) if alias else None
            review.append(
                {
                    "post_id": post["post_id"],
                    "student_key": post["student_key"],
                    "reason": "NO_EXACT_QA_ID",
                    "prefix_alias_candidate_student_key": alias_key or "",
                }
            )
            continue
        links.append(
            {
                "post_id": post["post_id"],
                "student_key": post["student_key"],
                "candidate_session_id": "",
                "link_status": "STUDENT_EXACT_ONLY",
                "candidate_count_same_student": len(candidates),
                "manual_review_required": True,
                "semantic_review_required": True,
            }
        )
    return links, review


def build_student_outputs(
    sessions: list[dict], posts: list[dict], links: list[dict]
) -> tuple[list[dict], list[dict], list[dict]]:
    sessions_by_student = defaultdict(list)
    posts_by_student = defaultdict(list)
    links_by_post = {link["post_id"]: link for link in links}
    for session in sessions:
        sessions_by_student[session["student_key"]].append(session)
    for post in posts:
        posts_by_student[post["student_key"]].append(post)
    profiles = []
    feature_rows = []
    identity_rows = []
    for student_key in sorted(set(sessions_by_student) | set(posts_by_student)):
        student_sessions = sorted(sessions_by_student[student_key], key=lambda item: item["created_at"] or "")
        student_posts = sorted(posts_by_student[student_key], key=lambda item: item["published_at"] or "9999")
        timeline = []
        for session in student_sessions:
            timeline.append(
                {
                    "event_type": "conversation_session",
                    "event_time": session["created_at"],
                    "sequence_basis": "session_created_at",
                    **session,
                }
            )
        for post in student_posts:
            timeline.append(
                {
                    "event_type": "feedback_post",
                    "event_time": post["published_at"],
                    "sequence_basis": "published_at" if post["published_at"] else "document_order_only",
                    **post,
                    "candidate_session_link": links_by_post.get(post["post_id"]),
                }
            )
        timeline.sort(key=lambda item: (item["event_time"] is None, item["event_time"] or "", item["event_type"]))
        profiles.append(
            {
                "student_key": student_key,
                "term": student_key.split(":", 1)[0],
                "raw_student_id": student_key.split(":", 1)[1],
                "identity_role": student_sessions[0]["identity_role"] if student_sessions else student_posts[0]["identity_role"],
                "identity_role_basis": student_sessions[0]["identity_role_basis"] if student_sessions else student_posts[0]["identity_role_basis"],
                "timeline_order_limit": "Autumn feedback has no publication time; its relative order to sessions is unknown.",
                "timeline": timeline,
            }
        )
        sums = Counter({key: 0 for key in FEATURE_KEYS})
        for session in student_sessions:
            for key, value in session["features"].items():
                if isinstance(value, bool):
                    sums[key] += int(value)
                elif isinstance(value, int):
                    sums[key] += value
        linked = [links_by_post[post["post_id"]] for post in student_posts if post["post_id"] in links_by_post]
        feature_rows.append(
            {
                "student_key": student_key,
                "term": student_key.split(":", 1)[0],
                "raw_student_id": student_key.split(":", 1)[1],
                "identity_role": student_sessions[0]["identity_role"] if student_sessions else student_posts[0]["identity_role"],
                "identity_role_basis": student_sessions[0]["identity_role_basis"] if student_sessions else student_posts[0]["identity_role_basis"],
                "session_count": len(student_sessions),
                "first_session_at": student_sessions[0]["created_at"] if student_sessions else "",
                "last_session_at": student_sessions[-1]["created_at"] if student_sessions else "",
                **dict(sums),
                "feedback_post_count": len([post for post in student_posts if not post["is_reply"]]),
                "feedback_reply_count": len([post for post in student_posts if post["is_reply"]]),
                "student_exact_feedback_links": len(linked),
                "ranking_status": (
                    "EXCLUDED_TEACHER"
                    if student_sessions and student_sessions[0]["identity_role"] == "teacher"
                    else (
                        "FEATURES_ONLY_NO_WEIGHTING"
                        if student_sessions
                        else "INSUFFICIENT_NO_SESSION"
                    )
                ),
            }
        )
        identity_rows.append(
            {
                "student_key": student_key,
                "term": student_key.split(":", 1)[0],
                "raw_student_id": student_key.split(":", 1)[1],
                "identity_role": student_sessions[0]["identity_role"] if student_sessions else student_posts[0]["identity_role"],
                "identity_role_basis": student_sessions[0]["identity_role_basis"] if student_sessions else student_posts[0]["identity_role_basis"],
                "session_count": len(student_sessions),
                "ideological_agent_session_count": sum(session["agent_type"] == "思政点灯人" for session in student_sessions),
                "feedback_event_count": len(student_posts),
            }
        )
    return profiles, feature_rows, identity_rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw_paths = [AUTUMN_QA, AUTUMN_DUPLICATE, SPRING_QA, SPRING_ROSTER] + [item[1] for item in FEEDBACK_DOCS]
    before = {str(path.relative_to(ROOT)): digest(path) for path in raw_paths}
    assert before[str(AUTUMN_QA.relative_to(ROOT))] == before[str(AUTUMN_DUPLICATE.relative_to(ROOT))]

    roster = load_spring_roster()
    autumn_sessions, autumn_summary = load_sessions(AUTUMN_QA, "2025秋", None)
    spring_sessions, spring_summary = load_sessions(SPRING_QA, "2026春", roster)
    sessions = autumn_sessions + spring_sessions

    posts = []
    for term, path, feedback_type, agent_type in FEEDBACK_DOCS:
        posts.extend(load_feedback_posts(term, path, feedback_type, agent_type))

    # Human-confirmed identity rule: use of the ideological-political agent marks
    # the identity as a teacher within the same term. Apply the role to all of
    # that identity's sessions and feedback, not only the triggering session.
    teacher_keys = {
        session["student_key"] for session in sessions if session["agent_type"] == "思政点灯人"
    }
    for session in sessions:
        session["identity_role"] = "teacher" if session["student_key"] in teacher_keys else "student"
        session["identity_role_basis"] = (
            "human_rule:identity_used_思政点灯人"
            if session["student_key"] in teacher_keys
            else "in_scope_roster_or_qa_identity"
        )
    for post in posts:
        post["identity_role"] = "teacher" if post["student_key"] in teacher_keys else "student_or_unresolved"
        post["identity_role_basis"] = (
            "human_rule:identity_used_思政点灯人"
            if post["student_key"] in teacher_keys
            else "feedback_identity_not_teacher_flagged"
        )

    links, review = build_links(sessions, posts)
    profiles, feature_rows, identity_rows = build_student_outputs(sessions, posts, links)

    write_jsonl(OUT / "conversation_sessions.jsonl", sessions)
    write_jsonl(OUT / "feedback_posts.jsonl", posts)
    write_jsonl(OUT / "student_timelines.jsonl", profiles)
    write_csv(OUT / "session_feedback_links.csv", links)
    write_csv(
        OUT / "linkage_review.csv",
        review,
        ["post_id", "student_key", "reason", "prefix_alias_candidate_student_key"],
    )
    write_csv(OUT / "student_engagement_features.csv", feature_rows)
    write_csv(OUT / "identity_roles.csv", identity_rows)

    after = {str(path.relative_to(ROOT)): digest(path) for path in raw_paths}
    assert before == after, "A raw attachment changed during the read-only build."
    summary = {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(),
        "scope": "Student-level chronological panel and evidence features; no L1-L6 labels or final willingness score.",
        "autumn_duplicate_workbooks_identical": True,
        "spring_roster_students": len(roster),
        "session_counts": {"2025秋": len(autumn_sessions), "2026春名册切片": len(spring_sessions)},
        "session_build": {"2025秋": autumn_summary, "2026春名册切片": spring_summary},
        "feedback_posts": len(posts),
        "students_in_panel": len(profiles),
        "teacher_identities": len(teacher_keys),
        "teacher_sessions": sum(session["identity_role"] == "teacher" for session in sessions),
        "teacher_feedback_events": sum(post["identity_role"] == "teacher" for post in posts),
        "student_identities_eligible_for_future_ranking": sum(
            row["ranking_status"] == "FEATURES_ONLY_NO_WEIGHTING" for row in feature_rows
        ),
        "session_feedback_candidate_links": len(links),
        "linkage_review_rows": len(review),
        "feedback_links_requiring_semantic_session_review": len(links),
        "raw_sha256": before,
        "limits": [
            "Conversation rows have session creation time, not per-turn timestamps.",
            "Autumn feedback documents do not provide publication time, so session-feedback order is unknown.",
            "Cross-term student IDs and prefix aliases are not auto-merged.",
            "Feedback is linked only at the exact same-student level; any session-specific link requires semantic review.",
            "Engagement features are observable behaviors, not a psychological motivation diagnosis.",
            "No engagement weighting or student-level ranking is finalized in this build.",
            "No keyword, punctuation, text-length threshold, or numeric score is used to create a semantic label.",
        ],
    }
    (OUT / "audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
