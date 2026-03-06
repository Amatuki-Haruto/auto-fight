# デプロイ手順（Render・クレジットカード不要）

1. [render.com](https://render.com) に GitHub でログイン
2. **New** → **Web Service**
3. リポジトリを選択
4. **Create Web Service**（`render.yaml` で自動設定）

URL 発行後、`.env` に `BACKEND_URL=https://xxxx.onrender.com` を設定。
