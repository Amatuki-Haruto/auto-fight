# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- config.py: 設定の一元管理
- 複数セレクタのフォールバック対応
- httpx クライアント再利用
- クリック位置のボタン内クランプ
- ループ数のファイル永続化 (.loop_count)
- 連続エラー検知・警告
- MAX_LOOPS, HEADLESS, VERBOSE 環境変数
- static/index.html: HTMLテンプレート分離
- ダブルクリック防止 (600ms)
- オフライン検知
- prefers-color-scheme 対応
- ログ上限 (MAX_LOG=50)
- ヘルスチェックに SSE 接続数追加
- tests/: pytest テスト追加
- .github/workflows/ci.yml: GitHub Actions CI
- .pre-commit-config.yaml: ruff, hooks
- docker-compose.yml, Dockerfile
- .env.example

### Changed
- requirements.txt: バージョン固定
- app.py: 型ヒント追加、HTML をファイル読み込みに変更

### Fixed
- 探索ループのインデント修正（連続ループが動作するように）
