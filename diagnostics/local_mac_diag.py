"""Mac上のPlaywrightで同じ現象が起きるか切り分けるための一時診断スクリプト。

認証情報の値は一切表示しない。記録するのは要素のサイズ・スタイル等の
安全な技術情報のみ（生徒名・CSV内容は扱わない）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from takeda_updater import (  # noqa: E402
    _automatic_login_credentials,
    _click_history_navigation,
    _require_env,
)


def main() -> int:
    load_dotenv()
    credentials = _automatic_login_credentials()
    if credentials is None:
        print("credentials: NOT CONFIGURED")
        return 2
    history_url = _require_env("TAKEDA_HISTORY_URL")
    target = urlsplit(history_url)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(locale="ja-JP", timezone_id="Asia/Tokyo")
        page = context.new_page()
        page.goto(history_url, wait_until="domcontentloaded", timeout=60_000)

        staff_button = page.get_by_role("button", name="校舎担当者", exact=True)
        email_input = page.get_by_placeholder("メールアドレス", exact=True)
        password_input = page.get_by_placeholder("パスワード", exact=True)

        staff_button.wait_for(state="visible", timeout=30_000)
        staff_button.click()
        email_input.wait_for(state="visible", timeout=15_000)
        password_input.wait_for(state="visible", timeout=15_000)

        email, password = credentials
        email_input.fill(email)
        password_input.fill(password)

        login_button = page.get_by_role("button", name="管理ログイン", exact=True)
        login_button.click()
        page.wait_for_timeout(3_000)

        clicked = _click_history_navigation(page)
        print(f"nav-click成功: {clicked}")
        if not clicked:
            page.goto(history_url, wait_until="domcontentloaded", timeout=60_000)

        csv_button = page.get_by_role("button", name="CSV出力", exact=True)
        csv_button.wait_for(state="visible", timeout=60_000)
        print("CSV出力ボタン: 表示確認OK")

        period_input = page.get_by_placeholder("期間を選択", exact=True)
        try:
            period_input.wait_for(state="attached", timeout=30_000)
            print("period_input attached: OK")
        except Exception as exc:
            print(f"period_input attached: 失敗 {type(exc).__name__}")
        count = period_input.count()
        print(f"period_input count: {count}")
        if count >= 1:
            info = period_input.first.evaluate(
                "el => ({"
                "display: getComputedStyle(el).display,"
                "visibility: getComputedStyle(el).visibility,"
                "w: el.offsetWidth, h: el.offsetHeight"
                "})"
            )
            print(f"period_input[0] state: {info}")

        # placeholderが同じ複数要素がないか、全input要素も走査する。
        all_inputs = page.locator("input").all()
        print(f"page内のinput要素数: {len(all_inputs)}")
        for index, item in enumerate(all_inputs):
            try:
                placeholder = item.get_attribute("placeholder")
                box = item.bounding_box()
                visible = item.is_visible()
            except Exception as exc:
                print(f"  input[{index}]: evaluate失敗 {type(exc).__name__}")
                continue
            if placeholder == "期間を選択":
                print(f"  input[{index}] placeholder={placeholder!r} visible={visible} box={box}")

        page.wait_for_timeout(3_000)
        context.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
