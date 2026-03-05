#!/usr/bin/env python3
"""
あるけみすと 自動探索 - Web通知サーバー
Renderデプロイ用。軽量・高速。
"""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

# グローバル状態
go_requested: bool = False
stop_requested: bool = False
sse_clients: list = []

# 探索状態（UI同期・再接続用）
state_running: bool = False
state_lucky: bool = False

# 探索ログ（周回・メッセージ・ドロップ一覧）
state_loop_count: int = 0
state_last_message: str = ""
state_drops: list[str] = []

STATIC_DIR = Path(__file__).parent / "static"


async def broadcast(event: str, data: dict) -> None:
    msg = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    for q in sse_clients[:]:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    sse_clients.clear()


app = FastAPI(title="あるけみすと 自動探索", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=500)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "sse_clients": len(sse_clients)}


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content=_fallback_html())


def _fallback_html() -> str:
    """静的ファイルが無い場合のフォールバック"""
    return """<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>あるけみすと</title></head><body><h1>あるけみすと 自動探索</h1><p>static/index.html を配置してください</p></body></html>"""


@app.get("/api/state")
async def api_state() -> dict:
    """現在の探索状態（再接続・初期表示の同期用）"""
    return {
        "running": state_running,
        "lucky": state_lucky,
        "loop_count": state_loop_count,
        "last_message": state_last_message,
        "drops": state_drops.copy(),
    }


class ExplorationLogBody(BaseModel):
    loop_count: int = 0
    message: str = ""
    drops: list[str] | None = None  # 今回のドロップ（追加される）


@app.post("/api/exploration-log")
async def api_exploration_log(body: ExplorationLogBody) -> dict:
    """探索ログ受信（周回・メッセージ・ドロップ追加）"""
    global state_loop_count, state_last_message, state_drops
    if body.loop_count > 0:
        state_loop_count = body.loop_count
    if body.message:
        state_last_message = body.message
    if body.drops:
        state_drops.extend(body.drops)
    await broadcast("exploration_log", {"loop_count": state_loop_count, "message": state_last_message, "drops": state_drops.copy()})
    return {"ok": True}


@app.post("/api/lucky-chance")
async def api_lucky_chance() -> dict:
    global state_running, state_lucky
    state_running = False
    state_lucky = True
    await broadcast("lucky_chance", _state_payload())
    return {"ok": True}


@app.post("/api/go")
async def api_go() -> dict:
    global go_requested
    go_requested = True
    return {"ok": True}


@app.get("/api/check-go")
async def api_check_go() -> dict:
    global go_requested
    if go_requested:
        go_requested = False
        return {"go": True}
    return {"go": False}


@app.post("/api/stop-exploration")
async def api_stop_exploration() -> dict:
    global stop_requested
    stop_requested = True
    return {"ok": True}


@app.get("/api/check-stop")
async def api_check_stop() -> dict:
    global stop_requested
    if stop_requested:
        stop_requested = False
        return {"stop": True}
    return {"stop": False}


def _state_payload() -> dict:
    return {
        "at": datetime.now().isoformat(),
        "loop_count": state_loop_count,
        "message": state_last_message,
        "drops": state_drops.copy(),
    }


@app.post("/api/exploration-started")
async def api_exploration_started() -> dict:
    global state_running, state_lucky
    state_running = True
    state_lucky = False
    await broadcast("exploration_started", _state_payload())
    return {"ok": True}


@app.post("/api/exploration-stopped")
async def api_exploration_stopped() -> dict:
    global state_running, state_lucky
    state_running = False
    state_lucky = False
    await broadcast("exploration_stopped", _state_payload())
    return {"ok": True}


@app.get("/api/events")
async def api_events() -> StreamingResponse:
    async def stream():
        q: asyncio.Queue = asyncio.Queue()
        sse_clients.append(q)
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield msg
                except asyncio.TimeoutError:
                    yield ": k\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if q in sse_clients:
                sse_clients.remove(q)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
