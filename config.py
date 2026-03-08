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


def _get_int(key: str, default: int) -> int:
    """環境変数を int で安全に取得（不正値は default にフォールバック）"""
    try:
        return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


def _get_float(key: str, default: float) -> float:
    """環境変数を float で安全に取得（不正値は default にフォールバック）"""
    try:
        return float(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


def _get_bool(key: str, default: bool = False) -> bool:
    """環境変数を bool で取得（1/true/yes で True）"""
    val = os.environ.get(key, "1" if default else "0")
    return str(val).lower() in ("1", "true", "yes")


# -----------------------------------------------------------------------------
# 公開定数（__all__ で明示）
# -----------------------------------------------------------------------------

# Web通知サーバー
BACKEND_URL: str = os.environ.get("BACKEND_URL", "http://localhost:8000")

# URL
HOME_URL: str = "https://games-alchemist.com/home/"

# クリック成功判定: 探索/挑戦後に期待するURLに含まれる文字（複数候補）
URL_AFTER_EXPLORE: list[str] = ["monster", "arena", "battle", "tower"]

# パス
USER_DATA_DIR: Path = Path(__file__).parent / "browser_data"

# ブラウザ（環境変数BROWSER_PATHで上書き可）
BRAVE_PATH: str = os.environ.get(
    "BROWSER_PATH",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
)

# 待機時間（秒）- プリセット: fast, normal, slow（1周あたり約20〜23秒を想定）
_WAIT_PRESET: dict[str, dict[str, tuple[float, float]]] = {
    "fast": {"start": (0.1, 0.3), "home_scroll": (0.1, 0.3), "monster_scroll": (0.1, 0.3), "return": (2.0, 5.0)},
    "normal": {"start": (0.15, 0.4), "home_scroll": (0.1, 0.3), "monster_scroll": (0.1, 0.3), "return": (2.5, 5.5)},
    "slow": {"start": (0.2, 0.5), "home_scroll": (0.15, 0.4), "monster_scroll": (0.15, 0.4), "return": (3.0, 6.0)},
}
_PRESET = _WAIT_PRESET.get(os.environ.get("WAIT_PRESET", "normal"), _WAIT_PRESET["normal"])

WAIT_START: tuple[float, float] = _PRESET["start"]
WAIT_AFTER_HOME_SCROLL: tuple[float, float] = _PRESET["home_scroll"]
WAIT_AFTER_MONSTER_SCROLL: tuple[float, float] = _PRESET["monster_scroll"]
WAIT_AFTER_RETURN: tuple[float, float] = _PRESET["return"]
WAIT_HOVER_BEFORE_CLICK: tuple[float, float] = (0.02, 0.08)

# クリック・読み込み後の待機（秒）
WAIT_AFTER_CLICK: float = max(0.1, _get_float("WAIT_AFTER_CLICK", 2.0))
WAIT_AFTER_LOAD: tuple[float, float] = (0.4, 0.8)  # (min, max) ページ読み込み後
WAIT_AFTER_REFRESH: tuple[float, float] = (1.0, 2.0)  # 更新ボタンクリック後
WAIT_AFTER_CONFIRM_RANDOM: tuple[float, float] = (0.2, 0.5)  # 確認クリック後のランダム追加（4%の確率）
WAIT_CLICK_RETRY: float = max(0.1, _get_float("WAIT_CLICK_RETRY", 2.0))  # クリックリトライ間隔

# タイムアウト
TIMEOUT_MS: int = max(1000, _get_int("TIMEOUT_MS", 30000))
BUTTON_TIMEOUT_MS: int = max(500, _get_int("BUTTON_TIMEOUT_MS", 2000))
AUTO_START_SECONDS: int = max(0, _get_int("AUTO_START_SECONDS", 5))
HTTP_TIMEOUT: float = max(1.0, _get_float("HTTP_TIMEOUT", 5.0))
CLICK_RETRY_COUNT: int = max(1, _get_int("CLICK_RETRY_COUNT", 10))
LUCKY_CHANCE_WAIT_SEC: int = max(1, _get_int("LUCKY_CHANCE_WAIT_SEC", 20))

# セレクタ（複数フォールバック対応）
SELECTOR_EXPLORE: list[str] = [
    'form[action*="monster"] input[type="submit"][value="探索する"]',
    'input[type="submit"][value="探索する"]',
]
SELECTOR_CHALLENGE: list[str] = [
    'input[type="submit"][value="挑戦する"]',
]
SELECTOR_RETURN: list[str] = [
    'form[action*="home"] input[type="submit"][value="街に戻る"]',
    'input[type="submit"][value="街に戻る"]',
]
SELECTOR_CONFIRM: list[str] = [
    'input[type="submit"][value="確認"]',
    'input[type="submit"][value="OK"]',
    'button:has-text("確認")',
    'button:has-text("OK")',
]
# 停止後の再開時に押す「更新」ボタン（左上）
SELECTOR_REFRESH: list[str] = [
    'a:has-text("更新")',
    'button:has-text("更新")',
    'input[type="submit"][value="更新"]',
    '[href*="home"]:has-text("更新")',
]

# 解像度オプション
VIEWPORT_OPTIONS: list[dict[str, int]] = [
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 720},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
]
WINDOW_POSITION: tuple[int, int] = (_get_int("WINDOW_X", 0), _get_int("WINDOW_Y", 0))

# User-Agent
USER_AGENT: str = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# オプション
HEADLESS: bool = _get_bool("HEADLESS", False)
MAX_LOOPS: int = max(0, _get_int("MAX_LOOPS", 0))  # 0=無制限
VERBOSE: bool = _get_bool("VERBOSE", False)
CHALLENGE_ARENA: bool = _get_bool("CHALLENGE_ARENA", True)

# 強制停止トリガー（画面上に表示されたら停止）
FORCE_STOP_PATTERNS: list[str] = [
    "あなたはLv100になりました",
    "転生してください",
]

# 人間らしいクリック用（auto_click.py）
HUMAN_CLICK_PRE_WAIT: tuple[float, float] = (0.08, 0.2)  # クリック前の初期待機（秒）
HUMAN_CLICK_OFFSET_SIGMA: float = 0.15  # クリック位置オフセットのσ（幅/高さの比率）
HUMAN_CLICK_STEPS_BASE: int = 80  # マウス移動ステップ計算の基準距離（px）
HUMAN_CLICK_JITTER_PROB: float = 0.25  # 軌道にジッターを加える確率
HUMAN_CLICK_OVERSHOOT_PROB: float = 0.1  # オーバーシュートする確率
HUMAN_CLICK_CONFIRM_RANDOM_PROB: float = 0.04  # 確認クリック後のランダム待機確率

# エラー・リトライ
CONSECUTIVE_ERROR_THRESHOLD: int = max(1, _get_int("CONSECUTIVE_ERROR_THRESHOLD", 5))
LUCKY_CHANCE_MAX_WAIT_SEC: int = max(60, _get_int("LUCKY_CHANCE_MAX_WAIT_SEC", 30 * 60))  # ラッキーチャンス最大待機（秒）
SAFE_GOTO_HOME_RETRIES: int = max(1, _get_int("SAFE_GOTO_HOME_RETRIES", 3))

# Webサーバー未接続時も探索のみ続行するか
BACKEND_OPTIONAL: bool = _get_bool("BACKEND_OPTIONAL", True)

# CORS（カンマ区切り、* で全許可）
_cors_raw: str = os.environ.get("CORS_ORIGINS", "*")
CORS_ORIGINS: list[str] = ["*"] if _cors_raw.strip() == "*" else [o.strip() for o in _cors_raw.split(",") if o.strip()]

# -----------------------------------------------------------------------------
# 公開 API
# -----------------------------------------------------------------------------
__all__ = [
    "AUTO_START_SECONDS",
    "CORS_ORIGINS",
    "BACKEND_OPTIONAL",
    "BACKEND_URL",
    "BRAVE_PATH",
    "BUTTON_TIMEOUT_MS",
    "CHALLENGE_ARENA",
    "CLICK_RETRY_COUNT",
    "CONSECUTIVE_ERROR_THRESHOLD",
    "FORCE_STOP_PATTERNS",
    "HEADLESS",
    "HOME_URL",
    "HTTP_TIMEOUT",
    "HUMAN_CLICK_CONFIRM_RANDOM_PROB",
    "HUMAN_CLICK_JITTER_PROB",
    "HUMAN_CLICK_OFFSET_SIGMA",
    "HUMAN_CLICK_OVERSHOOT_PROB",
    "HUMAN_CLICK_PRE_WAIT",
    "HUMAN_CLICK_STEPS_BASE",
    "LUCKY_CHANCE_MAX_WAIT_SEC",
    "LUCKY_CHANCE_WAIT_SEC",
    "MAX_LOOPS",
    "SAFE_GOTO_HOME_RETRIES",
    "SELECTOR_CHALLENGE",
    "SELECTOR_CONFIRM",
    "SELECTOR_EXPLORE",
    "SELECTOR_REFRESH",
    "SELECTOR_RETURN",
    "TIMEOUT_MS",
    "URL_AFTER_EXPLORE",
    "USER_AGENT",
    "USER_DATA_DIR",
    "VERBOSE",
    "VIEWPORT_OPTIONS",
    "WAIT_AFTER_CLICK",
    "WAIT_AFTER_CONFIRM_RANDOM",
    "WAIT_AFTER_HOME_SCROLL",
    "WAIT_AFTER_LOAD",
    "WAIT_AFTER_MONSTER_SCROLL",
    "WAIT_AFTER_REFRESH",
    "WAIT_AFTER_RETURN",
    "WAIT_CLICK_RETRY",
    "WAIT_HOVER_BEFORE_CLICK",
    "WAIT_START",
    "WINDOW_POSITION",
]
