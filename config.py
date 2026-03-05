#!/usr/bin/env python3
"""
あるけみすと 自動探索 - 設定
"""
import os
from pathlib import Path

# .env を読み込む（python-dotenv があれば）
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# Web通知サーバー
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

# URL
HOME_URL = "https://games-alchemist.com/home/"
MONSTER_URL = "https://games-alchemist.com/monster/"

# クリック成功判定: 探索/挑戦後に期待するURLに含まれる文字（複数候補）
URL_AFTER_EXPLORE = ["monster", "arena", "battle", "tower"]

# パス
USER_DATA_DIR = Path(__file__).parent / "browser_data"
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
LOG_DIR = Path(__file__).parent / "logs"

# ブラウザ（環境変数BROWSER_PATHで上書き可）
BRAVE_PATH = os.environ.get(
    "BROWSER_PATH",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
)

# 待機時間（秒）- プリセット: fast, normal, slow
_WAIT_PRESET = {
    "fast": {"start": (0.1, 0.3), "home_scroll": (0.1, 0.3), "monster_scroll": (0.1, 0.3), "return": (14.0, 17.0)},
    "normal": {"start": (0.2, 0.5), "home_scroll": (0.15, 0.4), "monster_scroll": (0.15, 0.4), "return": (16.0, 19.0)},
    "slow": {"start": (0.3, 0.8), "home_scroll": (0.2, 0.5), "monster_scroll": (0.2, 0.5), "return": (18.0, 21.0)},
}
_WAIT_PRESET_NAME = os.environ.get("WAIT_PRESET", "normal")
_PRESET = _WAIT_PRESET.get(_WAIT_PRESET_NAME, _WAIT_PRESET["normal"])

WAIT_START = _PRESET["start"]
WAIT_AFTER_HOME_SCROLL = _PRESET["home_scroll"]
WAIT_AFTER_MONSTER_SCROLL = _PRESET["monster_scroll"]
WAIT_AFTER_RETURN = _PRESET["return"]
WAIT_HOVER_BEFORE_CLICK = (0.02, 0.08)

# タイムアウト
TIMEOUT_MS = int(os.environ.get("TIMEOUT_MS", 30000))
BUTTON_TIMEOUT_MS = int(os.environ.get("BUTTON_TIMEOUT_MS", 2000))
AUTO_START_SECONDS = int(os.environ.get("AUTO_START_SECONDS", 5))
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", 5.0))
CLICK_RETRY_COUNT = int(os.environ.get("CLICK_RETRY_COUNT", 10))
LUCKY_CHANCE_WAIT_SEC = int(os.environ.get("LUCKY_CHANCE_WAIT_SEC", 20))

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
SELECTOR_CONFIRM = [
    'input[type="submit"][value="確認"]',
    'input[type="submit"][value="OK"]',
    'button:has-text("確認")',
    'button:has-text("OK")',
]

# 解像度オプション
VIEWPORT_OPTIONS = [
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 720},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
]
WINDOW_POSITION = (int(os.environ.get("WINDOW_X", 0)), int(os.environ.get("WINDOW_Y", 0)))

# User-Agent
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# オプション
HEADLESS = os.environ.get("HEADLESS", "").lower() in ("1", "true", "yes")
MAX_LOOPS = int(os.environ.get("MAX_LOOPS", 0))  # 0=無制限
VERBOSE = os.environ.get("VERBOSE", "").lower() in ("1", "true", "yes")
CHALLENGE_ARENA = os.environ.get("CHALLENGE_ARENA", "1").lower() in ("1", "true", "yes")
SAVE_SCREENSHOT_ON_ERROR = os.environ.get("SAVE_SCREENSHOT_ON_ERROR", "1").lower() in ("1", "true", "yes")
AUTO_RESTART = os.environ.get("AUTO_RESTART", "0").lower() in ("1", "true", "yes")

# 強制停止トリガー（画面上に表示されたら停止）
FORCE_STOP_PATTERNS = [
    "あなたはLv100になりました",
    "転生してください",
]
