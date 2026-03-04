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

# グローバル状態（開始・再開は同じシグナル、ラッキーチャンス後も「自動探索開始」で再開）
go_requested = False
stop_requested = False
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
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 50%, #f8fafc 100%);
      --bg-solid: #f0f9ff;
      --card: #ffffff;
      --text: #0c4a6e;
      --text-muted: #0369a1;
      --primary: #0284c7;
      --primary-hover: #0369a1;
      --primary-glow: rgba(2, 132, 199, 0.4);
      --danger: #dc2626;
      --danger-hover: #b91c1c;
      --danger-glow: rgba(220, 38, 38, 0.4);
      --border: #bae6fd;
      --code-bg: #e0f2fe;
      --card-shadow: 0 4px 20px rgba(2, 132, 199, 0.08);
    }
    [data-theme="dark"] {
      --bg: linear-gradient(160deg, #0c4a6e 0%, #0f172a 50%, #020617 100%);
      --bg-solid: #0f172a;
      --card: #1e293b;
      --text: #f0f9ff;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --primary-hover: #7dd3fc;
      --primary-glow: rgba(56, 189, 248, 0.35);
      --danger: #f87171;
      --danger-hover: #fca5a5;
      --danger-glow: rgba(248, 113, 113, 0.35);
      --border: #334155;
      --code-bg: #1e3a5f;
      --card-shadow: 0 4px 24px rgba(0, 0, 0, 0.4);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Noto Sans JP', -apple-system, sans-serif;
      background: var(--bg-solid);
      background-image: var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 2rem 1rem;
      transition: background 0.3s, color 0.3s, background-image 0.3s;
    }
    .container { max-width: 440px; margin: 0 auto; }
    h1 {
      font-size: 1.6rem;
      font-weight: 700;
      margin-bottom: 1.5rem;
      letter-spacing: -0.02em;
    }
    .card {
      background: var(--card);
      border-radius: 16px;
      padding: 1.5rem;
      margin-bottom: 1.25rem;
      box-shadow: var(--card-shadow);
      border: 1px solid var(--border);
      transition: box-shadow 0.2s;
    }
    .card:hover { box-shadow: 0 8px 32px rgba(2, 132, 199, 0.12); }
    [data-theme="dark"] .card:hover { box-shadow: 0 8px 40px rgba(0, 0, 0, 0.5); }
    .status {
      padding: 0.9rem 1.1rem;
      border-radius: 10px;
      background: var(--code-bg);
      font-size: 0.9rem;
      font-weight: 500;
    }
    .btn-row { display: flex; gap: 0.75rem; margin-top: 1.25rem; flex-wrap: wrap; }
    .btn {
      flex: 1;
      min-width: 150px;
      padding: 0.9rem 1.25rem;
      font-size: 0.95rem;
      border: none;
      border-radius: 10px;
      cursor: pointer;
      font-weight: 600;
      font-family: inherit;
      transition: all 0.2s;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    .btn:hover:not(:disabled) { transform: translateY(-2px); }
    .btn:active:not(:disabled) { transform: translateY(0); }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
    .btn-start {
      background: linear-gradient(180deg, var(--primary) 0%, var(--primary-hover) 100%);
      color: white;
    }
    .btn-start:hover:not(:disabled) { box-shadow: 0 4px 16px var(--primary-glow); }
    .btn-stop {
      background: linear-gradient(180deg, var(--danger) 0%, var(--danger-hover) 100%);
      color: white;
    }
    .btn-stop:hover:not(:disabled) { box-shadow: 0 4px 16px var(--danger-glow); }
    .instructions { font-size: 0.875rem; color: var(--text-muted); line-height: 1.8; }
    .instructions code {
      background: var(--code-bg);
      padding: 0.2em 0.5em;
      border-radius: 6px;
      font-size: 0.85em;
      font-weight: 500;
    }
    .theme-btn {
      position: fixed;
      top: 1rem;
      right: 1rem;
      width: 44px;
      height: 44px;
      border-radius: 12px;
      background: var(--card);
      border: 1px solid var(--border);
      cursor: pointer;
      font-size: 1.25rem;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
      transition: transform 0.2s;
    }
    .theme-btn:hover { transform: scale(1.05); }
    .log {
      font-size: 0.8rem;
      color: var(--text-muted);
      margin-top: 1rem;
      max-height: 140px;
      overflow-y: auto;
      padding: 0.5rem;
    }
    .log p { padding: 0.25em 0; }
  </style>
</head>
<body>
  <button class="theme-btn" id="themeBtn" title="ダークモード切り替え">🌙</button>
  <div class="container">
    <h1>あるけみすと 自動探索</h1>
    <div class="card">
      <div class="status" id="status">接続中...</div>
      <p class="instructions" style="margin-top: 1rem;">
        1. ターミナルで <code>python3 auto_click.py</code> を実行<br>
        2. ブラウザでゲームにログイン<br>
        3. ログインできたら「自動探索開始」を押す<br>
        ※ラッキーチャンス時も「自動探索開始」で再開できます
      </p>
      <div class="btn-row">
        <button class="btn btn-start" id="startBtn">自動探索開始</button>
        <button class="btn btn-stop" id="stopBtn" disabled>自動探索終了</button>
      </div>
    </div>
    <div class="log" id="log"></div>
  </div>
  <script>
    const status = document.getElementById('status');
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    const themeBtn = document.getElementById('themeBtn');
    const log = document.getElementById('log');

    const dark = localStorage.getItem('theme') === 'dark';
    if (dark) { document.documentElement.setAttribute('data-theme', 'dark'); themeBtn.textContent = '☀️'; }

    themeBtn.addEventListener('click', () => {
      const isDark = document.documentElement.hasAttribute('data-theme');
      if (isDark) { document.documentElement.removeAttribute('data-theme'); themeBtn.textContent = '🌙'; localStorage.setItem('theme', 'light'); }
      else { document.documentElement.setAttribute('data-theme', 'dark'); themeBtn.textContent = '☀️'; localStorage.setItem('theme', 'dark'); }
    });

    function addLog(msg) { const p = document.createElement('p'); p.textContent = new Date().toLocaleTimeString('ja') + ' ' + msg; log.appendChild(p); }

    if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission();

    const es = new EventSource('/api/events');
    es.onopen = () => { status.textContent = '接続済み - 準備ができました'; };
    es.onerror = () => { status.textContent = '切断・再接続中...'; };

    es.addEventListener('lucky_chance', (e) => {
      status.textContent = '★ ラッキーチャンス！ 「自動探索開始」を押すと20秒後に再開';
      startBtn.disabled = false;
      startBtn.textContent = '自動探索開始（再開）';
      stopBtn.disabled = true;
      addLog('ラッキーチャンスを検出');
      if (Notification.permission === 'granted') new Notification('あるけみすと', { body: 'ラッキーチャンスがあるよ！' });
    });

    es.addEventListener('exploration_started', () => {
      status.textContent = '自動探索実行中';
      startBtn.disabled = true;
      startBtn.textContent = '自動探索開始';
      stopBtn.disabled = false;
    });

    es.addEventListener('exploration_stopped', () => {
      status.textContent = '停止しました。再度開始するには「自動探索開始」を押してください';
      startBtn.disabled = false;
      stopBtn.disabled = true;
    });

    startBtn.addEventListener('click', async () => {
      try {
        await fetch('/api/go', { method: 'POST' });
        status.textContent = 'シグナル送信済み';
        addLog('自動探索開始を送信');
      } catch (err) { addLog('エラー: ' + err); }
    });

    stopBtn.addEventListener('click', async () => {
      try {
        await fetch('/api/stop-exploration', { method: 'POST' });
        addLog('自動探索終了を送信');
      } catch (err) { addLog('エラー: ' + err); }
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


@app.post("/api/go")
async def api_go():
    """Web画面のボタン: 自動探索開始・再開（開始とラッキーチャンス後の再開で共用）"""
    global go_requested
    go_requested = True
    return {"ok": True}


@app.get("/api/check-go")
async def api_check_go():
    """ローカルスクリプト用: 開始・再開シグナル（1回だけTrueを返しリセット）"""
    global go_requested
    if go_requested:
        go_requested = False
        return {"go": True}
    return {"go": False}


@app.post("/api/stop-exploration")
async def api_stop_exploration():
    """Web画面のボタン: 自動探索終了"""
    global stop_requested
    stop_requested = True
    return {"ok": True}


@app.get("/api/check-stop")
async def api_check_stop():
    """ローカルスクリプト用: 停止シグナル（1回だけTrueを返しリセット）"""
    global stop_requested
    if stop_requested:
        stop_requested = False
        return {"stop": True}
    return {"stop": False}


@app.post("/api/exploration-started")
async def api_exploration_started():
    """ローカルスクリプトから: 探索開始を通知"""
    await broadcast("exploration_started", {"at": datetime.now().isoformat()})
    return {"ok": True}


@app.post("/api/exploration-stopped")
async def api_exploration_stopped():
    """ローカルスクリプトから: 探索停止を通知"""
    await broadcast("exploration_stopped", {"at": datetime.now().isoformat()})
    return {"ok": True}


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
