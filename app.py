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

from fastapi import FastAPI, Body
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

# セッション統計
state_session_started_at: str | None = None  # ISO形式
state_total_exp: int = 0
state_drops_by_rank: dict[str, int] = {}  # {"S": 1, "A": 2, ...}
state_activity_log: list[dict] = []  # 直近のアクティビティ [{loop, msg, drops, at}, ...]
state_stop_reason: str = ""  # 強制停止理由（転生等）
state_stats: dict = {}  # 統計（連続エラー数等）

STATIC_DIR = Path(__file__).parent / "static"
MAX_ACTIVITY_LOG = 20


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


class StopReasonBody(BaseModel):
    reason: str = ""


@app.get("/api/state")
async def api_state() -> dict:
    """現在の探索状態（再接続・初期表示の同期用）"""
    return {
        "running": state_running,
        "lucky": state_lucky,
        "loop_count": state_loop_count,
        "last_message": state_last_message,
        "drops": state_drops.copy(),
        "session_started_at": state_session_started_at,
        "total_exp": state_total_exp,
        "drops_by_rank": state_drops_by_rank.copy(),
        "activity_log": state_activity_log.copy(),
        "stop_reason": state_stop_reason,
        "stats": state_stats.copy(),
    }


class ExplorationLogBody(BaseModel):
    loop_count: int = 0
    message: str = ""
    exp: int = 0
    drops: list[str] | None = None  # 今回のドロップ（追加される）
    stats: dict | None = None  # 統計（consecutive_errors, loop_time_sec等）


def _rank_from_drop(s: str) -> str:
    """[C] 弱体の種 → C"""
    if s.startswith("[") and "]" in s:
        return s[1 : s.index("]")].strip().upper()
    return "?"


@app.post("/api/exploration-log")
async def api_exploration_log(body: ExplorationLogBody) -> dict:
    """探索ログ受信（周回・メッセージ・経験値・ドロップ・統計）"""
    global state_loop_count, state_last_message, state_drops, state_total_exp, state_drops_by_rank, state_activity_log, state_stats
    if body.loop_count > 0:
        state_loop_count = body.loop_count
    if body.message:
        state_last_message = body.message
    if body.exp > 0:
        state_total_exp += body.exp
    if body.drops:
        for d in body.drops:
            state_drops.append(d)
            rk = _rank_from_drop(d)
            state_drops_by_rank[rk] = state_drops_by_rank.get(rk, 0) + 1
    if body.message or body.drops or body.exp > 0:
        entry = {"loop": state_loop_count, "msg": body.message, "drops": body.drops or [], "exp": body.exp, "at": datetime.now().isoformat()}
        state_activity_log.insert(0, entry)
        state_activity_log = state_activity_log[:MAX_ACTIVITY_LOG]
    if body.stats:
        state_stats.update(body.stats)
    payload = {
        "running": state_running,
        "lucky": state_lucky,
        "loop_count": state_loop_count,
        "message": state_last_message,
        "drops": state_drops.copy(),
        "total_exp": state_total_exp,
        "drops_by_rank": state_drops_by_rank.copy(),
        "activity_log": state_activity_log.copy(),
        "session_started_at": state_session_started_at,
    }
    await broadcast("exploration_log", payload)
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
        "session_started_at": state_session_started_at,
        "total_exp": state_total_exp,
        "drops_by_rank": state_drops_by_rank.copy(),
        "activity_log": state_activity_log.copy(),
        "stop_reason": state_stop_reason,
        "stats": state_stats.copy(),
    }


@app.post("/api/exploration-started")
async def api_exploration_started() -> dict:
    global state_running, state_lucky, state_session_started_at
    state_running = True
    state_lucky = False
    state_session_started_at = datetime.now().isoformat()
    await broadcast("exploration_started", _state_payload())
    return {"ok": True}


@app.post("/api/exploration-stopped")
async def api_exploration_stopped(body: StopReasonBody = Body(default=StopReasonBody())) -> dict:
    global state_running, state_lucky, state_stop_reason
    state_running = False
    state_lucky = False
    state_stop_reason = body.reason or ""
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
