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

## 市場価格の自動取得

市場（myshop）の価格を定期的に記録する機能があります。

### 手動での「今すぐ取得」

1. `http://localhost:8000/myshop` を開く
2. 「今すぐ取得」ボタンをクリック
3. ゲームにログイン済みのブラウザプロファイル（`browser_data`）を使って市場ページを取得し、価格をDBに保存

※ 初回は auto_click.py でゲームにログインしておく必要があります。

### 定期自動取得（:15, :45 に実行）

Web サーバー起動時に環境変数 `MYSHOP_AUTO_FETCH=1` を設定すると、毎時 **1:15, 1:45, 2:15, 2:45** … のタイミングで自動取得します。

```bash
MYSHOP_AUTO_FETCH=1 python run_server.py
```

または `.env` に `MYSHOP_AUTO_FETCH=1` を追加。

実行時刻の分は `MYSHOP_FETCH_MINUTES=15,45`（デフォルト）で変更できます。

### Render で自動取得する場合

Render にはブラウザがないため、**Cookie 方式**を使います。詳しくは [DEPLOY.md](DEPLOY.md) を参照。

1. ローカルで `python export_myshop_cookies.py` を実行   
2. 出力を Render の `MYSHOP_COOKIES`（Secret）に設定
3. `MYSHOP_AUTO_FETCH=1` を設定してデプロイ

---

## 環境変数（.env）

| 変数 | 説明 |
|------|------|
| `BACKEND_URL` | Web サーバー URL（例: https://xxx.onrender.com） |
| `WAIT_PRESET` | 待機時間: `fast` / `normal` / `slow` |
| `BACKEND_OPTIONAL` | `1` で Web サーバー未接続時も探索のみ続行 |
| `CONSECUTIVE_ERROR_THRESHOLD` | 連続エラー警告の閾値（デフォルト: 5） |
| `LUCKY_CHANCE_MAX_WAIT_SEC` | ラッキーチャンス再開待ちの最大秒数（デフォルト: 1800） |
| `MYSHOP_AUTO_FETCH` | `1` で市場価格を定期自動取得（:15, :45 に実行） |
| `MYSHOP_FETCH_MINUTES` | 実行時刻の分（カンマ区切り、デフォルト: `15,45`） |
| `MYSHOP_COOKIES` | Render 用: ログイン Cookie（`export_myshop_cookies.py` の出力を Base64 で設定） |

---

## デプロイ

Web 通知サーバーを Render にデプロイする場合は [DEPLOY.md](DEPLOY.md) を参照。
