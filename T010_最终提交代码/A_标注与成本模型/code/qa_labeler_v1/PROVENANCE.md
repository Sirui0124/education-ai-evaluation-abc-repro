# 版本来源

用户指定的依据任务：`codex://threads/01a0d981-3295-7010-be2c-4d2e79e7c15f`，标题《定义QAPro多轮交互指标》。采用该任务最新完成轮次交付的 QAPro v2.4，而非其上一轮 v0.9。

本包来源于同项目的以下文件：

- `workspace/data_clean/module_b_dialogue_validity_v3_1_full/standard_v3.md`：完整复制 QA3 v3.1 标准。
- `workspace/code/scripts/label_dialogue_validity_full.py`：提取 schema、语义 Prompt、标签枚举、分段及证据校验和会话汇总函数，移除原项目的路径、固定总量、角色审计文件和个人 CLI 依赖。
- `workspace/code/scripts/build_qapro_student_retrieval_input.py`：原样复制为 `student_retrieval.py`。
- `workspace/code/scripts/build_qapro_retrieval_candidates.py`：原样复制为 `candidates.py`。
- `workspace/code/scripts/build_qapro_v24_hits.py`：原样复制为 `frozen_hits.py`。
- `题目理解/模块B_QAPro冻结命中打标标准_v2.4.md`：完整复制。
- `workspace/data_clean/module_b_full_hierarchy_v1/qapro_708_labels.jsonl`：历史逐场 QAPro 复算参照，不随包分发。

本包新增通用输入适配、API 接口、离线导入、缓存、CSV/JSONL 输出、严格结构校验、运行参数和回归测试。QAPro 规则未调整；不重新定义认知分级、不改动原项目的标签文件。

原 QA3 规则末尾保留了历史试标页面的相对链接，作为原文溯源；该页面不随包提供，运行也不依赖该链接。历史标准中的“QA Pro 留待后续”只描述当时 QA3 步骤的范围；本包在该步骤之后按独立的 v2.4 执行 QAPro。
