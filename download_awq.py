#!/usr/bin/env python3
"""从 ModelScope 直接下载 Qwen2.5-Coder-7B-Instruct-AWQ 模型文件。"""

import os
import subprocess

BASE = "https://modelscope.cn/api/v1/models/Qwen/Qwen2.5-Coder-7B-Instruct-AWQ/repo"
# 模型下载到项目根目录（自动推导，不再写死 /mnt/e/agent）
DEST = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "Qwen2.5-Coder-7B-Instruct-AWQ",
)
# 可用环境变量覆盖
DEST = os.getenv("MODEL_DIR", DEST)

os.makedirs(DEST, exist_ok=True)

# 需要下载的文件（小文件用 urllib，大文件用 curl 支持断点续传）
FILES = [
    "config.json",
    "configuration.json",
    "generation_config.json",
    "LICENSE",
    "merges.txt",
    "model.safetensors.index.json",
    "model-00001-of-00002.safetensors",
    "model-00002-of-00002.safetensors",
    "README.md",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
]


def download(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        print(f"  [skip] {path}")
        return
    print(f"  [downloading] {os.path.basename(path)}")
    subprocess.run(
        ["curl", "-L", "-C", "-", "--retry", "3", "-o", path, url],
        check=True,
    )


def main():
    for f in FILES:
        url = f"{BASE}?Revision=master&FilePath={f}"
        path = os.path.join(DEST, f)
        download(url, path)
    print("ALL DONE")


if __name__ == "__main__":
    main()
