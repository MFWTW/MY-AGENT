#!/bin/bash
set -euo pipefail

# 自动推导项目根目录（本脚本位于 <项目>/back/vllm_server/start.sh）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# 激活 conda 环境（可用 AGENT_ENV 覆盖，默认 agent）
CONDA_ENV="${AGENT_ENV:-agent}"
CONDA_BASE="${CONDA_BASE:-}"
if [ -z "$CONDA_BASE" ] && command -v conda >/dev/null 2>&1; then
  CONDA_BASE="$(conda info --base 2>/dev/null || true)"
fi
if [ -z "$CONDA_BASE" ] || [ ! -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
  for base in "$HOME/miniconda3" "$HOME/anaconda3" /opt/conda /opt/miniconda3; do
    if [ -f "$base/etc/profile.d/conda.sh" ]; then
      CONDA_BASE="$base"
      break
    fi
  done
fi
if [ -z "$CONDA_BASE" ] || [ ! -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
  echo "[错误] 未找到 conda，请先运行项目根目录下的 setup.sh" >&2
  exit 1
fi
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "$CONDA_ENV"

# 读取 back/.env（里面可能保存了 LOCAL_MODEL_DIR / LOCAL_MODEL_ID）
if [ -f "$PROJECT_ROOT/back/.env" ]; then
  set -a
  source "$PROJECT_ROOT/back/.env"
  set +a
fi

# 模型路径：优先环境变量 MODEL_DIR，其次 LOCAL_MODEL_DIR，最后项目默认目录
MODEL_DIR="${MODEL_DIR:-${LOCAL_MODEL_DIR:-$PROJECT_ROOT/Qwen2.5-Coder-7B-Instruct-AWQ}}"
if [ ! -f "$MODEL_DIR/config.json" ]; then
  echo "[错误] 模型目录不存在: $MODEL_DIR" >&2
  echo "请先运行 setup.sh 下载模型，或用 MODEL_DIR 指定模型路径" >&2
  exit 1
fi
MODEL_NAME="${LOCAL_MODEL_ID:-${LLM_MODEL_ID:-$(basename "$MODEL_DIR")}}"

# 确保日志目录存在
mkdir -p "$PROJECT_ROOT/logs"

# 优先使用 conda 环境的 libstdc++（修复 CXXABI_1.3.15 not found 问题）
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:${LD_LIBRARY_PATH:-}"

# WSL2 下启用 pinned memory，否则 vLLM 0.26 报 "UVA is not available"
# （要求 WSL2 内核 >= 4.19.121，当前内核满足要求）
export VLLM_WSL2_ENABLE_PIN_MEMORY=1

# 关闭 FlashInfer 采样器，避免启动时 JIT 编译需要 nvcc/CUDA 工具链
# （机器上只有 pip 版 nvcc，路径不在默认 CUDA_HOME，会导致启动失败）
export VLLM_USE_FLASHINFER_SAMPLER=0

# 启动 vllm_server
python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL_DIR" \
    --served-model-name "$MODEL_NAME" \
    --host 0.0.0.0 \
    --port 8000 \
    --quantization awq \
    --dtype float16 \
    --gpu-memory-utilization 0.85 \
    --max-model-len 4096 \
    > logs/vllm.log 2>&1
