#!/usr/bin/env python3
"""
あるけみすと - ダンジョン探索の自動クリックスクリプト

・ホームで「探索する」→ モンスター画面で「街に戻る」を繰り返し
・Web通知サーバー(app.py)と連携: ラッキーチャンス・レベル100を通知
"""

import asyncio
import os
import random
import time
from pathlib import Path

import httpx
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# Web通知サーバーのURL（環境変数で上書き可能、Renderデプロイ先を指定）
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

# 設定
HOME_URL = "https://games-alchemist.com/home/"
MONSTER_URL = "https://games-alchemist.com/monster/"
USER_DATA_DIR = Path(__file__).parent / "browser_data"

# Brave ブラウザのパス（Mac標準の場所）
BRAVE_PATH = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
# 待機時間（秒）※すべてランダム
WAIT_START_MIN, WAIT_START_MAX = 1.499, 1.999          # ループ開始時
WAIT_AFTER_HOME_SCROLL_MIN, WAIT_AFTER_HOME_SCROLL_MAX = 0.5, 0.999   # スクロール後→探索する前
WAIT_AFTER_MONSTER_SCROLL_MIN, WAIT_AFTER_MONSTER_SCROLL_MAX = 0.499, 1.499  # 下までスクロール後→街に戻る前
WAIT_AFTER_RETURN_MIN, WAIT_AFTER_RETURN_MAX = 20.499, 20.999        # 街に戻る後→次ループ前
TIMEOUT = 30000  # 要素待ちのタイムアウト（ミリ秒）

# 最近のChrome User-Agent（検出されにくくするため）
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


async def human_like_click(page, locator):
    """
    人間らしいマウス動作でクリック（カーブした軌道・位置のばらつき）
    必要に応じてスクロールしてボタンを表示してからクリック
    """
    await locator.wait_for(state="attached", timeout=TIMEOUT)
    await locator.scroll_into_view_if_needed()
    await asyncio.sleep(0.2)  # スクロール後少し待つ
    await locator.wait_for(state="visible", timeout=TIMEOUT)
    box = await locator.bounding_box()
    if not box:
        await locator.click()
        return

    # ボタン内のクリック位置にランダムなオフセット（中心より少しずらす）
    offset_x = random.uniform(-box["width"] * 0.3, box["width"] * 0.3)
    offset_y = random.uniform(-box["height"] * 0.3, box["height"] * 0.3)
    target_x = box["x"] + box["width"] / 2 + offset_x
    target_y = box["y"] + box["height"] / 2 + offset_y

    # 現在位置（ビューポート内のランダムな場所から開始）
    viewport = page.viewport_size
    start_x = random.uniform(100, viewport["width"] - 100) if viewport else 640
    start_y = random.uniform(100, viewport["height"] - 100) if viewport else 360

    # 3〜5ステップでカーブを描きながら移動（中間点は1回だけ決める）
    steps = random.randint(3, 5)
    mid_x = (start_x + target_x) / 2 + random.uniform(-30, 30)
    mid_y = (start_y + target_y) / 2 + random.uniform(-20, 20)
    for i in range(1, steps + 1):
        t = i / steps
        x = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * mid_x + t**2 * target_x
        y = (1 - t) ** 2 * start_y + 2 * (1 - t) * t * mid_y + t**2 * target_y
        await page.mouse.move(x, y, steps=1)
        await asyncio.sleep(random.uniform(0.03, 0.08))

    await asyncio.sleep(random.uniform(0.05, 0.12))
    await page.mouse.click(target_x, target_y)


async def _check_and_wait_lucky_chance(page) -> bool:
    """
    ラッキーチャンスを検知したらWebに通知し、ボタン押下で再開。
    戻り値: ラッキーチャンスが検出されたか
    """
    lucky_chance = await page.evaluate(
        """() => {
            const text = document.body.innerText.toUpperCase();
            return (text.includes('LUCKY') && text.includes('CHANCE')) || text.includes('LUCKYCHANCE');
        }"""
    )
    if not lucky_chance:
        return False

    print()
    print("★ ラッキーチャンスがあるよ！ Web画面のボタンを押して再開してください ★")
    base = BACKEND_URL.rstrip("/")
    try:
        async with httpx.AsyncClient() as client:
            await client.post(f"{base}/api/lucky-chance", timeout=5.0)
        backend_ok = True
    except Exception as e:
        print(f"  (通知サーバー接続失敗: {e}。ターミナルで y 入力に切り替えます)")
        backend_ok = False

    if backend_ok:
        while True:
            await asyncio.sleep(2)
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.get(f"{base}/api/check-resume", timeout=5.0)
                    if r.json().get("resume"):
                        break
            except Exception:
                pass
    else:
        # フォールバック: ターミナルで y 入力
        def wait_for_input():
            return input(">> ")

        loop = asyncio.get_running_loop()
        while True:
            inp = (
                await loop.run_in_executor(None, wait_for_input)
            ).strip().lower()
            if inp == "y":
                break

    print("再開します。20秒後に探索から始めます。")
    await asyncio.sleep(20)
    return True


async def _check_level_100(page) -> bool:
    """レベル100かどうか"""
    try:
        return await page.evaluate(
            """() => {
                const c = (document.body.innerText || '') + (document.body.innerHTML || '');
                const t = c.toUpperCase();
                return /100\\s*[Ll][Vv]|[Ll][Vv]\\.?\\s*100|100[Ll][Vv]|[Ll][Vv]100|レベル\\s*100|100\\s*レベル/.test(t);
            }"""
        )
    except Exception:
        return False


def _init_stealth_script():
    """navigator.webdriver などを隠す初期化スクリプト"""
    return """
    if (typeof navigator !== 'undefined') {
        try {
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
                configurable: true
            });
        } catch (e) {}
        try {
            delete Object.getPrototypeOf(navigator).webdriver;
        } catch (e) {}
    }
    """


async def run_loop():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            executable_path=BRAVE_PATH,
            headless=False,
            viewport={"width": 1280, "height": 720},
            locale="ja-JP",
            user_agent=USER_AGENT,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            ignore_default_args=["--enable-automation"],
        )
        context.add_init_script(_init_stealth_script())
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            from playwright_stealth import Stealth

            stealth = Stealth()
            await stealth.apply_stealth_async(context)
        except Exception:
            pass

        print("=" * 50)
        print("あるけみすと 自動ダンジョン探索")
        print("=" * 50)
        print("ログインするまで待機します。")
        print("ログイン後、Web画面の「自動探索開始」ボタンを押してください。")
        print("終了: Ctrl+C")
        print("=" * 50)

        # ホームへ遷移（既に該当ページならそのまま）
        if "games-alchemist.com/home" not in page.url:
            await page.goto(HOME_URL, wait_until="domcontentloaded")

        # ログインするまで待機（探索ボタンが出るまで何もしない）
        logged_in = False
        last_msg_at = 0.0
        while not logged_in:
            try:
                btn = page.locator(
                    'form[action*="monster"] input[type="submit"][value="探索する"]'
                ).first
                await btn.wait_for(state="visible", timeout=3000)
                logged_in = True
                print("ログインを確認しました。Web画面で「自動探索開始」を押すまで待機します。")
            except PlaywrightTimeout:
                now = time.monotonic()
                if last_msg_at == 0 or (now - last_msg_at) > 10:
                    print("ログインしてください…")
                    last_msg_at = now
                await asyncio.sleep(5)

        # ログイン後5秒待機
        await asyncio.sleep(5)

        # Web画面の「自動探索開始」ボタンを待つ
        base = BACKEND_URL.rstrip("/")
        start_received = False
        try:
            while not start_received:
                await asyncio.sleep(2)
                async with httpx.AsyncClient() as client:
                    r = await client.get(f"{base}/api/check-start", timeout=5.0)
                    if r.json().get("start"):
                        start_received = True
        except Exception as e:
            print(f"  (通知サーバーに接続できません: {e})")
            print("  5秒後に自動で開始します...")
            await asyncio.sleep(5)
        print("自動探索を開始します。")

        count = 0
        try:
            while True:
                count += 1
                print(f"[{count}] ループ開始")

                # (1.499〜1.999秒待機)
                delay = random.uniform(WAIT_START_MIN, WAIT_START_MAX)
                print(f"  → {delay:.3f}秒待機...")
                await asyncio.sleep(delay)

                # スクロール（ホーム）
                await page.evaluate("window.scrollBy(0, 400)")
                await asyncio.sleep(0.2)

                # (0.5〜0.999秒待機)
                delay = random.uniform(WAIT_AFTER_HOME_SCROLL_MIN, WAIT_AFTER_HOME_SCROLL_MAX)
                print(f"  → {delay:.3f}秒待機...")
                await asyncio.sleep(delay)

                # 「挑戦する」(天空闘技場) があれば優先、なければ「探索する」をクリック
                clicked = False
                try:
                    challenge_btn = page.locator(
                        'input[type="submit"][value="挑戦する"]'
                    ).first
                    await challenge_btn.wait_for(state="visible", timeout=2000)
                    print("  → 挑戦する（天空闘技場）をクリック")
                    await human_like_click(page, challenge_btn)
                    clicked = True
                except PlaywrightTimeout:
                    pass

                if not clicked:
                    try:
                        explore_btn = page.locator(
                            'form[action*="monster"] input[type="submit"][value="探索する"]'
                        ).first
                        print("  → 探索するをクリック")
                        await human_like_click(page, explore_btn)
                        clicked = True
                    except PlaywrightTimeout:
                        print("  → 探索ボタンが見つかりません。ホームへ戻ります。")
                        await page.goto(HOME_URL, wait_until="domcontentloaded")
                        continue

                # ページ遷移待機
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(1.5)

                # ラッキーチャンス検知（探索/挑戦後の結果画面）
                if await _check_and_wait_lucky_chance(page):
                    # 再開: 街に戻ってから次ループへ
                    await page.evaluate(
                        "window.scrollTo(0, Math.max(document.body.scrollHeight, document.documentElement.scrollHeight))"
                    )
                    await asyncio.sleep(0.2)
                    delay = random.uniform(
                        WAIT_AFTER_MONSTER_SCROLL_MIN, WAIT_AFTER_MONSTER_SCROLL_MAX
                    )
                    await asyncio.sleep(delay)
                    try:
                        return_btn = page.locator(
                            'form[action*="home"] input[type="submit"][value="街に戻る"]'
                        ).first
                        await human_like_click(page, return_btn)
                    except PlaywrightTimeout:
                        await page.goto(HOME_URL, wait_until="domcontentloaded")
                    continue

                # 下までスクロール（モンスター画面）
                await page.evaluate(
                    "window.scrollTo(0, Math.max(document.body.scrollHeight, document.documentElement.scrollHeight))"
                )
                await asyncio.sleep(0.2)

                # (0.499〜1.499秒待機)
                delay = random.uniform(WAIT_AFTER_MONSTER_SCROLL_MIN, WAIT_AFTER_MONSTER_SCROLL_MAX)
                print(f"  → {delay:.3f}秒待機...")
                await asyncio.sleep(delay)

                # 「街に戻る」ボタンをクリック
                try:
                    return_btn = page.locator(
                        'form[action*="home"] input[type="submit"][value="街に戻る"]'
                    ).first
                    await human_like_click(page, return_btn)
                except PlaywrightTimeout:
                    print("  → 街に戻るボタンが見つかりません。ホームへ戻ります。")
                    await page.goto(HOME_URL, wait_until="domcontentloaded")
                    continue

                # ページ遷移待機（ホームへ）
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(1.5)

                # ラッキーチャンス検知（街に戻った後のホーム画面）
                if await _check_and_wait_lucky_chance(page):
                    continue  # 20秒待ち済み、次ループで探索から開始

                # レベル100検知（通知して停止）
                if await _check_level_100(page):
                    try:
                        async with httpx.AsyncClient() as client:
                            await client.post(
                                f"{BACKEND_URL.rstrip('/')}/api/level-100", timeout=5.0
                            )
                    except Exception:
                        pass
                    print()
                    print("★ レベル100に到達しました！ 自動操作を停止します。 ★")
                    break

                # (20.499〜20.999秒待機) → スクロールに戻ってループ
                delay = random.uniform(WAIT_AFTER_RETURN_MIN, WAIT_AFTER_RETURN_MAX)
                print(f"  → {delay:.3f}秒待機...")
                await asyncio.sleep(delay)

        except KeyboardInterrupt:
            print("\n終了しました。")
        finally:
            await context.close()


def main():
    asyncio.run(run_loop())


if __name__ == "__main__":
    main()
