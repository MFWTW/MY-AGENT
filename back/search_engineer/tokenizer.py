"""手写中文分词器：基于词典的正向最大匹配法"""

import re

# 内置一个小词典（真实的词典会有几万词，这里够演示用）
DICTIONARY = {
    "Python",
    "Java",
    "很好用",
    "很好",
    "后端",
    "前端",
    "搜索引擎",
    "倒排索引",
    "分词",
    "编程",
    "语言",
    "中文",
    "英文",
    "电脑",
    "代码",
    "开发",
    "学习",
    "人工智能",
    "机器学习",
    "数据",
    "算法",
    "开源",
    # 新增 OpenCV 专业词（中英文都加，方便中文搜索）
    "图像",
    "图片",
    "阈值",
    "边缘",
    "轮廓",
    "滤波",
    "模糊",
    "直方图",
    "模板",
    "匹配",
    "形态学",
    "腐蚀",
    "膨胀",
    "梯度",
    "特征",
    "检测",
    "二值化",
    "灰度",
    "像素",
    "卷积",
    "变换",
    "金字塔",
    "颜色",
    "空间",
    "处理",
    "转换",
    "角点",
    "光流",
    "视频",
    "相机",
    "标定",
    "深度",
}


class Tokenizer:
    """基本正向最大匹配法的分词器"""

    def __init__(self, dictionary=None):
        # 用传入的词典，如果没有就用内置的
        self.dictionary = dictionary or DICTIONARY
        # 提前算好词典里最长的词有几个字，用于匹配时从长到短尝试
        self.max_word_len = max(len(word) for word in self.dictionary)
        # 匹配"连续的英文/数字/下划线"，如 cv、threshold、THRESH_BINARY、img
        self.en_pattern = re.compile(r"[A-Za-z0-9_]+")

    def cut(self, text: str) -> list[str]:
        """把文本切成词列表"""
        tokens = []
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]

            # ---- 通道1：英文/数字/代码符号 ----
            # 判断是不是 ASCII 字母、数字或下划线
            if ch.isascii() and (ch.isalnum() or ch == "_"):
                m = self.en_pattern.match(text, i)
                if m:
                    word = m.group()
                    tokens.append(word.lower())  # 统一小写，搜索不区分大小写
                    i = m.end()
                    continue

            # ---- 通道2：中文字符 ----
            if "\u4e00" <= ch <= "\u9fff":
                matched = None
                for length in range(self.max_word_len, 0, -1):
                    word = text[i : i + length]
                    if word in self.dictionary:
                        matched = word
                        break
                if matched:
                    tokens.append(matched)
                    i += len(matched)
                else:
                    # 词典里没有，就保留单字（这样搜索单字也能命中）
                    tokens.append(ch)
                    i += 1
                continue

            # ---- 其他字符（空格、标点）：跳过 ----
            i += 1

        return tokens


if __name__ == "__main__":
    t = Tokenizer()
    print(t.cut("cv.threshold(img, 127, 255, cv.THRESH_BINARY)"))
    print(t.cut("图像阈值处理"))
    print(t.cut("Canny边缘检测"))
    print(t.cut("Python很好用"))
