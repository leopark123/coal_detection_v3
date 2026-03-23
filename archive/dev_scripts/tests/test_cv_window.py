"""
测试OpenCV窗口是否能正常显示
"""

import os
import cv2
import numpy as np
import pytest


@pytest.mark.skipif(
    os.getenv("ENABLE_GUI_TESTS", "0") != "1",
    reason="GUI 测试默认跳过，设置 ENABLE_GUI_TESTS=1 后启用"
)
def test_opencv_window():
    # 创建一个简单的测试图像
    img = np.zeros((400, 600, 3), dtype=np.uint8)

    # 绘制一些文字
    cv2.putText(img, "OpenCV Window Test", (50, 200),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    cv2.putText(img, "Press any key to close", (50, 250),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)

    # 显示窗口
    window_name = "OpenCV Test Window"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.imshow(window_name, img)

    print("OpenCV窗口已显示，按任意键关闭...")
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    print("窗口已关闭")

if __name__ == "__main__":
    test_opencv_window()
