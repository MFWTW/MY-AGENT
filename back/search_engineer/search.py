"""关键词搜索：TF-IDF 相关性打分 + 排序"""

import math
from collections import Counter


class SearchEngine:
    def __init__(self, inverted_index):
        # 依赖注入：把已经建好的倒排索引传进来
        self.index = inverted_index
        # 方便引用
        self.tokenizer = self.index.tokenizer

    def _tf(self, doc_id: int, word: str) -> float:
        """TF：词在文档里出现的次数 / 文档总词数"""
        text = self.index.document[doc_id]
        tokens = self.tokenizer.cut(text)
        word_count = Counter(tokens)  # 统计每个词出现几次
        total = len(tokens)  # 文档总词数
        return word_count.get(word, 0) / total  # 归一化，避免长文档占便宜

    def _idf(self, word: str) -> float:
        """IDF：词越稀有，权重越高"""
        N = len(self.index.document)
        df = len(self.index.search(word))
        return math.log(N / (df + 1))

    def _score(self, doc_id: int, word: str) -> float:
        """单篇文档对单个词的 TF-IDF 分数"""
        return self._tf(doc_id, word) * self._idf(word)

    def search(self, query: str, top_k: int = 5) -> list:
        """搜索入口：输入查询，返回排好序的 (文档ID, 原文, 分数) 列表"""
        # 1.查询也分词
        query_words = self.tokenizer.cut(query)

        # 2. 收集所有可能相关的文档（至少命中一个词）
        candidate_docs = set()
        for word in query_words:
            candidate_docs.update(self.index.search(word))

        # 3. 对每个候选文档打分
        results = []
        for doc_id in candidate_docs:
            score = sum(self._score(doc_id, word) for word in query_words)
            results.append((doc_id, self.index.document[doc_id], score))

        # 4.按分数从高到低排序，取前 top_k 个
        results.sort(key=lambda x: x[2], reverse=True)
        return results[:top_k]


if __name__ == "__main__":
    from tokenizer import Tokenizer
    from inverted_index import InvertedIndex

    # 搭建完整的流程
    idx = InvertedIndex(Tokenizer())
    idx.add_document("Python很好用，用来写后端")
    idx.add_document("Python和Java都很好用")
    idx.add_document("Java写后端很流行")
    idx.add_document("搜索引擎的核心是倒排索引")

    engine = SearchEngine(idx)

    print("\n搜索：'后端'")
    for doc_id, text, score in engine.search("后端"):
        print(f"  文档{doc_id} 分数={score:.4f}  {text}")
