"""
Git 工具集
用法：注册到 ReAct.py 的 TOOLS 字典里，供 LLM 调用。
约定：输入都是字符串，返回字符串（会被 ReAct.py 截断到 MAX_OBS_LEN）。
"""

import subprocess
from typing import List

GIT_TIMEOUT = 30  # git 命令超时时间，单位秒
MAX_GIT_OUT_LEN = 2000  # 输出最多保留字符数

# git 命令白名单：只允许这些子命令，防止模型乱执行危险操作
ALLOWED_SUBCOMMANDS = {
    "status",
    "log",
    "add",
    "commit",
    "diff",
    "show",
    "branch",
    "checkout",
    "pull",
    "push",
    "fetch",
    "merge",
    "remote",
    "stash",
    "tag",
    "init",
    "switch",
    "restore",
    "clean",
}


def _run_git(args: List[str]) -> str:
    """执行git命令并返回输出（内部函数，不在工具清单里）

    Args:
        args (List[str]): 指令

    Returns:
        str: 返回执行结果
    """
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            return f"[git 失败(exit={result.returncode})] {output}"
        return output if output else "[git 执行成功，无输出]"
    except subprocess.TimeoutExpired:
        return f"[错误] git 命令超时(>{GIT_TIMEOUT}秒)"
    except FileNotFoundError:
        return "[错误] 未找到 git 命令，请确认已安装并加入 PATH"
    except Exception as e:
        return f"[错误] git 执行异常: {e}"


def git_status() -> str:
    """查看当前 git 仓库状态（哪些文件被修改/新增/暂存）。无需参数。

    Returns:
        str: git status 的输出
    """
    return _run_git(["status", "--short"])


def git_log(n: str = "10") -> str:
    """查看最近 n 条提交记录。参数 n 是条数，默认 10。

    Args:
        n (str): 显示最近几条提交，如 '5'
    """
    return _run_git(["log", "--oneline", "-n", n])


def git_add(paths: str) -> str:
    """把文件加入暂存区。参数 paths 是要暂存的文件路径，多个用空格分隔。

    Args:
        paths (str): 文件路径，如 'back/llm_client.py' 或 '.'
    """
    return _run_git(["add", *paths.split()])


def git_commit(message: str) -> str:
    """提交暂存区的内容。参数 message 是提交信息。

    Args:
        message (str): 提交说明，如 'fix: 修复路径解析'
    """
    return _run_git(["commit", "-m", message])


def git_diff() -> str:
    """查看工作区未暂存的改动内容。无需参数。

    Returns:
        str: git diff 的输出
    """
    out = _run_git(["diff", "--stat"])
    return out[:MAX_GIT_OUT_LEN]


def git_run(cmd: str) -> str:
    """执行一条完整的 git 命令（带参数）。参数 cmd 是 git 后面的完整命令字符串。

    Args:
        cmd (str): git 命令参数，如 'branch -a' 或 'remote -v'
    """
    parts = cmd.split()
    if not parts:
        return "[错误] 命令为空"
    if parts[0] not in ALLOWED_SUBCOMMANDS:
        return f"[错误] 不允许的子命令 {parts[0]!r}，仅允许: {', '.join(sorted(ALLOWED_SUBCOMMANDS))}"
    out = _run_git(parts)
    return out[:MAX_GIT_OUT_LEN]
