#!/usr/bin/env python3
"""
あるけみすと - ダンジョン探索の自動クリックスクリプト

・ホームで「探索する」→ モンスター画面で「街に戻る」を繰り返し
・Web通知サーバー(app.py)と連携: ラッキーチャンスを通知
・Lv100転生メッセージ検知で強制停止
・自動探索終了後もブラウザは開いたまま。再度「自動探索開始」で再開可能

ステートマシン:
  INIT → WAITING_LOGIN → IDLE ⇄ EXPLORING → IN_BATTLE → RETURNING → (EXPLORING|LUCKY_CHANCE|STOPPED)
"""

import argparse
import asyncio
import json
import logging
import re
import random
import signal
import sys
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Literal, Optional

import httpx
from playwright.async_api import Page, async_playwright, TimeoutError as PlaywrightTimeout
from playwright.async_api import Locator

import config  # type: ignore

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
DEFAULT_VIEWPORT = {"width": 1280, "height": 720}
POLL_INTERVAL_SEC = 2
GOTO_HOME_TIMEOUT_MS = 15000

# ---------------------------------------------------------------------------
# ログ設定
# ---------------------------------------------------------------------------
logger = logging.getLogger("auto_click")


class ColoredStreamHandler(logging.StreamHandler):
    """ANSI色付きログハンドラ"""

    COLORS = {
        "ERROR": "\033[91m",
        "WARNING": "\033[93m",
        "INFO": "\033[0m",
        "SUCCESS": "\033[92m",
    }
    LEVEL_COLORS = {25: "\033[92m"}  # SUCCESS
    RESET = "\033[0m"

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            if self.stream.isatty():
                color = self.COLORS.get(record.levelname) or self.LEVEL_COLORS.get(record.levelno)
                if color:
                    msg = f"{color}{msg}{self.RESET}"
            self.stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


def _setup_logging() -> None:
    """ロガーを初期化"""
    logger.setLevel(logging.DEBUG if config.VERBOSE else logging.INFO)
    if not logger.handlers:
        handler = ColoredStreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)


def _log(msg: str, verbose_only: bool = False, level: str = "info") -> None:
    """互換用ラッパー（verbose_only 時は SUCCESS を INFO で）"""
    if config.VERBOSE or not verbose_only:
        if level == "error":
            logger.error(msg)
        elif level == "warn":
            logger.warning(msg)
        elif level == "success":
            logger.log(25, msg)  # SUCCESS カスタムレベル
        else:
            logger.info(msg)


# カスタムログレベル "SUCCESS"
logging.addLevelName(25, "SUCCESS")

# ---------------------------------------------------------------------------
# ステートマシン
# ---------------------------------------------------------------------------
class State(Enum):
    """探索フローの状態"""
    INIT = auto()
    WAITING_LOGIN = auto()
    IDLE = auto()
    REFRESHING = auto()
    EXPLORING = auto()
    IN_BATTLE = auto()
    RETURNING = auto()
    LUCKY_CHANCE = auto()
    STOPPED = auto()


@dataclass
class ExplorationContext:
    """ステートマシンのコンテキスト"""
    page: Optional[Page] = None
    client: Optional[httpx.AsyncClient] = None
    base: str = ""
    backend_connected: bool = False
    count: int = 0
    consecutive_errors: int = 0
    start_time: float = 0.0
    first_wait: bool = True
    needs_refresh: bool = False
    loop_count_file: Path = field(default_factory=Path)
    lucky_detected: bool = False
    _idle_wait_start: Optional[float] = field(default=None, repr=False)
    _loop_start: float = field(default=0.0, repr=False)


_shutdown_requested = False


def _cubic_bezier(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
    """3次ベジェ曲線（人間の手の軌道に近い）"""
    u = 1 - t
    return u**3 * p0 + 3 * u**2 * t * p1 + 3 * u * t**2 * p2 + t**3 * p3


# ---------------------------------------------------------------------------
# ページ・テキスト
# ---------------------------------------------------------------------------


async def _is_page_valid(page: Page) -> bool:
    """ページが有効か（閉じられていないか）チェック"""
    try:
        _ = page.url
        return True
    except Exception:
        return False


async def _get_page_text(page: Page) -> str:
    """ページテキストを安全に取得"""
    if not await _is_page_valid(page):
        return ""
    try:
        return await page.evaluate("() => document.body.innerText") or ""
    except Exception as e:
        if config.VERBOSE:
            logger.debug("_get_page_text failed: %s", e)
        return ""


def _text_has_force_stop(text: str) -> Optional[str]:
    """テキストにLv100転生等の強制停止トリガーが含まれるか。該当すれば理由を返す"""
    if not text:
        return None
    for pat in config.FORCE_STOP_PATTERNS:
        if pat in text:
            return f"Lv100転生のため停止（{pat}）"
    return None


async def _check_force_stop(page: Page) -> Optional[str]:
    """Lv100転生等の強制停止トリガーをチェック。該当すれば理由を返す"""
    text = await _get_page_text(page)
    return _text_has_force_stop(text)


def _is_champion_text(text: str) -> bool:
    """〇〇階のチャンプです → 天空闘技場行けない"""
    return "チャンプです" in (text or "")


def _extract_level(text: str) -> Optional[int]:
    """ページテキストから現在のレベルを抽出。Lv45, レベル45 等のパターン。"""
    if not text:
        return None
    levels: list[int] = []
    for m in re.finditer(r"(?:Lv\.?|レベル)\s*(\d+)", text, re.IGNORECASE):
        levels.append(int(m.group(1)))
    return max(levels) if levels else None


def _extract_exploration_result(text: str) -> tuple[str, int, list[str]]:
    """勝利メッセージ・経験値・ドロップを抽出。戻り値: (message, exp, drops)"""
    message = ""
    exp = 0
    drops: list[str] = []

    vic_exp = re.search(r"([^\n]+は勝利した[^\n]*?(\d+)\s*の経験値を獲得した[^\n]*?)(?:\n|$)", text)
    if vic_exp:
        message = vic_exp.group(1).strip()
        exp = int(vic_exp.group(2))

    if not message:
        vic_m = re.search(r"([^\n。]+は勝利した)", text)
        exp_m = re.search(r"(\d+)\s*の経験値を獲得した", text)
        if vic_m:
            message = vic_m.group(1) + "。"
        if exp_m:
            exp = int(exp_m.group(1))
            message += f" {exp_m.group(1)}の経験値を獲得した。"

    for m in re.finditer(r"\[([A-Z])\]\s*([^を\n！]+)を手に入れた", text):
        drops.append(f"[{m.group(1)}] {m.group(2).strip()}")

    message = message.strip() or text[:300] if text else ""
    return (message, exp, drops)


def _url_matches_success(url: str, expect: str | list[str]) -> bool:
    if isinstance(expect, str):
        return expect in url
    for pat in expect:
        if pat in url:
            return True
    return False


# ---------------------------------------------------------------------------
# ボタン・クリック
# ---------------------------------------------------------------------------


async def _find_button(page: Page, selectors: list[str], timeout: int | None = None) -> Optional[Locator]:
    """複数セレクタでフォールバック。テキストセレクタも試行"""
    tout = timeout or config.BUTTON_TIMEOUT_MS
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            await btn.wait_for(state="visible", timeout=tout)
            return btn
        except PlaywrightTimeout:
            continue
    return None


async def _click_and_verify(
    page: Page, selectors: list[str], expect_url_contains: str | list[str]
) -> bool:
    """クリック → 待機 → 成功確認。失敗ならリトライ"""
    expect = expect_url_contains
    if expect == "monster":
        expect = config.URL_AFTER_EXPLORE

    for attempt in range(config.CLICK_RETRY_COUNT):
        btn = await _find_button(page, selectors, timeout=3000)
        if not btn:
            _log(f"  → ボタンが見つかりません（試行{attempt+1}/{config.CLICK_RETRY_COUNT}）", level="warn")
            await asyncio.sleep(config.WAIT_CLICK_RETRY)
            continue
        try:
            await human_like_click(page, btn)
        except PlaywrightTimeout:
            _log(f"  → クリック中に要素が消えました（試行{attempt+1}/{config.CLICK_RETRY_COUNT}）", level="warn")
            await asyncio.sleep(config.WAIT_CLICK_RETRY)
            continue
        await asyncio.sleep(config.WAIT_AFTER_CLICK)
        try:
            url = page.url or ""
            if _url_matches_success(url, expect):
                return True
            if isinstance(expect, list) and "games-alchemist.com" in url and "/home/" not in url:
                return True
            await page.wait_for_load_state("domcontentloaded", timeout=3000)
            url = page.url or ""
            if _url_matches_success(url, expect) or (
                isinstance(expect, list) and "games-alchemist.com" in url and "/home/" not in url
            ):
                return True
        except Exception as e:
            if config.VERBOSE:
                _log(f"  → URL確認で例外: {e}", level="warn")
        _log(f"  → クリック未反映（試行{attempt+1}/{config.CLICK_RETRY_COUNT}）、待機後にリトライ", level="warn")
        await asyncio.sleep(config.WAIT_CLICK_RETRY)
    return False


async def human_like_click(page: Page, locator: Locator) -> None:
    """人間らしいマウス動作"""
    hmin, hmax = config.HUMAN_CLICK_PRE_WAIT
    sigma = config.HUMAN_CLICK_OFFSET_SIGMA
    base_dist = config.HUMAN_CLICK_STEPS_BASE
    jitter_prob = config.HUMAN_CLICK_JITTER_PROB
    overshoot_prob = config.HUMAN_CLICK_OVERSHOOT_PROB

    await locator.wait_for(state="attached", timeout=config.TIMEOUT_MS)
    await locator.scroll_into_view_if_needed()
    await asyncio.sleep(random.uniform(hmin, hmax))
    await locator.wait_for(state="visible", timeout=config.TIMEOUT_MS)
    box = await locator.bounding_box()
    if not box:
        await locator.click()
        return

    offset_x = random.gauss(0, box["width"] * sigma)
    offset_y = random.gauss(0, box["height"] * sigma)
    target_x = max(
        box["x"] + 5,
        min(box["x"] + box["width"] - 5, box["x"] + box["width"] / 2 + offset_x),
    )
    target_y = max(
        box["y"] + 5,
        min(box["y"] + box["height"] - 5, box["y"] + box["height"] / 2 + offset_y),
    )

    viewport = page.viewport_size or DEFAULT_VIEWPORT
    start_x = random.uniform(80, viewport["width"] - 80)
    start_y = random.uniform(80, viewport["height"] - 80)

    c1_x = start_x + (target_x - start_x) * random.uniform(0.2, 0.4) + random.uniform(-25, 25)
    c1_y = start_y + (target_y - start_y) * random.uniform(0.2, 0.4) + random.uniform(-15, 15)
    c2_x = start_x + (target_x - start_x) * random.uniform(0.6, 0.8) + random.uniform(-20, 20)
    c2_y = start_y + (target_y - start_y) * random.uniform(0.6, 0.8) + random.uniform(-15, 15)

    dist = ((target_x - start_x) ** 2 + (target_y - start_y) ** 2) ** 0.5
    steps = max(4, min(10, int(dist / base_dist))) + random.randint(-1, 1)

    for i in range(1, steps + 1):
        t_raw = i / steps
        t = t_raw**1.2 * (1 - (1 - t_raw) ** 1.1) + t_raw * 0.2
        x = _cubic_bezier(t, start_x, c1_x, c2_x, target_x)
        y = _cubic_bezier(t, start_y, c1_y, c2_y, target_y)
        if random.random() < jitter_prob:
            x += random.gauss(0, 0.6)
            y += random.gauss(0, 0.6)
        await page.mouse.move(x, y, steps=1)
        await asyncio.sleep(max(0.015, min(0.06, random.gauss(0.03, 0.01))))

    if random.random() < overshoot_prob:
        overshoot_x = target_x + random.uniform(3, 12) * random.choice([-1, 1])
        overshoot_y = target_y + random.uniform(2, 8) * random.choice([-1, 1])
        await page.mouse.move(overshoot_x, overshoot_y, steps=1)
        await asyncio.sleep(random.uniform(0.02, 0.06))
        await page.mouse.move(target_x, target_y, steps=1)

    hmin_hover, hmax_hover = config.WAIT_HOVER_BEFORE_CLICK
    await asyncio.sleep(random.uniform(hmin_hover, hmax_hover))
    await page.mouse.click(target_x, target_y)


async def _human_scroll_down(page: Page, amount: Optional[int] = None) -> None:
    if amount is None:
        amount = random.randint(250, 400)
    chunk = random.randint(100, 200)
    moved = 0
    while moved < amount:
        step = min(chunk, amount - moved)
        await page.evaluate(f"window.scrollBy(0, {step})")
        moved += step
        await asyncio.sleep(random.uniform(0.01, 0.04))
        if random.random() < 0.08:
            await asyncio.sleep(random.uniform(0.05, 0.12))


async def _human_scroll_to_bottom(page: Page) -> None:
    await page.evaluate(
        "window.scrollTo(0, Math.max(document.body.scrollHeight, document.documentElement.scrollHeight))"
    )
    if random.random() < 0.25:
        await asyncio.sleep(random.uniform(0.05, 0.12))
        await page.evaluate("window.scrollBy(0, -20)")
        await asyncio.sleep(random.uniform(0.02, 0.06))
        await page.evaluate("window.scrollBy(0, 25)")


# ---------------------------------------------------------------------------
# ナビゲーション・スクリーンショット
# ---------------------------------------------------------------------------


async def _safe_goto_home(page: Page, max_retries: int | None = None) -> tuple[bool, Optional[Exception]]:
    """ホームへ遷移。戻り値: (成功したか, 最後の例外)"""
    retries = max_retries or config.SAFE_GOTO_HOME_RETRIES
    last_error: Optional[Exception] = None
    for attempt in range(retries):
        try:
            await page.goto(config.HOME_URL, wait_until="domcontentloaded", timeout=GOTO_HOME_TIMEOUT_MS)
            return (True, None)
        except Exception as e:
            last_error = e
            err_msg = str(e).lower()
            if "err_aborted" in err_msg or "aborted" in err_msg or "destroyed" in err_msg:
                _log(f"  → 遷移失敗 (試行{attempt+1}/{retries})、待機してリトライ", level="warn")
                if config.VERBOSE:
                    logger.debug("  → 例外: %s", e)
                await asyncio.sleep(random.uniform(1.0, 2.5))
                continue
            return (False, e)
    return (False, last_error)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


async def _api_post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    json_data: dict,
    max_retries: int = 3,
) -> bool:
    """API POSTを指数バックオフでリトライ"""
    for attempt in range(max_retries):
        try:
            r = await client.post(url, json=json_data, timeout=config.HTTP_TIMEOUT)
            if r.status_code == 200:
                return True
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            if config.VERBOSE and attempt == max_retries - 1:
                logger.debug("API POST failed: %s", e)
        if attempt < max_retries - 1:
            await asyncio.sleep(2**attempt)
    return False


def _is_lucky_chance_text(text: str) -> bool:
    """ラッキーチャンス判定（英語のみ：LUCKY+CHANCE）"""
    t = text.upper()
    return ("LUCKY" in t and "CHANCE" in t) or "LUCKYCHANCE" in t


async def _check_and_wait_lucky_chance(
    page: Page,
    client: httpx.AsyncClient,
    *,
    already_detected: bool = False,
    backend_connected: bool = True,
) -> bool:
    """ラッキーチャンス検知→Web通知→再開待ち。タイムアウト付き"""
    if not already_detected:
        try:
            text = await _get_page_text(page)
            if not _is_lucky_chance_text(text):
                return False
        except Exception as e:
            err_msg = str(e).lower()
            if "destroyed" in err_msg or "navigation" in err_msg or "target closed" in err_msg:
                return False
            raise

    base = config.BACKEND_URL.rstrip("/")

    if backend_connected and client:
        _log("")
        _log("★ ラッキーチャンス！ Web画面の「自動探索開始」を押して再開してください ★", level="success")
        await _api_post_with_retry(client, f"{base}/api/lucky-chance", {})

        waited = 0
        while waited < config.LUCKY_CHANCE_MAX_WAIT_SEC:
            await asyncio.sleep(POLL_INTERVAL_SEC)
            waited += POLL_INTERVAL_SEC
            try:
                r = await client.get(f"{base}/api/check-go", timeout=config.HTTP_TIMEOUT)
                if r.json().get("go"):
                    break
            except Exception as e:
                if config.VERBOSE and waited % 30 < POLL_INTERVAL_SEC:
                    logger.debug("check-go failed: %s", e)
        else:
            _log("  ※ラッキーチャンス待機がタイムアウトしました。自動で続行します。", level="warn")

        wait_sec = config.LUCKY_CHANCE_WAIT_SEC
        _log(f"再開します。{wait_sec}秒後に探索から始めます。")
        await asyncio.sleep(wait_sec)
        await _api_post_with_retry(client, f"{base}/api/exploration-started", {})
    else:
        _log("")
        _log("★ ラッキーチャンス検知（Webサーバー未接続のため自動続行）", level="success")
        await asyncio.sleep(config.LUCKY_CHANCE_WAIT_SEC)
    return True


# ---------------------------------------------------------------------------
# ブラウザ・その他
# ---------------------------------------------------------------------------


def _init_stealth_script() -> str:
    return """
    (function(){
        if (typeof navigator === 'undefined') return;
        try { Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true }); } catch(e){}
        try { delete Object.getPrototypeOf(navigator).webdriver; } catch(e){}
    })();
    """


def _get_browser_executable() -> Optional[str]:
    if Path(config.BRAVE_PATH).exists():
        return config.BRAVE_PATH
    return None


async def _click_refresh_button(page: Page) -> bool:
    """左上の「更新」ボタンをクリック"""
    for sel in config.SELECTOR_REFRESH:
        try:
            btn = page.locator(sel).first
            await btn.wait_for(state="visible", timeout=2000)
            await human_like_click(page, btn)
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
            await asyncio.sleep(random.uniform(0.5, 1.0))
            return True
        except PlaywrightTimeout:
            continue
    return False


async def _try_click_confirm(page: Page) -> bool:
    """確認/OKボタンを探してクリック"""
    for sel in config.SELECTOR_CONFIRM:
        try:
            btn = page.locator(sel).first
            await btn.wait_for(state="visible", timeout=1500)
            await human_like_click(page, btn)
            return True
        except PlaywrightTimeout:
            continue
    return False


# ---------------------------------------------------------------------------
# ステートハンドラ
# ---------------------------------------------------------------------------

async def _handle_init(ctx: ExplorationContext) -> tuple[State, ExplorationContext]:
    """ブラウザ起動・接続確認（page, client は run_loop でセット済み想定）"""
    return (State.WAITING_LOGIN, ctx)


async def _handle_waiting_login(ctx: ExplorationContext) -> tuple[State, ExplorationContext]:
    """ログイン待ち"""
    page = ctx.page
    if not page:
        return (State.STOPPED, ctx)
    if "games-alchemist.com/home" not in (page.url or ""):
        ok, err = await _safe_goto_home(page)
        if not ok:
            _log("  → 初回のホーム遷移に失敗しました", level="warn")
            if err and config.VERBOSE:
                logger.debug("  → 例外: %s", err)
    btn = await _find_button(page, config.SELECTOR_EXPLORE, timeout=3000)
    if btn:
        _log("ログイン確認。Web画面で「自動探索開始」を押すまで待機", level="success")
        await asyncio.sleep(5)
        return (State.IDLE, ctx)
    _log("ログインしてください…")
    await asyncio.sleep(5)
    return (State.WAITING_LOGIN, ctx)


async def _handle_idle(ctx: ExplorationContext) -> tuple[State, ExplorationContext]:
    """開始シグナル待ち"""
    global _shutdown_requested
    if not ctx.client:
        return (State.STOPPED, ctx)
    if _shutdown_requested:
        return (State.STOPPED, ctx)
    if ctx.needs_refresh:
        return (State.REFRESHING, ctx)
    if not ctx.backend_connected:
        if ctx.first_wait:
            await asyncio.sleep(config.AUTO_START_SECONDS)
            _log("  (オフラインモード: 自動開始)")
            ctx.first_wait = False
        _log("自動探索を開始します。", level="success")
        ctx.start_time = time.monotonic()
        return (State.EXPLORING, ctx)
    try:
        r = await ctx.client.get(f"{ctx.base}/api/check-stop", timeout=2.0)
        if r.json().get("stop"):
            await asyncio.sleep(POLL_INTERVAL_SEC)
            return (State.IDLE, ctx)
    except Exception as e:
        if config.VERBOSE:
            logger.debug("check-stop failed: %s", e)
    try:
        r = await ctx.client.get(f"{ctx.base}/api/check-go", timeout=config.HTTP_TIMEOUT)
        if r.json().get("go"):
            _log("自動探索を開始します。", level="success")
            await _api_post_with_retry(ctx.client, f"{ctx.base}/api/exploration-started", {})
            ctx.first_wait = False
            ctx.start_time = time.monotonic()
            return (State.EXPLORING, ctx)
    except Exception as e:
        if config.VERBOSE:
            logger.debug("check-go failed: %s", e)
    if ctx.first_wait:
        # 初回は AUTO_START_SECONDS 経過で自動開始（呼び出し側で経過時間を管理）
        pass
    await asyncio.sleep(POLL_INTERVAL_SEC)
    return (State.IDLE, ctx)


async def _handle_idle_with_timer(ctx: ExplorationContext) -> tuple[State, ExplorationContext]:
    """IDLE のラッパー（初回自動開始用タイマー付き）"""
    if ctx._idle_wait_start is None:
        ctx._idle_wait_start = time.monotonic()
    wait_start = ctx._idle_wait_start
    state, ctx = await _handle_idle(ctx)
    if state == State.IDLE and ctx.first_wait and (time.monotonic() - wait_start) >= config.AUTO_START_SECONDS:
        _log("  (初回のため5秒経過で自動開始)")
        ctx.first_wait = False
        if ctx.backend_connected and ctx.client:
            await _api_post_with_retry(ctx.client, f"{ctx.base}/api/exploration-started", {})
        ctx.start_time = time.monotonic()
        return (State.EXPLORING, ctx)
    return (state, ctx)


async def _handle_refreshing(ctx: ExplorationContext) -> tuple[State, ExplorationContext]:
    """更新ボタンクリック"""
    if not ctx.page:
        return (State.STOPPED, ctx)
    page = ctx.page
    if await _click_refresh_button(page):
        _log("  → 更新ボタンをクリック", level="success")
        await page.wait_for_load_state("domcontentloaded")
        wmin, wmax = config.WAIT_AFTER_REFRESH
        await asyncio.sleep(random.uniform(wmin, wmax))
    else:
        _log("  → 更新ボタンが見つかりません。そのまま続行", level="warn")
    ctx.needs_refresh = False
    return (State.IDLE, ctx)


async def _handle_exploring(ctx: ExplorationContext) -> tuple[State, ExplorationContext]:
    """ホームで探索/挑戦をクリック"""
    global _shutdown_requested
    if not ctx.page or not ctx.client:
        return (State.STOPPED, ctx)
    page, client, base = ctx.page, ctx.client, ctx.base
    if _shutdown_requested:
        return (State.STOPPED, ctx)
    if config.MAX_LOOPS and ctx.count >= config.MAX_LOOPS:
        _log(f"最大ループ数 {config.MAX_LOOPS} に達しました。")
        ctx.needs_refresh = True
        return (State.IDLE, ctx)
    if ctx.count > 0 and ctx.backend_connected:
        try:
            r = await client.get(f"{base}/api/check-stop", timeout=3.0)
            if r.json().get("stop"):
                _log("")
                _log("自動探索を停止しました。ブラウザは開いたままです。", level="success")
                await _api_post_with_retry(client, f"{base}/api/exploration-stopped", {})
                ctx.needs_refresh = True
                return (State.IDLE, ctx)
        except Exception as e:
            if config.VERBOSE:
                logger.debug("check-stop failed: %s", e)
    ctx.count += 1
    ctx._loop_start = time.monotonic()
    try:
        with open(ctx.loop_count_file, "w") as f:
            f.write(str(ctx.count))
    except Exception:
        pass
    if ctx.backend_connected:
        payload: dict = {"loop_count": ctx.count, "stats": {"consecutive_errors": ctx.consecutive_errors}}
        level = _extract_level(page_text)
        if level is not None:
            payload["level"] = level
        await _api_post_with_retry(client, f"{base}/api/exploration-log", payload)
    _log(f"[{ctx.count}] ループ開始 (経過: {ctx._loop_start - ctx.start_time:.0f}秒)")
    wmin, wmax = config.WAIT_START
    await asyncio.sleep(random.uniform(wmin, wmax))
    await _human_scroll_down(page)
    wmin, wmax = config.WAIT_AFTER_HOME_SCROLL
    await asyncio.sleep(random.uniform(wmin, wmax))
    page_text = await _get_page_text(page)
    force_reason = _text_has_force_stop(page_text)
    if force_reason:
        _log("")
        _log(f"★ {force_reason}", level="error")
        if ctx.backend_connected:
            await _api_post_with_retry(client, f"{base}/api/exploration-stopped", {"reason": force_reason})
        ctx.needs_refresh = True
        return (State.IDLE, ctx)
    result = await _do_explore_step(page, page_text)
    if result == "no_explore":
        _log("  → 探索ボタンが見つかりません。ホームへ戻ります。", level="warn")
        if ctx.consecutive_errors + 1 >= config.CONSECUTIVE_ERROR_THRESHOLD:
            _log("  ※連続エラーが多いため停止を検討してください", level="error")
        ok, _ = await _safe_goto_home(page)
        if not ok:
            _log("  → ホームへの遷移に失敗しました", level="warn")
        ctx.consecutive_errors += 1
        return (State.EXPLORING, ctx)
    if result == "click_fail":
        _log("  → クリックが反映されませんでした。ホームへ戻ります。", level="warn")
        ok, _ = await _safe_goto_home(page)
        if not ok:
            _log("  → ホームへの遷移に失敗しました", level="warn")
        ctx.consecutive_errors += 1
        return (State.EXPLORING, ctx)
    ctx.consecutive_errors = 0
    return (State.IN_BATTLE, ctx)


async def _handle_in_battle(ctx: ExplorationContext) -> tuple[State, ExplorationContext]:
    """戦闘画面で結果確認・街に戻る"""
    if not ctx.page or not ctx.client:
        return (State.STOPPED, ctx)
    page, client, base = ctx.page, ctx.client, ctx.base
    await page.wait_for_load_state("domcontentloaded")
    wmin, wmax = config.WAIT_AFTER_LOAD
    await asyncio.sleep(random.uniform(wmin, wmax))
    await _try_click_confirm(page)
    if random.random() < config.HUMAN_CLICK_CONFIRM_RANDOM_PROB:
        rmin, rmax = config.WAIT_AFTER_CONFIRM_RANDOM
        await asyncio.sleep(random.uniform(rmin, rmax))
    await _human_scroll_to_bottom(page)
    wmin, wmax = config.WAIT_AFTER_MONSTER_SCROLL
    await asyncio.sleep(random.uniform(wmin, wmax))
    body_text = await _get_page_text(page)
    try:
        msg, exp_val, new_drops = _extract_exploration_result(body_text)
        level = _extract_level(body_text)
        loop_start = ctx._loop_start or time.monotonic()
        payload: dict = {
            "loop_count": ctx.count,
            "message": msg,
            "exp": exp_val,
            "drops": new_drops,
            "stats": {"loop_time_sec": round(time.monotonic() - loop_start, 1), "consecutive_errors": 0},
        }
        if level is not None:
            payload["level"] = level
        if (msg or new_drops or exp_val > 0 or level is not None) and ctx.backend_connected:
            await _api_post_with_retry(client, f"{base}/api/exploration-log", payload)
    except Exception as e:
        _log(f"  → 探索結果抽出失敗: {e}", level="warn")
    force_reason = _text_has_force_stop(body_text)
    if force_reason:
        _log("")
        _log(f"★ {force_reason}", level="error")
        if ctx.backend_connected:
            await _api_post_with_retry(client, f"{base}/api/exploration-stopped", {"reason": force_reason})
        ctx.needs_refresh = True
        return (State.IDLE, ctx)
    ctx.lucky_detected = bool(body_text and _is_lucky_chance_text(body_text))
    if not await _do_return_step(page):
        _log("  → 街に戻るボタンが見つかりません。ホームへ戻ります。", level="warn")
        ok, _ = await _safe_goto_home(page)
        if not ok:
            _log("  → ホームへの遷移に失敗しました", level="warn")
        return (State.EXPLORING, ctx)
    return (State.RETURNING, ctx)


async def _handle_returning(ctx: ExplorationContext) -> tuple[State, ExplorationContext]:
    """街に戻った後"""
    if not ctx.page or not ctx.client:
        return (State.STOPPED, ctx)
    page, client, base = ctx.page, ctx.client, ctx.base
    await page.wait_for_load_state("domcontentloaded")
    wmin, wmax = config.WAIT_AFTER_LOAD
    await asyncio.sleep(random.uniform(wmin, wmax))
    await _try_click_confirm(page)
    force_reason = await _check_force_stop(page)
    if force_reason:
        _log("")
        _log(f"★ {force_reason}", level="error")
        if ctx.backend_connected:
            await _api_post_with_retry(client, f"{base}/api/exploration-stopped", {"reason": force_reason})
        ctx.needs_refresh = True
        return (State.IDLE, ctx)
    if await _check_and_wait_lucky_chance(
        page, client, already_detected=ctx.lucky_detected, backend_connected=ctx.backend_connected
    ):
        return (State.EXPLORING, ctx)
    wmin, wmax = config.WAIT_AFTER_RETURN
    delay = random.uniform(wmin, wmax)
    if config.VERBOSE:
        _log(f"  → {delay:.3f}秒待機...", verbose_only=True)
    await asyncio.sleep(delay)
    return (State.EXPLORING, ctx)


async def _handle_lucky_chance(ctx: ExplorationContext) -> tuple[State, ExplorationContext]:
    """ラッキーチャンス（通常は _check_and_wait_lucky_chance で処理済み）"""
    return (State.EXPLORING, ctx)


async def _handle_stopped(ctx: ExplorationContext) -> tuple[State, ExplorationContext]:
    return (State.STOPPED, ctx)


async def _handle_idle_dispatch(ctx: ExplorationContext) -> tuple[State, ExplorationContext]:
    """IDLE のラッパー（初回自動開始タイマー付き）"""
    return await _handle_idle_with_timer(ctx)


STATE_HANDLERS: dict[State, Callable] = {
    State.INIT: _handle_init,
    State.WAITING_LOGIN: _handle_waiting_login,
    State.IDLE: _handle_idle_dispatch,
    State.REFRESHING: _handle_refreshing,
    State.EXPLORING: _handle_exploring,
    State.IN_BATTLE: _handle_in_battle,
    State.RETURNING: _handle_returning,
    State.LUCKY_CHANCE: _handle_lucky_chance,
    State.STOPPED: _handle_stopped,
}


# ---------------------------------------------------------------------------
# 探索ループの分割関数（ステートハンドラから使用）
# ---------------------------------------------------------------------------




async def _do_explore_step(
    page: Page,
    page_text: str,
) -> Literal["ok", "no_explore", "click_fail"]:
    """探索 or 挑戦を実行。戻り値: ok / no_explore / click_fail"""
    if not config.CHALLENGE_ARENA:
        challenge_btn = None
    elif _is_champion_text(page_text):
        _log("  → チャンプのため天空闘技場はスキップ")
        challenge_btn = None
    else:
        challenge_btn = await _find_button(page, config.SELECTOR_CHALLENGE)

    clicked = False
    if challenge_btn:
        _log("  → 挑戦する（天空闘技場）をクリック")
        clicked = await _click_and_verify(page, config.SELECTOR_CHALLENGE, "monster")

    if not clicked:
        explore_btn = await _find_button(page, config.SELECTOR_EXPLORE)
        if explore_btn:
            _log("  → 探索するをクリック")
            clicked = await _click_and_verify(page, config.SELECTOR_EXPLORE, "monster")
        else:
            return "no_explore"

    if not clicked:
        return "click_fail"
    return "ok"


async def _do_return_step(page: Page) -> bool:
    """街に戻るを実行。成功したか"""
    return_btn = await _find_button(page, config.SELECTOR_RETURN, timeout=3000)
    if not return_btn:
        return False
    return await _click_and_verify(page, config.SELECTOR_RETURN, "home")


# ---------------------------------------------------------------------------
# メインループ
# ---------------------------------------------------------------------------


async def run_loop(
    http_client: httpx.AsyncClient | None = None,
    browser_context=None,
) -> None:
    """
    メインループ。ステートマシン駆動。テスト用に http_client を渡せる。
    """
    global _shutdown_requested

    limits = httpx.Limits(max_connections=4, keepalive_expiry=30.0)
    own_client = http_client is None
    client = http_client or httpx.AsyncClient(limits=limits, timeout=config.HTTP_TIMEOUT)

    async def _run() -> None:
        global _shutdown_requested
        base = config.BACKEND_URL.rstrip("/")
        backend_connected = True
        try:
            r = await client.get(f"{base}/health", timeout=2.0)
            if r.status_code == 200:
                backend_connected = True
        except (httpx.ConnectError, httpx.TimeoutException):
            backend_connected = False
            if config.BACKEND_OPTIONAL:
                _log("※Webサーバーに接続できません。探索のみ継続します（通知・停止ボタンは利用できません）", level="warn")
            else:
                _log("※Webサーバーに接続できません。uvicorn app:app --port 8000 で起動するか、BACKEND_OPTIONAL=1 で探索のみ実行", level="warn")
                return

        if config.HEADLESS:
            _log("※ヘッドレスモード: ラッキーチャンス検知時は画面確認できません", level="warn")

        exec_path = _get_browser_executable()
        viewport = random.choice(config.VIEWPORT_OPTIONS)
        pos = config.WINDOW_POSITION
        launch_opts: dict = {
            "user_data_dir": str(config.USER_DATA_DIR),
            "headless": config.HEADLESS,
            "viewport": viewport,
            "locale": "ja-JP",
            "user_agent": config.USER_AGENT,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
                f"--window-position={pos[0]},{pos[1]}",
                "--disable-extensions",
                "--disable-popup-blocking",
                "--mute-audio",
            ],
            "ignore_default_args": ["--enable-automation"],
        }
        if exec_path:
            launch_opts["executable_path"] = exec_path

        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(**launch_opts)
            await context.add_init_script(_init_stealth_script())
            page = context.pages[0] if context.pages else await context.new_page()

            try:
                from playwright_stealth import Stealth
                await Stealth().apply_stealth_async(context)
            except ImportError:
                pass
            except Exception:
                pass

            _log("=" * 50)
            _log("あるけみすと 自動ダンジョン探索")
            _log("=" * 50)
            if backend_connected:
                _log("Webサーバーに接続済み。通知・操作が利用できます。")
            _log("-" * 50)
            _log("ログインするまで待機。ログイン後「自動探索開始」を押すか、初回のみ5秒で自動開始")
            _log("終了: Ctrl+C")
            _log("=" * 50)

            ctx = ExplorationContext(
                page=page,
                client=client,
                base=base,
                backend_connected=backend_connected,
                loop_count_file=config.USER_DATA_DIR.parent / ".loop_count",
                first_wait=True,
            )

            state = State.WAITING_LOGIN
            try:
                while state != State.STOPPED:
                    if not backend_connected and not config.BACKEND_OPTIONAL:
                        break
                    handler = STATE_HANDLERS.get(state)
                    if handler is None:
                        _log(f"  → 未定義の状態: {state}", level="error")
                        break
                    if config.VERBOSE:
                        logger.debug("state=%s", state.name)
                    state, ctx = await handler(ctx)
            except KeyboardInterrupt:
                _log("\n終了しました。")
            except Exception as e:
                _log(f"\n予期しないエラー: {e}", level="error")
                raise
            finally:
                try:
                    await context.close()
                except Exception:
                    pass

    if own_client:
        async with client:
            await _run()
    else:
        await _run()


def _sig_handler(signum: int, frame) -> None:
    global _shutdown_requested
    _shutdown_requested = True
    _log("\n終了シグナルを受信。ループ完了後に停止します...")


def main() -> None:
    parser = argparse.ArgumentParser(description="あるけみすと 自動ダンジョン探索")
    parser.add_argument("--headless", action="store_true", help="ヘッドレスモード")
    parser.add_argument("--max-loops", type=int, default=0, help="最大ループ数 (0=無制限)")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログ")
    args = parser.parse_args()

    import config as _config
    if args.headless:
        _config.HEADLESS = True
    if args.max_loops:
        _config.MAX_LOOPS = args.max_loops
    if args.verbose:
        _config.VERBOSE = True

    _setup_logging()
    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    asyncio.run(run_loop())


if __name__ == "__main__":
    main()
