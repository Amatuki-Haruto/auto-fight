#!/usr/bin/env python3
"""
あるけみすと 自動探索 - Web通知サーバー
Renderデプロイ用。軽量・高速。システムフォントのみで外部リクエストゼロ。
"""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

# グローバル状態
go_requested = False
stop_requested = False
sse_clients: list = []


async def broadcast(event: str, data: dict):
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
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>あるけみすと 自動探索</title><style>
:root{--bg:#0a0e14;--card:#131920;--border:#2a3441;--text:#e6edf3;--muted:#8b949e;--accent:#f0883e;--accent2:#58a6ff;--success:#3fb950;--danger:#f85149;--radius:12px;--shadow:0 8px 32px rgba(0,0,0,.4)}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Hiragino Sans','Yu Gothic',Meiryo,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;line-height:1.6}
main{max-width:400px;margin:0 auto;padding:1.5rem 1rem}
h1{font-size:1.4rem;font-weight:700;margin-bottom:1.25rem;color:var(--text)}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:1.25rem;margin-bottom:1rem;box-shadow:var(--shadow)}
.status{display:flex;align-items:center;gap:.5rem;padding:.75rem 1rem;background:rgba(255,255,255,.04);border-radius:8px;font-size:.9rem;font-weight:500}
.status::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--muted);animation:pulse 2s infinite}
.status.ready::before{background:var(--success)}
.status.running::before{background:var(--accent2)}
.status.lucky::before{background:var(--accent);animation:pulse .8s infinite}
.status.lucky{box-shadow:0 0 0 2px rgba(240,136,62,.3)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.steps{font-size:.8rem;color:var(--muted);margin-top:1rem;line-height:1.9}
.steps code{background:rgba(255,255,255,.08);padding:.15em .4em;border-radius:4px;font-size:.85em}
.btns{display:flex;gap:.6rem;margin-top:1rem;flex-wrap:wrap}
.btn{flex:1;min-width:120px;padding:.8rem 1rem;font-size:.9rem;font-weight:600;border:none;border-radius:8px;cursor:pointer;transition:transform .15s,box-shadow .15s;font-family:inherit}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn-start{background:linear-gradient(135deg,var(--accent),#c76d2e);color:#fff}
.btn-start:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 4px 12px rgba(240,136,62,.3)}
.btn-stop{background:linear-gradient(135deg,var(--danger),#c0392b);color:#fff}
.btn-stop:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 4px 12px rgba(248,81,73,.3)}
.theme-btn{position:fixed;top:1rem;right:1rem;width:40px;height:40px;border-radius:10px;background:var(--card);border:1px solid var(--border);cursor:pointer;font-size:1.1rem;transition:transform .15s}
.theme-btn:hover{transform:scale(1.05)}
.log{font-size:.75rem;color:var(--muted);margin-top:1rem;max-height:100px;overflow-y:auto;padding:.5rem}
.log p{padding:.15em 0}
[data-theme="light"]{--bg:#f6f8fa;--card:#fff;--border:#d0d7de;--text:#1f2328;--muted:#656d76;--accent:#cf5d0e;--accent2:#0969da;--success:#1a7f37;--danger:#cf222e}
</style></head><body>
<button class="theme-btn" id="themeBtn" title="テーマ切替">🌙</button>
<main>
<h1>🧪 あるけみすと 自動探索</h1>
<div class="card">
<div class="status" id="status">接続中...</div>
<p class="steps">
1. <code>python3 auto_click.py</code> を実行<br>
2. Braveでゲームにログイン<br>
3. 「自動探索開始」を押す
</p>
<div class="btns">
<button class="btn btn-start" id="startBtn">▶ 自動探索開始</button>
<button class="btn btn-stop" id="stopBtn" disabled>■ 停止</button>
</div>
</div>
<div class="log" id="log"></div>
</main>
<script>
const $=(e)=>document.querySelector(e);const st=$('#status'),sb=$('#startBtn'),sp=$('#stopBtn'),tb=$('#themeBtn'),lg=$('#log');
if(localStorage.theme==='light'){document.documentElement.setAttribute('data-theme','light');tb.textContent='☀️'}
tb.onclick=()=>{const d=document.documentElement;if(d.dataset.theme){d.removeAttribute('data-theme');tb.textContent='🌙';localStorage.theme=''}else{d.dataset.theme='light';tb.textContent='☀️';localStorage.theme='light'}};
const log=m=>{const p=document.createElement('p');p.textContent=new Date().toLocaleTimeString('ja')+' '+m;lg.appendChild(p);lg.scrollTop=lg.scrollHeight};
if('Notification'in window&&Notification.permission==='default')Notification.requestPermission();
const es=new EventSource('/api/events');
es.onopen=()=>{st.textContent='接続済み - 準備OK';st.className='status ready'};
es.onerror=()=>{st.textContent='再接続中...';st.className='status'};
es.addEventListener('lucky_chance',()=>{st.textContent='★ ラッキーチャンス！ 「開始」で20秒後に再開';st.className='status lucky';sb.disabled=false;sb.textContent='▶ 再開';sp.disabled=true;log('ラッキーチャンス検出');if(Notification.permission==='granted')new Notification('あるけみすと',{body:'ラッキーチャンス！'})});
es.addEventListener('exploration_started',()=>{st.textContent='探索実行中';st.className='status running';sb.disabled=true;sb.textContent='▶ 自動探索開始';sp.disabled=false});
es.addEventListener('exploration_stopped',()=>{st.textContent='停止済み - 「開始」で再開';st.className='status ready';sb.disabled=false;sp.disabled=true});
sb.onclick=async()=>{try{await fetch('/api/go',{method:'POST'});st.textContent='送信完了';log('開始');}catch(e){log('エラー:'+e)}};
sp.onclick=async()=>{try{await fetch('/api/stop-exploration',{method:'POST'});log('停止送信');}catch(e){log('エラー:'+e)}};
</script>
</body></html>
"""


@app.post("/api/lucky-chance")
async def api_lucky_chance():
    await broadcast("lucky_chance", {"at": datetime.now().isoformat()})
    return {"ok": True}


@app.post("/api/go")
async def api_go():
    global go_requested
    go_requested = True
    return {"ok": True}


@app.get("/api/check-go")
async def api_check_go():
    global go_requested
    if go_requested:
        go_requested = False
        return {"go": True}
    return {"go": False}


@app.post("/api/stop-exploration")
async def api_stop_exploration():
    global stop_requested
    stop_requested = True
    return {"ok": True}


@app.get("/api/check-stop")
async def api_check_stop():
    global stop_requested
    if stop_requested:
        stop_requested = False
        return {"stop": True}
    return {"stop": False}


@app.post("/api/exploration-started")
async def api_exploration_started():
    await broadcast("exploration_started", {"at": datetime.now().isoformat()})
    return {"ok": True}


@app.post("/api/exploration-stopped")
async def api_exploration_stopped():
    await broadcast("exploration_stopped", {"at": datetime.now().isoformat()})
    return {"ok": True}


@app.get("/api/events")
async def api_events():
    async def stream():
        q = asyncio.Queue()
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
