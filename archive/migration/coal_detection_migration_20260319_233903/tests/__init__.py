"""
翻车机积煤检测系统 V3.0 - 测试套件

包含以下测试模块：
1. test_detector.py - 检测算法测试
2. test_ecc.py - ECC 配准测试
3. test_performance.py - 性能测试
4. test_integration.py - 集成测试
5. test_multiprocess.py - 多进程架构测试
6. test_plc.py - PLC 通信测试
7. test_camera.py - 相机驱动测试

运行方法：
pytest tests/ -v                    # 运行所有测试
pytest tests/test_detector.py -v    # 运行特定测试
pytest tests/ --cov=algo --cov-report=html  # 生成覆盖率报告
"""