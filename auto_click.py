#!/usr/bin/env python3
"""
あるけみすと - ダンジョン探索の自動クリックスクリプト

・ホームで「探索する」→ モンスター画面で「街に戻る」を繰り返し
・Web通知サーバー(app.py)と連携: ラッキーチャンスを通知
・自動探索終了後もブラウザは開いたまま。再度「自動探索開始」で再開可能
"""

import asyncio
import random
import time
from pathlib import Path
from typing import Optional

import httpx
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

import config  # type: ignore


def _cubic_bezier(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
    """3次ベジェ曲線（人間の手の軌道に近い）"""
    u = 1 - t
    return u**3 * p0 + 3 * u**2 * t * p1 + 3 * u * t**2 * p2 + t**3 * p3


def _log(msg: str, verbose_only: bool = False) -> None:
    if config.VERBOSE or not verbose_only:
        print(msg)


async def human_like_click(page, locator) -> None:
    """
    人間らしいマウス動作：3次ベジェ曲線・オーバーシュート・微振動・可変速度
    クリック位置はボタン内にクランプ
    """
    await locator.wait_for(state="attached", timeout=config.TIMEOUT_MS)
    await locator.scroll_into_view_if_needed()
    await asyncio.sleep(random.uniform(0.08, 0.2))
    await locator.wait_for(state="visible", timeout=config.TIMEOUT_MS)
    box = await locator.bounding_box()
    if not box:
        await locator.click()
        return

    # クリック位置：ボタン内にクランプ（範囲外クリック防止）
    offset_x = random.gauss(0, box["width"] * 0.15)
    offset_y = random.gauss(0, box["height"] * 0.15)
    target_x = box["x"] + box["width"] / 2 + offset_x
    target_y = box["y"] + box["height"] / 2 + offset_y
    target_x = max(box["x"] + 5, min(box["x"] + box["width"] - 5, target_x))
    target_y = max(box["y"] + 5, min(box["y"] + box["height"] - 5, target_y))

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
    """人間らしいスクロール（短時間で）"""
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
    """ページ最下部までスクロール"""
    await page.evaluate(
        "window.scrollTo(0, Math.max(document.body.scrollHeight, document.documentElement.scrollHeight))"
    )
    if random.random() < 0.25:
        await asyncio.sleep(random.uniform(0.05, 0.12))
        await page.evaluate("window.scrollBy(0, -20)")
        await asyncio.sleep(random.uniform(0.02, 0.06))
        await page.evaluate("window.scrollBy(0, 25)")


async def _safe_goto_home(page, max_retries: int = 3) -> bool:
    """ホームへ安全に遷移（ERR_ABORTED等をキャッチしてリトライ）"""
    for attempt in range(max_retries):
        try:
            await page.goto(config.HOME_URL, wait_until="domcontentloaded", timeout=15000)
            return True
        except Exception as e:
            err_msg = str(e).lower()
            if "err_aborted" in err_msg or "aborted" in err_msg or "destroyed" in err_msg:
                _log(f"  → 遷移失敗 (試行{attempt+1}/{max_retries})、待機してリトライ")
                await asyncio.sleep(random.uniform(1.0, 2.5))
                continue
            raise
    return False


async def _find_button(page, selectors: list[str], timeout: int = 2000):
    """複数セレクタでフォールバックしてボタンを探す"""
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            await btn.wait_for(state="visible", timeout=timeout)
            return btn
        except PlaywrightTimeout:
            continue
    return None


async def _check_and_wait_lucky_chance(page, client: httpx.AsyncClient) -> bool:
    """ラッキーチャンス検知→Web通知→再開待ち"""
    try:
        lucky = await page.evaluate(
            """() => {
                const t = document.body.innerText.toUpperCase();
                return (t.includes('LUCKY') && t.includes('CHANCE')) || t.includes('LUCKYCHANCE');
            }"""
        )
    except Exception as e:
        # ページ遷移中で実行コンテキストが破棄された場合など → ラッキーチャンスなしとして続行
        err_msg = str(e).lower()
        if "destroyed" in err_msg or "navigation" in err_msg or "target closed" in err_msg:
            return False
        raise
    if not lucky:
        return False

    _log("")
    _log("★ ラッキーチャンス！ Web画面の「自動探索開始」を押して再開してください ★")
    base = config.BACKEND_URL.rstrip("/")
    try:
        await client.post(f"{base}/api/lucky-chance", timeout=config.HTTP_TIMEOUT)
        backend_ok = True
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        _log(f"  (通知サーバー接続失敗: {e}。ターミナルで y 入力)")
        backend_ok = False

    if backend_ok:
        while True:
            await asyncio.sleep(2)
            try:
                r = await client.get(f"{base}/api/check-go", timeout=config.HTTP_TIMEOUT)
                if r.json().get("go"):
                    break
            except Exception:
                pass
    else:
        def wait_input():
            return input(">> ")

        loop = asyncio.get_running_loop()
        while True:
            if (await loop.run_in_executor(None, wait_input)).strip().lower() == "y":
                break

    _log("再開します。20秒後に探索から始めます。")
    await asyncio.sleep(20)
    try:
        await client.post(f"{base}/api/exploration-started", timeout=config.HTTP_TIMEOUT)
    except Exception:
        pass
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


async def run_loop() -> None:
    limits = httpx.Limits(max_connections=4, keepalive_expiry=30.0)
    async with httpx.AsyncClient(limits=limits, timeout=config.HTTP_TIMEOUT) as http_client:
        async with async_playwright() as p:
            exec_path = _get_browser_executable()
            viewport = random.choice(config.VIEWPORT_OPTIONS)
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
                    "--window-position=0,0",
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
                _log("※Web通知なしで動作。ボタン操作は uvicorn app:app --port 8000 → http://localhost:8000")
            _log("-" * 50)
            _log("ログインするまで待機。ログイン後「自動探索開始」か5秒で自動開始")
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
                    _log("ログイン確認。Web画面で「自動探索開始」を押すまで待機")
                else:
                    now = time.monotonic()
                    if last_msg_at == 0 or (now - last_msg_at) > 10:
                        _log("ログインしてください…")
                        last_msg_at = now
                    await asyncio.sleep(5)

            await asyncio.sleep(5)
            loop_count_file = config.USER_DATA_DIR.parent / ".loop_count"

            try:
                while True:
                    wait_start = time.monotonic()
                    started = False
                    while True:
                        try:
                            r = await http_client.get(f"{base}/api/check-go", timeout=config.HTTP_TIMEOUT)
                            if r.json().get("go"):
                                started = True
                                break
                        except Exception:
                            pass
                        if (time.monotonic() - wait_start) >= config.AUTO_START_SECONDS:
                            _log("  (5秒経過のため自動開始)")
                            started = True
                            break
                        await asyncio.sleep(2)

                    if not started:
                        continue

                    _log("自動探索を開始します。")
                    try:
                        await http_client.post(f"{base}/api/exploration-started", timeout=config.HTTP_TIMEOUT)
                    except Exception:
                        pass

                    count = 0
                    start_time = time.monotonic()
                    consecutive_errors = 0

                    while True:
                        if config.MAX_LOOPS and count >= config.MAX_LOOPS:
                            _log(f"最大ループ数 {config.MAX_LOOPS} に達しました。")
                            break

                        # 停止チェック（ループの最初＝前ループ完了後。押したらこのループは行わず停止）
                        if count > 0:
                            try:
                                r = await http_client.get(f"{base}/api/check-stop", timeout=3.0)
                                if r.json().get("stop"):
                                    _log("")
                                    _log("自動探索を停止しました。ブラウザは開いたままです。")
                                    try:
                                        await http_client.post(f"{base}/api/exploration-stopped", timeout=config.HTTP_TIMEOUT)
                                    except Exception:
                                        pass
                                    break
                            except Exception:
                                pass

                        count += 1
                        elapsed = time.monotonic() - start_time
                        try:
                            with open(loop_count_file, "w") as f:
                                f.write(str(count))
                        except Exception:
                            pass

                        _log(f"[{count}] ループ開始 (経過: {elapsed:.0f}秒)")
                        wmin, wmax = config.WAIT_START
                        delay = random.uniform(wmin, wmax)
                        _log(f"  → {delay:.3f}秒待機...", verbose_only=True)
                        await asyncio.sleep(delay)

                        await _human_scroll_down(page)
                        wmin, wmax = config.WAIT_AFTER_HOME_SCROLL
                        await asyncio.sleep(random.uniform(wmin, wmax))

                        clicked = False
                        challenge_btn = await _find_button(page, config.SELECTOR_CHALLENGE, timeout=2000)
                        if challenge_btn:
                            _log("  → 挑戦する（天空闘技場）をクリック")
                            await human_like_click(page, challenge_btn)
                            clicked = True

                        if not clicked:
                            explore_btn = await _find_button(page, config.SELECTOR_EXPLORE, timeout=2000)
                            if explore_btn:
                                _log("  → 探索するをクリック")
                                await human_like_click(page, explore_btn)
                                clicked = True
                            else:
                                _log("  → 探索ボタンが見つかりません。ホームへ戻ります。")
                                consecutive_errors += 1
                                if consecutive_errors >= 5:
                                    _log("  ※連続エラーが多いため停止を検討してください")
                                await _safe_goto_home(page)
                                continue

                        consecutive_errors = 0
                        await page.wait_for_load_state("domcontentloaded")
                        await asyncio.sleep(random.uniform(0.4, 0.8))
                        if random.random() < 0.04:
                            await asyncio.sleep(random.uniform(0.2, 0.5))

                        if await _check_and_wait_lucky_chance(page, http_client):
                            await _human_scroll_to_bottom(page)
                            wmin, wmax = config.WAIT_AFTER_MONSTER_SCROLL
                            await asyncio.sleep(random.uniform(wmin, wmax))
                            return_btn = await _find_button(page, config.SELECTOR_RETURN, timeout=3000)
                            if return_btn:
                                await human_like_click(page, return_btn)
                            else:
                                await _safe_goto_home(page)
                            continue

                        await _human_scroll_to_bottom(page)
                        wmin, wmax = config.WAIT_AFTER_MONSTER_SCROLL
                        await asyncio.sleep(random.uniform(wmin, wmax))

                        return_btn = await _find_button(page, config.SELECTOR_RETURN, timeout=3000)
                        if not return_btn:
                            _log("  → 街に戻るボタンが見つかりません。ホームへ戻ります。")
                            await _safe_goto_home(page)
                            continue

                        await human_like_click(page, return_btn)
                        await page.wait_for_load_state("domcontentloaded")
                        await asyncio.sleep(random.uniform(0.4, 0.8))

                        if await _check_and_wait_lucky_chance(page, http_client):
                            continue

                        wmin, wmax = config.WAIT_AFTER_RETURN
                        delay = random.uniform(wmin, wmax)
                        _log(f"  → {delay:.3f}秒待機...", verbose_only=True)
                        await asyncio.sleep(delay)

            except KeyboardInterrupt:
                _log("\n終了しました。")
            finally:
                await context.close()


def main() -> None:
    asyncio.run(run_loop())


if __name__ == "__main__":
    main()
