#!/usr/bin/env bash
# ============================================
#  HelloAents 一键安装 (Ubuntu / WSL2 / Linux)
#  用法: bash setup.sh
#  安装完成后输入 myagent 即可直接启动
# ============================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"
ENV_NAME="${AGENT_ENV:-agent}"
MODEL_DIR="${MODEL_DIR:-$PROJECT_ROOT/Qwen2.5-Coder-7B-Instruct-AWQ}"
CONDA_BASE=""

say() { printf '\n\033[1;34m[setup]\033[0m %s\n' "$*"; }
die() { printf '\n\033[1;31m[setup][错误]\033[0m %s\n' "$*" >&2; exit 1; }

say "HelloAents 一键安装"
say "项目目录: $PROJECT_ROOT"

# ---------- 系统与 GPU 检查 ----------
[ "$(uname -s)" = "Linux" ] || die "仅支持 Linux / WSL2"
case "$(uname -m)" in
  x86_64|amd64) ;;
  *) die "vLLM 目前仅支持 x86_64 架构" ;;
esac

if ! command -v nvidia-smi >/dev/null 2>&1 || ! nvidia-smi -L >/dev/null 2>&1; then
  if [ "${SKIP_GPU_CHECK:-0}" != "1" ]; then
    die "未检测到 NVIDIA GPU（nvidia-smi 不可用）。" \
        "Ubuntu 请先安装 NVIDIA 驱动；WSL2 请在 Windows 侧安装驱动。" \
        "如确需跳过，可执行: SKIP_GPU_CHECK=1 bash setup.sh"
  fi
  say "警告: SKIP_GPU_CHECK=1，已跳过 GPU 检查"
fi

if ! command -v apt-get >/dev/null 2>&1; then
  die "当前系统没有 apt-get，仅支持 Ubuntu/Debian 系系统"
fi

# ---------- 系统工具 ----------
MISSING=""
for c in curl git; do
  command -v "$c" >/dev/null 2>&1 || MISSING="$MISSING $c"
done
if [ -n "$MISSING" ]; then
  say "安装系统工具:$MISSING"
  if [ "$(id -u)" -eq 0 ]; then
    apt-get update -y
    apt-get install -y $MISSING
  else
    command -v sudo >/dev/null 2>&1 || die "安装系统依赖需要 sudo"
    sudo apt-get update -y
    sudo apt-get install -y $MISSING
  fi
fi

# ---------- conda ----------
find_conda() {
  if command -v conda >/dev/null 2>&1; then
    local base
    base="$(conda info --base 2>/dev/null || true)"
    if [ -n "$base" ] && [ -f "$base/etc/profile.d/conda.sh" ]; then
      CONDA_BASE="$base"
      return 0
    fi
  fi
  for base in "$HOME/miniconda3" "$HOME/anaconda3" /opt/conda /opt/miniconda3; do
    if [ -f "$base/etc/profile.d/conda.sh" ]; then
      CONDA_BASE="$base"
      return 0
    fi
  done
  return 1
}

if ! find_conda; then
  say "未检测到 conda，安装 Miniconda 到 $HOME/miniconda3 ..."
  curl -fsSL "https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh" \
    -o /tmp/miniconda-install.sh
  bash /tmp/miniconda-install.sh -b -p "$HOME/miniconda3"
  rm -f /tmp/miniconda-install.sh
  CONDA_BASE="$HOME/miniconda3"
fi

source "$CONDA_BASE/etc/profile.d/conda.sh"
say "conda 位于: $CONDA_BASE"

# ---------- conda 环境 ----------
if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  say "conda 环境 '$ENV_NAME' 已存在，直接复用"
else
  say "创建 conda 环境 '$ENV_NAME'（Python 3.10）..."
  conda create -n "$ENV_NAME" python=3.10 -y
fi
conda activate "$ENV_NAME"

# ---------- Python 依赖 ----------
say "安装 Python 基础依赖..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [ "${SKIP_VLLM:-0}" != "1" ]; then
  say "安装 vLLM 0.26.0（需要几分钟，请耐心等待）..."
  python -m pip install "vllm==0.26.0"
else
  say "SKIP_VLLM=1，跳过 vLLM 安装"
fi

# ---------- 模型下载 ----------
if [ -f "$MODEL_DIR/config.json" ] &&
   [ -f "$MODEL_DIR/model-00001-of-00002.safetensors" ] &&
   [ -f "$MODEL_DIR/model-00002-of-00002.safetensors" ]; then
  say "模型已存在，跳过下载"
else
  say "下载 Qwen2.5-Coder-7B-Instruct-AWQ 模型（约 5.5GB）..."
  MODEL_DIR="$MODEL_DIR" python download_awq.py
fi

# ---------- 本地配置 ----------
if [ ! -f "back/.env" ]; then
  say "生成 back/.env"
  cp back/.env.example back/.env
else
  say "back/.env 已存在，跳过"
fi

# ---------- myagent 命令 ----------
say "安装 myagent 命令..."
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
ln -sfn "$PROJECT_ROOT/start.sh" "$BIN_DIR/myagent"
chmod +x "$PROJECT_ROOT/start.sh" \
       "$PROJECT_ROOT/setup.sh" \
       "$PROJECT_ROOT/back/vllm_server/start.sh" \
       "$PROJECT_ROOT/back/vllm_server/stop.sh"

add_path_line() {
  local rc="$1"
  [ -f "$rc" ] || touch "$rc"
  if ! grep -qF 'export PATH="$HOME/.local/bin:$PATH"' "$rc"; then
    printf '\n# myagent\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$rc"
  fi
}
add_path_line "$HOME/.bashrc"
[ -f "$HOME/.zshrc" ] && add_path_line "$HOME/.zshrc"

say "安装完成！"
echo
echo "  打开一个新终端，或先执行: source ~/.bashrc"
echo "  然后输入: myagent"
echo
echo "  myagent 会自动完成："
echo "    1. 启动 vLLM 模型服务"
echo "    2. 等待 API 就绪"
echo "    3. 打开 Agent 前端"
echo "    4. 退出前端后自动停止 vLLM，释放显存"
echo
