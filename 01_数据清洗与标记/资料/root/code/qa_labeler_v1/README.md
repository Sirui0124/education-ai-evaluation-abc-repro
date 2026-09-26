# 有效 QA3、QAPro 独立打标代码包

输入一批完整对话，输出每场的有效 QA3、QAPro 标签、原因和原文证据。采用 **QA3 v3.1 + QAPro v2.4**，QAPro 以用户指定任务 `01a0d981-3295-7010-be2c-4d2e79e7c15f` 最新交付为准。

包版本：1.0.0。运行环境：Python 3.9 或以上。运行不需要第三方 Python 库，不依赖原项目目录、Codex 登录、历史样本或个人电脑路径。

## 1. 先离线试跑

解压后在 `qa_labeler_v1` 目录打开终端：

```bash
python3 -m qa_labeler --input examples/conversations.jsonl --qa3-annotations examples/qa3_annotations.jsonl --output out-demo
```

示例为人工构造的四场对话；随包 QA3 标注用于演示离线导入，**不冒充模型实测结果**。预期输出：QA Pro 1 场、仅 QA3 1 场、空对话 1 场、疑似老师剔除 1 场。

## 2. 给新对话自动打标

有效 QA3 需要理解完整对话，程序将每场对话发送到你配置的模型接口进行语义标注；QAPro 随后在本地计算。接口需要兼容 `/chat/completions`，支持 JSON 输出。每场单独请求，不携带其他会话的历史。

在自己的环境中配置以下变量（代码不会保存密钥）：

```bash
export QA_BASE_URL='https://你的接口域名/v1'
export QA_MODEL='你的模型标识'
export QA_API_KEY='你的密钥'
python3 -m qa_labeler --input conversations.jsonl --output out-labels
```

程序自动在基址后拼接 `/chat/completions`，不要把完整请求路径填入基址。原 QA3 标准使用 `gpt-5.6-terra / medium`；本包默认发送 `reasoning_effort=medium`，模型标识由你的服务提供。换模型后应重新抽样核验语义一致性。

如果接口不支持 JSON Schema，使用 `--json-mode object`；如果不支持推理强度参数，使用 `--reasoning-effort omit`。这两项均不会放松本地结构和证据校验。单次默认超时 180 秒、失败最多重试 2 次，可用 `--timeout`、`--retries` 调整。

输入也可以是 JSON 数组、单场 JSON 对象，或包含多个 `.json` / `.jsonl` 文件的目录：

```bash
python3 -m qa_labeler --input ./dialogs --output out-labels
```

目录只读取第一层文件，按文件名排序；所有文件中的会话 ID 必须全局唯一。每场全文发送，不截断、不按固定字数拆分；超出模型上下文或请求失败的会话标为 `ERROR`，不会自动改判“不有效”。

## 3. 输入格式

JSONL 每行一场完整对话，正文中的换行应使用 JSON 转义。以下单场对象也可直接保存成 `.json`：

```json
{
  "id": "dialogue-001",
  "messages": [
    {"role": "user", "content": "什么是非平稳序列？"},
    {"role": "assistant", "content": "统计性质随时间变化。请举一个非平稳序列？"},
    {"role": "user", "content": "股价"}
  ]
}
```

也支持 `turns` 数组，使用 `role: student/agent` 和 `text` 字段。`turn_index` 可省略，程序按输入顺序从 1 编号；如果提供，则必须是按顺序连续递增的整数。正文保持原样，不去重、不删短答、不改写证据。没有角色边界的长文本、图片、PDF、Excel 需先转换为上述结构。

可选字段 `identity_role: teacher` 沿用已有身份审计结果，标记为“疑似老师剔除”，优先于空对话判断。程序不会根据文风猜测教师身份。`domain`、`topic`、`student_id` 等自定义字段保存在输出 `metadata` 中，不参与 QAPro 判定，也不自动补领域标签。

## 4. 输出是什么

| 文件 | 用途 |
|---|---|
| `labels.csv` | 可用 Excel 打开的会话汇总表 |
| `labels.jsonl` | 完整结果，含任务段、理由、学生证据和三组命中 |
| `summary.json` | 会话数量、状态及层级汇总 |
| `manifest.json` | 输入、代码与规则哈希，以及模型配置；不含密钥 |
| `cache/` | 每场独立缓存，支持中断后继续 |

主要字段：

| 字段 | 含义 |
|---|---|
| `qa3` | `true` 有有效 QA3；`false` 已判无有效 QA3；`null` 未定或被剔除 |
| `qapro` | 仅在 QA3 为 true 时输出 true/false；其他情况为 null，表示未进入此步骤 |
| `tier` | 仅QA、仅QA3、QA Pro；待复核或剔除可为空 |
| `status` | DONE、REVIEW、DATA_REVIEW、ERROR |
| `exclusion` | 不剔除、空对话、疑似老师剔除 |
| `segments` | QA3 语义任务段及逐段原文证据 |
| `qapro_details` | ENTER/NOT_ENTER、主类型、R1/R2/R3 完整命中 |

`REVIEW` 表示语义边界待复核，`DATA_REVIEW` 表示正文或角色不完整，`ERROR` 表示调用或校验失败，三者均不应直接当作负例。会话已有一段明确 QA3、另一段 REVIEW 时，保留已成立的 QA3 和 QAPro 结果，同时保留 REVIEW 状态。

R1/R2/R3 可重叠；主类型优先级 R1 > R2 > R3。QAPro 为假时原因是 `NO_COGNITIVE_CHANGE`；为真时完整证据在命中列表内。未进入 QA3 的情况保留 `qa3_reason`，例如无需追答、对话中断等原标准原因码。

重新执行相同命令会复用成功缓存，只重试 ERROR。修改输入、规则、代码或模型配置后需指定新输出目录，防止混用结果。命令退出码：0 完成（仍需查看是否有复核项）；1 输入/配置错误；2 存在失败会话。

## 5. 已有 QA3 标注时完全离线运行

```bash
python3 -m qa_labeler --input conversations.jsonl --qa3-annotations existing_qa3.jsonl --output out-offline
```

导入文件每行需有 `id`、原文 `turns`/`messages` 和 `segments`，结构见 `examples/qa3_annotations.jsonl`。程序逐场核对正文、角色、回合、证据和分段；不能仅提供一个 `qa3=true` 就跳过验证。缺记录或正文不一致的会话为 ERROR。

## 6. 在其他 Python 程序中调用

可以在包目录使用，也可执行 `python3 -m pip install .` 安装后调用。安装过程需要 setuptools；直接运行不需要安装步骤。

```python
from qa_labeler import label_conversations
from qa_labeler.backend import APIAnnotator
import os

annotator = APIAnnotator(
    base_url=os.environ["QA_BASE_URL"],
    api_key=os.environ["QA_API_KEY"],
    model=os.environ["QA_MODEL"],
)
results = label_conversations(conversations, annotator)
```

`conversations` 为输入对象列表。也可传入自定义 `annotate(record)` 函数，返回单场 QA3 结构；返回内容仍需通过同一套校验。

## 7. 规则与验证范围

完整标准位于 `qa_labeler/rules/`。QA3 先划分语义任务段，不要求三轮；只要一段成立，整场即为有效 QA3。QAPro v2.4 原样移植三步程序：提取学生发言及 AI 问句、检索候选、冻结 R1/R2/R3 命中。为了保持最终版本一致，检索作用于整场，不额外增加任务段过滤，不套用 v0.9 语义判据，不设置进入比例配额。

v2.4 的 R1、R2、R3 使用固定正则、问句提取和公共文本锚点。代码可复算不等于已经证明认知变化的真实性；词面命中可能与人工语义判断不同。新对话的语义质量仍需抽检，QA3/QAPro 均不能直接证明学习增量。

历史 708 场 QAPro 的标签、主类型和完整命中列表可精确复算为 425 ENTER、283 NOT_ENTER。验证记录见 `verification.json`，来源说明见 `PROVENANCE.md`。历史真实对话、身份数据和密钥不放入代码包。

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖输入校验、证据真实性、QA3/QAPro 层级、异常状态、断点恢复和本地 HTTP 接口模拟。接口模拟不等于真实供应商调用成功；本次打包未调用远程模型重新判定新对话的 QA3。
