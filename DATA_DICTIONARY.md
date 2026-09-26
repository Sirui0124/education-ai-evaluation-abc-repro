# 数据字典

所有 `jsonl` 文件一行一条 JSON 记录，UTF-8 编码。`csv` 为 UTF-8（部分带 BOM），首行为字段名。字段中的 `null`/空白表示未观察、不可评或未进入该阶段，不能自动转成 0。以下列出一键复算与板块衔接使用的主字段；更细字段见各目录规则文档和输入样例。

| 数据表 | 粒度 | 主键或关联键 | 主要字段及定义 |
|---|---|---|---|
| `conversation_labels.jsonl` | 原始会话 | `session_id`；有效会话另有 `conversation_id` | `interaction_tier`：仅QA、仅QA3、QA Pro；空值表示剔除；`exclusion_status` 保留剔除原因；`existing_topic_labels` 是主题标签，不能替代认知评分 |
| QA3 v3.1 `annotations.jsonl` | 原始会话及任务段 | `session_id` | `segments` 含有效任务段、学生回合、理由和证据；`REVIEW`、`DATA_REVIEW` 为待核状态 |
| 领域 `annotations.jsonl` | 会话及知识单元 | `id`，与 `conversation_id` 对齐 | `units[].domain` 为领域，`topic` 是话题，`concepts` 是学生支持的知识点；多领域可以共存 |
| v5 `record_labels.csv` | 有效 QA3 会话 | `id`；`student_key` 为学期×脱敏学生 | `terra_`、`sol_` 前缀是两名独立标注者，`final_` 是裁决结果；后缀 `baseline_s6`/`baseline_s3` 为首次有效回合，`highest_s6`/`highest_s3` 为全场已见最高；`U` 是证据不足；仅 QA3 的 `highest_*` 为空 |
| v5 `metrics.json` | 阶段×量尺×分组 | `stages[stage][group][scale]` | `n` 为双标记录数；`exact` 精确一致数；`nominal_alpha_with_u` 将 U 当独立名义类别；`cohen_kappa_with_u` 用两独立标注者计算；裁决结果不进入一致性 |
| `学生领域采纳版.jsonl` | 学生×学期×领域 | `student_key` + `domain` | `before_score`、`after_score` 是当前量尺的数值或经验代理；`pair_status=COMPARABLE` 才有 `delta_l=after−before`；`domain_pair_valid` 为核对结果；不可配对保留 `null` |
| `学生指标采纳版.jsonl` | 学生×学期 | `student_key` | QA3/QAPro 使用、领域覆盖和认知指标汇总；比单条领域表更高一级，不可反推缺失领域的真实能力 |
| `学生指标与多方案排名_174人.jsonl` | 纳入旧版 AIV 的学生 | `student_key` | `observed_ctq_sum_equal` 为概念总进展，`observed_ctq_mean_equal` 为均值，`observed_ctq_peak` 为峰值，`quality_ratio=QAPro/QA3`；`scores_and_rankings.observed_all_exploratory.normative_balanced` 存旧版分数与排名；`strict_baseline_eligible` 表示情景基线资格 |
| 新八指标 `weights.json` | 评价目的×八指标 | 目的名称 | `schemes` 中每目的八项全精度权重；仅是权重方案，尚无 H/E 完整学生得分 |

## 编码和缺失约定

- 六级 `L1`–`L6` 与独立三级 `低/中/高` 是分别标注的两套结果，不从其中一套直接推出另一套。
- `U` 是认知证据不足，与缺标、数据错误和真实低分分开。
- 学生学期身份是本数据内关联键；同一数字学生标识跨学期不自动视为同一分析单位。
- `before_score`/`after_score` 可为直接六级或领域内三级经验折算。跨领域数值比较是研究假设，不是已验证测量等值。
- 模块 C 的 H/E 未全量评分时应保留缺失，不能用均值、零或旧榜代替最终新榜。
