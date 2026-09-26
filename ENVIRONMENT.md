# 环境说明

## 快速复算

- Python 3.9 或更新版本；`reproduce.py` 仅使用标准库。
- macOS、Linux 和 Windows 均可直接运行 `python3 reproduce.py --claim all`。Windows 若命令为 `py`，使用 `py -3 reproduce.py --claim all`。
- 无需安装依赖，无需 GPU、网络、模型账户、密钥或 Notebook 服务器。
- 从 GitHub ZIP 解压后在根目录运行。输入路径相对脚本定位，不依赖当前终端所在目录。
- 随机单项复算：`python3 reproduce.py --claim random --seed 42`。

## 其他代码

`01_数据清洗与标记/资料/root/code/qa_labeler_v1` 的离线示例和单元测试也仅需 Python 3.9；新会话自动 QA3 标注需要兼容 Chat Completions 的模型接口及自行配置的环境变量。重新跑语义模型属于新实验，不能替代仓库内冻结标签的复算。模块 B 的旧分析脚本和工作簿生成脚本保留原工程绝对路径及 Node 依赖，用于溯源；一键数值复算以仓库根目录 `reproduce.py` 为准。

建议 2 GB 空闲磁盘空间，用于克隆、解压和可能生成的文件。快速复算只读输入，不改写冻结结果。项目包含教学对话原文和学生标识（源方已脱敏，公开副本另遮蔽联系信息）；转用时仍应遵守数据提供方的授权条件。
