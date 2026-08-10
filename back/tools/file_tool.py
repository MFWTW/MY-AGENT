"""
文件读写工具集
用法：注册到 ReAct.py 的 TOOLS 字典里，供 LLM 调用。
约定：输入都是字符串，返回字符串（会被 ReAct.py 截断到 MAX_OBS_LEN）。
"""

import os
from typing import List

MAX_FILE_READ_LEN = 3000  # 单次读取最多返回多少字符
MAX_WRITE_LEN = 5000  # 单次写入内容长度上限

def project_tree(root: str = ".") -> str:
    """输出项目的目录树结构（文件夹层级 + 文件列表），用于了解项目布局。
    参数 root 是起始目录，默认当前目录。

    Args:
        root (str): 起始目录，如 '.'
    """
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "logs", ".vscode"}
    lines: List[str] = []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in skip)
            depth = dirpath.replace(root, "", 1).count(os.sep)
            indent = "  " * depth
            name = os.path.basename(dirpath) or dirpath
            lines.append(f"{indent}{name}/")
            for fn in sorted(filenames):
                lines.append(f"{indent}  {fn}")
            if len(lines) > 200:
                lines.append("... (目录结构过长，已截断)")
                break
        return "\n".join(lines)
    except FileNotFoundError:
        return f"[错误] 目录不存在: {root}"
    except Exception as e:
        return f"[错误] 读取目录树失败: {e}"

def read_file(path: str) -> str:
    """读取指定文件的文本内容。参数 path 是文件路径，返回文件内容。

    Args:
        path (str): 要读取的文件路径，如 'back/llm_client.py'
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if len(content) > MAX_FILE_READ_LEN:
            return (
                content[:MAX_FILE_READ_LEN]
                + f"\n...\n[内容过长，已截断，共 {len(content)} 字符]"
            )
        return content
    except FileNotFoundError:
        return f"[错误] 文件不存在: {path}"
    except IsADirectoryError:
        return f"[错误] 这是目录不是文件: {path}"
    except UnicodeDecodeError:
        return f"[错误] 文件不是 UTF-8 文本，可能为二进制: {path}"
    except Exception as e:
        return f"[错误] 读取失败: {e}"


def write_file(path: str, content: str) -> str:
    """写入或覆盖文件内容（自动创建父目录）。参数 path 是文件路径，content 是要写入的内容。

    Args:
        path (str): 目标文件路径，如 'back/notes.txt'
        content (str): 要写入的完整内容
    """
    if len(content) > MAX_WRITE_LEN:
        return f"[错误] 内容过长({len(content)}字符)，超过上限 {MAX_WRITE_LEN}"
    try:
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"[成功] 已写入 {path}（{len(content)} 字符）"
    except Exception as e:
        return f"[错误] 写入失败: {e}"


def append_file(path: str, content: str) -> str:
    """向文件末尾追加内容，不覆盖原内容。参数 path 是文件路径，content 是追加的内容。

    Args:
        path (str): 目标文件路径
        content (str): 要追加的内容
    """
    try:
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(content + "\n")
        return f"[成功] 已追加到 {path}"
    except Exception as e:
        return f"[错误] 追加失败: {e}"


def list_dir(path: str = ".") -> str:
    """列出目录下的所有文件和子目录。参数 path 是目录路径，默认当前目录。

    Args:
        path (str): 目录路径，如 'back'
    """
    try:
        items = os.listdir(path)
        lines = [
            f"{d}/" if os.path.isdir(os.path.join(path, d)) else d
            for d in sorted(items)
        ]
        return "\n".join(lines) if lines else "(空目录)"
    except FileNotFoundError:
        return f"[错误] 目录不存在: {path}"
    except Exception as e:
        return f"[错误] 列出目录失败: {e}"


def file_search(root: str, keyword: str) -> str:
    """在目录里按关键字搜索文件名。参数 root 是起始目录，keyword 是文件名关键字。

    Args:
        root (str): 起始目录，如 '.'
        keyword (str): 文件名包含的关键字，如 'llm'
    """
    matches: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # 跳过常见无关目录，避免遍历 node_modules 等
        dirnames[:] = [
            d
            for d in dirnames
            if d not in {".git", "node_modules", "__pycache__", ".venv", "venv", "logs"}
        ]
        for fn in filenames:
            if keyword.lower() in fn.lower():
                matches.append(os.path.join(dirpath, fn))
        if len(matches) >= 50:
            break
    return "\n".join(matches) if matches else f"(未找到包含 '{keyword}' 的文件)"
