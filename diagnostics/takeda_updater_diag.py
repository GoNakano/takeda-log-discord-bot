"""ログイン失敗の原因切り分け専用の一時診断スクリプト。

安全のため、記録するのは接続先ドメイン・リソース種類・HTTPステータス・
エラー種別・想定パス一致の真偽・読込時間・メモリ空き容量だけ。
ページ本文・CSV・生徒名・認証情報・クエリ文字列は一切記録しない。
ログイン試行は1回だけで、失敗しても再試行しない。
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from takeda_updater import (  # noqa: E402
    _automatic_login_credentials,
    _browser_launch_options,
    _download_headless,
    _require_env,
)

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "diag-login.log"
HARD_TIMEOUT_SECONDS = 380
# 診断1回目の実測: domcontentloaded後もBubble.io系SPAの読み込み・
# 内部リダイレクトが150秒以上続くことを確認した。ボタン探索の猶予は
# スクリプト起動時刻ではなく、ページ遷移が落ち着き始めた後から測る。
BUTTON_SEARCH_SECONDS = 200
START = time.monotonic()


def _log(line: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    text = f"[{timestamp}] {line}"
    print(text, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")
    os.chmod(LOG_PATH, 0o600)


def _safe_path(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def _mem_available_mi() -> str:
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    kib = int(line.split()[1])
                    return f"{kib // 1024}Mi"
    except OSError:
        pass
    return "不明"


def _memory_sampler(stop_event: threading.Event) -> None:
    while not stop_event.wait(5):
        elapsed = time.monotonic() - START
        _log(f"MEM +{elapsed:6.2f}s available={_mem_available_mi()}")


def main() -> int:
    load_dotenv()

    credentials = _automatic_login_credentials()
    if credentials is None:
        _log("credentials: NOT CONFIGURED (aborting, no attempt made)")
        return 2
    _log("credentials: present (email+password both set) — values not logged")

    history_url = _require_env("TAKEDA_HISTORY_URL")
    target = urlsplit(history_url)

    from playwright.sync_api import sync_playwright

    stop_event = threading.Event()
    sampler = threading.Thread(target=_memory_sampler, args=(stop_event,), daemon=True)
    sampler.start()

    try:
        with sync_playwright() as playwright:
            launch_options = _browser_launch_options(headless=_download_headless())
            browser = playwright.chromium.launch(**launch_options)
            context = browser.new_context(
                accept_downloads=True, locale="ja-JP", timezone_id="Asia/Tokyo"
            )
            page = context.new_page()

            def on_request(request):
                elapsed = time.monotonic() - START
                netloc = urlsplit(request.url).netloc
                _log(f"REQUEST +{elapsed:6.2f}s {request.resource_type:10s} {netloc}")

            def on_response(response):
                elapsed = time.monotonic() - START
                netloc = urlsplit(response.url).netloc
                _log(f"RESPONSE +{elapsed:6.2f}s status={response.status} {netloc}")

            def on_requestfailed(request):
                elapsed = time.monotonic() - START
                netloc = urlsplit(request.url).netloc
                failure = request.failure or "不明"
                _log(
                    f"REQUEST_FAILED +{elapsed:6.2f}s {request.resource_type:10s} "
                    f"{netloc} error={failure}"
                )

            def on_console(msg):
                elapsed = time.monotonic() - START
                _log(f"CONSOLE +{elapsed:6.2f}s type={msg.type}")

            def on_pageerror(error):
                elapsed = time.monotonic() - START
                _log(f"PAGEERROR +{elapsed:6.2f}s type={type(error).__name__}")

            def on_frame_navigated(frame):
                if frame != page.main_frame:
                    return
                elapsed = time.monotonic() - START
                path_match = urlsplit(frame.url).path == target.path
                _log(
                    f"NAVIGATED +{elapsed:6.2f}s path_match={path_match} "
                    f"path={_safe_path(frame.url)}"
                )

            page.on("request", on_request)
            page.on("response", on_response)
            page.on("requestfailed", on_requestfailed)
            page.on("console", on_console)
            page.on("pageerror", on_pageerror)
            page.on("framenavigated", on_frame_navigated)

            try:
                _log(f"GOTO history_url path={_safe_path(history_url)}")
                page.goto(history_url, wait_until="domcontentloaded", timeout=60_000)

                staff_button = page.get_by_role("button", name="校舎担当者", exact=True)
                email_input = page.get_by_placeholder("メールアドレス", exact=True)
                password_input = page.get_by_placeholder("パスワード", exact=True)

                search_start = time.monotonic()
                deadline = search_start + BUTTON_SEARCH_SECONDS
                clicked = False
                while time.monotonic() < deadline:
                    if email_input.count() == 1 and password_input.count() == 1:
                        break
                    if not clicked and staff_button.count() == 1:
                        _log(
                            f"STATE staff_button found (count=1) at +{time.monotonic()-START:.2f}s, clicking"
                        )
                        staff_button.click()
                        clicked = True
                        try:
                            email_input.wait_for(state="visible", timeout=30_000)
                            password_input.wait_for(state="visible", timeout=30_000)
                        except Exception:
                            pass
                        break
                    page.wait_for_timeout(1_000)

                if email_input.count() != 1 or password_input.count() != 1:
                    _log(
                        f"RESULT login form not reachable within {BUTTON_SEARCH_SECONDS}s of settling "
                        f"(email_count={email_input.count()} password_count={password_input.count()} "
                        f"staff_button_clicked={clicked})"
                    )
                    return 1
                _log("STATE login form visible (email_count=1 password_count=1)")

                email, password = credentials
                email_input.fill(email)
                password_input.fill(password)
                _log("STATE credentials filled")

                login_button = page.get_by_role("button", name="管理ログイン", exact=True)
                if login_button.count() != 1:
                    _log(f"RESULT login button count={login_button.count()} (not unique)")
                    return 1

                login_page_url = page.url
                login_button.click()
                _log("STATE login button clicked")

                login_deadline = time.monotonic() + 60
                while time.monotonic() < login_deadline:
                    email_visible = email_input.count() == 1 and email_input.is_visible()
                    password_visible = password_input.count() == 1 and password_input.is_visible()
                    if page.url != login_page_url:
                        _log(f"STATE page.url changed at +{time.monotonic()-START:.2f}s (no forced goto needed)")
                        break
                    if not (email_visible and password_visible):
                        _log(
                            f"STATE login fields hidden at +{time.monotonic()-START:.2f}s "
                            "(url unchanged — SPA client-side transition suspected)"
                        )
                        break
                    page.wait_for_timeout(500)
                else:
                    _log("RESULT login screen did not change within 60s after click")
                    return 1

                _log(
                    f"STATE about to force page.goto(history_url) at +{time.monotonic()-START:.2f}s"
                )
                pre_goto_path_match = urlsplit(page.url).path == target.path
                _log(f"STATE pre-goto path_match={pre_goto_path_match}")

                if not pre_goto_path_match:
                    page.goto(history_url, wait_until="domcontentloaded", timeout=60_000)
                    _log(
                        f"STATE post-goto path_match="
                        f"{urlsplit(page.url).path == target.path}"
                    )

                period_input = page.get_by_placeholder("期間を選択", exact=True)
                try:
                    period_input.wait_for(state="visible", timeout=90_000)
                    _log("RESULT SUCCESS period_input visible — history screen reached")
                    return 0
                except Exception:
                    _log(
                        "RESULT FAILURE period_input not visible, "
                        f"final path={_safe_path(page.url)}"
                    )
                    return 1
            finally:
                elapsed = time.monotonic() - START
                _log(f"DONE total_elapsed={elapsed:.2f}s")
                context.close()
                browser.close()
    finally:
        stop_event.set()


if __name__ == "__main__":
    import signal

    def _on_alarm(signum, frame):
        _log("HARD TIMEOUT reached — aborting diagnostic run (no retry)")
        os._exit(3)

    signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(HARD_TIMEOUT_SECONDS)
    raise SystemExit(main())
