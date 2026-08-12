"""命令行搜索引擎入口：交互式搜索"""

from tokenizer import Tokenizer
from inverted_index import InvertedIndex
from search import SearchEngine
from corpus import DOCUMENTS


def build_engine():
    """把所有零件组装起来，返回一个能用的搜索引擎"""
    tokenizer = Tokenizer()
    index = InvertedIndex(tokenizer)

    # 把语料里每篇文档都加进索引
    for text in DOCUMENTS:
        index.add_document(text)

    print(f"✅ 已索引 {len(DOCUMENTS)} 篇文档")
    return SearchEngine(index)


def main():
    engine = build_engine()

    print("=" * 40)
    print("  手写搜索引擎 v1.0")
    print("  输入关键词搜索，输入 exit 退出")
    print("=" * 40)

    while True:
        # 交互是输入
        query = input("\n请输入搜索词 > ").strip()

        if query.lower() in ("exit", "quit", "q"):
            print("再见！")
            break
        if not query:
            continue

        # 调用搜索引擎
        results = engine.search(query, top_k=5)

        if not results:
            print("  没有找到相关结果 😢")
            continue

        print(f"\n  🔍 共找到 {len(results)} 个相关结果：")
        for rank, (doc_id, text, score) in enumerate(results, start=1):
            print(f"  {rank}. [文档{doc_id}] 相关度 {score:.3f}")
            print(f"     {text}")


if __name__ == "__main__":
    main()
