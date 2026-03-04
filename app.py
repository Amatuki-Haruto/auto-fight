#!/usr/bin/env python3
"""
あるけみすと 自動探索 - Web通知サーバー

Render にデプロイ。ローカルの auto_click.py からイベントを受信し、
Web画面に通知をプッシュ。ラッキーチャンス終了ボタンで再開シグナルを送信。
"""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

# グローバル状態
resume_requested = False
start_requested = False
sse_clients: list = []


async def broadcast(event: str, data: dict):
    """全SSEクライアントにイベントを送信"""
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


@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>あるけみすと 自動探索</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; max-width: 480px; margin: 2rem auto; padding: 0 1rem; }
    h1 { font-size: 1.25rem; }
    .status { padding: 1rem; background: #f0f0f0; border-radius: 8px; margin: 1rem 0; }
    .btn { display: block; width: 100%; padding: 1rem 1.5rem; font-size: 1rem; border: none;
           border-radius: 8px; cursor: pointer; margin-top: 1rem; font-weight: bold; }
    .btn:hover { opacity: 0.9; }
    .btn:disabled { background: #ccc; cursor: not-allowed; opacity: 1; }
    .btn-primary { background: #2196F3; color: white; }
    .btn-primary:hover { background: #1976D2; }
    .btn-success { background: #4CAF50; color: white; }
    .btn-success:hover { background: #45a049; }
    .instructions { font-size: 0.9rem; color: #555; margin: 1rem 0; line-height: 1.6; }
    .instructions code { background: #eee; padding: 0.2em 0.4em; border-radius: 4px; }
    .section { margin: 1.5rem 0; }
  </style>
</head>
<body>
  <h1>あるけみすと 自動探索</h1>
  <div class="status" id="status">接続中...</div>

  <div class="section">
    <p class="instructions">
      1. ターミナルで <code>python3 auto_click.py</code> を実行<br>
      2. ブラウザでゲームにログイン<br>
      3. ログインできたら下のボタンを押す
    </p>
    <button class="btn btn-primary" id="startBtn">自動探索開始</button>
  </div>

  <div class="section">
    <button class="btn btn-success" id="luckyBtn" disabled>ラッキーチャンスを終了した</button>
  </div>

  <div class="log" id="log"></div>
  <script>
    const status = document.getElementById('status');
    const startBtn = document.getElementById('startBtn');
    const luckyBtn = document.getElementById('luckyBtn');
    const log = document.getElementById('log');

    function addLog(msg) {
      const p = document.createElement('p');
      p.textContent = new Date().toLocaleTimeString('ja') + ' ' + msg;
      log.appendChild(p);
    }

    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }

    const es = new EventSource('/api/events');
    es.onopen = () => { status.textContent = '接続済み - 自動探索の準備ができました'; };
    es.onerror = () => { status.textContent = '切断・再接続中...'; };

    startBtn.addEventListener('click', async () => {
      try {
        await fetch('/api/start-exploration', { method: 'POST' });
        startBtn.disabled = true;
        startBtn.textContent = '開始シグナル送信済み';
        status.textContent = '自動探索を開始しました';
        addLog('自動探索開始を送信');
      } catch (err) {
        addLog('エラー: ' + err);
      }
    });

    es.addEventListener('lucky_chance', (e) => {
      const d = JSON.parse(e.data);
      status.textContent = '★ ラッキーチャンス！';
      luckyBtn.disabled = false;
      addLog('ラッキーチャンスを検出');
      if (Notification.permission === 'granted') {
        new Notification('あるけみすと', { body: 'ラッキーチャンスがあるよ！' });
      }
    });

    es.addEventListener('level_100', (e) => {
      status.textContent = 'レベル100に到達！';
      luckyBtn.disabled = true;
      addLog('レベル100に到達');
      if (Notification.permission === 'granted') {
        new Notification('あるけみすと', { body: 'レベル100に到達しました！' });
      }
    });

    luckyBtn.addEventListener('click', async () => {
      try {
        await fetch('/api/lucky-chance-done', { method: 'POST' });
        luckyBtn.disabled = true;
        status.textContent = '20秒後に探索を再開します';
        addLog('ラッキーチャンス終了を送信');
      } catch (err) {
        addLog('エラー: ' + err);
      }
    });
  </script>
</body>
</html>
"""


@app.post("/api/lucky-chance")
async def api_lucky_chance():
    """ローカルスクリプトから: ラッキーチャンス検知"""
    await broadcast("lucky_chance", {"at": datetime.now().isoformat()})
    return {"ok": True}


@app.post("/api/level-100")
async def api_level_100():
    """ローカルスクリプトから: レベル100到達"""
    await broadcast("level_100", {"at": datetime.now().isoformat()})
    return {"ok": True}


@app.post("/api/start-exploration")
async def api_start_exploration():
    """Web画面のボタン: 自動探索開始を通知"""
    global start_requested
    start_requested = True
    return {"ok": True}


@app.get("/api/check-start")
async def api_check_start():
    """ローカルスクリプト用: 開始シグナルを取得（1回だけTrueを返しリセット）"""
    global start_requested
    if start_requested:
        start_requested = False
        return {"start": True}
    return {"start": False}


@app.post("/api/lucky-chance-done")
async def api_lucky_chance_done():
    """Web画面のボタン: ラッキーチャンス終了を通知"""
    global resume_requested
    resume_requested = True
    return {"ok": True}


@app.get("/api/check-resume")
async def api_check_resume():
    """ローカルスクリプト用: 再開シグナルを取得（1回だけTrueを返しリセット）"""
    global resume_requested
    if resume_requested:
        resume_requested = False
        return {"resume": True}
    return {"resume": False}


@app.get("/api/events")
async def api_events():
    """SSEストリーム"""

    async def stream():
        q: asyncio.Queue = asyncio.Queue()
        sse_clients.append(q)
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield msg
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if q in sse_clients:
                sse_clients.remove(q)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
