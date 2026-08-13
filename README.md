# HelloAents 项目说明

## 项目概述

本项目是一个运行在 WSL2 / Linux + NVIDIA GPU 上的**本地 Coding Agent**：

- 推理后端：本地部署的 **Qwen2.5-Coder-7B-Instruct-AWQ**（4bit AWQ 量化，适配 8GB 显存），通过 vLLM 提供 OpenAI 兼容 HTTP API；
- Agent 核心：`back/ReAct.py` 实现 ReAct（Reason + Act）主循环，让模型调用文件 / git / shell / 知识库工具真正完成任务；
- 上下文管理：`back/memory.py` 提供五层记忆（短期滑动窗口、历史压缩、长期记忆、外部状态、按需检索）；
- 终端前端：`front/agent_cli.py` 是基于 Textual 的 Codex 风格界面，支持 Agent 模式和对话模式；
- 知识库：`back/search_engineer/` 手写中文分词 + 倒排索引 + TF-IDF 搜索引擎，已接入 OpenCV 文档知识库。

整体流程：

```text
下载模型（download_awq.py）
        ↓
启动 vLLM 服务（back/vllm_server/start.sh）
        ↓
监听 http://localhost:8000（OpenAI 兼容 API）
        ↓
启动终端前端（front/agent_cli.py）→ ReAct 循环调用工具
        ↓
停止服务（back/vllm_server/stop.sh）
```

## 功能特性

- **Agent 模式**：输入任务后由模型自主规划，循环调用工具直至完成（最多 20 轮）；
- **对话模式**：输入 `/chat` 切换，直接与 LLM 流式对话；
- **工具集**：`run_bash`、文件读写 / 搜索 / 目录树、git 状态 / 提交 / 推送、OpenCV 知识库搜索；
- **五层记忆**：长任务上下文不爆，中断后可恢复进度；
- **安全防护**：命令白名单 + 危险命令黑名单 + 人工确认（前端输入 y/n）；
- **知识库问答**：支持中英文关键词搜索 OpenCV 官方教程。

## 目录结构

```text
.
├── download_awq.py                  # 模型下载脚本（ModelScope）
├── README.md
├── readme_path.md                   # Coding Agent 能力建设路线文档
├── back/
│   ├── .env                         # 环境变量（LLM 配置，已 gitignore，勿提交）
│   ├── llm_client.py                # OpenAI 兼容 LLM 客户端封装
│   ├── ReAct.py                     # ReAct 主循环、工具注册、命令白名单/黑名单
│   ├── memory.py                    # 五层记忆：滑动窗口/摘要/长期记忆/状态/检索
│   ├── tools/
│   │   ├── file_tool.py             # 文件读写、追加、搜索、目录树
│   │   ├── git_tool.py              # git 状态/日志/提交/推送等工具
│   │   └── search_tool.py           # OpenCV 知识库搜索工具（供 Agent 调用）
│   ├── search_engineer/             # 手写搜索引擎（分词/倒排索引/TF-IDF）
│   │   ├── tokenizer.py             # 基于词典的正向最大匹配中文分词
│   │   ├── inverted_index.py        # 倒排索引
│   │   ├── search.py                # TF-IDF 打分与排序
│   │   ├── kb_indexer.py            # OpenCV 知识库索引器
│   │   ├── build_kb.py              # 从 docs/opencv-5.x 构建知识库
│   │   └── main.py                  # 示例搜索引擎命令行入口
│   ├── vllm_server/
│   │   ├── start.sh                 # 启动 vLLM 服务
│   │   └── stop.sh                  # 停止 vLLM 服务
│   └── storage_text/task_state.json # 任务进度状态（运行时生成，已 gitignore）
├── front/
│   └── agent_cli.py                 # Codex 风格终端前端（Textual）
├── knowledge_base/
│   └── opencv_kb/                   # OpenCV 知识库（构建产物，已 gitignore）
├── docs/
│   └── opencv-5.x/                  # OpenCV 官方教程源码（本地，已 gitignore）
└── logs/
    └── vllm.log                     # vLLM 运行日志（已 gitignore）
```

## 环境要求

- WSL2 / Linux，NVIDIA GPU（本项目按 8GB 显存配置）；
- conda，且已创建名为 `agent` 的环境，安装了 vLLM 0.26.0、PyTorch（CUDA 版）、AutoAWQ、FlashAttention、Textual 等依赖；
- 模型文件已存在于 `/mnt/e/agent/Qwen2.5-Coder-7B-Instruct-AWQ`；
- 知识库 `knowledge_base/opencv_kb` 已构建（若缺失可参考“知识库”一节重建）。

如果模型文件缺失，可用以下命令下载：

```bash
conda activate agent
python download_awq.py
```

## 快速开始

### 1. 启动 vLLM 服务

`back/vllm_server/start.sh` 会自动激活 conda 的 `agent` 环境，直接执行即可：

```bash
cd /mnt/e/agent
bash back/vllm_server/start.sh
```

脚本会：

1. 激活 conda 的 `agent` 环境；
2. 加载 `/mnt/e/agent/Qwen2.5-Coder-7B-Instruct-AWQ` 模型；
3. 以 AWQ 量化 + float16 启动服务，监听 `0.0.0.0:8000`，服务名（`--served-model-name`）为 `Qwen2.5-Coder-7B-Instruct-AWQ`；
4. 将日志写入 `logs/vllm.log`。

首次启动需要加载约 5.2GB 权重并完成内核编译和 CUDA Graph 捕获，
**通常需要等待 2~3 分钟**。看到日志中出现 `Application startup complete.` 即表示启动完成。

### 2. 验证服务

查询模型列表：

```bash
curl http://localhost:8000/v1/models
```

发送一次对话请求：

```bash
curl http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "Qwen2.5-Coder-7B-Instruct-AWQ",
    "messages": [{"role": "user", "content": "你好"}],
    "max_tokens": 64
  }'
```

> 模型 ID 使用 `--served-model-name` 指定的短名称，而不是本地路径。

### 3. 启动终端前端

```bash
cd /mnt/e/agent
python front/agent_cli.py
```

前端默认是 **Agent 模式**（走 `back/ReAct.py`，展示思考 / 工具调用 / 观察结果 / 最终答案），
也可以输入 `/chat` 切换到直接对话模式。常用命令：

- `/help`：查看所有命令
- `/clear`：清空当前对话
- `/agent` / `/chat`：切换 Agent / 对话模式
- `/again`：重新执行上一条任务
- `/model`：查看当前模型配置
- `/pwd`：查看当前所在项目目录
- `/stop`：停止当前任务（或 `Ctrl+X`）
- `/quit`：退出（或 `Ctrl+Q`）

> 输入框下方的状态行会从 `back/.env` 读取并显示当前模型名称和 API 地址（不显示密钥）。
> 模型思考过程超过 1000 字时会折叠成小框，点击标题即可展开查看完整思考内容。

### 4. 停止服务

```bash
bash back/vllm_server/stop.sh
```

该脚本会释放 8000 端口并终止 vLLM 相关进程（包括 `VLLM::EngineCore` 子进程）。

## 配置

`back/.env` 由 `back/llm_client.py` 自动加载，通过环境变量读取模型配置：

- `LLM_BASE_URL`：API 地址，本地 vLLM 为 `http://localhost:8000/v1`
- `LLM_MODEL_ID`：模型名称，对应 vLLM 的 `--served-model-name`
- `LLM_API_KEY`：API Key（本地 vLLM 可填任意值）
- `LLM_TIMEOUT`：请求超时时间（秒）

单独测试 LLM 客户端：

```bash
cd back
python llm_client.py
```

> `.env` 中含真实密钥，已在 `.gitignore` 中排除，请勿提交到版本库。

## Agent 工具与安全

`back/ReAct.py` 中注册了以下工具：

| 工具 | 说明 |
| --- | --- |
| `run_bash` | 执行 shell 命令（受白名单 / 黑名单 / 人工确认限制） |
| `read_file` / `write_file` / `append_file` | 文件读取、覆盖写入、追加 |
| `list_dir` / `file_search` / `project_tree` | 列出目录、按文件名搜索、输出目录树 |
| `git_status` / `git_log` / `git_add` / `git_commit` / `git_diff` / `git_push` / `git_run` | git 查看与操作 |
| `search_kb` | 搜索 OpenCV 知识库 |

安全机制：

- **白名单**：只允许 `ls`、`cat`、`python`、`git` 等预置命令，未在名单中的命令直接拦截；
- **黑名单**：拦截 `sudo`、关机 / 重启、磁盘格式化、危险 `rm -rf` 等模式；
- **人工确认**：`rm`、`mv`、`pip install`、`git push`、重定向写文件等命令，需要用户输入 `y` / `n` 确认。

## 知识库

- 知识库位于 `knowledge_base/opencv_kb/`，由 `back/search_engineer/build_kb.py` 从 `docs/opencv-5.x/opencv-5.x/doc/py_tutorials` 构建；
- `back/search_engineer/kb_indexer.py` 首次调用时会自动建立倒排索引，之后复用；
- Agent 可直接调用 `search_kb` 搜索 OpenCV 函数用法、图像处理算法和代码示例（支持中英文）。

若需重建知识库，注意 `build_kb.py` 中的 `SRC_ROOT` / `KB_DIR` 目前是 Windows 风格绝对路径（`E:\agent\...`），在 WSL 下执行前需改为 `/mnt/e/agent/...` 形式的路径。

## 已知问题与处理

- **Triton 3.6.0 与 vLLM 0.26 兼容问题**：vLLM 启动时会无条件加载 MiniMax 的
  Triton 内核，触发 Triton 源码解析 bug（`'NoneType' object has no attribute 'start'`）。
  已在 conda 环境中的 `kernel_warmup.py` 打补丁（导入异常时跳过 MiniMax warmup），
  原文件备份为 `kernel_warmup.py.bak`。
- **FlashInfer 采样器需要 nvcc**：本机 CUDA 工具链路径不完整，`start.sh` 中已通过
  `VLLM_USE_FLASHINFER_SAMPLER=0` 关闭 FlashInfer 采样器，回退到原生采样器。
- **显存较小（8GB）**：模型权重约占 5.3GB，KV Cache 空间有限，长上下文并发能力较弱；
  如遇显存不足，可调低 `--gpu-memory-utilization` 或 `--max-model-len`。
- **知识库与文档不纳入版本库**：`knowledge_base/`、`docs/opencv-5.x/`、`logs/` 已在
  `.gitignore` 中排除，克隆仓库后需要自行准备或重建。
