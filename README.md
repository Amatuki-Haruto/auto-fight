# あるけみすと - 自動ダンジョン探索

[あるけみすと](https://games-alchemist.com/home/) で、ダンジョン探索と街への戻りを自動で繰り返すスクリプトです。

## 動作

1. **ホーム** (`/home/`) で「ダンジョンの方の探索する」をクリック
2. **モンスター画面** (`/monster/`) で「街に戻る」をクリック
3. 上記を繰り返し実行

---

## 始め方（どこで・何を動かすか）

**すべて同じフォルダ**（このリポジトリのルート）で実行します。

```
自動ボタンクリック/
├── app.py          ← Webサーバー
├── auto_click.py   ← 自動クリック（ゲーム操作）
├── ...
```

### パターンA: ボタン操作を使う場合（推奨）

| 順番 | どこ | 何をする |
|------|------|----------|
| 1 | **ターミナル1**（フォルダ: `自動ボタンクリック`） | `uvicorn app:app --port 8000` を実行 → **止めない** |
| 2 | **ブラウザ**（Chrome・Safari等） | http://localhost:8000 を開く |
| 3 | **ターミナル2**（同じフォルダ: `自動ボタンクリック`） | `python3 auto_click.py` を実行 |
| 4 | **Brave**（自動で開く） | ゲームにログイン |
| 5 | **ブラウザのタブ**（localhost:8000） | 「自動探索開始」をクリック |

- ターミナル1と2は**どちらも** `cd /Users/masato/Desktop/Workspace/自動ボタンクリック` してから実行
- ターミナル1の uvicorn は**起動したまま**にしておく

### パターンB: ボタンなしで使う場合

1. ターミナルで `python3 auto_click.py` を実行
2. ログイン後、**5秒待つ**と自動で開始

---

## セットアップ（初回だけ）

### 1. Python のインストール

Python 3.8 以上が必要です。

### 2. 依存関係のインストール

```bash
cd /Users/masato/Desktop/Workspace/自動ボタンクリック   # またはあなたのパス
pip install -r requirements-local.txt
playwright install chromium
```

Webボタンを使う場合は追加で:

```bash
pip install -r requirements.txt
```

## 初回起動時

1. 上記「始め方」の手順で実行
2. ブラウザが開き、ゲームのホームページが表示されます
3. **ログインするまで待機**します（自動操作は一切しません）
4. ログイン後、**「自動探索開始」** を押すか、5秒待つとループが開始されます
5. セッションは `browser_data` フォルダに保存され、次回以降はログイン不要です

## 終了方法

ターミナルで **Ctrl+C** を押すと終了します。

## Web通知サーバー（Render デプロイ）

ラッキーチャンスをWeb通知で受け取れます。

### ローカルでWebサーバーを起動（ボタン操作用）

```bash
cd /Users/masato/Desktop/Workspace/自動ボタンクリック
uvicorn app:app --port 8000
```

別のターミナルで `python3 auto_click.py` を実行し、ブラウザで http://localhost:8000 を開いてください。

### 2. Render にデプロイ

1. [Render](https://render.com) で新規 Web サービスを作成
2. GitHubリポジトリ `https://github.com/Amatuki-Haruto/auto-fight.git` を接続
3. **Start Command** を `python run_server.py` に設定（または `render.yaml` を使用）
4. デプロイ後、表示されるURL（例: `https://xxx.onrender.com`）を控える
5. ローカルで `auto_click.py` 実行時に環境変数を設定：
   ```bash
   BACKEND_URL=https://あなたのサービス.onrender.com python3 auto_click.py
   ```
   （例: `BACKEND_URL=https://arukemisuto-autoclick.onrender.com python3 auto_click.py`）

### 3. ラッキーチャンス

検知すると自動操作を一時停止し、Web画面に通知が届きます。  
**「自動探索開始」** ボタンを押すと、20秒後に探索から再開します。

### 4. 自動探索終了

**「自動探索終了」** ボタンを押すと探索を停止します。ブラウザ（あるけみすとのタブ）は閉じず、再度「自動探索開始」で再開できます。

## カスタマイズ

`auto_click.py` の先頭で以下を変更できます：

- **BRAVE_PATH**: Brave の実行ファイルパス
- **WAIT_START**: ループ開始時の待機（1.499〜1.999秒）
- **WAIT_AFTER_HOME_SCROLL**: スクロール後→探索する前（0.5〜0.999秒）
- **WAIT_AFTER_MONSTER_SCROLL**: 下までスクロール後→街に戻る前（0.499〜1.499秒）
- **WAIT_AFTER_RETURN**: 街に戻る後→次ループ前（20.499〜20.999秒）

## 接続できないとき

- **「サーバーに接続できません」と出る**
  - ターミナル1で `uvicorn app:app --port 8000` を**先に**起動していますか？
  - 同じPCで実行していますか？（auto_click.py は localhost:8000 に接続します）
- **接続確認**: ブラウザで http://localhost:8000 を開いて画面が表示されればOK。表示されなければ uvicorn が動いていません。

## 注意事項

- 利用規約を確認し、許可されている範囲でご利用ください
- 過度な連続リクエストはサーバーに負荷をかけるため、`CLICK_INTERVAL` を短くしすぎないことを推奨します
- ボタンの見つかり方やテキストがサイト更新で変わった場合は、スクリプト内のセレクタを調整してください
