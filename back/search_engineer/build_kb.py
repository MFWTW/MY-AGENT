"""构建 OpenCV 知识库：扫描官方教程，整理成干净的 .md 文件"""

import os
import re

# OpenCV 教程根目录（用你本地的 opencv-5.x）
SRC_ROOT = r"E:\agent\docs\opencv-5.x\opencv-5.x\doc\py_tutorials"
# 知识库输出目录
KB_DIR = r"E:\agent\knowledge_base\opencv_kb"

# 过滤掉这些"导航页/目录页"（真正的教程内容不在这里）
SKIP_KEYWORDS = ("table_of_contents", "tutorial_table_of", "index.markdown")


def clean_content(text: str) -> str:
    """清理 markdown：去掉代码块标记、LaTeX 公式标记，保留正文和代码"""
    # 去掉 @code{.py} ... @endcode 包裹标记，保留内部代码
    text = re.sub(r"@code\{\.py\}", "```python", text)
    text = re.sub(r"@code\{\.cpp\}", "```cpp", text)
    text = re.sub(r"@endcode", "```", text)
    text = re.sub(r"@sa\s+", "参考: ", text)  # 交叉引用
    text = re.sub(r"@note\s+", "提示: ", text)  # 提示
    text = re.sub(r"@warning\s+", "警告: ", text)  # 警告
    # 去掉 LaTeX 公式标记 \f[ ... \f] 和 \f$
    text = re.sub(r"\\f\[.*?\\f\]", "[公式]", text, flags=re.DOTALL)
    text = re.sub(r"\\f\$", "", text)
    # 去掉行内 {#anchor} 标签
    text = re.sub(r"\{#[\w-]+\}", "", text)
    return text


def extract_title(text: str, fallback: str) -> str:
    """提取文档标题（第一行 # 开头的内容）"""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
        if line.startswith("=") or line.startswith("-"):
            continue
        if line:
            return line.strip()
    return fallback


def build():
    os.makedirs(KB_DIR, exist_ok=True)
    count = 0
    skipped = 0

    # 递归扫描所有 .markdown 文件
    for root, dirs, files in os.walk(SRC_ROOT):
        for fname in sorted(files):
            if not fname.endswith((".markdown", ".md")):
                continue
            if any(k in fname.lower() for k in SKIP_KEYWORDS):
                skipped += 1
                continue

            md_path = os.path.join(root, fname)
            with open(md_path, "r", encoding="utf-8") as f:
                raw = f.read()

            # 太小的文件多半是导航页
            if len(raw) < 2000:
                skipped += 1
                continue

            cleaned = clean_content(raw)
            title = extract_title(cleaned, fname)

            # 用模块名 + 文件名作为新文件名，保证唯一
            rel = os.path.relpath(md_path, SRC_ROOT)
            parts = rel.split(os.sep)
            module = parts[0] if len(parts) > 1 else "misc"
            stem = fname.replace(".markdown", "").replace(".md", "")
            out_name = f"{module}__{stem}.md"
            out_path = os.path.join(KB_DIR, out_name)

            # 写入：标题 + 正文
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(f"# {title}\n\n")
                f.write(f"<!-- 来源: {rel} -->\n\n")
                f.write(cleaned)

            count += 1

    print(f"✅ 构建完成: {count} 篇文档写入 {KB_DIR}")
    print(f"   跳过 {skipped} 个导航/小文件")


if __name__ == "__main__":
    build()
