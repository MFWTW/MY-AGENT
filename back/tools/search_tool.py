"""知识库搜索工具：供 Coding Agent (ReAct.py) 调用，搜索 OpenCV 文档"""

import os
import sys

# 动态计算 search_engineer 目录（基于本文件位置），兼容 Windows / WSL / 任意路径
# 本文件在 search_tool.py
# 往上两级 = back/ 目录，再进 search_engineer/
SEARCH_ENGINEER_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "search_engineer"
)
sys.path.insert(0, SEARCH_ENGINEER_DIR)

from kb_indexer import KBIndexer  # 现在一定能找到

# 全局单例：只需构建一次索引，AI 反复调用不用重复建
_indexer = None


def get_indexer() -> KBIndexer:
    """懒加载：第一次调用才构建索引，之后复用"""
    global _indexer
    if _indexer is None:
        _indexer = KBIndexer()  # 记得加括号！这才是创建实例
    return _indexer


def search_kb(query: str, top_k: int = 3) -> str:
    """在 OpenCV 知识库中搜索文档，返回与查询最相关的文档片段。

    当需要了解 OpenCV 函数的用法、图像处理算法、代码示例时，
    用这个工具搜索官方教程。参数 query 是搜索关键词（支持中英文），
    例如 "cv.threshold 怎么用"、"Canny 边缘检测"、"轮廓检测"。
    返回：文档标题 + 内容片段列表。
    """
    kb = get_indexer()
    results = kb.search(query, top_k=top_k)

    if not results:
        return f"[知识库] 未找到与 '{query}' 相关的文档"

    lines = [f"[知识库] 找到 {len(results)} 篇相关文档："]
    for i, (fname, title, snippet, score) in enumerate(results, start=1):
        lines.append(f"\n--- 文档{i} [{title}] (相关度{score:.3f}) ---")
        lines.append(f"文件: {fname}")
        lines.append(snippet)
    return "\n".join(lines)


if __name__ == "__main__":
    # 测试工具
    print(search_kb("cv.threshold"))
    print()
    print(search_kb("轮廓检测"))
