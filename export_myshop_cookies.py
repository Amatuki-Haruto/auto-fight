#!/usr/bin/env python3
"""
あるけみすと ログイン済み Cookie エクスポート
ローカルで auto_click.py によりゲームにログインした後、このスクリプトを実行。
出力を Render の MYSHOP_COOKIES 環境変数（Secret）に貼り付けてください。

※ auto_click.py は停止してから実行してください（同じ browser_data を同時に使えません）
"""
import asyncio
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config
from playwright.async_api import async_playwright


async def main() -> None:
    exec_path = config.BRAVE_PATH if Path(config.BRAVE_PATH).exists() else None
    launch_opts: dict = {
        "user_data_dir": str(config.USER_DATA_DIR),
        "headless": True,
        "args": ["--mute-audio"],
        "ignore_default_args": ["--enable-automation"],
    }
    if exec_path:
        launch_opts["executable_path"] = exec_path

    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(**launch_opts)
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto("https://games-alchemist.com/myshop/", wait_until="domcontentloaded")
            await asyncio.sleep(1)
            cookies = await context.cookies("https://games-alchemist.com")
            await context.close()
    except Exception as e:
        if "profile" in str(e).lower() and ("in use" in str(e).lower() or "singleton" in str(e).lower()):
            print("エラー: browser_data は auto_click.py で使用中です。", file=sys.stderr)
            print("auto_click.py を停止（Ctrl+C）してから、再度実行してください。", file=sys.stderr)
        else:
            print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

    # name, value のみ（domain 等は httpx が自動付与）
    export = [
        {"name": n, "value": v}
        for c in cookies
        if (n := c.get("name")) is not None and (v := c.get("value")) is not None
    ]
    if not export:
        print("エラー: games-alchemist.com の Cookie が取得できませんでした。先に auto_click.py でログインしてください。", file=sys.stderr)
        sys.exit(1)

    b64 = base64.b64encode(json.dumps(export, ensure_ascii=False).encode("utf-8")).decode("ascii")
    print("=" * 60)
    print("以下を Render の MYSHOP_COOKIES（Secret）にコピーしてください:")
    print("=" * 60)
    print(b64)
    print("=" * 60)
    print(f"Cookie 件数: {len(export)}")
    print("※ セッションの有効期限が切れたら再実行して更新してください")


if __name__ == "__main__":
    asyncio.run(main())
