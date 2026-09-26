#!/usr/bin/env python3
"""Parameterized Module-C ranking runner for the frozen v4 cohort.

This runner reads only explicitly supplied frozen matrices. The q=.23 matrix is
the primary migrated-baseline scenario; q=.48 is an alternate scenario used on
the exact common eligible cohort. Neither q value is treated as an observed
control-group estimate.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEGACY_ENGINE = Path(
    "/Users/sirui/Documents/ChatGPT/数学建模/outputs/"
    "module-c-ranking-20260926/weights/compute_rankings.py"
)

SCHEME_DEFS = {
    "normative_balanced": {
        "label": "均衡型",
        "type": "normative_scenario",
        "weights": {
            "ctq_weighted_sum": 0.30,
            "ctq_mean_progress": 0.25,
            "ctq_peak_progress": 0.15,
            "qapro_ratio_in_qa3": 0.30,
        },
    },
    "normative_breakthrough": {
        "label": "突破优先型",
        "type": "normative_scenario",
        "weights": {
            "ctq_weighted_sum": 0.20,
            "ctq_mean_progress": 0.20,
            "ctq_peak_progress": 0.40,
            "qapro_ratio_in_qa3": 0.20,
        },
    },
    "normative_teaching_stability": {
        "label": "质量导向型（教学诊断对照）",
        "type": "normative_scenario",
        "weights": {
            "ctq_weighted_sum": 0.25,
            "ctq_mean_progress": 0.30,
            "ctq_peak_progress": 0.10,
            "qapro_ratio_in_qa3": 0.35,
        },
    },
    "grouped_entropy": {
        "label": "分组熵权型",
        "type": "data_driven",
        "weights": None,
    },
    "raw_entropy_4": {
        "label": "四项原始熵权对照",
        "type": "sensitivity_only",
        "weights": None,
    },
    "weak_mab_complete_case": {
        "label": "MAB弱权重对照",
        "type": "sensitivity_only",
        "weights": {
            "ctq_weighted_sum": 0.28,
            "ctq_mean_progress": 0.24,
            "ctq_peak_progress": 0.13,
            "qapro_ratio_in_qa3": 0.30,
            "mab": 0.05,
        },
    },
}

PRIMARY_SCOPES = [
    "observed_all_exploratory",
    "observed_s3_stratified",
    "observed_s6_stratified",
    "strict_baseline_adjusted",
]


def load_engine():
    if not LEGACY_ENGINE.exists():
        raise FileNotFoundError(f"Shared ranking engine is missing: {LEGACY_ENGINE}")
    spec = importlib.util.spec_from_file_location("module_c_shared_ranking_engine", LEGACY_ENGINE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import shared ranking engine: {LEGACY_ENGINE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not ready: {path}")


def unweighted_means(path: Path) -> dict[str, float]:
    frame = pd.DataFrame(read_jsonl(path))
    required = {"student_key", "net_ctq"}
    if not required.issubset(frame.columns):
        raise ValueError(f"{path.name} lacks fields: {sorted(required - set(frame.columns))}")
    return frame.groupby("student_key")["net_ctq"].mean().to_dict()


def scheme_maps() -> tuple[dict[str, str], dict[str, str]]:
    labels = {k: v["label"] for k, v in SCHEME_DEFS.items()}
    types = {k: v["type"] for k, v in SCHEME_DEFS.items()}
    return labels, types


def same_cohort_frames(engine, primary: pd.DataFrame, alternate: pd.DataFrame):
    p = engine.normalized_scope(primary, "strict_baseline_adjusted")
    a = engine.normalized_scope(alternate, "strict_baseline_adjusted")
    common = sorted(set(p["student_key"]) & set(a["student_key"]))
    if not common:
        raise ValueError("q=.23 and q=.48 have no common strict eligible students")
    p = p.loc[p["student_key"].isin(common)].sort_values("student_key").reset_index(drop=True)
    a = a.loc[a["student_key"].isin(common)].sort_values("student_key").reset_index(drop=True)
    if p["student_key"].tolist() != a["student_key"].tolist():
        raise AssertionError("Scenario common-cohort alignment failed")
    return p, a


def baseline_scenario_comparison(
    engine,
    primary: pd.DataFrame,
    alternate: pd.DataFrame,
    primary_weights: dict[str, dict[str, float]],
    labels: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    q23, q48 = same_cohort_frames(engine, primary, alternate)
    payload: dict[str, Any] = {
        "primary_q": 0.23,
        "alternate_q": 0.48,
        "baseline_interpretation": "cross-study migration scenarios, not class-specific observed controls",
        "common_student_n": len(q23),
        "student_keys": q23["student_key"].tolist(),
        "weight_policy": "freeze q=.23 resolved weights in both scenarios to isolate baseline-q sensitivity",
        "global_rank_status": "exploratory because the strict common cohort contains multiple scale groups without validated cross-scale equivalence",
        "schemes": {},
    }
    score_rows: list[dict[str, Any]] = []
    for scheme_id in engine.ALL_CORE_SCHEMES:
        weights = primary_weights[scheme_id]
        p_rank, p_cut = engine.rank_frame(q23, engine.score_values(q23, weights))
        a_rank, a_cut = engine.rank_frame(q48, engine.score_values(q48, weights))
        comparison = engine.compare_rankings(p_rank, a_rank)
        within_scale_comparisons: dict[str, Any] = {}
        within_scale_maps: dict[str, dict[str, Any]] = {}
        for scale in sorted(set(q23["scale_group"]) & set(q48["scale_group"])):
            if scale == "mixed":
                continue
            p_scale = p_rank.loc[p_rank["scale_group"] == scale].copy()
            a_scale = a_rank.loc[a_rank["scale_group"] == scale].copy()
            drop_cols = [
                "rank", "top20_strict", "top20_boundary", "top20_inclusive",
                "bottom20_strict", "bottom20_boundary", "bottom20_inclusive",
            ]
            p_scale = p_scale.drop(columns=drop_cols)
            a_scale = a_scale.drop(columns=drop_cols)
            p_scale, _ = engine.rank_frame(p_scale, p_scale["score"])
            a_scale, _ = engine.rank_frame(a_scale, a_scale["score"])
            within_scale_comparisons[scale] = engine.compare_rankings(p_scale, a_scale)
            for _, scale_row in p_scale.iterrows():
                within_scale_maps.setdefault(scale_row["student_key"], {})[
                    "rank_q23_within_scale"
                ] = float(scale_row["rank"])
            for _, scale_row in a_scale.iterrows():
                within_scale_maps.setdefault(scale_row["student_key"], {})[
                    "rank_q48_within_scale"
                ] = float(scale_row["rank"])
        payload["schemes"][scheme_id] = {
            "scheme_label": labels[scheme_id],
            "weights_frozen_from_q23": weights,
            "q23_cutoff": p_cut,
            "q48_cutoff": a_cut,
            "within_scale_comparisons": within_scale_comparisons,
            **comparison,
        }
        merged = p_rank[[
            "student_key", "term", "scale_group", "score", "rank",
            "top20_strict", "top20_boundary", "top20_inclusive",
            "bottom20_strict", "bottom20_boundary", "bottom20_inclusive",
        ]].merge(
            a_rank[[
                "student_key", "score", "rank",
                "top20_strict", "top20_boundary", "top20_inclusive",
                "bottom20_strict", "bottom20_boundary", "bottom20_inclusive",
            ]],
            on="student_key",
            suffixes=("_q23", "_q48"),
        )
        for _, row in merged.iterrows():
            record = {
                "student_key": row["student_key"],
                "term": row["term"],
                "scale_group": row["scale_group"],
                "scheme": scheme_id,
                "scheme_label": labels[scheme_id],
                "score_q23": row["score_q23"],
                "rank_q23": row["rank_q23"],
                "score_q48": row["score_q48"],
                "rank_q48": row["rank_q48"],
                "rank_change_q48_minus_q23": row["rank_q48"] - row["rank_q23"],
                "top20_inclusive_q23": row["top20_inclusive_q23"],
                "top20_inclusive_q48": row["top20_inclusive_q48"],
                "bottom20_inclusive_q23": row["bottom20_inclusive_q23"],
                "bottom20_inclusive_q48": row["bottom20_inclusive_q48"],
                "cross_scale_comparison_used": True,
                "cross_scale_measurement_equivalence_validated": False,
            }
            record.update(within_scale_maps.get(row["student_key"], {
                "rank_q23_within_scale": None,
                "rank_q48_within_scale": None,
            }))
            score_rows.append(engine.to_builtin(record))
    return payload, score_rows


def annotate_within_scale_ranks(engine, records: list[dict[str, Any]]) -> None:
    """Add same-score within-scale ranks to both global exploratory scopes."""
    global_scopes = [
        "observed_all_exploratory",
        "strict_baseline_adjusted",
        "observed_mab_complete_case",
        "strict_baseline_adjusted_mab_complete_case",
    ]
    for scope in global_scopes:
        scope_schemes = sorted({
            row["scheme"] for row in records if row["scope"] == scope
        })
        for scheme_id in scope_schemes:
            positions = [
                i for i, row in enumerate(records)
                if row["scope"] == scope and row["scheme"] == scheme_id
            ]
            if not positions:
                continue
            scope_scales = {records[i]["scale_group"] for i in positions}
            cross_scale = len({s for s in scope_scales if s != "mixed"}) > 1
            for i in positions:
                records[i]["cross_scale_comparison_used"] = cross_scale
                records[i]["cross_scale_measurement_equivalence_validated"] = False
            for scale in sorted(scope_scales):
                if scale == "mixed":
                    continue
                scale_positions = [i for i in positions if records[i]["scale_group"] == scale]
                scores = pd.Series(
                    [records[i]["score"] for i in scale_positions],
                    index=scale_positions,
                    dtype=float,
                )
                ranks = scores.round(engine.TIE_DECIMALS).rank(method="average", ascending=False)
                flags, _ = engine.membership_flags(scores)
                for i in scale_positions:
                    records[i]["within_scale_rank"] = float(ranks.loc[i])
                    for col in flags.columns:
                        records[i][f"within_scale_{col}"] = bool(flags.loc[i, col])
            for i in positions:
                if records[i]["scale_group"] == "mixed":
                    records[i]["within_scale_rank"] = None
                    for suffix in [
                        "top20_strict", "top20_boundary", "top20_inclusive",
                        "bottom20_strict", "bottom20_boundary", "bottom20_inclusive",
                    ]:
                        records[i][f"within_scale_{suffix}"] = None


def mab_incremental_effect(
    engine, primary: pd.DataFrame
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Isolate the effect of adding 5% MAB on the exact complete-case cohort."""
    weights_5 = SCHEME_DEFS["weak_mab_complete_case"]["weights"]
    weights_0 = {
        factor: weight / (1.0 - weights_5["mab"])
        for factor, weight in weights_5.items()
        if factor != "mab"
    }
    payload: dict[str, Any] = {
        "comparison": "same cohort and same relative core weights; MAB changes only from 0% to 5%",
        "weights_mab_0": weights_0,
        "weights_mab_5": weights_5,
        "scopes": {},
    }
    rows: list[dict[str, Any]] = []
    for scope in ["observed_all_exploratory", "strict_baseline_adjusted"]:
        frame = engine.normalized_scope(primary, scope)
        frame = frame.dropna(subset=engine.CORE + ["mab"]).copy()
        rank_0, cutoff_0 = engine.rank_frame(frame, engine.score_values(frame, weights_0))
        rank_5, cutoff_5 = engine.rank_frame(frame, engine.score_values(frame, weights_5))
        comparison = engine.compare_rankings(rank_0, rank_5)
        reference_score = engine.score_values(frame, weights_0)
        corr_frame = frame[engine.CORE + ["mab"]].copy()
        corr_frame["mab0_reference_score"] = reference_score
        payload["scopes"][scope] = {
            "n": len(frame),
            "q_scenario": 0.23 if scope == "strict_baseline_adjusted" else None,
            "cutoff_mab_0": cutoff_0,
            "cutoff_mab_5": cutoff_5,
            "mab_correlations": {
                "pearson": corr_frame.corr(method="pearson")["mab"].to_dict(),
                "spearman": corr_frame.corr(method="spearman")["mab"].to_dict(),
            },
            **comparison,
        }
        merged = rank_0[[
            "student_key", "term", "scale_group", "mab", "score", "rank",
            "top20_strict", "top20_boundary", "top20_inclusive",
            "bottom20_strict", "bottom20_boundary", "bottom20_inclusive",
        ]].merge(
            rank_5[[
                "student_key", "score", "rank",
                "top20_strict", "top20_boundary", "top20_inclusive",
                "bottom20_strict", "bottom20_boundary", "bottom20_inclusive",
            ]],
            on="student_key",
            suffixes=("_mab0", "_mab5"),
        )
        payload["scopes"][scope]["max_absolute_rank_change"] = float(
            (merged["rank_mab5"] - merged["rank_mab0"]).abs().max()
        )
        for _, row in merged.iterrows():
            rows.append(engine.to_builtin({
                "student_key": row["student_key"],
                "term": row["term"],
                "scale_group": row["scale_group"],
                "scope": scope,
                "mab_saturated": row["mab"],
                "score_mab0": row["score_mab0"],
                "rank_mab0": row["rank_mab0"],
                "score_mab5": row["score_mab5"],
                "rank_mab5": row["rank_mab5"],
                "rank_change_mab5_minus_mab0": row["rank_mab5"] - row["rank_mab0"],
                "top20_inclusive_mab0": row["top20_inclusive_mab0"],
                "top20_inclusive_mab5": row["top20_inclusive_mab5"],
                "bottom20_inclusive_mab0": row["bottom20_inclusive_mab0"],
                "bottom20_inclusive_mab5": row["bottom20_inclusive_mab5"],
                "cross_scale_measurement_equivalence_validated": False,
            }))
    return payload, rows


def write_json(path: Path, payload: Any, engine) -> None:
    engine.dump_json(path, payload)


def build_report(
    meta: dict[str, Any],
    robustness: dict[str, Any],
    scenario: dict[str, Any],
    resolved: dict[str, Any],
    dhi_summary: dict[str, int],
    out_path: Path,
) -> None:
    strict = robustness["scopes"]["strict_baseline_adjusted"]
    observed = robustness["scopes"]["observed_all_exploratory"]
    pairs_strict = strict["pairwise_main_schemes"]
    pairs_observed = observed["pairwise_main_schemes"]
    pert_strict = [r for rows in strict["weight_perturbations"].values() for r in rows]
    pert_observed = [r for rows in observed["weight_perturbations"].values() for r in rows]
    delete_strict = [r for rows in strict["indicator_deletions"].values() for r in rows]
    delete_observed = [r for rows in observed["indicator_deletions"].values() for r in rows]
    nonlinear_strict = list(strict["nonlinear_diminishing_return"].values())
    nonlinear_observed = list(observed["nonlinear_diminishing_return"].values())
    q_rows = list(scenario["schemes"].values())
    strict_n = strict["n"]
    cohort_n = observed["n"]
    strict_cut = resolved["scopes"]["strict_baseline_adjusted"]["cutoffs"]["normative_balanced"]
    observed_cut = resolved["scopes"]["observed_all_exploratory"]["cutoffs"]["normative_balanced"]
    strict_extreme = strict["extreme_group_diagnostics"]["normative_balanced"]
    observed_extreme = observed["extreme_group_diagnostics"]["normative_balanced"]
    mab = robustness["mab_complete_case_sensitivity"]
    mab_effect = robustness["mab_incremental_effect_0_vs_5pct"]["scopes"]
    text = f"""# 模块C v4 多方案评分与稳健性结论

## 结论

本轮以冻结 v4 矩阵计算 {cohort_n} 人全量观察进展探索榜，并在 {strict_n} 人共同可计算样本上给出 q=.23 固定假设基线调整情景。两套榜单都包含多种量尺，因此全局名次只作探索比较，并同时给出 s3、s6 量尺内 midrank。q=.23 是跨研究迁移假设，不是本班实测自然基线或真实反事实；q=.48 仅作为同一共同样本的替代迁移情景。

透明主方案建议使用均衡型，同时并列报告突破优先型、质量导向型（教学诊断对照）和分组熵权型。四项纯熵权只用于敏感性，不代表最优权重。均衡型保留认知进展与QA质量的可解释平衡；其主方案地位来自权重含义清楚、q情景下排名保持度高和小幅权重扰动稳定，不是最优性证明。

## 稳健性

q=.23 严格情景四主方案两两 Spearman 最低为 {min(r['spearman_rho'] for r in pairs_strict):.3f}，全量观察榜为 {min(r['spearman_rho'] for r in pairs_observed):.3f}。单项权重相对±10%并重归一后，最低 Spearman 分别为 {min(r['spearman_rho'] for r in pert_strict):.3f}、{min(r['spearman_rho'] for r in pert_observed):.3f}；删去一个指标后则降至 {min(r['spearman_rho'] for r in delete_strict):.3f}、{min(r['spearman_rho'] for r in delete_observed):.3f}。因此只能表述为“对小幅权重变化稳健”，不能写成“对指标构成稳健”。

边际递减变换后，严格情景和全量观察榜的最低 Spearman 分别为 {min(r['spearman_rho'] for r in nonlinear_strict):.3f}、{min(r['spearman_rho'] for r in nonlinear_observed):.3f}；后20%含边界 Jaccard 最低为 {min(r['bottom20_inclusive_jaccard'] for r in nonlinear_strict):.3f}、{min(r['bottom20_inclusive_jaccard'] for r in nonlinear_observed):.3f}。总体名次比尾部名单稳定，极端组应用必须保留方案和边界说明。

在 q=.23 与 q=.48 的相同可比样本中，五套核心方案的 Spearman 最低为 {min(r['spearman_rho'] for r in q_rows):.3f}，前、后20%含边界 Jaccard 最低为 {min(r['top20_inclusive_jaccard'] for r in q_rows):.3f}、{min(r['bottom20_inclusive_jaccard'] for r in q_rows):.3f}。该比较只说明迁移假设变化对排序的敏感程度，不检验哪一个 q 更接近真实无AI反事实。

## 前后20%诊断

均衡型全量观察榜目标为 {observed_cut['target_k']} 人，前20%严格进入/边界/含边界人数为 {observed_cut['top_strict_n']}/{observed_cut['top_boundary_n']}/{observed_cut['top_inclusive_n']}，后20%为 {observed_cut['bottom_strict_n']}/{observed_cut['bottom_boundary_n']}/{observed_cut['bottom_inclusive_n']}。q=.23 假设基线调整榜目标为 {strict_cut['target_k']} 人，前20%为 {strict_cut['top_strict_n']}/{strict_cut['top_boundary_n']}/{strict_cut['top_inclusive_n']}，后20%为 {strict_cut['bottom_strict_n']}/{strict_cut['bottom_boundary_n']}/{strict_cut['bottom_inclusive_n']}。边界同分没有按学号拆分。

全量榜前20%的平均QA质量比和观察CTQ均值为 {observed_extreme['top20_inclusive']['means']['quality_ratio']:.3f}、{observed_extreme['top20_inclusive']['means']['ctq_mean_progress_raw']:.3f}，后20%为 {observed_extreme['bottom20_inclusive']['means']['quality_ratio']:.3f}、{observed_extreme['bottom20_inclusive']['means']['ctq_mean_progress_raw']:.3f}。q=.23 情景前20%的平均QA质量比和调整后CTQ均值为 {strict_extreme['top20_inclusive']['means']['quality_ratio']:.3f}、{strict_extreme['top20_inclusive']['means']['ctq_mean_progress_raw']:.3f}，后20%为 {strict_extreme['bottom20_inclusive']['means']['quality_ratio']:.3f}、{strict_extreme['bottom20_inclusive']['means']['ctq_mean_progress_raw']:.3f}。方向与评分公式一致，但前后组平均可评概念数接近1，且没有独立人工效标，因此这只是内部合理性诊断，不能称准确性验证。

## 解释边界

全量观察榜和 q=.23 假设基线调整榜都直接使用固定界合成，同时提供纯 s3、纯 s6 组内名次；跨量尺总名次尚未建立测量等值。s6严格样本只有8人，分层极端组重合率只能作小样本提示。

DHI主分权重为0：冻结DHI共 {dhi_summary['rows']} 条学生×量尺记录，其中 {dhi_summary['low_evidence_rows']} 条低证据，少量非低证据记录不足以支持统一主权重。学生自述没有独立复核，主分权重为0。MAB只在非缺失共同样本中以0.05权重运行敏感性，全量共同样本为 {mab['observed_mab_complete_case']['n']} 人，q=.23严格共同样本为 {mab['strict_baseline_adjusted_mab_complete_case']['n']} 人。

MAB纯增量检验保持四个核心指标的相对权重不变，只把MAB从0%增加到5%。全量共同样本的 Spearman 为 {mab_effect['observed_all_exploratory']['spearman_rho']:.3f}，前、后20%含边界 Jaccard 为 {mab_effect['observed_all_exploratory']['top20_inclusive_jaccard']:.3f}、{mab_effect['observed_all_exploratory']['bottom20_inclusive_jaccard']:.3f}，最大绝对名次变化 {mab_effect['observed_all_exploratory']['max_absolute_rank_change']:.1f}；q=.23严格共同样本对应为 {mab_effect['strict_baseline_adjusted']['spearman_rho']:.3f}、{mab_effect['strict_baseline_adjusted']['top20_inclusive_jaccard']:.3f}、{mab_effect['strict_baseline_adjusted']['bottom20_inclusive_jaccard']:.3f}，最大变化 {mab_effect['strict_baseline_adjusted']['max_absolute_rank_change']:.1f}。5%权重仍明显改变前列成员，支持MAB主分维持0；这才是MAB 5%本身的敏感性，与均衡型的差异还包含核心权重结构变化，不能混称纯MAB效应。

错误纠正率和自主推理没有统一全样本编码，不构造替代分数。所有结果都是评价情景与观察关联，不能识别学生、Agent、教学三方各自努力，也不能宣称因果AI效应。
"""
    out_path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary-matrix", type=Path, default=ROOT / "indicator_matrix.jsonl")
    parser.add_argument("--primary-metadata", type=Path, default=ROOT / "matrix_metadata.json")
    parser.add_argument("--primary-components", type=Path, default=ROOT / "strict_concept_components.jsonl")
    parser.add_argument("--alternate-matrix", type=Path, default=ROOT / "indicator_matrix_q048.jsonl")
    parser.add_argument("--dhi", type=Path, default=ROOT / "dhi" / "student_dhi.jsonl")
    parser.add_argument("--output-dir", type=Path, default=HERE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for path, label in [
        (args.primary_matrix, "q=.23 primary matrix"),
        (args.primary_metadata, "primary metadata"),
        (args.primary_components, "primary strict components"),
        (args.alternate_matrix, "q=.48 alternate matrix"),
        (args.dhi, "frozen DHI diagnostics"),
    ]:
        require_file(path, label)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(tempfile.mkdtemp(prefix=".ranking-stage-", dir=args.output_dir))

    engine = load_engine()
    primary = pd.DataFrame(read_jsonl(args.primary_matrix))
    alternate = pd.DataFrame(read_jsonl(args.alternate_matrix))
    meta = json.loads(args.primary_metadata.read_text(encoding="utf-8"))
    dhi_rows = read_jsonl(args.dhi)
    dhi_summary = {
        "rows": len(dhi_rows),
        "low_evidence_rows": sum(bool(row.get("low_evidence_flag")) for row in dhi_rows),
    }
    labels, types = scheme_maps()
    unweighted = unweighted_means(args.primary_components)

    score_records: list[dict[str, Any]] = []
    schemes_out: dict[str, Any] = {
        "schema_version": "module-c-v4-resolved-schemes-v1.0.0",
        "primary_baseline_q": 0.23,
        "alternate_baseline_q": 0.48,
        "baseline_status": "cross-study migration hypotheses, not class-specific observed controls",
        "scheme_labels": labels,
        "scope_labels": {
            "observed_all_exploratory": "v4全量观察进展探索榜",
            "observed_s3_stratified": "纯s3观察进展分层榜",
            "observed_s6_stratified": "纯s6观察进展分层榜",
            "strict_baseline_adjusted": "q=.23固定假设基线调整探索榜",
        },
        "scopes": {},
    }
    robustness: dict[str, Any] = {
        "schema_version": "module-c-v4-robustness-v1.0.0",
        "scopes": {},
    }
    correlation_rows: list[dict[str, Any]] = []

    strict_weights: dict[str, dict[str, float]] | None = None
    for scope in PRIMARY_SCOPES:
        frame = engine.normalized_scope(primary, scope)
        if frame[engine.CORE].isna().any().any():
            raise ValueError(f"Core missing values in scope {scope}")
        weights, entropy = engine.resolved_weights(frame, SCHEME_DEFS)
        records, ranked, cutoffs = engine.build_long_scores(scope, frame, weights, types, labels)
        for record in records:
            record["baseline_scenario_q"] = 0.23 if scope == "strict_baseline_adjusted" else None
            record["dataset_version"] = "v4_frozen"
        score_records.extend(records)
        schemes_out["scopes"][scope] = {
            "n": len(frame),
            "normalization_bounds": frame.attrs["bounds"],
            "weights": weights,
            "entropy_details": entropy,
            "cutoffs": cutoffs,
        }
        robustness["scopes"][scope] = engine.robustness_for_scope(
            scope, frame, weights, ranked, unweighted
        )
        correlations = robustness["scopes"][scope]["factor_correlations"]
        for method in ["pearson", "spearman"]:
            for factor_a, columns in correlations[method].items():
                for factor_b, value in columns.items():
                    correlation_rows.append({
                        "scope": scope,
                        "n": len(frame),
                        "method": method,
                        "factor_a": factor_a,
                        "factor_b": factor_b,
                        "correlation": value,
                    })
        if scope == "strict_baseline_adjusted":
            strict_weights = weights

    if strict_weights is None:
        raise AssertionError("Strict q=.23 weights were not resolved")
    mab_records, mab_summary = engine.add_mab_sensitivity(primary, SCHEME_DEFS)
    for record in mab_records:
        record["baseline_scenario_q"] = 0.23 if "strict" in record["scope"] else None
        record["dataset_version"] = "v4_frozen"
    score_records.extend(mab_records)
    robustness["mab_complete_case_sensitivity"] = mab_summary
    annotate_within_scale_ranks(engine, score_records)

    scenario, scenario_scores = baseline_scenario_comparison(
        engine, primary, alternate, strict_weights, labels
    )
    robustness["q23_vs_q48"] = scenario
    mab_effect, mab_effect_scores = mab_incremental_effect(engine, primary)
    robustness["mab_incremental_effect_0_vs_5pct"] = mab_effect

    with (stage_dir / "scores.jsonl").open("w", encoding="utf-8") as f:
        for record in score_records:
            f.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    pd.DataFrame(score_records).to_csv(stage_dir / "scores.csv", index=False, encoding="utf-8-sig")
    with (stage_dir / "q23_vs_q48_scores.jsonl").open("w", encoding="utf-8") as f:
        for record in scenario_scores:
            f.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    pd.DataFrame(scenario_scores).to_csv(
        stage_dir / "q23_vs_q48_scores.csv", index=False, encoding="utf-8-sig"
    )
    with (stage_dir / "mab_0_vs_5_scores.jsonl").open("w", encoding="utf-8") as f:
        for record in mab_effect_scores:
            f.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    pd.DataFrame(mab_effect_scores).to_csv(
        stage_dir / "mab_0_vs_5_scores.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(correlation_rows).to_csv(
        stage_dir / "factor_correlations.csv", index=False, encoding="utf-8-sig"
    )
    write_json(stage_dir / "schemes.json", schemes_out, engine)
    write_json(stage_dir / "robustness.json", robustness, engine)
    build_report(
        meta, robustness, scenario, schemes_out, dhi_summary, stage_dir / "方法结论.md"
    )

    output_paths = [
        stage_dir / "scores.jsonl",
        stage_dir / "scores.csv",
        stage_dir / "q23_vs_q48_scores.jsonl",
        stage_dir / "q23_vs_q48_scores.csv",
        stage_dir / "mab_0_vs_5_scores.jsonl",
        stage_dir / "mab_0_vs_5_scores.csv",
        stage_dir / "factor_correlations.csv",
        stage_dir / "schemes.json",
        stage_dir / "robustness.json",
        stage_dir / "方法结论.md",
    ]
    manifest = {
        "schema_version": "module-c-v4-ranking-manifest-v1.0.0",
        "as_of_policy": "read only explicitly supplied frozen v4 matrices; never recompute from drifting live sources",
        "inputs": {str(p): sha256(p) for p in [
            args.primary_matrix, args.primary_metadata, args.primary_components,
            args.alternate_matrix, args.dhi
        ]},
        "outputs": {p.name: sha256(p) for p in output_paths},
        "counts": {
            "primary_matrix_rows": len(primary),
            "alternate_matrix_rows": len(alternate),
            "primary_strict_rows": int(primary["strict_baseline_eligible"].sum()),
            "q23_q48_common_rows": scenario["common_student_n"],
            "score_records": len(score_records),
            "scenario_score_records": len(scenario_scores),
            "mab_effect_score_records": len(mab_effect_scores),
        },
        "rules": {
            "sample_minmax_used": False,
            "missing_zero_fill_used": False,
            "per_student_weight_redistribution_used": False,
            "tie_rank": "average_midrank",
            "q_comparison_weights": "frozen_from_q23",
        },
    }
    manifest_path = stage_dir / "manifest.json"
    write_json(manifest_path, manifest, engine)
    for staged_path in output_paths + [manifest_path]:
        os.replace(staged_path, args.output_dir / staged_path.name)
    shutil.rmtree(stage_dir)
    print(json.dumps({"status": "ok", **manifest["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
