#!/usr/bin/env python3
"""
あるけみすと - ダンジョン探索の自動クリックスクリプト

・ホームで「探索する」→ モンスター画面で「街に戻る」を繰り返し
・Web通知サーバー(app.py)と連携: ラッキーチャンスを通知
・自動探索終了後もブラウザは開いたまま。再度「自動探索開始」で再開可能
"""

import asyncio
import os
import random
import time
from pathlib import Path

import httpx
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# Web通知サーバーのURL（環境変数BACKEND_URLで上書き、未設定時はlocalhost）
# Renderデプロイ時: BACKEND_URL=https://xxx.onrender.com python3 auto_click.py
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

# 設定
HOME_URL = "https://games-alchemist.com/home/"
MONSTER_URL = "https://games-alchemist.com/monster/"
USER_DATA_DIR = Path(__file__).parent / "browser_data"

# ブラウザのパス（環境変数BROWSER_PATHで上書き可）
# Brave優先、未インストール時はChromiumを使用
BRAVE_PATH = os.environ.get(
    "BROWSER_PATH",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
)
# 待機時間（秒）※人間らしい広いランダム幅
WAIT_START_MIN, WAIT_START_MAX = 1.8, 3.2                    # ループ開始（「考える」時間）
WAIT_AFTER_HOME_SCROLL_MIN, WAIT_AFTER_HOME_SCROLL_MAX = 0.7, 2.1   # スクロール後（画面を読む）
WAIT_AFTER_MONSTER_SCROLL_MIN, WAIT_AFTER_MONSTER_SCROLL_MAX = 0.6, 2.4  # モンスター画面
WAIT_AFTER_RETURN_MIN, WAIT_AFTER_RETURN_MAX = 19.5, 25.0     # 街に戻った後（自然な間隔）
WAIT_HOVER_BEFORE_CLICK_MIN, WAIT_HOVER_BEFORE_CLICK_MAX = 0.05, 0.25  # ホバー→クリック間
TIMEOUT = 30000

# よく使われる解像度からランダム選択（人間らしさ）
VIEWPORT_OPTIONS = [
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 720},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
]

# 実在する最新Chrome User-Agent
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _cubic_bezier(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
    """3次ベジェ曲線（人間の手の軌道に近い）"""
    u = 1 - t
    return u**3 * p0 + 3 * u**2 * t * p1 + 3 * u * t**2 * p2 + t**3 * p3


async def human_like_click(page, locator):
    """
    人間らしいマウス動作：3次ベジェ曲線・オーバーシュート・微振動・可変速度
    """
    await locator.wait_for(state="attached", timeout=TIMEOUT)
    await locator.scroll_into_view_if_needed()
    await asyncio.sleep(random.uniform(0.15, 0.45))  # スクロール後「読み」の時間
    await locator.wait_for(state="visible", timeout=TIMEOUT)
    box = await locator.bounding_box()
    if not box:
        await locator.click()
        return

    # クリック位置：中心よりややずらす（人間は完璧に中心を狙わない）
    offset_x = random.gauss(0, box["width"] * 0.15)
    offset_y = random.gauss(0, box["height"] * 0.15)
    target_x = box["x"] + box["width"] / 2 + offset_x
    target_y = box["y"] + box["height"] / 2 + offset_y

    viewport = page.viewport_size or {"width": 1280, "height": 720}
    # 開始位置：前回の操作付近か、画面内の自然な位置
    start_x = random.uniform(80, viewport["width"] - 80)
    start_y = random.uniform(80, viewport["height"] - 80)

    # 3次ベジェ制御点（曲線を人間っぽく）
    c1_x = start_x + (target_x - start_x) * random.uniform(0.2, 0.4) + random.uniform(-25, 25)
    c1_y = start_y + (target_y - start_y) * random.uniform(0.2, 0.4) + random.uniform(-15, 15)
    c2_x = start_x + (target_x - start_x) * random.uniform(0.6, 0.8) + random.uniform(-20, 20)
    c2_y = start_y + (target_y - start_y) * random.uniform(0.6, 0.8) + random.uniform(-15, 15)

    # 距離に応じてステップ数（遠いほどゆっくり）
    dist = ((target_x - start_x) ** 2 + (target_y - start_y) ** 2) ** 0.5
    steps = max(6, min(18, int(dist / 50)))  # 6〜18ステップ
    steps += random.randint(-2, 2)  # ばらつき

    # イージング：最初ゆっくり、中間速く、最後ややゆっくり
    for i in range(1, steps + 1):
        t_raw = i / steps
        t = t_raw**1.3 * (1 - (1 - t_raw) ** 1.2) + t_raw * 0.3  # カスタムイージング
        x = _cubic_bezier(t, start_x, c1_x, c2_x, target_x)
        y = _cubic_bezier(t, start_y, c1_y, c2_y, target_y)
        # 微振動（人間の手ぶれ）
        if random.random() < 0.3:
            x += random.gauss(0, 0.8)
            y += random.gauss(0, 0.8)
        await page.mouse.move(x, y, steps=1)
        # 可変速度（途中で微妙に速くなったり遅くなったり）
        delay = random.gauss(0.045, 0.02)
        delay = max(0.02, min(0.12, delay))
        await asyncio.sleep(delay)

    # たまにオーバーシュート（通り過ぎてから戻る）
    if random.random() < 0.15:
        overshoot_x = target_x + random.uniform(3, 12) * random.choice([-1, 1])
        overshoot_y = target_y + random.uniform(2, 8) * random.choice([-1, 1])
        await page.mouse.move(overshoot_x, overshoot_y, steps=1)
        await asyncio.sleep(random.uniform(0.02, 0.06))
        await page.mouse.move(target_x, target_y, steps=1)

    # ホバーしてからクリック（人間はボタンを見てから押す）
    await asyncio.sleep(
        random.uniform(WAIT_HOVER_BEFORE_CLICK_MIN, WAIT_HOVER_BEFORE_CLICK_MAX)
    )
    await page.mouse.click(target_x, target_y)


async def _human_scroll_down(page, amount: int = None):
    """人間らしいスクロール：可変量・チャンク分割・微休止"""
    if amount is None:
        amount = random.randint(280, 520)
    chunk = random.randint(80, 180)
    moved = 0
    while moved < amount:
        step = min(chunk, amount - moved)
        await page.evaluate(f"window.scrollBy(0, {step})")
        moved += step
        await asyncio.sleep(random.uniform(0.02, 0.08))
        if random.random() < 0.15:  # たまに「読んでる」休止
            await asyncio.sleep(random.uniform(0.1, 0.3))


async def _human_scroll_to_bottom(page):
    """ページ最下部まで人間らしくスクロール"""
    await page.evaluate(
        "window.scrollTo(0, Math.max(document.body.scrollHeight, document.documentElement.scrollHeight))"
    )
    # 一気にではなく数回に分ける場合も
    if random.random() < 0.4:
        await asyncio.sleep(random.uniform(0.1, 0.25))
        await page.evaluate("window.scrollBy(0, -30)")
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.evaluate("window.scrollBy(0, 40)")


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
    print("★ ラッキーチャンスがあるよ！ Web画面の「自動探索開始」を押して再開してください ★")
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
                    r = await client.get(f"{base}/api/check-go", timeout=5.0)
                    if r.json().get("go"):
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


def _init_stealth_script():
    """自動化検出の回避スクリプト"""
    return """
    (function(){
        if (typeof navigator === 'undefined') return;
        try { Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true }); } catch(e){}
        try { delete Object.getPrototypeOf(navigator).webdriver; } catch(e){}
    })();
    """


def _get_browser_executable():
    """Braveが存在すればBrave、なければChromiumを使用"""
    if Path(BRAVE_PATH).exists():
        return BRAVE_PATH
    return None  # NoneでPlaywright標準のChromium


async def run_loop():
    async with async_playwright() as p:
        exec_path = _get_browser_executable()
        viewport = random.choice(VIEWPORT_OPTIONS)
        launch_options = {
            "user_data_dir": str(USER_DATA_DIR),
            "headless": False,
            "viewport": viewport,
            "locale": "ja-JP",
            "user_agent": USER_AGENT,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
                "--window-position=0,0",
                "--disable-extensions",
                "--disable-popup-blocking",
            ],
            "ignore_default_args": ["--enable-automation"],
        }
        if exec_path:
            launch_options["executable_path"] = exec_path
        context = await p.chromium.launch_persistent_context(**launch_options)
        await context.add_init_script(_init_stealth_script())
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
        # 起動時に通知サーバーの接続を確認
        try:
            async with httpx.AsyncClient() as c:
                await c.get(f"{BACKEND_URL.rstrip('/')}/api/check-go", timeout=2.0)
        except Exception:
            print("※Web通知なしで動作します。ボタン操作を使うには:")
            print("  別ターミナルで「uvicorn app:app --port 8000」を実行 → http://localhost:8000 を開く")
        print("-" * 50)
        print("ログインするまで待機します。")
        print("ログイン後、Web画面の「自動探索開始」ボタンを押すか、5秒待機で自動開始")
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

        # Web画面の「自動探索開始」で開始、 stop で停止→再度開始待ち（ブラウザは閉じない）
        base = BACKEND_URL.rstrip("/")
        AUTO_START_SECONDS = 5  # サーバー未接続時にこの秒数後に自動開始

        try:
            while True:
                # --- 開始・再開待ち ---
                wait_start = time.monotonic()
                started = False
                try:
                    while True:
                        try:
                            async with httpx.AsyncClient() as client:
                                r = await client.get(f"{base}/api/check-go", timeout=5.0)
                                if r.json().get("go"):
                                    started = True
                                    break
                        except Exception:
                            pass
                        # サーバー未起動時はAUTO_START_SECONDS後に自動開始
                        if (time.monotonic() - wait_start) >= AUTO_START_SECONDS:
                            print("  (5秒経過のため自動開始)")
                            started = True
                            break
                        await asyncio.sleep(2)
                except Exception:
                    if not started:
                        print("  (サーバー未起動のため5秒後に自動開始)")
                        await asyncio.sleep(5)
                        started = True
                if not started:
                    continue
                print("自動探索を開始します。")

                try:
                    async with httpx.AsyncClient() as client:
                        await client.post(f"{base}/api/exploration-started", timeout=5.0)
                except Exception:
                    pass

                count = 0
                while True:
                    # 停止シグナルチェック
                    try:
                        async with httpx.AsyncClient() as client:
                            r = await client.get(f"{base}/api/check-stop", timeout=3.0)
                            if r.json().get("stop"):
                                print()
                                print("自動探索を停止しました。ブラウザは開いたままです。")
                                try:
                                    async with httpx.AsyncClient() as c:
                                        await c.post(f"{base}/api/exploration-stopped", timeout=5.0)
                                except Exception:
                                    pass
                                break  # 内側ループを抜け、再度「開始」待ちへ
                    except Exception:
                        pass

                    count += 1
                print(f"[{count}] ループ開始")

                # (1.499〜1.999秒待機)
                delay = random.uniform(WAIT_START_MIN, WAIT_START_MAX)
                print(f"  → {delay:.3f}秒待機...")
                await asyncio.sleep(delay)

                # スクロール（ホーム）
                await _human_scroll_down(page)

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

                # ページ遷移待機（人間は読み込むまで待つ）
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(random.uniform(1.2, 2.5))
                # たまに「考えてる」余分な待ち
                if random.random() < 0.06:
                    await asyncio.sleep(random.uniform(0.8, 2.2))

                # ラッキーチャンス検知（探索/挑戦後の結果画面）
                if await _check_and_wait_lucky_chance(page):
                    await _human_scroll_to_bottom(page)
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
                await _human_scroll_to_bottom(page)

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
                await asyncio.sleep(random.uniform(1.2, 2.5))

                # ラッキーチャンス検知（街に戻った後のホーム画面）
                if await _check_and_wait_lucky_chance(page):
                    continue  # 20秒待ち済み、次ループで探索から開始

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
