#!/usr/bin/env python3
"""
あるけみすと 自動探索 - Web通知サーバー
Render 等にデプロイ可能。軽量・高速。
"""

import asyncio
import json
import logging
import sys
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import config
from fastapi import Body, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.gzip import GZipMiddleware

# -----------------------------------------------------------------------------
# 定数
# -----------------------------------------------------------------------------
STATIC_DIR = Path(__file__).parent / "static"
MAX_ACTIVITY_LOG = 20
MAX_DROPS = 500  # ドロップ一覧の最大件数（メモリ対策）

# -----------------------------------------------------------------------------
# グローバル状態
# -----------------------------------------------------------------------------
go_requested: bool = False
stop_requested: bool = False
sse_clients: list[asyncio.Queue[str]] = []

# 探索状態（UI同期・再接続用）
state_running: bool = False
state_lucky: bool = False

# 探索ログ（周回・メッセージ・ドロップ一覧）
state_loop_count: int = 0
state_last_message: str = ""
state_drops: deque[str] = deque(maxlen=MAX_DROPS)
state_level: int = 0  # 現在のレベル（ページから抽出）

# セッション統計
state_session_started_at: str | None = None  # ISO形式
state_total_exp: int = 0
state_drops_by_rank: dict[str, int] = {}  # {"S": 1, "A": 2, ...}
state_activity_log: deque[dict] = deque(maxlen=MAX_ACTIVITY_LOG)
state_stop_reason: str = ""
state_stats: dict = {}

# 並行アクセス用ロック
_state_lock = asyncio.Lock()

# index.html キャッシュ
_cached_index_html: str | None = None

# ロガー（broadcast の QueueFull 用）
_logger = logging.getLogger(__name__)


def _get_full_state() -> dict:
    """完全な状態を返す。api_state と broadcast で共通利用。"""
    return {
        "running": state_running,
        "lucky": state_lucky,
        "at": datetime.now().isoformat(),
        "loop_count": state_loop_count,
        "level": state_level,
        "last_message": state_last_message,
        "message": state_last_message,
        "drops": list(state_drops),
        "session_started_at": state_session_started_at,
        "total_exp": state_total_exp,
        "drops_by_rank": state_drops_by_rank.copy(),
        "activity_log": list(state_activity_log),
        "stop_reason": state_stop_reason,
        "stats": state_stats.copy(),
        "lucky_chance_wait_sec": config.LUCKY_CHANCE_WAIT_SEC,
    }


async def broadcast(event: str, data: dict) -> None:
    """SSE クライアントへブロードキャスト"""
    msg = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    for q in sse_clients[:]:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            if config.VERBOSE:
                _logger.debug("SSE broadcast: QueueFull for client, skipping")


_myshop_scheduler_task: asyncio.Task | None = None


def _seconds_until_next_fetch() -> float:
    """次の実行時刻（:15 or :45）までの秒数を返す"""
    from datetime import timedelta
    now = datetime.now()
    minutes = sorted(set(config.MYSHOP_FETCH_MINUTES))
    for m in minutes:
        if now.minute < m:
            target = now.replace(minute=m, second=0, microsecond=0)
            return (target - now).total_seconds()
    next_hour = now.replace(minute=minutes[0], second=0, microsecond=0) + timedelta(hours=1)
    return (next_hour - now).total_seconds()


async def _myshop_scheduler_loop() -> None:
    """毎時 :15, :45 に myshop 価格を自動取得"""
    fetcher_path = Path(__file__).parent / "myshop_fetcher.py"
    if not fetcher_path.exists():
        _logger.warning("myshop_fetcher.py が見つかりません。自動取得をスキップします")
        return
    while True:
        wait_sec = _seconds_until_next_fetch()
        _logger.info("市場価格の次回取得: %s から約 %.0f 秒後", datetime.now().strftime("%H:%M"), wait_sec)
        await asyncio.sleep(wait_sec)
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(fetcher_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(Path(__file__).parent),
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0 and stderr:
                _logger.warning("市場価格取得: %s", stderr.decode("utf-8", errors="replace").strip())
            elif proc.returncode == 0:
                _logger.info("市場価格を自動取得しました")
        except Exception as e:
            _logger.warning("市場価格取得エラー: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _myshop_scheduler_task
    if config.MYSHOP_AUTO_FETCH:
        _myshop_scheduler_task = asyncio.create_task(_myshop_scheduler_loop())
        _logger.info("市場価格の自動取得を有効にしました（%s 毎時）", config.MYSHOP_FETCH_MINUTES)
    yield
    if _myshop_scheduler_task and not _myshop_scheduler_task.done():
        _myshop_scheduler_task.cancel()
        try:
            await _myshop_scheduler_task
        except asyncio.CancelledError:
            pass
    sse_clients.clear()


app = FastAPI(title="あるけみすと 自動探索", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)

# 静的ファイル（CSS, JS 等）
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# -----------------------------------------------------------------------------
# 静的・トップ
# -----------------------------------------------------------------------------


def _load_index_html() -> str:
    """index.html を読み込みキャッシュ（本番で毎回読まない）"""
    global _cached_index_html
    if _cached_index_html is not None:
        return _cached_index_html
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        _cached_index_html = html_path.read_text(encoding="utf-8")
        return _cached_index_html
    return _fallback_html()


def _fallback_html() -> str:
    """静的ファイルが無い場合のフォールバック"""
    return """<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>あるけみすと</title></head><body><h1>あるけみすと 自動探索</h1><p>static/index.html を配置してください</p></body></html>"""


@app.get("/health", tags=["ヘルス"], summary="ヘルスチェック")
async def health() -> dict:
    return {"status": "ok", "sse_clients": len(sse_clients)}


@app.get("/", response_class=HTMLResponse, tags=["静的"])
async def index() -> HTMLResponse:
    return HTMLResponse(content=_load_index_html())


@app.get("/myshop", response_class=HTMLResponse, tags=["静的"])
async def myshop_page() -> HTMLResponse:
    """市場価格推移ページ"""
    html_path = STATIC_DIR / "myshop.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<p>myshop.html が見つかりません</p>")


# -----------------------------------------------------------------------------
# API - 状態
# -----------------------------------------------------------------------------


@app.get("/api/state", tags=["状態"], summary="現在の探索状態を取得")
async def api_state() -> dict:
    """現在の探索状態（再接続・初期表示の同期用）"""
    return _get_full_state()


# -----------------------------------------------------------------------------
# API - 探索制御
# -----------------------------------------------------------------------------


class StopReasonBody(BaseModel):
    """停止理由"""

    reason: str = Field("", description="強制停止理由（転生等）")


class ExplorationLogBody(BaseModel):
    """探索ログ受信ボディ"""

    loop_count: int = Field(0, ge=0, description="周回数")
    level: int | None = Field(None, ge=0, le=999, description="現在のレベル（ページから抽出）")
    message: str = ""
    exp: int = Field(0, ge=0, description="今回の経験値")
    drops: list[str] | None = Field(None, description="今回のドロップ（追加される）")
    stats: dict | None = Field(None, description="統計（consecutive_errors, loop_time_sec等）")


def _rank_from_drop(s: str) -> str:
    """[C] 弱体の種 → C"""
    if s.startswith("[") and "]" in s:
        return s[1 : s.index("]")].strip().upper()
    return "?"


@app.post("/api/exploration-log", tags=["探索"], summary="探索ログ受信")
async def api_exploration_log(body: ExplorationLogBody) -> dict:
    """探索ログ受信（周回・メッセージ・経験値・ドロップ・統計）"""
    global state_loop_count, state_last_message, state_drops, state_total_exp
    global state_drops_by_rank, state_activity_log, state_stats, state_level

    async with _state_lock:
        if body.level is not None and body.level > 0:
            state_level = body.level
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
            entry = {
                "loop": state_loop_count,
                "msg": body.message,
                "drops": body.drops or [],
                "exp": body.exp,
                "at": datetime.now().isoformat(),
            }
            state_activity_log.appendleft(entry)
        if body.stats:
            state_stats.update(body.stats)

    await broadcast("exploration_log", _get_full_state())
    return {"ok": True}


@app.post("/api/lucky-chance", tags=["探索"], summary="ラッキーチャンス通知")
async def api_lucky_chance() -> dict:
    global state_running, state_lucky
    async with _state_lock:
        state_running = False
        state_lucky = True
    await broadcast("lucky_chance", _get_full_state())
    return {"ok": True}


@app.post("/api/go", tags=["制御"], summary="自動探索開始リクエスト")
async def api_go() -> dict:
    global go_requested
    go_requested = True
    return {"ok": True}


@app.get("/api/check-go", tags=["制御"], summary="開始リクエスト確認")
async def api_check_go() -> dict:
    global go_requested
    if go_requested:
        go_requested = False
        return {"go": True}
    return {"go": False}


@app.post("/api/stop-exploration", tags=["制御"], summary="探索停止リクエスト")
async def api_stop_exploration() -> dict:
    global stop_requested, go_requested
    stop_requested = True
    go_requested = False
    return {"ok": True}


@app.get("/api/check-stop", tags=["制御"], summary="停止リクエスト確認")
async def api_check_stop() -> dict:
    global stop_requested
    if stop_requested:
        stop_requested = False
        return {"stop": True}
    return {"stop": False}


@app.post("/api/exploration-started", tags=["探索"], summary="探索開始通知")
async def api_exploration_started() -> dict:
    global state_running, state_lucky, state_session_started_at, state_stop_reason
    async with _state_lock:
        state_running = True
        state_lucky = False
        state_stop_reason = ""
        state_session_started_at = datetime.now().isoformat()
    await broadcast("exploration_started", _get_full_state())
    return {"ok": True}


@app.post("/api/exploration-stopped", tags=["探索"], summary="探索停止通知")
async def api_exploration_stopped(body: StopReasonBody = Body(default=StopReasonBody())) -> dict:
    global state_running, state_lucky, state_stop_reason
    async with _state_lock:
        state_running = False
        state_lucky = False
        state_stop_reason = body.reason or ""
    await broadcast("exploration_stopped", _get_full_state())
    return {"ok": True}


# -----------------------------------------------------------------------------
# API - myshop 価格記録
# -----------------------------------------------------------------------------

try:
    from myshop_parser import parse_myshop_html
    from myshop_db import get_price_summary, get_snapshots, init_db, insert_prices
    _myshop_available = True
except ImportError:
    _myshop_available = False


@app.get("/api/myshop/summary", tags=["myshop"], summary="価格サマリ取得")
async def api_myshop_summary(category: str | None = None, days: int = 30) -> dict:
    """アイテム別の価格サマリ（min/max/avg）"""
    if not _myshop_available:
        return {"error": "myshop module not available", "items": []}
    init_db()
    items = get_price_summary(category=category, limit_days=days)
    return {"items": items, "days": days}


@app.get("/api/myshop/snapshots", tags=["myshop"], summary="記録済みスナップショット一覧")
async def api_myshop_snapshots() -> dict:
    if not _myshop_available:
        return {"snapshots": []}
    init_db()
    return {"snapshots": get_snapshots()}


@app.post("/api/myshop/import", tags=["myshop"], summary="HTMLから価格を取り込み")
async def api_myshop_import(html: str = Body(..., embed=True)) -> dict:
    """保存したHTMLの本文を送信して価格を記録"""
    if not _myshop_available:
        return {"error": "myshop module not available", "count": 0}
    init_db()
    items = parse_myshop_html(html)
    if items:
        count = insert_prices(items)
        return {"ok": True, "count": count, "items": items}
    return {"ok": True, "count": 0, "items": [], "message": "No items found in HTML"}


@app.post("/api/myshop/fetch-now", tags=["myshop"], summary="今すぐ市場価格を自動取得")
async def api_myshop_fetch_now() -> dict:
    """Playwright で市場ページを取得してDBに保存（手動トリガー）"""
    fetcher_path = Path(__file__).parent / "myshop_fetcher.py"
    if not fetcher_path.exists():
        return {"error": "myshop_fetcher.py not found", "count": 0}
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(fetcher_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(Path(__file__).parent),
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = (stderr or stdout or b"").decode("utf-8", errors="replace").strip()
            return {"error": err or "fetch failed", "count": 0}
        # 標準出力から件数を推測（"市場価格を N 件記録"）
        out = (stdout or b"").decode("utf-8")
        import re
        m = re.search(r"(\d+)\s*件記録", out)
        count = int(m.group(1)) if m else 0
        return {"ok": True, "count": count}
    except Exception as e:
        return {"error": str(e), "count": 0}


# -----------------------------------------------------------------------------
# API - SSE
# -----------------------------------------------------------------------------


@app.get("/api/events", tags=["SSE"], summary="SSE イベントストリーム")
async def api_events() -> StreamingResponse:
    """Server-Sent Events で状態変更をプッシュ"""

    async def stream():
        q: asyncio.Queue[str] = asyncio.Queue()
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
