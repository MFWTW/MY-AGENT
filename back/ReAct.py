import json
import os
import re
import subprocess
import sys
from tools.file_tool import (
    read_file,
    write_file,
    append_file,
    list_dir,
    file_search,
    project_tree,
)
from tools.git_tool import (
    git_status,
    git_log,
    git_add,
    git_commit,
    git_diff,
    git_run,
    git_push,
)
from llm_client import AgentsLLM

# ===== 固定工作目录到项目根，保证相对路径解析一致 =====
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # E:\agent
os.chdir(PROJECT_ROOT)

# 配置
MAX_STEPS = 5  # 最多迭代轮数
CMD_TIMEOUT = 30  # 命令执行超时时间，单位秒
MAX_OBS_LEN = 2000  # 工具输出最多保留的字数


# 工具注册表
def run_bash(cmd: str) -> str:
    """在shell执行命令，返回标准输出和标准错误"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=CMD_TIMEOUT
        )
        output = (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        output = f"[命令超时(>{CMD_TIMEOUT}秒)]"
    except Exception as exc:
        output = f"[执行错误: {exc}]"
    return output[:MAX_OBS_LEN]  # 限制输出长度


# 工具注册表
TOOLS = {
    "run_bash": run_bash,
    "read_file": read_file,
    "write_file": write_file,
    "append_file": append_file,
    "list_dir": list_dir,
    "file_search": file_search,
    "project_tree": project_tree,
    # ===== git 工具 =====
    "git_status": git_status,
    "git_log": git_log,
    "git_add": git_add,
    "git_commit": git_commit,
    "git_diff": git_diff,
    "git_run": git_run,
    "git_push": git_push,
}


# 系统提示词
TOOL_LIST = "\n".join(f"- {name}: {fn.__doc__}" for name, fn in TOOLS.items())

SYSTEM_PROMPT = f"""你是一个运行在终端里的 Coding Agent，你的任务是【实际执行】用户交给你的任务，而不是讲解步骤。

【核心规则：动手，不要讲解】
- 用户交给你的任务是要你去【做】的，你必须通过调用工具真正完成它
- 禁止只输出"你应该这样做：1. 2. 3."之类的文字说明作为 answer
- 只有当你已经通过工具调用【真正完成】了任务（比如文件已写入、git 已推送），才能输出 answer 总结结果
- 如果任务涉及多步，就一步一步调用工具，直到完成，不要中途停下来输出教程

【当前工作目录】{os.getcwd()}
【项目结构约定】
- 项目根目录：{PROJECT_ROOT}
- 业务代码全部放在 back/ 子目录下：back/llm_client.py、back/ReAct.py
- 工具脚本放在 back/tools/ 目录下：back/tools/file_tool.py
- 写文件时路径请【带上 back/ 前缀】，例如 back/tools/hello.py
- 不确定路径时，先调用 project_tree 查看整体结构，再操作

【git 使用约定】
- 提交代码的流程：先 git_status 查看改动 → 再 git_add 暂存 → 再 git_commit 提交
- 不要跳过 git_add 直接 git_commit（会导致提交为空）
- git_commit 的 message 用中文，格式如：fix: 修复xxx / feat: 新增xxx
- 推送到远程用 git_run，参数 cmd 写 "push origin main"

你可以调用这些工具：
{TOOL_LIST}

输出规则：
1. 每次只能输出一个 JSON 对象，不要输出任何解释文字。
2. 需要调用工具时，输出：{{"tool": "工具名", "args": {{"参数名": "值"}}}}
3. 【只有真正用工具完成了任务】才输出：{{"answer": "完成结果"}}
4. 禁止用 answer 输出操作步骤教程

示例（用户让你推送到 GitHub）：
{{"tool": "git_status", "args": {{}}}}
{{"tool": "git_add", "args": {{"paths": "."}}}}
{{"tool": "git_commit", "args": {{"message": "feat: 初始化项目"}}}}
{{"tool": "git_run", "args": {{"cmd": "push origin main"}}}}
{{"answer": "已成功推送到 GitHub origin/main"}}
"""


# 解析模型输出
def parse_llm_output(text: str):
    """从模型输出中提取 JSON，兼容 ```json 代码块和前后多余文字。"""
    if not text:
        return None
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}") + 1
        if start != -1 and end != -1:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


# ReAct 主循环
def run_react_loop(llm: AgentsLLM, task: str):
    """REACT主循环

    Args:
        llm (AgentsLLM): 大模型客户端
        task (str): 任务
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]

    for step in range(MAX_STEPS):
        print(f"\n=== Step {step + 1} ===")

        # 1.1.思考:让模型输出动作
        response = llm.think(
            messages=messages,
        )
        parsed = parse_llm_output(response)

        # 1.2.检查模型输出
        if parsed is None:
            messages.append({"role": "assistant", "content": response or ""})
            messages.append({"role": "system", "content": "[模型输出无法解析为JSON]"})
            continue

        # 2.1:输出answer:如果模型输出了最终答案，直接返回
        if "answer" in parsed:
            print(f"\n[完成]{parsed['answer']}")
            return parsed["answer"]

        # 3.1:输出tool:如果模型输出了工具调用，执行工具
        tool_name = parsed.get("tool")
        args = parsed.get("args") or {}
        if tool_name not in TOOLS:
            observation = (
                f"[系统]没有{tool_name!r}这个工具" f"可用工具:{', '.join(TOOLS)}"
            )

        else:
            try:
                observation = TOOLS[tool_name](**args)
            except Exception as e:
                observation = f"[系统]工具参数不正确: {e}"

        print(f"[观察]{observation[:300]}")  # 限制输出长度

        # 3.2:将观察结果加入消息列表，继续下一轮
        messages.append({"role": "assistant", "content": response})
        messages.append({"role": "user", "content": f"[工具结果]\n{observation}"})

    print("\n[停止] 达到最大轮数，任务未完成。")
    return None


# 入口
if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "列出当前目录下的文件"
    llm = AgentsLLM()
    run_react_loop(llm, task)
