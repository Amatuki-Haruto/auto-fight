#!/usr/bin/env python3
"""
あるけみすと myshop 自動価格取得

・ローカル: Playwright で browser_data（ログイン済み）を使って取得
・Render等: MYSHOP_COOKIES 環境変数があれば httpx で Cookie 付き取得（Playwright 不要）
"""
import argparse
import asyncio
import base64
import json
import logging
import os
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

MYSHOP_URL = "https://games-alchemist.com/myshop/"
PAGE_LOAD_TIMEOUT_MS = 15000
WAIT_AFTER_LOAD_SEC = 2.0
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

logger = logging.getLogger("myshop_fetcher")


def _setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(message)s")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)


def _fetch_myshop_with_cookies() -> str | None:
    """MYSHOP_COOKIES 環境変数を使って httpx で取得（Render 用）"""
    import httpx
    cookies_b64 = os.environ.get("MYSHOP_COOKIES", "").strip()
    if not cookies_b64:
        return None
    try:
        cookies = json.loads(base64.b64decode(cookies_b64).decode("utf-8"))
        cookie_dict = {c["name"]: c["value"] for c in cookies if isinstance(c, dict) and "name" in c and "value" in c}
        if not cookie_dict:
            logger.error("MYSHOP_COOKIES に有効な Cookie がありません")
            return None
    except Exception as e:
        logger.error("MYSHOP_COOKIES の解析に失敗: %s", e)
        return None

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": USER_AGENT},
            cookies=cookie_dict,
        ) as client:
            r = client.get(MYSHOP_URL)
            r.raise_for_status()
            return r.text
    except Exception as e:
        logger.error("市場ページの取得に失敗: %s", e)
        return None


async def _fetch_myshop_with_playwright() -> str | None:
    """Playwright で市場ページの HTML を取得。ログイン済み browser_data を使用"""
    try:
        import config
        from playwright.async_api import async_playwright
    except ImportError as e:
        logger.error("Playwright がインストールされていません。Render の場合は MYSHOP_COOKIES を設定してください: %s", e)
        return None

    exec_path = config.BRAVE_PATH if Path(config.BRAVE_PATH).exists() else None
    launch_opts: dict = {
        "user_data_dir": str(config.USER_DATA_DIR),
        "headless": True,
        "locale": "ja-JP",
        "user_agent": config.USER_AGENT,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--mute-audio",
        ],
        "ignore_default_args": ["--enable-automation"],
    }
    if exec_path:
        launch_opts["executable_path"] = exec_path

    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(**launch_opts)
            page = context.pages[0] if context.pages else await context.new_page()
            page.set_default_timeout(PAGE_LOAD_TIMEOUT_MS)

            await page.goto(MYSHOP_URL, wait_until="domcontentloaded")
            await asyncio.sleep(WAIT_AFTER_LOAD_SEC)

            # 市場タブがある場合はクリック
            try:
                market_links = page.locator('a:has-text("市場")')
                if await market_links.count() > 0:
                    await market_links.first.click()
                    await asyncio.sleep(WAIT_AFTER_LOAD_SEC)
            except Exception:
                pass

            html = await page.content()
            await context.close()
            return html
    except Exception as e:
        logger.error("市場ページの取得に失敗: %s", e)
        return None


def run_fetch_and_save() -> int:
    """HTML 取得 → パース → DB 保存。戻り値: 記録件数"""
    from myshop_parser import parse_myshop_html
    from myshop_db import init_db, insert_prices

    # Render 等: Cookie 方式（Playwright 不要）
    if os.environ.get("MYSHOP_COOKIES"):
        html = _fetch_myshop_with_cookies()
    else:
        html = asyncio.run(_fetch_myshop_with_playwright())
    if not html:
        return -1

    items = parse_myshop_html(html)
    if not items:
        logger.warning("HTML からアイテムが検出されませんでした")
        return 0

    init_db()
    count = insert_prices(items)
    logger.info("市場価格を %d 件記録しました", count)
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="myshop 市場価格を自動取得してDBに保存")
    parser.add_argument("-v", "--verbose", action="store_true", help="詳細ログ")
    args = parser.parse_args()
    _setup_logging(verbose=args.verbose)

    count = run_fetch_and_save()
    sys.exit(0 if count >= 0 else 1)  # -1 = 取得失敗


if __name__ == "__main__":
    main()
