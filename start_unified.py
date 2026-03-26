"""启动统一 Web 应用（DEV 模式）"""
import os
os.environ["COAL_ENV"] = "DEV"

import uvicorn

if __name__ == "__main__":
    uvicorn.run("web.unified_app:app", host="0.0.0.0", port=8080)
