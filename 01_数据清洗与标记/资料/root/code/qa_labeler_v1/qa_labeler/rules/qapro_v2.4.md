# QA Pro 冻结命中打标标准（v2.4）

## 输入

每场已由同一版本的可复算检索程序生成三组冻结记录：`r1_hits`、`r2_hits`、`r3_hits`。它们分别对应：

1. 学生采用明确方法、模型、变量或步骤；
2. 学生对真实领域问句作出有效回答；
3. 学生问题链保持主题一致并用至少两个方向标记缩窄概念。

首问只作基线，不能出现在 R1/R2 证据中。标注员不得新增、删除或重新解释冻结命中记录；如文件结构损坏，只报告错误。

## 标签

- 任一命中列表非空：`ENTER`；
- 三个列表都为空：`NOT_ENTER / NO_COGNITIVE_CHANGE`；
- 主类型按 `R1 > R2 > R3`：
  - R1 非空：`R1_METHOD_MODEL_VARIABLE`
  - 否则 R2 非空：`R2_EFFECTIVE_ANSWER`
  - 否则 R3 非空：`R3_DIFFERENTIATED_QUESTION`
  - 均为空：`null`

每行输出 `id,r1,r2,r3,label,primary_type,reason`。其中 r1/r2/r3 分别完整复制对应冻结命中列表。

## 合格门槛

固定 200 场；两名全新独立标注员。一致率不低于 90%，双方 `ENTER` 比例均在 30%–70%。
