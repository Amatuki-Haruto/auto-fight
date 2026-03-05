#!/usr/bin/env python3
"""
あるけみすと 自動探索 - 設定
"""
import os
from pathlib import Path

# Web通知サーバー
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

# URL
HOME_URL = "https://games-alchemist.com/home/"
MONSTER_URL = "https://games-alchemist.com/monster/"

# パス
USER_DATA_DIR = Path(__file__).parent / "browser_data"

# ブラウザ（環境変数BROWSER_PATHで上書き可）
BRAVE_PATH = os.environ.get(
    "BROWSER_PATH",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
)

# 待機時間（秒）- ゲームの20秒周期に合わせつつバレない程度のばらつき
WAIT_START = (0.8, 1.5)
WAIT_AFTER_HOME_SCROLL = (0.3, 0.8)
WAIT_AFTER_MONSTER_SCROLL = (0.3, 0.8)
WAIT_AFTER_RETURN = (17.5, 21.5)  # 20秒前後に（19.5〜25だと30秒超える）
WAIT_HOVER_BEFORE_CLICK = (0.05, 0.2)

# タイムアウト
TIMEOUT_MS = 30000
AUTO_START_SECONDS = 5
HTTP_TIMEOUT = 5.0

# セレクタ（複数フォールバック対応）
SELECTOR_EXPLORE = [
    'form[action*="monster"] input[type="submit"][value="探索する"]',
    'input[type="submit"][value="探索する"]',
]
SELECTOR_CHALLENGE = [
    'input[type="submit"][value="挑戦する"]',
]
SELECTOR_RETURN = [
    'form[action*="home"] input[type="submit"][value="街に戻る"]',
    'input[type="submit"][value="街に戻る"]',
]

# 解像度オプション
VIEWPORT_OPTIONS = [
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 720},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
]

# User-Agent
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# オプション
HEADLESS = os.environ.get("HEADLESS", "").lower() in ("1", "true", "yes")
MAX_LOOPS = int(os.environ.get("MAX_LOOPS", 0))  # 0=無制限
VERBOSE = os.environ.get("VERBOSE", "").lower() in ("1", "true", "yes")
