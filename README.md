# あるけみすと - 自動ダンジョン探索

ゲーム「あるけみすと」のダンジョン探索を自動で周回するスクリプトです。

## 自動周回の起動方法

### 1. 依存関係のインストール

```bash
pip install -r requirements-local.txt
playwright install chromium
```

### 2. Web 通知サーバーを起動（任意）

別ターミナルで実行。Web 画面から「自動探索開始」「停止」を操作できます。

```bash
python run_server.py
# → http://localhost:8000 でアクセス
```

### 3. 自動周回を起動

```bash
python auto_click.py
```

または、`AUTO_RESTART=1` でクラッシュ時に自動再起動：

```bash
python run_auto_click.py
```

### 4. ゲームでログイン

1. 起動後、Brave ブラウザが開きます
2. [games-alchemist.com](https://games-alchemist.com) でログイン
3. Web 画面（http://localhost:8000）で「自動探索開始」を押す  
   または、初回は 5 秒後に自動開始

### 5. 終了

- **Ctrl+C** でループ完了後に停止
- Web 画面の「停止」で、この周回終了後に停止

---

## オプション

| オプション | 説明 |
|-----------|------|
| `--headless` | ヘッドレスモード |
| `--max-loops N` | 最大 N 周で停止（0=無制限） |
| `-v` / `--verbose` | 詳細ログ |

例: `python auto_click.py --max-loops 100 -v`

---

## 環境変数（.env）

| 変数 | 説明 |
|------|------|
| `BACKEND_URL` | Web サーバー URL（例: https://xxx.onrender.com） |
| `WAIT_PRESET` | 待機時間: `fast` / `normal` / `slow` |

---

## デプロイ

Web 通知サーバーを Render にデプロイする場合は [DEPLOY.md](DEPLOY.md) を参照。
