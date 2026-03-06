# Fly.io へのデプロイ手順

Google Cloud 不要。無料枠あり。

## 前提

- [Fly.io](https://fly.io) アカウント（メールで無料登録）
- [flyctl](https://fly.io/docs/hands-on/install-flyctl/) のインストール

## 1. ログイン

```bash
fly auth login
```

## 2. デプロイ

```bash
# 初回: アプリ作成＆デプロイ（リージョンは nrt=東京 を推奨）
fly launch --no-deploy

# fly.toml の app 名が重複している場合は変更してから:
fly launch --name arukemisuto-xxxx --region nrt

# デプロイ実行
fly deploy
```

## 3. URL を確認

```bash
fly open
# または fly status で URL 表示
```

例: `https://arukemisuto-autoclick.fly.dev/`

## 4. auto_click.py の BACKEND_URL を設定

デプロイ後の URL を `config.py` の環境変数または `.env` で指定:

```bash
BACKEND_URL=https://arukemisuto-autoclick.fly.dev
```

ローカルで自動探索を実行する際、`BACKEND_URL` を Fly.io の URL に設定すると、Web 通知と連携できます。
