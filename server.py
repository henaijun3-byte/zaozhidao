#!/usr/bin/env python3
"""早知道 · 本地服务：网页 + API。

用法
  python server.py             # 默认 http://127.0.0.1:8000
  python server.py --port 8080
"""

import argparse
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import briefing

ROOT = Path(__file__).resolve().parent


class SettingsUpdate(BaseModel):
    origin: str = ""
    destination: str = ""
    arrival_time: str = ""
    reminder: str = "07:00"


app = FastAPI(title="早知道 · 每日通勤助手")


def _read_config():
    return briefing.load_config(briefing.DEFAULT_CONFIG)


def _public_settings(config):
    return {
        "origin": config["origin"],
        "destination": config["destination"],
        "arrival_time": config["arrival_time"],
        "reminder": config["push_time"],
        "city": config["city"],
        "has_schedule": bool(config.get("schedule")),
        "has_push_key": bool(config["serverchan_sendkey"]),
    }


@app.get("/api/settings")
def get_settings():
    config, _ = _read_config()
    return _public_settings(config)


@app.post("/api/settings")
def post_settings(update: SettingsUpdate):
    config, cfg_path = _read_config()
    config["origin"] = update.origin.strip()
    config["destination"] = update.destination.strip()
    config["arrival_time"] = update.arrival_time.strip()
    if update.reminder:
        config["push_time"] = update.reminder
    briefing.save_config(config, cfg_path)
    return _public_settings(config)


@app.get("/api/briefing")
def get_briefing():
    """每次刷新都实时抓取，返回给前端的简报 JSON。"""
    config, cfg_path = _read_config()
    return briefing.build_briefing(config, cfg_path)


# 静态页面最后注册，避免遮住 /api 路由
app.mount("/", StaticFiles(directory=str(ROOT), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="早知道本地服务")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port)
