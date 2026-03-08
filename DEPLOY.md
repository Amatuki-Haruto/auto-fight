# Render へのデプロイ

## 基本デプロイ

`render.yaml` に従い、Web サービスとしてデプロイできます。

## 市場価格の自動取得（Render 上で動かす）

Render では Playwright/ブラウザが使えないため、**Cookie 方式**で市場ページを取得します。

### 手順

#### 1. ローカルで Cookie をエクスポート

1. `auto_click.py` でゲームにログインする
2. 別ターミナルで以下を実行:
   ```bash
   python export_myshop_cookies.py
   ```
3. 出力された Base64 文字列をコピーする

#### 2. Render の環境変数を設定

Render ダッシュボード → 該当サービス → Environment:

| キー | 値 | 種別 |
|-----|-----|------|
| `MYSHOP_COOKIES` | （エクスポートした文字列） | **Secret** |
| `MYSHOP_AUTO_FETCH` | `1` | 通常 |
| `MYSHOP_FETCH_MINUTES` | `15,45` | 通常（任意・デフォルト） |

#### 3. 再デプロイ

環境変数を保存すると再デプロイが走ります。起動後、毎時 :15 と :45 に自動取得が実行されます。

### 注意点

- **Cookie の有効期限**: セッションが切れたら、再度 `export_myshop_cookies.py` を実行し、`MYSHOP_COOKIES` を更新してください
- **DB の永続化**: Render 無料プランでは再起動ごとに `myshop_prices.db` が消えます。永続化するには [Render Disk](https://render.com/docs/disks) の追加や、外部 DB 連携の検討が必要です
- **無料プランのスリープ**: Web サービスがスリープするとスケジューラも停止します。定期実行を維持するには有料プランや外部 cron サービス（例: cron-job.org）で `/health` を叩いてウォームアップする方法があります
