# HelloAents 项目说明

## 项目概述

本项目以本地部署的 **Qwen2.5-Coder-7B-Instruct-AWQ**（4bit AWQ 量化，适配 8GB 显存）为推理后端，
通过 vLLM 提供 OpenAI 兼容的 HTTP API，后端代码通过该 API 调用大模型完成对话、工具调用等任务。

整体流程：

```text
下载模型（download_awq.py）
        ↓
启动 vLLM 服务（back/vllm_server/start.sh，自动激活 conda 的 agent 环境）
        ↓
监听 http://localhost:8000（OpenAI 兼容 API）
        ↓
业务代码调用（back/llm_client.py 等）
        ↓
停止服务（back/vllm_server/stop.sh）
```

## 目录结构

```text
.
├── Qwen2.5-Coder-7B-Instruct-AWQ/   # 本地模型文件（从 ModelScope 下载）
├── download_awq.py                  # 模型下载脚本（ModelScope）
├── back/
│   ├── .env                         # 环境变量（LLM 配置、AppBuilder Token）
│   ├── llm_client.py                # OpenAI 兼容 LLM 客户端封装
│   ├── tool1.py                     # 百度千帆搜索工具（开发中，未完成）
│   ├── ReAct.py                     # ReAct 流程占位文件（当前为空）
│   └── vllm_server/
│       ├── start.sh                 # 启动 vLLM 服务
│       └── stop.sh                  # 停止 vLLM 服务
├── front/                           # 前端目录（当前为空）
├── tools/                           # 工具目录（当前为空）
└── logs/vllm.log                    # vLLM 运行日志
```

## 环境要求

- WSL2 / Linux，NVIDIA GPU（本项目按 8GB 显存配置）
- conda，且已创建名为 `agent` 的环境，其中安装了：
  - vLLM 0.26.0
  - PyTorch（CUDA 版）、AutoAWQ、FlashAttention 等依赖
- 模型文件已存在于 `/mnt/e/agent/Qwen2.5-Coder-7B-Instruct-AWQ`

如果模型文件缺失，可用以下命令下载：

```bash
conda activate agent
python download_awq.py
```

## 启动流程

### 1. 激活 conda 环境

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate agent
```

> `back/vllm_server/start.sh` 内部会自动完成环境激活，也可以直接执行脚本。

### 2. 启动 vLLM 服务

```bash
cd /mnt/e/agent
bash back/vllm_server/start.sh
```

脚本会：

1. 激活 conda 的 `agent` 环境；
2. 加载 `/mnt/e/agent/Qwen2.5-Coder-7B-Instruct-AWQ` 模型；
3. 以 AWQ 量化 + float16 启动服务，监听 `0.0.0.0:8000`；
4. 将日志写入 `logs/vllm.log`。

首次启动需要加载约 5.2GB 权重并完成内核编译和 CUDA Graph 捕获，
**通常需要等待 2~3 分钟**。看到日志中出现 `Application startup complete.` 即表示启动完成。

### 3. 验证服务

查询模型列表：

```bash
curl http://localhost:8000/v1/models
```

发送一次对话请求：

```bash
curl http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "/mnt/e/agent/Qwen2.5-Coder-7B-Instruct-AWQ",
    "messages": [{"role": "user", "content": "你好"}],
    "max_tokens": 64
  }'
```

### 4. 停止服务

```bash
bash back/vllm_server/stop.sh
```

该脚本会释放 8000 端口并终止 vLLM 相关进程。

## 业务代码调用

`back/llm_client.py` 封装了 OpenAI 兼容客户端，通过环境变量读取模型配置：

- `LLM_BASE_URL`：API 地址
- `LLM_MODEL_ID`：模型名称
- `LLM_API_KEY`：API Key（本地 vLLM 可填任意值）
- `LLM_TIMEOUT`：超时时间

```bash
cd back
python llm_client.py
```

> 注意：`back/.env` 目前配置的是 DeepSeek 云端 API。若要改为调用本地 vLLM，
> 请将 `LLM_BASE_URL` 改为 `http://localhost:8000/v1`，`LLM_MODEL_ID` 改为
> `/mnt/e/agent/Qwen2.5-Coder-7B-Instruct-AWQ`（或在启动参数中通过
> `--served-model-name` 指定简短名称）。`.env` 中含真实密钥，请勿提交到版本库。

## 已知问题与处理

- **Triton 3.6.0 与 vLLM 0.26 兼容问题**：vLLM 启动时会无条件加载 MiniMax 的
  Triton 内核，触发 Triton 源码解析 bug（`'NoneType' object has no attribute 'start'`）。
  已在 conda 环境中的 `kernel_warmup.py` 打补丁（导入异常时跳过 MiniMax warmup），
  原文件备份为 `kernel_warmup.py.bak`。
- **FlashInfer 采样器需要 nvcc**：本机 CUDA 工具链路径不完整，`start.sh` 中已通过
  `VLLM_USE_FLASHINFER_SAMPLER=0` 关闭 FlashInfer 采样器，回退到原生采样器。
- **显存较小（8GB）**：模型权重约占 5.3GB，KV Cache 空间有限，长上下文并发能力较弱；
  如遇显存不足，可调低 `--gpu-memory-utilization` 或 `--max-model-len`。
- **`back/tool1.py`、`back/ReAct.py` 尚未完成**：当前仅 `llm_client.py` 可直接运行。
