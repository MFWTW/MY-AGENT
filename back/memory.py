"""
长任务上下文管理：五层记忆
① 短期记忆 Short-term Memory   —— 滑动窗口
② 历史压缩 Summarization       —— 用 LLM 把旧对话浓缩成摘要
③ 长期记忆 Long-term Memory    —— 存到 JSON 文件，跨会话保留
④ 外部状态 External State      —— 进度/目标/结果存到外部文件
⑤ 按需检索 Retrieval          —— 关键词检索长期记忆
"""

import json
import os
import re

# 配置
MEMORY_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "storage/memory_store.json"
)
MAX_RAW_MESSAGES = 8  # 短期记忆：最多保留的原始消息条数（system 除外）
MAX_CONTEXT_CHARS = 6000  # 触发压缩的上下文总长度阈值（约等于 token 数）


# ① 短期记忆：滑动窗口
def trim_short_term(messages, max_msgs: int = MAX_RAW_MESSAGES):
    """保留 system + 最近的 max_msgs 条消息，丢弃最旧的中间消息。

    返回裁剪后的消息列表。
    """
    if len(messages) <= max_msgs + 1:  # +1 是 system 那条
        return messages
    # 1. 永远保留所有 system（含提示词和摘要）
    head = [m for m in messages if m["role"] == "system"]

    # 2. 永远保留第一个 user（即用户任务指令=锚点）
    anchor = None
    for m in messages:
        if m["role"] == "user":
            anchor = m
            break
    # 3. 从剩余消息里保留最近的消息（裁剪中间的工具对话）
    body = [m for m in messages if m not in head and m is not anchor]
    tail = body[-(max_msgs - len(head)) :] if max_msgs > len(head) else []

    # 4. 组装：system + 锚点 + 最近消息
    result = head + ([anchor] if anchor else []) + tail

    # 5. 去重保序（system 和锚点可能在 tail 里重复）
    seen = set()
    unique = []
    for m in result:
        key = (m["role"], str(m["content"])[:50])
        if key not in seen:
            seen.add(key)
            unique.append(m)
    return unique


# ② 历史压缩：修复版（任务锚点不进摘要）
def summarize_history(llm, messages, on_token=None):
    """压缩中间对话，保留 system + 用户任务锚点 + 最近 4 条。"""
    if len(messages) <= 4:
        return messages

    # 锚点：第一条 user（任务指令）
    anchor = None
    for m in messages:
        if m["role"] == "user":
            anchor = m
            break

    # 保留：所有 system + 锚点 + 最后 4 条
    head = [m for m in messages if m["role"] == "system"]
    keep = messages[-4:]
    # 待压缩：剩下的中间部分
    protected = head + ([anchor] if anchor else []) + keep
    to_summarize = [m for m in messages if m not in protected]

    if not to_summarize:
        return messages

    raw = "\n".join(f"[{m['role']}]{m['content'][:500]}" for m in to_summarize)
    summary_prompt = [
        {
            "role": "system",
            "content": "你是对话摘要器，把下面的执行过程压缩成不超过200字的中文摘要，保留：已完成的关键操作、重要结果、未完成事项。只输出摘要。",
        },
        {"role": "user", "content": raw},
    ]
    summary = llm.think(
        messages=summary_prompt,
        temperature=0,
        on_token=on_token,
    )
    summary = (summary or "")[:500]

    return (
        head
        + [
            {"role": "system", "content": f"[历史摘要]\n{summary}"},
        ]
        + ([anchor] if anchor else [])
        + keep
    )


# ③ 长期记忆：JSON 文件持久化
def load_memory() -> dict:
    """从 JSON 文件加载长期记忆（跨会话保留）。"""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_memory(memory: dict):
    """保存长期记忆到 JSON 文件。"""
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def remember(key: str, value: str, memory: dict) -> dict:
    """写入一条长期记忆。key 是主题，value 是内容。"""
    memory[key] = value
    save_memory(memory)
    return memory


# ④ 外部状态：任务进度/目标存文件

OUT_STATE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "storage_text/task_state.json"
)


def save_state(state: dict):
    """把任务外部状态（当前进度、目标、已做步骤）存到文件。

    这样即使中断，下次启动也能恢复。
    """
    with open(OUT_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_state() -> dict:
    """读取外部状态文件"""
    if os.path.exists(OUT_STATE_FILE):
        try:
            with open(OUT_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


# ⑤ 按需检索：关键词检索长期记忆
def search_memory(memory: dict, keyword: str, top_k: int = 5) -> str:
    """在长期记忆里按关键词检索相关内容，返回匹配的 key-value 文本。"""
    keyword = keyword.lower()
    hits = []
    for k, v in memory.items():
        if keyword in k.lower() or keyword in str(v).lower():
            hits.append(f"[{k}] {str(v)[:300]}")
        if len(hits) >= top_k:
            break
    return "\n".join(hits) if hits else f"(长期记忆中未找到与 '{keyword}' 相关的内容)"
