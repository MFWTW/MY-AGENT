import json
import os
import re
import subprocess
import sys
import shlex
import threading
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
from memory import (
    trim_short_term,
    summarize_history,
    load_memory,
    save_memory,
    remember,
    search_memory,
    save_state,
    load_state,
    MAX_CONTEXT_CHARS,
)
from tools.search_tool import search_kb
from llm_client import AgentsLLM

# ===== 第一层安全：命令白名单 =====
# 允许 Agent 执行的命令（白名单）
ALLOWED_COMMANDS = {
    # 查看 / 导航
    "ls",
    "ll",
    "dir",
    "pwd",
    "cd",
    "tree",
    "find",
    "which",
    "where",
    # 读文件
    "cat",
    "head",
    "tail",
    "less",
    "more",
    "grep",
    "rg",
    "wc",
    # 写文件（若想更严，可去掉，改用 write_file 工具）
    "touch",
    "mkdir",
    "cp",
    "mv",
    "rm",
    "chmod",
    # 编程 / 运行
    "python",
    "python3",
    "pip",
    "pip3",
    "conda",
    "pytest",
    # 网络 / 压缩
    "curl",
    "wget",
    "unzip",
    "tar",
    "zip",
    # git 兜底（git_tool.py 里还有更细的子命令白名单）
    "git",
}

# 危险命令黑名单（正则，命中即拒绝）
DANGEROUS_PATTERNS = [
    r"\bsudo\b",  # 提权
    r"\b(shutdown|reboot|halt|poweroff)\b",  # 关机重启
    r"\b(mkfs|parted|fdisk|format)\b",  # 磁盘操作
    r"rm\s+-[a-zA-Z]*rf\s+(/|~|\*|\.)",  # rm -rf 危险目标
    r"dd\s+if=.*\s+of=/dev/",  # 写块设备
    r">\s*/dev/(sd|hd|nvme)",  # 重定向到磁盘
    r"chmod\s+-R\s+777\s*/",  # 全盘放开权限
]

# 需要人工确认的命令模式（正则）：合法但有副作用
NEED_CONFIRM_PATTERNS = [
    r"^(rm|mv|cp|chmod|chown)\b",  # 文件写/删/改权限
    r"^(pip|pip3|conda)\s+(install|uninstall|remove|update)",  # 装/卸包
    r"^(git)\s+(push|reset|clean|checkout|merge|rebase|stash)",  # git 破坏性操作
    r"(>|>>)\s*\S+",  # 重定向写文件
    r"^(curl|wget)\s+.*( -o| -O| >)",  # 网络下载到本地
]

# 全局确认回调：由前端注册；None 时退回终端 input()
CONFIRM_CALLBACK = None
# 总开关：设为 False 可完全跳过确认（仅调试用）
CONFIRM_ENABLED = True


def _split_shell(cmd: str) -> list:
    """按 shell 规则切分命令，解析失败时退回简单 split。"""
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


def _check_command(cmd: str):
    """白名单 + 黑名单双重检查。返回 (是否放行, 说明)。"""
    # 1) 黑名单：危险模式直接拒绝
    for pat in DANGEROUS_PATTERNS:
        if re.search(pat, cmd):
            return False, f"命中危险命令模式: {pat}"
    # 2) 白名单：拆成子命令段逐个检查（处理 && ; | ||）
    for seg in re.split(r"(?:\&\&|\|\||[;|])", cmd):
        seg = seg.strip()
        if not seg:
            continue
        tokens = _split_shell(seg)
        if not tokens:
            continue
        base = os.path.basename(tokens[0]).lower().lstrip("./")
        if base not in ALLOWED_COMMANDS:
            return False, (
                f"命令 {tokens[0]!r} 不在白名单中。"
                f"允许的命令: {', '.join(sorted(ALLOWED_COMMANDS))}"
            )
    return True, ""


def _needs_confirm(cmd: str) -> bool:
    """判断命令是否需要人工确认"""
    for pat in NEED_CONFIRM_PATTERNS:
        if re.search(pat, cmd):
            return True
    return False


def _ask_confirm(cmd: str) -> bool:
    """判断命令是否需要人工确认"""
    for pat in NEED_CONFIRM_PATTERNS:
        if re.search(pat, cmd):
            return True

    return False


def _ask_confirm(cmd: str) -> bool:
    """请求人工确认。返回 True=放行，False=拒绝。

    优先走前端注册的回调；前端不可用时用终端 input() 兜底。
    """
    if not CONFIRM_ENABLED:
        return True
    if CONFIRM_CALLBACK is not None:
        return CONFIRM_CALLBACK(cmd)
    try:
        ans = input(f"[人工确认] 允许执行: {cmd}  (y/N): ").strip().lower()
        return ans in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


# ===== 固定工作目录到项目根，保证相对路径解析一致 =====
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # E:\agent

# ===== Workspace：自动识别 =====
# launcher.py 会把启动时的当前目录写入环境变量 AGENT_WORKSPACE；
# 直接跑 ReAct.py（未设环境变量）时，回退到项目根目录，保持原行为
WORKSPACE = os.getenv("AGENT_WORKSPACE") or PROJECT_ROOT
os.chdir(WORKSPACE)

# 配置
MAX_STEPS = 20  # 最多迭代轮数
CMD_TIMEOUT = 30  # 命令执行超时时间，单位秒
MAX_OBS_LEN = 2000  # 工具输出最多保留的字数

MEMORY = load_memory()  # 跨会话的长期记忆


def run_bash(cmd: str = None, **kwargs) -> str:
    """在shell执行命令（受命令白名单限制）。参数名是 cmd（或 command）。"""
    if cmd is None and "command" in kwargs:
        cmd = kwargs["command"]
    if not cmd:
        return "[系统] run_bash 需要 cmd 参数，例如 run_bash(cmd='ls')"

    # ===== 第一层安全：白名单检查 =====
    ok, reason = _check_command(cmd)
    if not ok:
        return f"[已拦截] {reason}"

    # ===== 第三层安全：人工确认 =====
    if _needs_confirm(cmd):
        if not _ask_confirm(cmd):
            return "[已拒绝] 用户未确认执行该命令，请换一个方案"

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=CMD_TIMEOUT
        )
        output = (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        output = f"[命令超时(>{CMD_TIMEOUT}秒)]"
    except Exception as exc:
        output = f"[执行错误: {exc}]"
    return output[:MAX_OBS_LEN]


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
    # ===== 知识库搜索 =====
    "search_kb": search_kb,
}


# 系统提示词
TOOL_LIST = "\n".join(f"- {name}: {fn.__doc__}" for name, fn in TOOLS.items())

# 长期记忆关键内容注入到提示词中
_memory_snippet = search_memory(MEMORY, "任务") or "(暂无长期记忆)"

SYSTEM_PROMPT = f"""你是一个运行在终端里的 Coding Agent，你的任务是【实际执行】用户交给你的任务，而不是讲解步骤。

【核心规则：动手，不要讲解】
- 用户交给你的任务是要你去【做】的，你必须通过调用工具真正完成它
- 禁止只输出"你应该这样做：1. 2. 3."之类的文字说明作为 answer
- 只有当你已经通过工具调用【真正完成】了任务（比如文件已写入、git 已推送），才能输出 answer 总结结果
- 如果任务涉及多步，就一步一步调用工具，直到完成，不要中途停下来输出教程

【防作弊：完成前必须自证】
- 每次用 write_file 写完代码后，必须立刻用 read_file 读回来确认内容正确
- 当你认为任务完成、想输出 answer 之前，必须先用 file_search 或 read_file 验证关键文件确实存在且内容正确
- 如果验证失败（文件不存在/内容为空/报错），禁止输出 answer，必须继续修复
- 只有验证通过后，才能输出 answer，并在 answer 里写明"已用 read_file 验证"

【长期记忆（跨会话经验，供参考）】
{_memory_snippet}

【工作区 Workspace（当前工作目录）】{WORKSPACE}
【项目结构约定】
- 项目根目录（本 Agent 自带代码）：{PROJECT_ROOT}
- 业务代码全部放在 back/ 子目录下：back/llm_client.py、back/ReAct.py
- 工具脚本放在 back/tools/ 目录下：back/tools/file_tool.py
- 你的工作区是 {WORKSPACE}：用户任务相关的文件都在这里操作
- 写文件时请【带上相对工作区的路径】
- 不确定路径时，先调用 project_tree 查看整体结构，再操作

【git 使用约定】
- 提交代码的流程：先 git_status 查看改动 → 再 git_add 暂存 → 再 git_commit 提交
- 不要跳过 git_add 直接 git_commit（会导致提交为空）
- git_commit 的 message 用中文，格式如：fix: 修复xxx / feat: 新增xxx
- 推送到远程用 git_run，参数 cmd 写 "push origin main"

- search_kb: 在 OpenCV 知识库中搜索文档，返回与查询最相关的文档片段。
  当需要了解 OpenCV 函数的用法、图像处理算法、代码示例时，用这个工具搜索官方教程...

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
def run_react_loop(llm: AgentsLLM, task: str, hooks: dict = None):
    """REACT主循环

    Args:
        llm (AgentsLLM): 大模型客户端
        task (str): 任务
        hooks (dict, optional): 前端事件回调。支持以下键：
            on_step(int), on_log(str), on_token(str), on_tool(str, dict),
            on_observe(str), on_warn(str), on_answer(str), on_stop(str)。
            传入 hooks 后，ReAct 不再向 stdout 打印过程信息。
    """
    hooks = hooks or {}

    def emit(name, *args):
        callback = hooks.get(name)
        if callback:
            callback(*args)

    quiet = bool(hooks)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]
    emit("on_start", task)

    # ④ 外部状态：恢复进度（作为 system 追加，受 head 保护）
    state = load_state()
    if state:
        messages.append(
            {
                "role": "system",
                "content": f"[上次任务进度]\n{state.get('progress', '')}",
            }
        )

    for step in range(MAX_STEPS):
        if not quiet:
            print(f"\n=== Step {step + 1} ===")
        emit("on_step", step + 1)

        # 每轮开头：① 短期记忆滑动窗口 + ② 历史压缩
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        if total_chars > MAX_CONTEXT_CHARS:
            log_msg = f"上下文 {total_chars} 字符超限，压缩历史..."
            if not quiet:
                print(f"[记忆] {log_msg}")
            emit("on_log", log_msg)
            messages = summarize_history(
                llm,
                messages,
                on_token=hooks.get("on_token"),
            )
        else:
            messages = trim_short_term(messages)
            log_msg = f"上下文 {total_chars} 字符，窗口内 {len(messages)} 条消息"
            if not quiet:
                print(f"[记忆] {log_msg}")
            emit("on_log", log_msg)

        # 1.1.思考:让模型输出动作
        response = llm.think(
            messages=messages,
            on_token=hooks.get("on_token"),
        )
        parsed = parse_llm_output(response)

        # 1.2.检查模型输出
        if parsed is None:
            messages.append({"role": "assistant", "content": response or ""})
            warn_msg = "模型输出无法解析为 JSON，已要求重新思考"
            if not quiet:
                print(f"[警告] {warn_msg}")
            emit("on_warn", warn_msg)
            messages.append({"role": "system", "content": f"[{warn_msg}]"})
            continue

        # 2.1:输出answer:如果模型输出了最终答案，直接返回
        if "answer" in parsed:
            if not quiet:
                print(f"\n[完成]{parsed['answer']}")
            emit("on_answer", parsed["answer"])
            return parsed["answer"]

        # 3.1:输出tool:如果模型输出了工具调用，执行工具
        tool_name = parsed.get("tool")
        args = parsed.get("args") or {}
        if tool_name not in TOOLS:
            warn_msg = f"没有 {tool_name!r} 这个工具，可用工具: {', '.join(TOOLS)}"
            if not quiet:
                print(f"[警告] {warn_msg}")
            emit("on_warn", warn_msg)
            observation = f"[系统]{warn_msg}"

        else:
            try:
                observation = TOOLS[tool_name](**args)
            except Exception as e:
                warn_msg = f"工具参数不正确: {e}"
                if not quiet:
                    print(f"[警告] {warn_msg}")
                emit("on_warn", warn_msg)
                observation = f"[系统]{warn_msg}"

        if not quiet:
            print(f"[观察]{observation[:300]}")  # 限制输出长度
        emit("on_tool", tool_name, args)
        emit("on_observe", observation)

        # 3.2:将观察结果加入消息列表，继续下一轮
        messages.append({"role": "assistant", "content": response})
        messages.append({"role": "user", "content": f"[工具结果]\n{observation}"})

        # ④ 外部状态：记录进度（中断后可恢复）
        save_state(
            {
                "progress": f"Step{step+1}: {tool_name} → {observation[:100]}",
                "done": False,
            }
        )

    stop_msg = "达到最大轮数，任务未完成。"
    if not quiet:
        print(f"\n[停止] {stop_msg}")
    emit("on_stop", stop_msg)
    save_state({"progress": "达到最大轮数未完成", "done": False})
    return None


# 入口
if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "列出当前目录下的文件"
    llm = AgentsLLM()
    run_react_loop(llm, task)
