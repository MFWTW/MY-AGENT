#!/usr/bin/env python
import cv2
import numpy as np

def apply_threshold(image_path, output_path, thresh_value, max_value):
    # 读取图像
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("图像读取失败")

    # 应用阈值处理
    _, binary_image = cv2.threshold(image, thresh_value, max_value, cv2.THRESH_BINARY)

    # 保存处理后的图像
    cv2.imwrite(output_path, binary_image)

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 5:
        print("Usage: python threshold_processing.py <input_image> <output_image> <thresh_value> <max_value>")
        sys.exit(1)

    input_image = sys.argv[1]
    output_image = sys.argv[2]
    thresh_value = int(sys.argv[3])
    max_value = int(sys.argv[4])

    apply_threshold(input_image, output_image, thresh_value, max_value)