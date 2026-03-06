#!/usr/bin/env python3
"""
あるけみすと - ダンジョン探索の自動クリックスクリプト

・ホームで「探索する」→ モンスター画面で「街に戻る」を繰り返し
・Web通知サーバー(app.py)と連携: ラッキーチャンスを通知
・Lv100転生メッセージ検知で強制停止
・自動探索終了後もブラウザは開いたまま。再度「自動探索開始」で再開可能
"""

import argparse
import asyncio
import re
import random
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

import config  # type: ignore

# ANSI色（ターミナル用）
_COLORS = {
    "reset": "\033[0m",
    "red": "\033[91m",
    "green": "\033[92m",
    "yellow": "\033[93m",
}

_shutdown_requested = False


def _colored(msg: str, color: str) -> str:
    if sys.stdout.isatty() and color in _COLORS:
        return f"{_COLORS[color]}{msg}{_COLORS['reset']}"
    return msg


def _log(msg: str, verbose_only: bool = False, level: str = "info") -> None:
    if config.VERBOSE or not verbose_only:
        if level == "error":
            print(_colored(msg, "red"))
        elif level == "warn":
            print(_colored(msg, "yellow"))
        elif level == "success":
            print(_colored(msg, "green"))
        else:
            print(msg)


def _cubic_bezier(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
    """3次ベジェ曲線（人間の手の軌道に近い）"""
    u = 1 - t
    return u**3 * p0 + 3 * u**2 * t * p1 + 3 * u * t**2 * p2 + t**3 * p3


async def _get_page_text(page) -> str:
    """ページテキストを安全に取得"""
    try:
        return await page.evaluate("() => document.body.innerText") or ""
    except Exception:
        return ""


def _text_has_force_stop(text: str) -> Optional[str]:
    """テキストにLv100転生等の強制停止トリガーが含まれるか。該当すれば理由を返す"""
    if not text:
        return None
    for pat in getattr(config, "FORCE_STOP_PATTERNS", ["あなたはLv100になりました", "転生してください"]):
        if pat in text:
            return f"Lv100転生のため停止（{pat}）"
    return None


async def _check_force_stop(page) -> Optional[str]:
    """Lv100転生等の強制停止トリガーをチェック。該当すれば理由を返す"""
    text = await _get_page_text(page)
    return _text_has_force_stop(text)


async def _is_champion(page) -> bool:
    """〇〇階のチャンプです → 天空闘技場行けない"""
    text = await _get_page_text(page)
    return "チャンプです" in text


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


async def _find_button(page, selectors: list[str], timeout: int | None = None) -> Optional[Any]:
    """複数セレクタでフォールバック。テキストセレクタも試行"""
    tout = timeout or getattr(config, "BUTTON_TIMEOUT_MS", 2000)
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            await btn.wait_for(state="visible", timeout=tout)
            return btn
        except PlaywrightTimeout:
            continue
    return None


async def _click_and_verify(page, locator, expect_url_contains: str | list[str]) -> bool:
    """クリック → 2秒待機 → 成功確認。失敗ならリトライ"""
    expect = expect_url_contains
    if expect == "monster":
        expect = getattr(config, "URL_AFTER_EXPLORE", ["monster", "arena", "battle", "tower"])
    max_retries = getattr(config, "CLICK_RETRY_COUNT", 10)

    for attempt in range(max_retries):
        try:
            await human_like_click(page, locator)
        except PlaywrightTimeout:
            _log(f"  → 要素が見つかりません（試行{attempt+1}/{max_retries}）。ホームへ戻ります。", level="warn")
            return False
        await asyncio.sleep(2.0)
        try:
            url = page.url or ""
            if _url_matches_success(url, expect):
                return True
            if isinstance(expect, list) and "games-alchemist.com" in url and "/home/" not in url:
                return True
            await page.wait_for_load_state("domcontentloaded", timeout=3000)
            url = page.url or ""
            if _url_matches_success(url, expect) or (isinstance(expect, list) and "games-alchemist.com" in url and "/home/" not in url):
                return True
        except Exception:
            pass
        _log(f"  → クリック未反映（試行{attempt+1}/{max_retries}）、2秒待機後にリトライ", level="warn")
        await asyncio.sleep(2.0)
    return False


async def human_like_click(page, locator) -> None:
    """人間らしいマウス動作"""
    await locator.wait_for(state="attached", timeout=config.TIMEOUT_MS)
    await locator.scroll_into_view_if_needed()
    await asyncio.sleep(random.uniform(0.08, 0.2))
    await locator.wait_for(state="visible", timeout=config.TIMEOUT_MS)
    box = await locator.bounding_box()
    if not box:
        await locator.click()
        return

    offset_x = random.gauss(0, box["width"] * 0.15)
    offset_y = random.gauss(0, box["height"] * 0.15)
    target_x = max(box["x"] + 5, min(box["x"] + box["width"] - 5, box["x"] + box["width"] / 2 + offset_x))
    target_y = max(box["y"] + 5, min(box["y"] + box["height"] - 5, box["y"] + box["height"] / 2 + offset_y))

    viewport = page.viewport_size or {"width": 1280, "height": 720}
    start_x = random.uniform(80, viewport["width"] - 80)
    start_y = random.uniform(80, viewport["height"] - 80)

    c1_x = start_x + (target_x - start_x) * random.uniform(0.2, 0.4) + random.uniform(-25, 25)
    c1_y = start_y + (target_y - start_y) * random.uniform(0.2, 0.4) + random.uniform(-15, 15)
    c2_x = start_x + (target_x - start_x) * random.uniform(0.6, 0.8) + random.uniform(-20, 20)
    c2_y = start_y + (target_y - start_y) * random.uniform(0.6, 0.8) + random.uniform(-15, 15)

    dist = ((target_x - start_x) ** 2 + (target_y - start_y) ** 2) ** 0.5
    steps = max(4, min(10, int(dist / 80))) + random.randint(-1, 1)

    for i in range(1, steps + 1):
        t_raw = i / steps
        t = t_raw**1.2 * (1 - (1 - t_raw) ** 1.1) + t_raw * 0.2
        x = _cubic_bezier(t, start_x, c1_x, c2_x, target_x)
        y = _cubic_bezier(t, start_y, c1_y, c2_y, target_y)
        if random.random() < 0.25:
            x += random.gauss(0, 0.6)
            y += random.gauss(0, 0.6)
        await page.mouse.move(x, y, steps=1)
        await asyncio.sleep(max(0.015, min(0.06, random.gauss(0.03, 0.01))))

    if random.random() < 0.1:
        overshoot_x = target_x + random.uniform(3, 12) * random.choice([-1, 1])
        overshoot_y = target_y + random.uniform(2, 8) * random.choice([-1, 1])
        await page.mouse.move(overshoot_x, overshoot_y, steps=1)
        await asyncio.sleep(random.uniform(0.02, 0.06))
        await page.mouse.move(target_x, target_y, steps=1)

    hmin, hmax = config.WAIT_HOVER_BEFORE_CLICK
    await asyncio.sleep(random.uniform(hmin, hmax))
    await page.mouse.click(target_x, target_y)


async def _human_scroll_down(page, amount: Optional[int] = None) -> None:
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


async def _human_scroll_to_bottom(page) -> None:
    await page.evaluate(
        "window.scrollTo(0, Math.max(document.body.scrollHeight, document.documentElement.scrollHeight))"
    )
    if random.random() < 0.25:
        await asyncio.sleep(random.uniform(0.05, 0.12))
        await page.evaluate("window.scrollBy(0, -20)")
        await asyncio.sleep(random.uniform(0.02, 0.06))
        await page.evaluate("window.scrollBy(0, 25)")


async def _safe_goto_home(page, max_retries: int = 3) -> bool:
    for attempt in range(max_retries):
        try:
            await page.goto(config.HOME_URL, wait_until="domcontentloaded", timeout=15000)
            return True
        except Exception as e:
            err_msg = str(e).lower()
            if "err_aborted" in err_msg or "aborted" in err_msg or "destroyed" in err_msg:
                _log(f"  → 遷移失敗 (試行{attempt+1}/{max_retries})、待機してリトライ", level="warn")
                await asyncio.sleep(random.uniform(1.0, 2.5))
                continue
            raise
    return False


async def _save_screenshot(page, prefix: str = "error") -> None:
    """エラー時のスクリーンショット保存"""
    if not getattr(config, "SAVE_SCREENSHOT_ON_ERROR", True):
        return
    try:
        screenshot_dir = getattr(config, "SCREENSHOT_DIR", Path(__file__).parent / "screenshots")
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = screenshot_dir / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        await page.screenshot(path=path)
        _log(f"  → スクリーンショット保存: {path}")
    except Exception as e:
        _log(f"  → スクリーンショット保存失敗: {e}", level="warn")


async def _api_post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    json: dict,
    max_retries: int = 3,
) -> bool:
    """API POSTを指数バックオフでリトライ"""
    for attempt in range(max_retries):
        try:
            r = await client.post(url, json=json, timeout=config.HTTP_TIMEOUT)
            if r.status_code == 200:
                return True
        except (httpx.ConnectError, httpx.TimeoutException):
            pass
        if attempt < max_retries - 1:
            await asyncio.sleep(2**attempt)
    return False


def _is_lucky_chance_text(text: str) -> bool:
    """ラッキーチャンス判定（英語のみ：LUCKY+CHANCE）"""
    t = text.upper()
    return ("LUCKY" in t and "CHANCE" in t) or "LUCKYCHANCE" in t


async def _check_and_wait_lucky_chance(page, client: httpx.AsyncClient, *, already_detected: bool = False) -> bool:
    """ラッキーチャンス検知→Web通知→再開待ち。already_detected=True ならテキストチェックをスキップ"""
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

    _log("")
    _log("★ ラッキーチャンス！ Web画面の「自動探索開始」を押して再開してください ★", level="success")
    base = config.BACKEND_URL.rstrip("/")
    await _api_post_with_retry(client, f"{base}/api/lucky-chance", {})

    while True:
        await asyncio.sleep(2)
        try:
            r = await client.get(f"{base}/api/check-go", timeout=config.HTTP_TIMEOUT)
            if r.json().get("go"):
                break
        except Exception:
            pass

    wait_sec = getattr(config, "LUCKY_CHANCE_WAIT_SEC", 20)
    _log(f"再開します。{wait_sec}秒後に探索から始めます。")
    await asyncio.sleep(wait_sec)
    await _api_post_with_retry(client, f"{base}/api/exploration-started", {})
    return True


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


async def _click_refresh_button(page) -> bool:
    """左上の「更新」ボタンをクリック（停止後の再開時にゲーム状態を更新）"""
    for sel in getattr(config, "SELECTOR_REFRESH", []):
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


async def _try_click_confirm(page) -> bool:
    """確認/OKボタンを探してクリック"""
    for sel in getattr(config, "SELECTOR_CONFIRM", []):
        try:
            btn = page.locator(sel).first
            await btn.wait_for(state="visible", timeout=1500)
            await human_like_click(page, btn)
            return True
        except PlaywrightTimeout:
            continue
    return False


async def run_loop() -> None:
    global _shutdown_requested
    limits = httpx.Limits(max_connections=4, keepalive_expiry=30.0)
    async with httpx.AsyncClient(limits=limits, timeout=config.HTTP_TIMEOUT) as http_client:
        async with async_playwright() as p:
            exec_path = _get_browser_executable()
            viewport = random.choice(config.VIEWPORT_OPTIONS)
            pos = getattr(config, "WINDOW_POSITION", (0, 0))
            launch_opts = {
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

            context = await p.chromium.launch_persistent_context(**launch_opts)
            await context.add_init_script(_init_stealth_script())
            page = context.pages[0] if context.pages else await context.new_page()

            try:
                from playwright_stealth import Stealth
                await Stealth().apply_stealth_async(context)
            except Exception:
                pass

            base = config.BACKEND_URL.rstrip("/")
            _log("=" * 50)
            _log("あるけみすと 自動ダンジョン探索")
            _log("=" * 50)
            try:
                await http_client.get(f"{base}/api/check-go", timeout=2.0)
            except Exception:
                _log("※Web通知なしで動作。uvicorn app:app --port 8000 → http://localhost:8000")
            _log("-" * 50)
            _log("ログインするまで待機。ログイン後「自動探索開始」を押すか、初回のみ5秒で自動開始")
            _log("終了: Ctrl+C")
            _log("=" * 50)

            if "games-alchemist.com/home" not in page.url:
                await _safe_goto_home(page)

            logged_in = False
            last_msg_at = 0.0
            while not logged_in:
                btn = await _find_button(page, config.SELECTOR_EXPLORE, timeout=3000)
                if btn:
                    logged_in = True
                    _log("ログイン確認。Web画面で「自動探索開始」を押すまで待機", level="success")
                else:
                    now = time.monotonic()
                    if last_msg_at == 0 or (now - last_msg_at) > 10:
                        _log("ログインしてください…")
                        last_msg_at = now
                    await asyncio.sleep(5)

            await asyncio.sleep(5)
            loop_count_file = config.USER_DATA_DIR.parent / ".loop_count"
            needs_refresh = False  # 停止後の再開時に「更新」を押す

            try:
                first_wait = True
                while True:
                    if _shutdown_requested:
                        break
                    wait_start = time.monotonic()
                    started = False
                    while True:
                        try:
                            r = await http_client.get(f"{base}/api/check-stop", timeout=2.0)
                            if r.json().get("stop"):
                                break  # 停止要求：開始しない
                        except Exception:
                            pass
                        try:
                            r = await http_client.get(f"{base}/api/check-go", timeout=config.HTTP_TIMEOUT)
                            if r.json().get("go"):
                                started = True
                                break
                        except Exception:
                            pass
                        if first_wait and (time.monotonic() - wait_start) >= config.AUTO_START_SECONDS:
                            _log("  (初回のため5秒経過で自動開始)")
                            started = True
                            break
                        await asyncio.sleep(2)

                    if not started:
                        continue

                    first_wait = False
                    if needs_refresh:
                        if await _click_refresh_button(page):
                            _log("  → 更新ボタンをクリック", level="success")
                            await page.wait_for_load_state("domcontentloaded")
                            await asyncio.sleep(random.uniform(1.0, 2.0))
                        needs_refresh = False

                    _log("自動探索を開始します。", level="success")
                    await _api_post_with_retry(http_client, f"{base}/api/exploration-started", {})

                    count = 0
                    start_time = time.monotonic()
                    consecutive_errors = 0

                    while True:
                        if _shutdown_requested:
                            break
                        if config.MAX_LOOPS and count >= config.MAX_LOOPS:
                            _log(f"最大ループ数 {config.MAX_LOOPS} に達しました。")
                            needs_refresh = True
                            break

                        # 強制停止チェック（Lv100転生等）
                        force_reason = await _check_force_stop(page)
                        if force_reason:
                            _log("")
                            _log(f"★ {force_reason}", level="error")
                            await _save_screenshot(page, "force_stop")
                            await _api_post_with_retry(
                                http_client,
                                f"{base}/api/exploration-stopped",
                                {"reason": force_reason},
                            )
                            needs_refresh = True
                            break

                        if count > 0:
                            try:
                                r = await http_client.get(f"{base}/api/check-stop", timeout=3.0)
                                if r.json().get("stop"):
                                    _log("")
                                    _log("自動探索を停止しました。ブラウザは開いたままです。", level="success")
                                    await _api_post_with_retry(http_client, f"{base}/api/exploration-stopped", {})
                                    needs_refresh = True
                                    break
                            except Exception:
                                pass

                        count += 1
                        loop_start = time.monotonic()
                        elapsed = loop_start - start_time
                        try:
                            with open(loop_count_file, "w") as f:
                                f.write(str(count))
                        except Exception:
                            pass
                        await _api_post_with_retry(
                            http_client,
                            f"{base}/api/exploration-log",
                            {"loop_count": count, "stats": {"consecutive_errors": consecutive_errors}},
                        )

                        _log(f"[{count}] ループ開始 (経過: {elapsed:.0f}秒)")
                        wmin, wmax = config.WAIT_START
                        delay = random.uniform(wmin, wmax)
                        _log(f"  → {delay:.3f}秒待機...", verbose_only=True)
                        await asyncio.sleep(delay)

                        await _human_scroll_down(page)
                        wmin, wmax = config.WAIT_AFTER_HOME_SCROLL
                        await asyncio.sleep(random.uniform(wmin, wmax))

                        if not getattr(config, "CHALLENGE_ARENA", True):
                            challenge_btn = None
                        elif await _is_champion(page):
                            _log("  → チャンプのため天空闘技場はスキップ")
                            challenge_btn = None
                        else:
                            challenge_btn = await _find_button(page, config.SELECTOR_CHALLENGE)

                        clicked = False
                        if challenge_btn:
                            _log("  → 挑戦する（天空闘技場）をクリック")
                            clicked = await _click_and_verify(page, challenge_btn, "monster")

                        if not clicked:
                            explore_btn = await _find_button(page, config.SELECTOR_EXPLORE)
                            if explore_btn:
                                _log("  → 探索するをクリック")
                                clicked = await _click_and_verify(page, explore_btn, "monster")
                            else:
                                _log("  → 探索ボタンが見つかりません。ホームへ戻ります。", level="warn")
                                consecutive_errors += 1
                                await _save_screenshot(page, "no_explore")
                                if consecutive_errors >= 5:
                                    _log("  ※連続エラーが多いため停止を検討してください", level="error")
                                await _safe_goto_home(page)
                                continue

                        if not clicked:
                            _log("  → クリックが反映されませんでした。ホームへ戻ります。", level="warn")
                            await _save_screenshot(page, "click_fail")
                            await _safe_goto_home(page)
                            continue

                        consecutive_errors = 0
                        await page.wait_for_load_state("domcontentloaded")
                        await asyncio.sleep(random.uniform(0.4, 0.8))
                        await _try_click_confirm(page)
                        if random.random() < 0.04:
                            await asyncio.sleep(random.uniform(0.2, 0.5))

                        await _human_scroll_to_bottom(page)
                        wmin, wmax = config.WAIT_AFTER_MONSTER_SCROLL
                        await asyncio.sleep(random.uniform(wmin, wmax))

                        body_text = ""
                        try:
                            body_text = await _get_page_text(page)
                            msg, exp_val, new_drops = _extract_exploration_result(body_text)
                            if msg or new_drops or exp_val > 0:
                                loop_time = time.monotonic() - loop_start
                                await _api_post_with_retry(
                                    http_client,
                                    f"{base}/api/exploration-log",
                                    {
                                        "loop_count": count,
                                        "message": msg,
                                        "exp": exp_val,
                                        "drops": new_drops,
                                        "stats": {"loop_time_sec": round(loop_time, 1), "consecutive_errors": 0},
                                    },
                                )
                        except Exception as e:
                            _log(f"  → 探索結果抽出失敗: {e}", level="warn")

                        # 戦闘結果テキストでLv100転生をチェック
                        force_reason = _text_has_force_stop(body_text)
                        if force_reason:
                            _log("")
                            _log(f"★ {force_reason}", level="error")
                            await _save_screenshot(page, "force_stop")
                            await _api_post_with_retry(
                                http_client,
                                f"{base}/api/exploration-stopped",
                                {"reason": force_reason},
                            )
                            needs_refresh = True
                            break

                        # 戦闘結果でラッキーチャンス検知しても街に戻るを優先（後で処理）
                        lucky_detected = bool(body_text and _is_lucky_chance_text(body_text))

                        return_btn = await _find_button(page, config.SELECTOR_RETURN, timeout=3000)
                        if not return_btn:
                            _log("  → 街に戻るボタンが見つかりません。ホームへ戻ります。", level="warn")
                            await _save_screenshot(page, "no_return")
                            await _safe_goto_home(page)
                            continue

                        try:
                            await _click_and_verify(page, return_btn, "home")
                        except PlaywrightTimeout:
                            _log("  → 街に戻るクリックでタイムアウト。ホームへ戻ります。", level="warn")
                            await _save_screenshot(page, "return_timeout")
                            await _safe_goto_home(page)
                            continue
                        await page.wait_for_load_state("domcontentloaded")
                        await asyncio.sleep(random.uniform(0.4, 0.8))
                        await _try_click_confirm(page)

                        # 街に戻った後のホーム画面でLv100転生をチェック
                        force_reason = await _check_force_stop(page)
                        if force_reason:
                            _log("")
                            _log(f"★ {force_reason}", level="error")
                            await _save_screenshot(page, "force_stop")
                            await _api_post_with_retry(
                                http_client,
                                f"{base}/api/exploration-stopped",
                                {"reason": force_reason},
                            )
                            needs_refresh = True
                            break

                        if await _check_and_wait_lucky_chance(page, http_client, already_detected=lucky_detected):
                            continue

                        wmin, wmax = config.WAIT_AFTER_RETURN
                        delay = random.uniform(wmin, wmax)
                        _log(f"  → {delay:.3f}秒待機...", verbose_only=True)
                        await asyncio.sleep(delay)

            except KeyboardInterrupt:
                _log("\n終了しました。")
            except Exception as e:
                _log(f"\n予期しないエラー: {e}", level="error")
                try:
                    await _save_screenshot(page, "crash")
                except Exception:
                    pass
                raise
            finally:
                try:
                    await context.close()
                except Exception:
                    pass


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

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    asyncio.run(run_loop())


if __name__ == "__main__":
    main()
