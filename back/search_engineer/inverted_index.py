"""手写倒排索引：词 → 文档列表"""

from collections import defaultdict


class InvertedIndex:
    def __init__(self, tokenizer):
        # 依赖注入：用那个分类词，由外部传入
        self.tokenizer = tokenizer
        # 倒排索引表：词 -> 出现过的文档ID列表
        self.index = defaultdict(list)
        # 文档存储：doc_id -> 原文（后面搜索时要返回给用户看）
        self.document = {}
        # 自动增长的文档ID
        self._next_id = 1

    def add_document(self, text: str) -> str:
        """加入一篇文档，返回它的ID"""
        doc_id = self._next_id
        self._next_id += 1
        self.document[doc_id] = text

        # 对文档分词
        tokens = self.tokenizer.cut(text)

        # 核心：把每个词对应的文档ID加进索引
        for word in tokens:
            # 如果这个词还没出现过这篇文档，就加上
            if doc_id not in self.index[word]:
                self.index[word].append(doc_id)

        return doc_id

    def search(self, word: str) -> list:
        """根据一个词查倒排表，返回文档ID列表"""
        return self.index.get(word, [])

    def __str__(self):
        """方便打印查看"""
        return dict(self.index).__str__()


if __name__ == "__main__":
    from tokenizer import Tokenizer

    idx = InvertedIndex(Tokenizer())

    # 加入几篇示例文档
    d1 = idx.add_document("Python很好用")
    d2 = idx.add_document("Python和Java都很好用")
    d3 = idx.add_document("Java写后端")

    print("=== 倒排索引表 ===")
    print(idx)
    print()
    print(f"搜索 'Python' -> 文档 {idx.search('Python')}")
    print(f"搜索 'Java'   -> 文档 {idx.search('Java')}")
