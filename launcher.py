#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键启动器
agent.bat -> launcher.py -> 自动启动 vLLM -> 等待 API -> 启动 Textual Agent
退出时自动停止 vLLM，释放显存（可用环境变量 AUTO_STOP_VLLM=0 关闭）

兼容两种运行环境：
  - Windows 双击 agent.bat：自动进入 WSL 执行完整启动流程
  - Ubuntu/WSL 里直接 python3 launcher.py：全部本地执行
"""

import os
import sys
import time
import subprocess
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ===== Workspace：自动识别启动时的当前目录 =====
# 注意顺序：先记录用户启动时的目录，再切到项目根
WORKSPACE = os.environ.get("AGENT_WORKSPACE") or os.getcwd()
os.environ["AGENT_WORKSPACE"] = WORKSPACE

os.chdir(PROJECT_ROOT)

# ===== 配置 =====
BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
HEALTH_URL = BASE_URL.rstrip("/") + "/models"
START_SCRIPT = os.path.join("back", "vllm_server", "start.sh")
STOP_SCRIPT = os.path.join("back", "vllm_server", "stop.sh")
MAX_WAIT = 300  # 等待 vLLM 就绪的最长秒数
POLL_INTERVAL = 5  # 轮询间隔（秒）
API_TIMEOUT = 3  # 单次健康检查超时（秒）
AUTO_STOP_VLLM = os.getenv("AUTO_STOP_VLLM", "1") == "1"  # 退出时自动停 vLLM


def get_active_profile() -> str:
    """读取当前模型配置：local=本地 vLLM，api=云端 API"""
    profile = os.getenv("AGENT_PROFILE", "").strip().lower()
    if profile not in ("local", "api"):
        profile = ""
        try:
            with open(
                os.path.join(
                    PROJECT_ROOT, "back", "storage_text", "active_profile.txt"
                ),
                encoding="utf-8",
            ) as f:
                profile = f.read().strip().lower()
        except OSError:
            profile = ""
    return profile if profile in ("local", "api") else "local"


def local_model_ready() -> bool:
    """本地模型目录是否已导入且完整"""
    try:
        back_dir = os.path.join(PROJECT_ROOT, "back")
        if back_dir not in sys.path:
            sys.path.insert(0, back_dir)
        from llm_client import has_local_model

        return has_local_model()
    except Exception:
        return False


def is_wsl() -> bool:
    """判断当前是否运行在 WSL 里"""
    if not sys.platform.startswith("linux"):
        return False
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def is_windows() -> bool:
    """判断当前是否运行在 Windows（agent.bat 场景）"""
    return sys.platform.startswith("win")


def to_wsl_path(path: str) -> str:
    """Windows 路径 E:\agent\... 转 WSL 路径 /mnt/e/agent/..."""
    path = os.path.abspath(path)
    drive, rest = os.path.splitdrive(path)
    if drive:
        drive = drive.rstrip(":").lower()
        return f"/mnt/{drive}{rest.replace(os.sep, '/')}"
    return path.replace(os.sep, "/")


def api_ready() -> bool:
    """探测 vLLM API 是否就绪（GET /v1/models 返回 200）"""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=API_TIMEOUT) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_vllm():
    """启动 vLLM 服务（后台运行，不阻塞当前进程）"""
    if is_windows():
        wsl_script = to_wsl_path(os.path.join(PROJECT_ROOT, START_SCRIPT))
        print(f"  [Windows] wsl -e bash {wsl_script}")
        subprocess.Popen(
            ["wsl", "-e", "bash", wsl_script],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        # 原生 Ubuntu 和 WSL2 都直接在本机执行
        print(f"  [Linux/WSL] bash {START_SCRIPT}")
        subprocess.Popen(
            ["bash", START_SCRIPT],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def stop_vllm():
    """停止 vLLM 服务，释放显存（stop.sh 已幂等，未在跑也不报错）"""
    print("正在停止 vLLM 服务，释放显存...")
    if is_windows():
        wsl_script = to_wsl_path(os.path.join(PROJECT_ROOT, STOP_SCRIPT))
        subprocess.run(
            ["wsl", "-e", "bash", wsl_script],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        subprocess.run(
            ["bash", STOP_SCRIPT],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    print("vLLM 已停止，显存已释放。")


def wait_for_api() -> bool:
    """轮询等待 API 就绪，超时返回 False"""
    print(f"等待 vLLM API 就绪: {HEALTH_URL}")
    print(f"（最长等待 {MAX_WAIT}s，日志见 logs/vllm.log）")
    elapsed = 0
    while elapsed < MAX_WAIT:
        if api_ready():
            print(f"[OK] vLLM API 已就绪（用时约 {elapsed}s）")
            return True
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        print(f"  ...已等待 {elapsed}s")
    print("[失败] vLLM 启动超时，请检查 logs/vllm.log")
    return False


def main():
    print("=" * 50)
    print("  HelloAents 一键启动")
    print("=" * 50)

    # 1) 按当前配置启动模型服务
    profile = get_active_profile()
    if profile == "api":
        print("[1/3] 当前配置为 API 模型，跳过本地 vLLM 启动")
    elif api_ready():
        print("[跳过] 检测到 vLLM 已在运行")
    elif not local_model_ready():
        print("[提示] 未找到本地模型，跳过 vLLM 启动")
        print("        请在前端输入 /import-local 导入，或 /config-api 配置 API")
    else:
        print("[1/3] 启动本地 vLLM 服务...")
        start_vllm()
        if not wait_for_api():
            sys.exit(1)

    # 2) 启动 Textual Agent
    print("[2/3] 启动 Textual Agent (front/agent_cli.py)...")
    agent_script = os.path.join("front", "agent_cli.py")
    try:
        subprocess.call([sys.executable, agent_script], cwd=PROJECT_ROOT)
    except KeyboardInterrupt:
        print("\n已手动中断。")

    print("[3/3] Agent 已退出。")

    # 3) 退出时自动停止 vLLM，释放显存
    if AUTO_STOP_VLLM:
        stop_vllm()
    else:
        print("提示：AUTO_STOP_VLLM=0，未自动停止。")
        print("      如需停止 vLLM：bash back/vllm_server/stop.sh")


if __name__ == "__main__":
    main()
