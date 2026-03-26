"""
翻车机积煤检测系统 V3.0 - 管理员 API

功能：
1. 简单密码认证
2. 翻车机增删改查
3. 漏斗增删改查
4. 检测参数调节（实时生效）
5. 系统运行信息

所有 /api/admin/* 路由需要 X-Admin-Token header 验证。
"""

import os
import time
import hashlib
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel
from loguru import logger

from config.devices_config import MachineConfig, FunnelConfig

# ═══════════════════════════════════════════════════════════════
# 密码配置
# ═══════════════════════════════════════════════════════════════
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


ADMIN_TOKEN = _hash_password(ADMIN_PASSWORD)


def verify_admin(x_admin_token: Optional[str] = Header(None)):
    """验证管理员 token"""
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="未授权")


# ═══════════════════════════════════════════════════════════════
# Pydantic 请求模型
# ═══════════════════════════════════════════════════════════════
class AuthRequest(BaseModel):
    password: str


class MachineCreateRequest(BaseModel):
    id: str
    name: str
    plc_ip: str
    plc_timeout_ms: int = 3000
    plc_heartbeat_interval_ms: int = 500


class MachineUpdateRequest(BaseModel):
    name: Optional[str] = None
    plc_ip: Optional[str] = None
    plc_timeout_ms: Optional[int] = None
    plc_heartbeat_interval_ms: Optional[int] = None


class FunnelCreateRequest(BaseModel):
    id: str
    name: str
    camera_ip: str
    pixel_format: str = "mono"
    camera_timeout_ms: int = 5000
    grid_count: int = 125
    grid_config_path: str = "config/grid_manual.yaml"


class FunnelUpdateRequest(BaseModel):
    name: Optional[str] = None
    camera_ip: Optional[str] = None
    pixel_format: Optional[str] = None
    camera_timeout_ms: Optional[int] = None
    grid_count: Optional[int] = None


class ThresholdsRequest(BaseModel):
    GRID_VISIBLE_THRESHOLD: Optional[float] = None
    COAL_COVERAGE_THRESHOLD: Optional[float] = None
    VOTE_WINDOW_SIZE: Optional[int] = None
    VOTE_THRESHOLD: Optional[int] = None


# ═══════════════════════════════════════════════════════════════
# Router 工厂（需要 state_manager 引用）
# ═══════════════════════════════════════════════════════════════
def create_admin_router(state_manager) -> APIRouter:
    """创建管理员 API 路由，绑定到指定的 state_manager"""

    router = APIRouter(prefix="/api/admin", tags=["admin"])

    # ─── 认证 ───
    @router.post("/auth")
    async def admin_auth(req: AuthRequest):
        """验证管理员密码，返回 token"""
        if req.password == ADMIN_PASSWORD:
            return {"token": ADMIN_TOKEN}
        raise HTTPException(status_code=401, detail="密码错误")

    # ─── 翻车机管理 ───
    @router.get("/machines")
    async def list_machines(x_admin_token: str = Header()):
        verify_admin(x_admin_token)
        result = []
        for mid, ms in state_manager.machines.items():
            mc = ms.machine_config
            result.append({
                "id": mc.id,
                "name": mc.name,
                "plc_ip": mc.plc_ip,
                "plc_timeout_ms": mc.plc_timeout_ms,
                "plc_heartbeat_interval_ms": mc.plc_heartbeat_interval_ms,
                "plc_connected": ms.plc_connected,
                "funnel_count": len(ms.funnels),
                "alert_level": ms.worst_alert_level,
                "funnels": [
                    {
                        "id": fc.id,
                        "name": fc.name,
                        "camera_ip": fc.camera_ip,
                        "pixel_format": fc.pixel_format,
                        "camera_timeout_ms": fc.camera_timeout_ms,
                        "grid_count": fc.grid_count,
                        "is_running": ms.funnels.get(fc.id, None) is not None
                            and ms.funnels[fc.id].is_running,
                    }
                    for fc in mc.funnels
                ],
            })
        return {"machines": result}

    @router.post("/machines")
    async def add_machine(req: MachineCreateRequest, x_admin_token: str = Header()):
        verify_admin(x_admin_token)
        mc = MachineConfig(
            id=req.id, name=req.name, plc_ip=req.plc_ip,
            plc_timeout_ms=req.plc_timeout_ms,
            plc_heartbeat_interval_ms=req.plc_heartbeat_interval_ms,
        )
        try:
            state_manager.add_machine(mc)
            return {"status": "ok", "message": f"翻车机 {req.name} 已添加"}
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

    @router.put("/machines/{machine_id}")
    async def update_machine(machine_id: str, req: MachineUpdateRequest, x_admin_token: str = Header()):
        verify_admin(x_admin_token)
        ms = state_manager.get_machine_state(machine_id)
        if not ms:
            raise HTTPException(status_code=404, detail="翻车机不存在")

        mc = ms.machine_config
        if req.name is not None:
            mc.name = req.name
        if req.plc_ip is not None:
            mc.plc_ip = req.plc_ip
        if req.plc_timeout_ms is not None:
            mc.plc_timeout_ms = req.plc_timeout_ms
        if req.plc_heartbeat_interval_ms is not None:
            mc.plc_heartbeat_interval_ms = req.plc_heartbeat_interval_ms

        state_manager._save_config()
        return {"status": "ok", "message": f"翻车机 {machine_id} 已更新"}

    @router.delete("/machines/{machine_id}")
    async def delete_machine(machine_id: str, x_admin_token: str = Header()):
        verify_admin(x_admin_token)
        try:
            state_manager.remove_machine(machine_id)
            return {"status": "ok", "message": f"翻车机 {machine_id} 已删除"}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ─── 漏斗管理 ───
    @router.post("/machines/{machine_id}/funnels")
    async def add_funnel(machine_id: str, req: FunnelCreateRequest, x_admin_token: str = Header()):
        verify_admin(x_admin_token)
        fc = FunnelConfig(
            id=req.id, name=req.name, camera_ip=req.camera_ip,
            pixel_format=req.pixel_format, camera_timeout_ms=req.camera_timeout_ms,
            grid_count=req.grid_count, grid_config_path=req.grid_config_path,
        )
        try:
            state_manager.add_funnel(machine_id, fc)
            return {"status": "ok", "message": f"漏斗 {req.name} 已添加到 {machine_id}"}
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

    @router.put("/machines/{machine_id}/funnels/{funnel_id}")
    async def update_funnel(machine_id: str, funnel_id: str, req: FunnelUpdateRequest, x_admin_token: str = Header()):
        verify_admin(x_admin_token)
        fc = state_manager.devices_config.get_funnel(machine_id, funnel_id)
        if not fc:
            raise HTTPException(status_code=404, detail="漏斗不存在")

        if req.name is not None:
            fc.name = req.name
        if req.camera_ip is not None:
            fc.camera_ip = req.camera_ip
        if req.pixel_format is not None:
            fc.pixel_format = req.pixel_format
        if req.camera_timeout_ms is not None:
            fc.camera_timeout_ms = req.camera_timeout_ms
        if req.grid_count is not None:
            fc.grid_count = req.grid_count

        state_manager._save_config()
        return {"status": "ok", "message": f"漏斗 {funnel_id} 已更新"}

    @router.delete("/machines/{machine_id}/funnels/{funnel_id}")
    async def delete_funnel(machine_id: str, funnel_id: str, x_admin_token: str = Header()):
        verify_admin(x_admin_token)
        try:
            state_manager.remove_funnel(machine_id, funnel_id)
            return {"status": "ok", "message": f"漏斗 {funnel_id} 已删除"}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ─── 检测参数 ───
    @router.get("/thresholds")
    async def get_thresholds(x_admin_token: str = Header()):
        verify_admin(x_admin_token)
        return state_manager.get_thresholds()

    @router.put("/thresholds")
    async def update_thresholds(req: ThresholdsRequest, x_admin_token: str = Header()):
        verify_admin(x_admin_token)
        params = {k: v for k, v in req.model_dump().items() if v is not None}
        if not params:
            raise HTTPException(status_code=400, detail="未提供任何参数")
        applied = state_manager.update_thresholds(params)
        return {"status": "ok", "applied": applied}

    # ─── 系统信息 ───
    @router.get("/system_info")
    async def system_info(x_admin_token: str = Header()):
        verify_admin(x_admin_token)
        import psutil
        info = {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "machines": {},
        }
        for mid, ms in state_manager.machines.items():
            m_info = {
                "plc_connected": ms.plc_connected,
                "funnels": {},
            }
            if ms.plc and hasattr(ms.plc, "get_plc_info"):
                m_info["plc_info"] = ms.plc.get_plc_info()

            for fid, fs in ms.funnels.items():
                f_info = {
                    "is_running": fs.is_running,
                    "detection_count": fs.detection_count,
                    "coal_detections": fs.coal_detections,
                }
                if fs.camera and hasattr(fs.camera, "get_camera_info"):
                    f_info["camera_info"] = fs.camera.get_camera_info()
                m_info["funnels"][fid] = f_info

            info["machines"][mid] = m_info
        return info

    return router
