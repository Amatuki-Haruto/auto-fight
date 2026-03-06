#!/usr/bin/env python3
"""
Render 等デプロイ用: Web サーバー起動エントリーポイント
"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
