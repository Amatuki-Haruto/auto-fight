#!/usr/bin/env python3
"""
自動再起動付きで auto_click を実行。
AUTO_RESTART=1 のとき、クラッシュ時に自動で再起動する。
"""
import os
import subprocess
import sys
import time

def main() -> None:
    auto_restart = os.environ.get("AUTO_RESTART", "0").lower() in ("1", "true", "yes")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    auto_click_path = os.path.join(script_dir, "auto_click.py")

    while True:
        try:
            result = subprocess.run([sys.executable, auto_click_path] + sys.argv[1:])
            code = result.returncode
            if not auto_restart:
                sys.exit(code)
            if code == 0:
                print("正常終了。再起動しません。")
                sys.exit(0)
            print(f"\n終了コード {code}。10秒後に再起動します...")
            time.sleep(10)
        except KeyboardInterrupt:
            print("\n終了しました。")
            sys.exit(0)

if __name__ == "__main__":
    main()
