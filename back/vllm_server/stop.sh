#!/bin/bash

# 停止 vllm_server：查找监听 8000 端口的进程并终止
PORT=8000

echo "正在停止端口 ${PORT} 上的 vllm 服务..."

# 使用 fuser 杀掉占用端口的进程（如果没有 fuser 会报错，忽略即可）
fuser -k ${PORT}/tcp 2>/dev/null

# 备用方案：通过 pkill 匹配 vllm 启动命令
pkill -f "vllm.entrypoints.openai.api_server" 2>/dev/null

# vLLM 的 EngineCore 子进程会被重命名为 VLLM::EngineCore，
# 父进程命令匹配不到它，需要单独结束，否则显存不会释放
# 同时按“命令行”和“进程名”匹配：不同 vLLM 版本改名的方式不同，双保险
pkill -f "VLLM::EngineCore" 2>/dev/null
pkill -x "VLLM::EngineCore" 2>/dev/null
sleep 1
# 若普通信号无效（进程卡在 D/R 状态），再强制结束
pkill -9 -f "VLLM::EngineCore" 2>/dev/null
pkill -9 -x "VLLM::EngineCore" 2>/dev/null

echo "vllm 服务已停止。"
