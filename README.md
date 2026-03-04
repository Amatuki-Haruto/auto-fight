# あるけみすと - 自動ダンジョン探索

[あるけみすと](https://games-alchemist.com/home/) で、ダンジョン探索と街への戻りを自動で繰り返すスクリプトです。

## 動作

1. **ホーム** (`/home/`) で「ダンジョンの方の探索する」をクリック
2. **モンスター画面** (`/monster/`) で「街に戻る」をクリック
3. 上記を繰り返し実行

## セットアップ

### 1. Python のインストール

Python 3.8 以上が必要です。

### 2. 依存関係のインストール

```bash
pip install -r requirements-local.txt
playwright install chromium
```

### 3. 実行

```bash
python3 auto_click.py
```

## 初回起動時

1. このページを開いた状態で、ターミナルで `python3 auto_click.py` を実行
2. ブラウザが開き、ゲームのホームページが表示されます
3. **ログインするまで待機**します（自動操作は一切しません）
4. ログイン後、このページの **「自動探索開始」** ボタンを押すとループが開始されます
5. セッションは `browser_data` フォルダに保存され、次回以降はログイン不要です

## 終了方法

ターミナルで **Ctrl+C** を押すと終了します。

## Web通知サーバー（Render デプロイ）

ラッキーチャンスをWeb通知で受け取れます。

### 1. ローカルでWebサーバーを起動（開発時）

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

ブラウザで http://localhost:8000 を開き、通知を許可してください。このタブを開いたまま `auto_click.py` を実行します。

### 2. Render にデプロイ

1. [Render](https://render.com) で新規 Web サービスを作成
2. リポジトリを接続
3. **Start Command** を `python run_server.py` に設定（または `render.yaml` を使用）
4. デプロイ後、表示されるURL（例: `https://xxx.onrender.com`）を控える
5. ローカルで `auto_click.py` 実行時に環境変数を設定：
   ```bash
   BACKEND_URL=https://あなたのサービス.onrender.com python3 auto_click.py
   ```

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

## 注意事項

- 利用規約を確認し、許可されている範囲でご利用ください
- 過度な連続リクエストはサーバーに負荷をかけるため、`CLICK_INTERVAL` を短くしすぎないことを推奨します
- ボタンの見つかり方やテキストがサイト更新で変わった場合は、スクリプト内のセレクタを調整してください
