"""
翻车机积煤检测系统 V3.0 - 检测算法

检测流程：
1. 画面质量自检
2. CLAHE 增强
3. ECC 配准（可选）
4. 格栅孔计数
5. 积煤面积检测
6. 综合判定
"""

import cv2
import numpy as np
import time
import yaml
from dataclasses import dataclass, field
from typing import Optional, Tuple
from collections import deque
from pathlib import Path
from loguru import logger


@dataclass
class GridInfo:
    """格栅口信息"""
    id: int                         # 格栅口ID
    x: int                          # X坐标
    y: int                          # Y坐标
    w: int                          # 宽度
    h: int                          # 高度
    is_visible: bool                # 是否可见
    visibility_score: float         # 可见度分数 0.0~1.0
    has_coal: bool                  # 是否有积煤
    coal_coverage: float            # 积煤覆盖率


@dataclass
class DetectionResult:
    """检测结果（纯 dataclass，不再继承 dict）"""
    has_coal: Optional[bool]        # True/False/None(无法判定)
    confidence: str                 # HIGH/MEDIUM/LOW/NORMAL/WARNING
    confidence_score: float         # 0.0 ~ 1.0
    need_manual_confirm: bool       # 是否需要人工确认
    grid_visible_ratio: float       # 格栅可见率
    coal_coverage: float            # 积煤覆盖率
    process_time_ms: float          # 处理耗时
    frame_id: int                   # 帧号
    quality_ok: bool                # 画面质量
    quality_reason: str = ""        # 质量问题原因
    grid_details: Optional[list[GridInfo]] = None  # 格栅详细信息
    annotated_frame: Optional[np.ndarray] = None  # 标注后的图像

    # 缓存 to_dict 结果，避免重复创建
    _cached_dict: Optional[dict] = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict:
        """转为字典（带缓存）"""
        if self._cached_dict is not None:
            return self._cached_dict
        details = self.grid_details or []
        process_time_sec = self.process_time_ms / 1000.0
        d = {
            "has_coal": self.has_coal,
            "coal_present": self.has_coal,
            "confidence": self.confidence,
            "confidence_score": self.confidence_score,
            "need_manual_confirm": self.need_manual_confirm,
            "need_manual": self.need_manual_confirm,
            "grid_visible_ratio": self.grid_visible_ratio,
            "grid_ratio": self.grid_visible_ratio,
            "coal_coverage": self.coal_coverage,
            "coverage_ratio": self.coal_coverage,
            "process_time_ms": self.process_time_ms,
            "processing_time": process_time_sec,
            "frame_id": self.frame_id,
            "quality_ok": self.quality_ok,
            "quality_reason": self.quality_reason,
            "grid_count": len(details),
            "visible_grids": sum(1 for g in details if g.is_visible),
            "coal_grids": sum(1 for g in details if g.has_coal),
        }
        self._cached_dict = d
        return d

    def __getitem__(self, key):
        return self.to_dict()[key]

    def get(self, key, default=None):
        return self.to_dict().get(key, default)

    def __contains__(self, key):
        return key in self.to_dict()

    def keys(self):
        return self.to_dict().keys()

    def values(self):
        return self.to_dict().values()

    def items(self):
        return self.to_dict().items()

    def __len__(self):
        return len(self.to_dict())

    def __iter__(self):
        return iter(self.to_dict())


class CoalDetector:
    """
    积煤检测器
    
    支持开发模式（跳过 ECC）和生产模式（完整流程）
    """
    
    def __init__(self, config, grid_rois: Optional[list] = None):
        """
        初始化检测器
        
        Args:
            config: 配置对象
            grid_rois: 格栅孔 ROI 列表 [(x, y, w, h), ...]
        """
        self.config = config
        
        # 格栅 ROI（优先使用真实检测的格栅位置）
        if grid_rois is None:
            self.grid_rois = self._load_real_grids()
            if not self.grid_rois:
                logger.warning("[Detector] 未找到真实格栅配置，使用模拟数据")
                # 生成 4x6 = 24 个模拟格栅孔
                self.grid_rois = self._generate_mock_rois()
            else:
                logger.info(f"[Detector] 加载真实格栅配置，共 {len(self.grid_rois)} 个格栅口")
        else:
            self.grid_rois = grid_rois
        
        # 预创建 CLAHE 对象
        self.clahe = cv2.createCLAHE(
            clipLimit=config.CLAHE_CLIP_LIMIT,
            tileGridSize=(config.CLAHE_TILE_SIZE, config.CLAHE_TILE_SIZE)
        )

        # 兼容旧接口属性
        self.grid_counter = _GridCounterAdapter(self)
        self.coal_area_detector = _CoalAreaDetectorAdapter(self)
        self.judge = _JudgeAdapter(self)
        
        # ECC 参数
        self.ecc_criteria = (
            cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
            config.ECC_MAX_ITERATIONS,
            config.ECC_EPSILON
        )
        self.warp_matrix = np.eye(2, 3, dtype=np.float32)
        
        # 基准图像（ECC 用）
        self.reference_gray = None
        self._load_reference()
        
        # 预计算格栅掩码
        self.grid_mask = self._create_grid_mask()
        
        # 预热
        self._warmup()
        
        logger.info(f"[Detector] 初始化完成，格栅孔数: {len(self.grid_rois)}")

    def _load_real_grids(self) -> list:
        """加载格栅配置（优先使用手动标注）"""
        if self.config.DEV_MODE and not getattr(self.config, "USE_REAL_GRID_IN_DEV", False):
            return []

        # 从配置对象读取路径，不再硬编码
        manual_config_path = Path(getattr(self.config, "GRID_MANUAL_PATH", "config/grid_manual.yaml"))
        baseline_config_path = Path(getattr(self.config, "GRID_BASELINE_PATH", "config/grid_baseline.yaml"))

        config_path = None
        config_type = ""

        if manual_config_path.exists():
            config_path = manual_config_path
            config_type = "手动标注"
        elif baseline_config_path.exists():
            config_path = baseline_config_path
            config_type = "基准配置"

        if not config_path:
            return []

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                grid_config = yaml.safe_load(f)

            rois = []
            raw_rois = grid_config.get("grid_rois", [])

            # 格式1：自动检测输出（list[{"x","y","w","h"}]）
            if isinstance(raw_rois, list):
                for grid_roi in raw_rois:
                    if not isinstance(grid_roi, dict):
                        continue
                    if not all(k in grid_roi for k in ("x", "y", "w", "h")):
                        continue

                    x = int(round(grid_roi["x"]))
                    y = int(round(grid_roi["y"]))
                    w = int(round(grid_roi["w"]))
                    h = int(round(grid_roi["h"]))

                    if w > 0 and h > 0:
                        rois.append((x, y, w, h))

            # 格式2：手工标注输出（dict[roi_id -> {"corners": [...]}]）
            elif isinstance(raw_rois, dict):
                for roi_data in raw_rois.values():
                    if not isinstance(roi_data, dict):
                        continue
                    if not roi_data.get("enabled", True):
                        continue

                    corners = roi_data.get("corners", [])
                    if len(corners) < 4:
                        continue

                    xs = [float(p[0]) for p in corners if isinstance(p, (list, tuple)) and len(p) >= 2]
                    ys = [float(p[1]) for p in corners if isinstance(p, (list, tuple)) and len(p) >= 2]
                    if not xs or not ys:
                        continue

                    x1, y1 = int(round(min(xs))), int(round(min(ys)))
                    x2, y2 = int(round(max(xs))), int(round(max(ys)))
                    w, h = x2 - x1, y2 - y1
                    if w > 0 and h > 0:
                        rois.append((x1, y1, w, h))

            logger.info(f"[Detector] 加载{config_type}格栅配置: {config_path.name}")
            return rois

        except Exception as e:
            logger.error(f"[Detector] 加载格栅配置失败: {e}")
            return []

    def _generate_mock_rois(self) -> list:
        """生成模拟格栅 ROI"""
        rois = []
        w, h = self.config.frame_width, self.config.frame_height
        
        # 4 行 6 列
        for row in range(4):
            for col in range(6):
                x = int(w * 0.10 + col * w * 0.137)
                y = int(h * 0.195 + row * h * 0.156)
                roi_w = int(w * 0.060)
                roi_h = int(h * 0.055)
                rois.append((x, y, roi_w, roi_h))
        
        return rois
    
    def _load_reference(self):
        """加载基准图像"""
        try:
            ref = cv2.imread(self.config.REFERENCE_IMAGE_PATH)
            if ref is not None:
                ref = cv2.resize(ref, (
                    self.config.ECC_PROCESS_WIDTH,
                    self.config.ECC_PROCESS_HEIGHT
                ))
                self.reference_gray = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
                logger.info("[Detector] 基准图像加载成功")
            else:
                logger.warning("[Detector] 未找到基准图像，ECC 将被禁用")
        except Exception as e:
            logger.warning(f"[Detector] 加载基准图像失败: {e}")
    
    def _create_grid_mask(self) -> np.ndarray:
        """预计算格栅区域掩码"""
        mask = np.zeros(
            (self.config.frame_height, self.config.frame_width),
            dtype=np.uint8
        )
        for (x, y, w, h) in self.grid_rois:
            x1 = max(0, int(x))
            y1 = max(0, int(y))
            x2 = min(self.config.frame_width, x1 + int(w))
            y2 = min(self.config.frame_height, y1 + int(h))
            if x2 > x1 and y2 > y1:
                mask[y1:y2, x1:x2] = 255
        return mask
    
    def _warmup(self):
        """预热（让 OpenCV JIT 生效）"""
        dummy = np.random.randint(
            0, 255,
            (self.config.frame_height, self.config.frame_width, 3),
            dtype=np.uint8
        )
        for _ in range(3):
            self._detect_internal(dummy, 0)
        logger.debug("[Detector] 预热完成")
    
    def detect(self, frame: np.ndarray, frame_id: int = 0) -> DetectionResult:
        """
        主检测入口
        
        Args:
            frame: BGR 图像
            frame_id: 帧号
            
        Returns:
            DetectionResult
        """
        if frame is None:
            raise ValueError("frame cannot be None")
        if not isinstance(frame, np.ndarray):
            raise ValueError("frame must be a numpy.ndarray")
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("frame must be HxWx3 BGR image")
        if frame.shape[:2] != (self.config.frame_height, self.config.frame_width):
            raise ValueError(
                f"invalid frame shape {frame.shape[:2]}, "
                f"expected {(self.config.frame_height, self.config.frame_width)}"
            )
        if frame.dtype != np.uint8:
            frame = np.clip(frame, 0, 255).astype(np.uint8)

        t_start = time.perf_counter()
        result = self._detect_internal(frame, frame_id)
        result.process_time_ms = (time.perf_counter() - t_start) * 1000
        return result
    
    def _detect_internal(self, frame: np.ndarray, frame_id: int) -> DetectionResult:
        """内部检测逻辑"""
        
        # ═══════════════════════════════════════════════════════════
        # Step 1: 画面质量自检
        # ═══════════════════════════════════════════════════════════
        quality_ok, quality_reason = self._check_quality(frame)
        
        if not quality_ok:
            return DetectionResult(
                has_coal=None,
                confidence="LOW",
                confidence_score=0.0,
                need_manual_confirm=True,
                grid_visible_ratio=0.0,
                coal_coverage=0.0,
                process_time_ms=0.0,
                frame_id=frame_id,
                quality_ok=False,
                quality_reason=quality_reason,
                grid_details=[],
                annotated_frame=None
            )
        
        # ═══════════════════════════════════════════════════════════
        # Step 2: ECC 配准（开发模式可跳过）
        # ═══════════════════════════════════════════════════════════
        if self.config.use_ecc_actual and self.reference_gray is not None:
            frame = self._align_ecc(frame)
        
        # ═══════════════════════════════════════════════════════════
        # Step 3: CLAHE 增强
        # ═══════════════════════════════════════════════════════════
        enhanced = self._enhance(frame)
        
        # ═══════════════════════════════════════════════════════════
        # Step 4: 双因素检测
        # ═══════════════════════════════════════════════════════════
        grid_ratio, grid_details = self._count_grids(enhanced)
        coverage = self._detect_coverage(enhanced)

        # ═══════════════════════════════════════════════════════════
        # Step 5: 图像标注
        # ═══════════════════════════════════════════════════════════
        annotated_frame = self._annotate_frame(frame, grid_details)

        # ═══════════════════════════════════════════════════════════
        # Step 6: 综合判定
        # ═══════════════════════════════════════════════════════════
        has_coal, confidence, score, need_manual = self._judge(grid_ratio, coverage)

        return DetectionResult(
            has_coal=has_coal,
            confidence=confidence,
            confidence_score=score,
            need_manual_confirm=need_manual,
            grid_visible_ratio=grid_ratio,
            coal_coverage=coverage,
            process_time_ms=0.0,
            frame_id=frame_id,
            quality_ok=True,
            quality_reason="OK",
            grid_details=grid_details,
            annotated_frame=annotated_frame
        )
    
    def _check_quality(self, frame: np.ndarray) -> Tuple[bool, str]:
        """画面质量自检"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_val = gray.mean()
        
        # 全黑
        if mean_val < 15:
            return False, "画面全黑（曝光不足或遮挡）"
        
        # 全白
        if mean_val > 240:
            return False, "画面过曝"
        
        # 模糊检测
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        if laplacian_var < 50:
            return False, "画面模糊（可能镜头脏污）"
        
        return True, "OK"
    
    def _align_ecc(self, frame: np.ndarray) -> np.ndarray:
        """ECC 配准"""
        try:
            # 降采样
            small = cv2.resize(frame, (
                self.config.ECC_PROCESS_WIDTH,
                self.config.ECC_PROCESS_HEIGHT
            ))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            
            # 计算位移矩阵
            _, self.warp_matrix = cv2.findTransformECC(
                self.reference_gray, gray,
                self.warp_matrix,
                cv2.MOTION_TRANSLATION,
                self.ecc_criteria
            )

            # ★ 漂移量钳位：超过降采样图尺寸的 10% 就重置（防止长期累积漂移）
            max_drift = max(self.config.ECC_PROCESS_WIDTH, self.config.ECC_PROCESS_HEIGHT) * 0.1
            dx, dy = abs(self.warp_matrix[0, 2]), abs(self.warp_matrix[1, 2])
            if dx > max_drift or dy > max_drift:
                logger.warning(f"[CoalDetector] ECC 漂移过大 dx={dx:.1f} dy={dy:.1f}，重置矩阵")
                self.warp_matrix = np.eye(2, 3, dtype=np.float32)

            # 缩放到原图尺寸
            real_warp = self.warp_matrix.copy()
            real_warp[0, 2] *= self.config.ecc_scale_x
            real_warp[1, 2] *= self.config.ecc_scale_y
            
            # 应用配准
            aligned = cv2.warpAffine(
                frame, real_warp,
                (self.config.frame_width, self.config.frame_height)
            )
            return aligned
            
        except cv2.error:
            # 配准失败，重置矩阵
            self.warp_matrix = np.eye(2, 3, dtype=np.float32)
            return frame
    
    def _enhance(self, frame: np.ndarray) -> np.ndarray:
        """CLAHE 增强"""
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l = self.clahe.apply(l)
        return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
    
    def _count_grids(self, frame: np.ndarray) -> Tuple[float, list[GridInfo]]:
        """
        格栅孔计数和详细分析

        Returns:
            (visible_ratio, grid_details)
        """
        if not self.grid_rois:
            return 1.0, []

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        grid_details = []
        visible_count = 0

        for i, (x, y, w, h) in enumerate(self.grid_rois):
            x1 = max(0, int(x))
            y1 = max(0, int(y))
            x2 = min(self.config.frame_width, x1 + int(w))
            y2 = min(self.config.frame_height, y1 + int(h))

            roi_w = x2 - x1
            roi_h = y2 - y1
            if roi_w <= 0 or roi_h <= 0:
                grid_details.append(
                    GridInfo(
                        id=i + 1,
                        x=x1,
                        y=y1,
                        w=0,
                        h=0,
                        is_visible=False,
                        visibility_score=0.0,
                        has_coal=False,
                        coal_coverage=0.0,
                    )
                )
                continue

            roi_gray = gray[y1:y2, x1:x2]
            roi_hsv = hsv[y1:y2, x1:x2]

            # 格栅孔可见性检测
            _, binary = cv2.threshold(roi_gray, 60, 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(
                binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            visibility_score = 0.0
            is_visible = False

            if contours:
                max_area = max(cv2.contourArea(c) for c in contours)
                baseline = roi_w * roi_h * 0.5  # 假设孔占 50%
                visibility_score = min(max_area / baseline, 1.0)

                if max_area > baseline * 0.6:
                    visible_count += 1.0
                    is_visible = True
                elif max_area > baseline * 0.3:
                    visible_count += 0.5
                    is_visible = True

            # 兼容简单场景：当轮廓法不稳定时，使用暗像素占比辅助判定可见性
            total_pixels = roi_gray.size
            dark_ratio = np.count_nonzero(roi_gray < 90) / max(1, total_pixels)
            if dark_ratio > 0.04:
                if not is_visible:
                    visible_count += 1.0
                is_visible = True
                visibility_score = max(visibility_score, min(dark_ratio / 0.35, 1.0))
            elif dark_ratio > 0.015:
                if not is_visible:
                    visible_count += 0.5
                is_visible = True
                visibility_score = max(visibility_score, min(dark_ratio / 0.35, 1.0))

            # 积煤检测（在该格栅口区域）
            coal_mask = (roi_hsv[:, :, 1] < 30) & (roi_hsv[:, :, 2] < 60)
            coal_pixels = np.count_nonzero(coal_mask)
            coal_coverage_ratio = coal_pixels / total_pixels
            has_coal = coal_coverage_ratio > 0.1  # 10% 阈值

            grid_info = GridInfo(
                id=i + 1,
                x=x1,
                y=y1,
                w=roi_w,
                h=roi_h,
                is_visible=is_visible,
                visibility_score=visibility_score,
                has_coal=has_coal,
                coal_coverage=coal_coverage_ratio
            )
            grid_details.append(grid_info)

        visible_ratio = visible_count / len(self.grid_rois)
        return visible_ratio, grid_details
    
    def _detect_coverage(self, frame: np.ndarray) -> float:
        """积煤面积检测"""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        # 煤色：低饱和度 + 低亮度
        coal_mask = (hsv[:, :, 1] < 30) & (hsv[:, :, 2] < 60)
        
        # 只统计格栅区域
        coal_in_grid = coal_mask & (self.grid_mask > 0)
        
        grid_pixels = np.count_nonzero(self.grid_mask)
        coal_pixels = np.count_nonzero(coal_in_grid)
        
        return coal_pixels / grid_pixels if grid_pixels > 0 else 0
    
    def _judge(
        self, grid_ratio: float, coverage: float
    ) -> Tuple[Optional[bool], str, float, bool]:
        """
        综合判定
        
        Returns:
            (是否有煤, 置信度等级, 置信度分数, 是否需人工确认)
        """
        # 高置信度：两个指标一致
        if grid_ratio < 0.70 and coverage > 0.15:
            return True, "HIGH", 0.95, False
        
        if grid_ratio > 0.95 and coverage < 0.03:
            return False, "NORMAL", 0.95, False
        
        # 中置信度：单指标明显异常
        if grid_ratio < 0.60:
            return True, "MEDIUM", 0.80, False
        
        if coverage > 0.25:
            return True, "MEDIUM", 0.75, False
        
        # 低置信度：指标矛盾
        if grid_ratio < 0.80 and coverage < 0.05:
            return None, "LOW", 0.50, True
        
        if grid_ratio > 0.90 and coverage > 0.12:
            return None, "LOW", 0.50, True
        
        # 预警
        if grid_ratio < 0.90 or coverage > 0.05:
            return False, "WARNING", 0.60, False
        
        return False, "NORMAL", 0.90, False

    def _annotate_frame(self, frame: np.ndarray, grid_details: list[GridInfo]) -> np.ndarray:
        """
        在图像上标注格栅口信息

        Args:
            frame: 原始图像
            grid_details: 格栅口详细信息

        Returns:
            标注后的图像
        """
        annotated = frame.copy()

        # 字体设置
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        thickness = 1

        for grid in grid_details:
            x, y, w, h = grid.x, grid.y, grid.w, grid.h

            # 确定颜色
            if grid.has_coal:
                color = (0, 0, 255)  # 红色 - 有积煤
                status = "COAL"
            elif grid.is_visible:
                color = (0, 255, 0)  # 绿色 - 正常可见
                status = "OK"
            else:
                color = (0, 165, 255)  # 橙色 - 被遮挡
                status = "BLOCKED"

            # 绘制矩形框
            cv2.rectangle(annotated, (x, y), (x + w, y + h), color, thickness)

            # 绘制格栅口ID和状态
            label = f"#{grid.id} {status}"
            label_size, _ = cv2.getTextSize(label, font, font_scale, thickness)

            # 标签背景
            cv2.rectangle(
                annotated,
                (x, y - label_size[1] - 5),
                (x + label_size[0], y),
                color,
                -1
            )

            # 标签文字
            cv2.putText(
                annotated,
                label,
                (x, y - 3),
                font,
                font_scale,
                (255, 255, 255),
                thickness
            )

            # 显示可见度分数
            if grid.is_visible:
                score_text = f"{grid.visibility_score:.1f}"
                cv2.putText(
                    annotated,
                    score_text,
                    (x + 5, y + 15),
                    font,
                    font_scale * 0.8,
                    color,
                    thickness
                )

        # 添加总体统计信息
        total_grids = len(grid_details)
        visible_grids = sum(1 for g in grid_details if g.is_visible)
        coal_grids = sum(1 for g in grid_details if g.has_coal)

        stats_text = [
            f"Total Grids: {total_grids}",
            f"Visible: {visible_grids}",
            f"With Coal: {coal_grids}"
        ]

        for i, text in enumerate(stats_text):
            cv2.putText(
                annotated,
                text,
                (10, 30 + i * 20),
                font,
                0.6,
                (255, 255, 255),
                2
            )
            cv2.putText(
                annotated,
                text,
                (10, 30 + i * 20),
                font,
                0.6,
                (0, 0, 0),
                1
            )

        return annotated


class FrameVoter:
    """多帧投票器"""
    
    def __init__(self, config):
        self.config = config
        self.history: deque = deque(maxlen=config.VOTE_WINDOW_SIZE)
    
    def vote(self, result: DetectionResult) -> DetectionResult:
        """投票判定"""
        self.history.append(result)
        
        if len(self.history) < self.config.VOTE_WINDOW_SIZE:
            return result
        
        # 统计投票
        coal_votes = sum(1 for r in self.history if r.has_coal is True)
        no_coal_votes = sum(1 for r in self.history if r.has_coal is False)
        
        threshold = self.config.VOTE_THRESHOLD
        
        if coal_votes >= threshold:
            voted = True
        elif no_coal_votes >= threshold:
            voted = False
        else:
            voted = None
        
        # 返回投票后的结果
        return DetectionResult(
            has_coal=voted,
            confidence=result.confidence,
            confidence_score=result.confidence_score,
            need_manual_confirm=result.need_manual_confirm or (voted is None),
            grid_visible_ratio=result.grid_visible_ratio,
            coal_coverage=result.coal_coverage,
            process_time_ms=result.process_time_ms,
            frame_id=result.frame_id,
            quality_ok=result.quality_ok,
            quality_reason=result.quality_reason,
            grid_details=result.grid_details,
            annotated_frame=result.annotated_frame
        )


class _GridCounterAdapter:
    def __init__(self, detector: CoalDetector):
        self._detector = detector

    def count_visible_holes(self, frame: np.ndarray) -> float:
        enhanced = self._detector._enhance(frame)
        ratio, _ = self._detector._count_grids(enhanced)
        return float(ratio)


class _CoalAreaDetectorAdapter:
    def __init__(self, detector: CoalDetector):
        self._detector = detector

    def detect_coal_coverage(self, frame: np.ndarray) -> float:
        enhanced = self._detector._enhance(frame)
        return float(self._detector._detect_coverage(enhanced))


class _JudgeAdapter:
    def __init__(self, detector: CoalDetector):
        self._detector = detector

    def judge(self, grid_ratio: float, coverage: float) -> dict:
        has_coal, confidence, score, need_manual = self._detector._judge(grid_ratio, coverage)
        # NORMAL 表示无异常，在置信度语义中等同于 HIGH（明确无煤）
        # 保留原始值传递，不再静默重映射
        # 下游代码应将 NORMAL 和 HIGH 同等处理
        return {
            "coal_present": has_coal,
            "confidence": confidence,
            "confidence_score": score,
            "need_manual": need_manual,
        }
