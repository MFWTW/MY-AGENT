#!/bin/bash

# 激活 conda 环境（agent 是一个 conda 环境）
source ~/miniconda3/etc/profile.d/conda.sh
conda activate agent


#模型路径（4bit AWQ 量化版，适配 8GB 显存）
MODEL_PATH="/mnt/e/agent/Qwen2.5-Coder-7B-Instruct-AWQ"

# 确保日志目录存在
mkdir -p logs

# 优先使用 conda 环境的 libstdc++（修复 CXXABI_1.3.15 not found 问题）
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

# WSL2 下启用 pinned memory，否则 vLLM 0.26 报 "UVA is not available"
# （要求 WSL2 内核 >= 4.19.121，当前内核满足要求）
export VLLM_WSL2_ENABLE_PIN_MEMORY=1

# 关闭 FlashInfer 采样器，避免启动时 JIT 编译需要 nvcc/CUDA 工具链
# （机器上只有 pip 版 nvcc，路径不在默认 CUDA_HOME，会导致启动失败）
export VLLM_USE_FLASHINFER_SAMPLER=0

# 启动 vllm_server
python -m vllm.entrypoints.openai.api_server \
    --model ${MODEL_PATH} \
    --served-model-name Qwen2.5-Coder-7B-Instruct-AWQ \
    --host 0.0.0.0 \
    --port 8000 \
    --quantization awq \
    --dtype float16 \
    --gpu-memory-utilization 0.85 \
    --max-model-len 4096 \
    > logs/vllm.log 2>&1
