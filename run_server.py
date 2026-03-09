#!/usr/bin/env python3
"""
Render 等デプロイ用: Web サーバー起動エントリーポイント
本番: workers=1 で単一プロセス。開発: RELOAD=1 でホットリロード。
"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    reload = os.environ.get("RELOAD", "0").lower() in ("1", "true", "yes")
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        workers=1,
        reload=reload,
    )
