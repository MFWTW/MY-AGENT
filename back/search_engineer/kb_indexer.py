"""知识库索引器：扫描 OpenCV 文档目录，构建倒排索引并搜索"""

import os
from tokenizer import Tokenizer
from inverted_index import InvertedIndex
from search import SearchEngine

# 知识库目录（你的 build_kb.py 输出位置）
KB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "knowledge_base",
    "opencv_kb",
)
# 中文标题映射：英文文件名 → 中文标题
# 这样用户用中文搜，也能命中英文文档（标题作为"标签"参与索引）
TITLE_MAP = {
    "py_imgproc__py_thresholding": "图像阈值处理 threshold",
    "py_imgproc__py_canny": "Canny边缘检测 边缘检测",
    "py_imgproc__py_filtering": "图像滤波 平滑 卷积 filter2D",
    "py_imgproc__py_contours_begin": "轮廓检测 轮廓入门",
    "py_imgproc__py_contour_features": "轮廓特征",
    "py_imgproc__py_contour_properties": "轮廓属性",
    "py_imgproc__py_contours_more_functions": "轮廓更多函数",
    "py_imgproc__py_contours_hierarchy": "轮廓层级 层次结构",
    "py_imgproc__py_morphological_ops": "形态学操作 腐蚀 膨胀",
    "py_imgproc__py_histogram_begins": "直方图入门 直方图",
    "py_imgproc__py_histogram_equalization": "直方图均衡化",
    "py_imgproc__py_2d_histogram": "二维直方图",
    "py_imgproc__py_histogram_backprojection": "直方图反向投影",
    "py_imgproc__py_houghlines": "霍夫直线检测 直线检测",
    "py_imgproc__py_houghcircles": "霍夫圆检测 圆检测",
    "py_imgproc__py_template_matching": "模板匹配",
    "py_imgproc__py_grabcut": "GrabCut 图像分割",
    "py_imgproc__py_watershed": "分水岭算法 图像分割",
    "py_imgproc__py_gradients": "图像梯度 Sobel Laplacian",
    "py_imgproc__py_geometric_transformations": "几何变换 仿射变换 透视",
    "py_imgproc__py_pyramids": "图像金字塔",
    "py_imgproc__py_fourier_transform": "傅里叶变换",
    "py_imgproc__py_colorspaces": "颜色空间转换 BGR HSV",
    "py_imgproc__py_transforms": "图像变换",
    "py_features__py_features_harris": "Harris角点检测 角点",
    "py_features__py_shi_tomasi": "Shi-Tomasi角点检测 角点",
    "py_features__py_fast": "FAST角点检测 角点",
    "py_features__py_sift_intro": "SIFT特征 尺度不变特征",
    "py_features__py_orb": "ORB特征 特征检测",
    "py_features__py_matcher": "特征匹配 BFMatcher",
    "py_features__py_feature_homography": "特征匹配 单应性 图像拼接",
    "py_gui__py_drawing_functions": "绘图函数 画线 画圆",
    "py_gui__py_mouse_handling": "鼠标事件 交互",
    "py_gui__py_trackbar": "轨迹条 Trackbar",
    "py_core__py_basic_ops": "图像基础操作 像素",
    "py_core__py_image_arithmetics": "图像运算 加减 混合",
    "py_core__py_optimization": "性能优化",
    "py_bindings__py_bindings_basics": "Python绑定 基础",
    "py_calib3d__py_calibration": "相机标定 畸变校正",
    "py_calib3d__py_depthmap": "深度图 立体匹配",
    "py_calib3d__py_epipolar_geometry": "对极几何",
    "py_calib3d__py_pose": "姿态估计 位姿",
    "py_video__py_background_subtraction": "背景减除",
    "py_video__py_meanshift": "MeanShift 目标跟踪",
    "py_video__py_camshift": "CamShift 目标跟踪",
    "py_video__py_lucas_kanade": "光流 Lucas-Kanade",
    "py_photo__py_inpainting": "图像修复 去水印",
    "py_photo__py_non_local_means": "去噪 非局部均值",
    "py_ml__py_kmeans_understanding": "KMeans聚类 理解",
    "py_ml__py_kmeans_opencv": "KMeans聚类 OpenCV实现",
    "py_objdetect__py_face_detection": "人脸检测 Haar",
    "py_setup__py_intro": "OpenCV入门 介绍",
    "py_setup__py_pip_install": "pip安装 OpenCV安装",
}


class KBIndexer:
    """扫描目录、建立索引、提供搜索"""

    def __init__(self, kb_dir: str = KB_DIR):
        self.kb_dir = kb_dir
        # 组装零件：分词器 → 索引
        self.tokenizer = Tokenizer()
        self.index = InvertedIndex(self.tokenizer)
        # 记录 文档ID -> 文件名
        self.doc_names = {}
        self._build()

    def _build(self):
        """扫描目录下所有 .md 文件，逐个加入索引"""
        if not os.path.isdir(self.kb_dir):
            raise FileNotFoundError(f"知识库目录不存在: {self.kb_dir}")

        for fname in sorted(os.listdir(self.kb_dir)):
            if not fname.endswith(".md"):
                continue

            path = os.path.join(self.kb_dir, fname)
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()

            # 关键技巧：把中文标题拼在正文前面（作为"标签"参与索引）
            stem = fname[:-3]
            title_tag = TITLE_MAP.get(stem, "")
            if title_tag:
                text = f"{title_tag}\n\n{text}"

            doc_id = self.index.add_document(text)
            self.doc_names[doc_id] = stem

        print(f"✅ 知识库索引完成: {len(self.doc_names)} 篇文档")

    def search(self, query: str, top_k: int = 3, max_len: int = 1500) -> list:
        """搜索知识库，返回文档片段列表

        返回: [(文件名, 标题, 内容片段, 分数), ...]
        """
        engine = SearchEngine(self.index)
        results = []

        for doc_id, full_text, score in engine.search(query, top_k=top_k):
            fname = self.doc_names.get(doc_id, f"文档{doc_id}")
            # 提取中文标题（如果有）
            title = TITLE_MAP.get(fname, fname)
            # 只返回正文片段（去掉开头的标题标签）
            body = full_text
            for tag in (title,):
                if body.startswith(tag):
                    body = body[len(tag) :].strip()
            snippet = body[:max_len]
            results.append((fname, title, snippet, score))

        return results


if __name__ == "__main__":
    kb = KBIndexer()

    for q in ["threshold", "canny", "轮廓", "直方图", "滤波", "角点检测", "霍夫直线"]:
        print(f"\n=== 搜索: {q} ===")
        for fname, title, snippet, score in kb.search(q, top_k=2):
            print(f"  [{score:.3f}] {title}")
            first_line = snippet.strip().splitlines()[0] if snippet.strip() else ""
            print(f"    文件: {fname}")
            print(f"    开头: {first_line}")
