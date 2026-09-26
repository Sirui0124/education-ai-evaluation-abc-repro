# 问题2接口 v1

输出位置：`results/module_b_causal_v1/q2_interface.csv`。一行＝学生×学期×知识领域×变化尺度×记录×假设情景。同一学生可能有多个QAPro记录。每条候选保留慢、中、快三行，即使不可计算也保留U。正式效应估计在`estimates.json`，不能把三情景当成三倍样本。

## 统一终点

- 主实际变化：`signed_observed_change = after_L − baseline_L`，允许正、零、负。after_L是后续窗口最高可信学生L；before不计入after最高值。
- 主反事实：在与真实after一致的观测时点/机会下，计算最高观察L的分布，再求期望。`expected_end_L = E[max(Y0(t1),…,Y0(tn))]`，并非`max(E[Y0(t1)],…)`或单个终点状态期望。
- `baseline_expected_change = expected_end_L − expected_start_L`。
- `tool_excess_gain = signed_observed_change − baseline_expected_change`，仅在评分、顺序与机会可比性符合条件时输出；归因状态为ASSUMPTION_CONDITIONAL。
- `cumulative_peak_gain = max(0,signed_observed_change)`仅为辅助，不参与主归因，不支持退步判断。
- `endpoint_definition`和`counterfactual_endpoint_definition`明确两者目标。当前实现统一支持after窗口最高值；若问题2改用末次L、均值或保持成绩，不能直接复用本反事实，需标endpoint_mismatch并留空归因量。

## 时间窗与证据位置

| 字段 | 跨时间 longitudinal | 对话内 within_qapro |
|---|---|---|
| before_window_start_at | 首个QA3任务所属会话创建时间 | 空；没有逐轮时钟 |
| before_window_end_at | 空；原数据无任务结束时钟 | 空 |
| before_evidence_at | 空；无逐轮证据时钟 | 空 |
| after_window_start_at | baseline_at，开区间 | 空 |
| after_window_end_at | 预先指定的end_at | 空 |
| after_evidence_at | final_evidence_at：最高L证据所属会话创建时间，非逐轮精确时间 | 空 |
| session_created_at | 基线会话创建时间 | 该QAPro所属会话创建时间 |
| before_window_start/end_turn | 空，基线任务由baseline_unit_id定位 | baseline_turn |
| after_window_start_turn_exclusive | 空 | feedback_turn，不计反馈自身 |
| after_window_end_turn | 空 | 原QAPro任务turn_end |
| after_evidence_turn | 空 | final_turn，最高L证据轮次，不必等于末轮 |
| interval_length | (end_at−baseline_at)/86400，天 | post_opportunities，独立学生作答机会 |
| after_observation_offsets_days | after窗口全部可评分单元相对基线的天数JSON数组 | 空；机会索引为1…n |

时钟缺失保持空，不能以会话创建时刻伪装成每轮发生时刻。`clock_resolution=session_creation_only_not_turn_time`提示来源精度。final_evidence_at在本接口仍只是会话级实际时间定位；更细粒度证据时间需原始数据支持。

`before_measurement_units=1`表示首个基线任务单元，不表示只有一条学生发言。`after_measurement_units`是经过复核的可评分单元/作答机会数。两边数量不同不自动等价，需要measurement_protocol_ref说明：采用预先固定的相同机会抽样，或有经验证、能处理极值机会差异的评分方案；否则U。原始source_followup_units只是导出候选数，不足以证明可比。

## 基线成长与速度

`expected_start_L`为给定的学生起点；`expected_end_L`为无本工具时after最高值期望；`baseline_expected_change`为给定窗口的累计预期变化；`baseline_average_rate`为累计变化除以interval_length。单位由`baseline_rate_unit`给出（L_per_day/L_per_learning_opportunity）。

`rate_kind=window_average_NOT_constant_instantaneous_rate`。模型非线性，延长时段或改变机会数必须重跑，不能拿平均速度机械乘新时长。无本工具的L6学生也可能有短期表现下降，联合参照的变化不强制非负。

`baseline_source=ASSUMPTION_ONLY`；`baseline_scope`是自然背景成熟、正常教学/自学和替代资源的联合参照。当前μ、普通学习速率和难度因子都是结构假设，不能当作从数据独立识别的纯自然成熟速度。

`willingness`、`other_ai`保持原始已知/unknown值，`difficulty`是学期领域假设值；unknown只在情景内代入不同取值，不改写成真实学生特征。初始能力直接通过baseline_L进入反事实起点。

## 不确定性、未知与可信度

- `baseline_scenario_min/max`和`excess_scenario_min/max`为三个假设情景的范围；`scenario_range_type`明确不是95%区间。
- `estimates.json`的conditional_sampling_ci95/conditional_p_two_sided仅是固定假设条件下按真实学生等权汇总的统计量。它们不包括假设参数误差、标注噪声、班级相关性或选择偏差。
- 不生成虚拟学生以增加N；外部网格行数永远不进入显著性检验。
- 缺L、U、证据顺序不明、未来信息用于初始意愿、观察机会不可比或日程未知：attribution_status=U、tool_excess_gain空；exclusion_reasons保留原因。direction=U不覆盖已有数值，仅说明尚未通过可比性审查。
- 可信度不乘变化幅度。label_evidence_ref、mechanism_evidence_ref、measurement_protocol_ref保存依据；数值语义仍是原始等级变化。
- QAPro是使用后筛选，只解释具备该过程证据的记录；不能用其平均效果代表所有使用者。跨时间首QA3样本同样有进入选择和后续缺失偏差。不能用对话停下来推断零增量。
- 最高值容易受单次错标抬高。必须复核决定最高值的学生原文，并比较更严格的可信等级规则；代码另外输出label_noise_sensitivity.json，在假设相邻误标概率0.05下重新计算对照。这不是对实际标签错误的充分修正，更不是实测错误率。

## 需要与用户讨论的定性条件

1. **不用本工具时保留什么资源？** 正常教学、自学和其他AI是否照常；决定counterfactual定义及other_ai情景，不等同完全无AI。
2. **什么证据算可信L、可比机会？** 单次独立解释即可，还是需重复/迁移验证；决定label_status、measurement_protocol_ref和纳入样本，不给任意可信度权重。
3. **普通成长多快、难度如何排列？** 教师给出合理慢/中/快范围与领域相对难度；进入hj、μ、δ、w和difficulty，所有未校准数值保留假设来源。

默认假设已能运行，不把这些讨论变成代码完成的审批门槛；它们影响最终教育解释。当前无正式L输入，所以正式效应为空，这是预期行为。

2026-09-26 增加追溯列：`baseline_version`、`baseline_config_sha256`、`run_id`，对应同目录 `run_manifest.json` 和 `baseline_config_snapshot.json`。新预制参数与研究边界见 `BASELINE_RESEARCH.md`；新结果目录为 `results/module_b_causal_literature_v2`，旧目录保留。六级输入限定不变。
