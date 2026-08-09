# Coding Agent 能力建设路线

> 本文档概述“如何从现有项目起步，构建一个 Coding Agent”的完整路线。
> 项目启动流程见 [README.md](./README.md)。

## 目标拆解

构建 Coding Agent 的本质是让模型能够自主完成闭环：

```text
接收任务
  ↓
拆解计划（思考）
  ↓
调用工具：看代码 / 改代码 / 跑命令 / 看测试结果
  ↓
观察结果，发现问题
  ↓
修正并继续，直到任务完成
  ↓
输出总结
```

这就是经典的 **ReAct（Reason + Act）** 模式：思考 → 行动 → 观察 → 再思考。

## 已有家底

- **推理层已通**：本地 vLLM + Qwen2.5-Coder-7B-Instruct-AWQ，OpenAI 兼容 API（8000 端口）
- **`back/llm_client.py`**：封装了模型调用（流式输出）
- **`back/tool1.py`**：搜索工具雏形（尚未完成）
- **`back/ReAct.py`**：ReAct 流程占位文件（当前为空）

缺少的核心三块：

1. Agent 主循环（ReAct loop）
2. 工具注册与执行（tool registry + executor）
3. 上下文管理（截断 / 摘要 / 迭代上限）

## 构建路线

### 第 1 步：最小 ReAct 循环（先做一个工具）

- 让模型输出固定 JSON，例如：

```json
{"tool": "run_bash", "args": {"cmd": "ls"}}
```

- 流程：

```text
system prompt（角色 + 可用工具 + JSON 输出格式）
    ↓
调用 llm.think() 得到 {"tool": "...", "args": {...}}
    ↓
解析并执行工具，拿到观察结果
    ↓
把结果拼进 messages，继续循环（最多 N 轮）
    ↓
模型输出 "DONE" 或轮次用尽 → 结束
```

- 先只做 `run_bash` 一个工具，跑通“写代码 → 运行 → 看报错 → 修”的闭环。

### 第 2 步：加代码工具集

增加常用工具：

- `read_file`：读取文件
- `write_file`：写入 / 修改文件
- `list_dir`：列出目录
- `run_test`：运行测试
- `git_status` / `git_diff`：查看版本库状态

做一个工具注册表（字典：名称 → 函数 + 描述），在系统提示词里列出可用工具。
完成这一步后，Agent 才真正“会写代码”。

### 第 3 步：上下文管理

工具返回结果非常占 token，几轮之后 4096 的 `max-model-len` 就不够用了，需要：

- 工具结果截断（例如只保留前后 500 字符）
- 历史对话压缩 / 摘要
- 限制最大迭代次数

### 第 4 步：完善工程体验

- 错误重试与恢复
- 任务完成判定（明确输出 DONE 标记）
- 接入搜索工具（AppBuilder / 百度千帆）
- 前端展示（`front/` 当前为空）

## 具体第一步可以这么做

在 `back/` 下新建 `agent_core.py`，实现：

```python
SYSTEM_PROMPT = """
你是一个编码助手 Agent。
可用工具：run_bash
你必须严格按以下 JSON 格式输出：
{"tool": "run_bash", "args": {"cmd": "要执行的命令"}}
如果任务已完成，输出 {"tool": "DONE", "args": {}}
"""

# 循环伪代码
# for i in range(MAX_STEPS):
#     resp = llm.think(messages)              # 得到 JSON
#     if resp["tool"] == "DONE": break
#     result = tools[resp["tool"]](**resp["args"])
#     messages.append({"role": "user", "content": f"观察结果：\n{result}"})
```

测试任务建议：

1. “在项目里新建 `hello.py` 并运行它”
2. “写一个快速排序并运行测试”

跑通这个闭环，Agent 核心就成立了。

## 需要学习的内容

### 核心概念

- **ReAct / Agent 模式**：think → act → observe 循环设计，以及提示词如何写才能让模型稳定输出
- **结构化输出**：让模型稳定输出 JSON；vLLM 对 Qwen 支持原生 function calling（tool-call-parser），但手写 JSON 协议更简单，更适合 7B 小模型
- **上下文与 token 管理**：截断、摘要、迭代上限

### 工程基本功

- git：提交、diff、回滚
- 测试：怎么写、怎么跑、怎么看结果
- 调试：读懂报错信息（Agent 的本质是替你做这些事，你得先会判断它做得好不好）

### 安全边界

- 让 Agent 执行 shell 命令有风险
- 至少增加：命令白名单、危险命令拦截、人工确认机制
- 后期可考虑在容器 / 沙箱中运行 Agent

### 进阶方向

- **MCP（Model Context Protocol）**：工具接入的行业标准，工具多了之后再上不迟
- 对比成熟框架：LangChain、OpenAI Agents SDK、Codex CLI 等，理解它们的设计后再借鉴

## 现实预期

- 7B 本地模型完全可以跑通 Coding Agent 流程，但能力有限：
  - 适合：小任务、单文件修改、简单重构、教学演示
  - 吃力：大型仓库导航、复杂架构设计
- 更合理的设计是**用工具补足模型**：所有信息（文件内容、测试结果、git diff）都通过工具喂给它，不要让模型凭记忆猜。
- 建议先手写循环理解原理，之后再引入框架或 MCP，避免“只会调框架、不懂原理”。

## 里程碑检查清单

- [ ] 第 1 步：`run_bash` 单工具闭环跑通
- [ ] 第 2 步：文件读写 / 测试 / git 工具可用
- [ ] 第 3 步：长任务上下文不爆
- [ ] 第 4 步：搜索接入 + 前端展示
- [ ] 安全：命令白名单 / 人工确认
- [ ] 进阶：MCP 协议接入
