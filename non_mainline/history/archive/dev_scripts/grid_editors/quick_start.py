"""
快速启动14行10列网格编辑器
"""
from tools.universal_grid_editor import UniversalGridEditor

def quick_start():
    """快速启动14x10网格编辑器"""
    try:
        editor = UniversalGridEditor()

        # 设置参数
        editor.image_path = "tests/mock_data/clean/2.png"
        editor.rows = 14  # 14行
        editor.cols = 10  # 10列

        print("=" * 50)
        print("    快速启动网格编辑器")
        print("=" * 50)
        print(f"图片: {editor.image_path}")
        print(f"网格: {editor.rows}行 × {editor.cols}列")
        print("=" * 50)

        editor.run_editor()

    except Exception as e:
        print(f"启动失败: {e}")
        input("按Enter键退出...")

if __name__ == "__main__":
    quick_start()