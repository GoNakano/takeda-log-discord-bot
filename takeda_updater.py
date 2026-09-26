from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from time import monotonic, sleep
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv

from csv_store import CsvFormatError, load_snapshot


class AuthenticationRequired(RuntimeError):
    """Takeda-Logへの再ログインまたは認証情報の修正が必要な場合に送出する。"""


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"環境変数{name}が設定されていません。")
    return value


def _within_update_window(now: datetime) -> bool:
    start_hour = int(os.getenv("UPDATE_START_HOUR", "10"))
    end_hour = int(os.getenv("UPDATE_END_HOUR", "22"))
    return time(start_hour, 0) <= now.time() <= time(end_hour, 0)


def _date_cell_selector(target: date) -> str:
    # Air Datepickerの月は0始まり。
    return (
        '.air-datepicker.-active- '
        f'.air-datepicker-cell[data-year="{target.year}"]'
        f'[data-month="{target.month - 1}"]'
        f'[data-date="{target.day}"]'
    )


def _write_metadata(path: Path, *, date_from: date, date_to: date, row_count: int) -> None:
    metadata_path = path.with_suffix(".state.json")
    temporary_path = metadata_path.with_suffix(".tmp")
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "row_count": row_count,
    }
    temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temporary_path, 0o600)
    os.replace(temporary_path, metadata_path)


def _browser_channel() -> str | None:
    channel = os.getenv("TAKEDA_BROWSER_CHANNEL", "chromium").strip().lower()
    if channel in {"", "chromium", "bundled"}:
        return None
    return channel


def _low_memory_launch_args() -> list[str]:
    # Oracle E2（実RAM約500MB）でXvfb+Chromiumを安定させるための最小限の引数。
    # --disable-gpu/--disable-software-rasterizerはWebGLを完全に無効化し、
    # ヘッドレス/自動操作ブラウザの強い指標として検知され得るため外す。
    return [
        "--disable-dev-shm-usage",
        "--disable-background-networking",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-extensions",
        "--no-first-run",
        "--js-flags=--max-old-space-size=400",
    ]


def _browser_launch_options(*, headless: bool) -> dict[str, object]:
    options: dict[str, object] = {"headless": headless, "args": _low_memory_launch_args()}
    channel = _browser_channel()
    if channel is not None:
        options["channel"] = channel
    return options


def _download_headless() -> bool:
    # Takeda-Logはheadless Chromiumでは履歴URLが200でも期間欄を描画しない。
    # MacのGUIセッション上では専用ブラウザを短時間だけ表示して取得する。
    value = os.getenv("TAKEDA_DOWNLOAD_HEADLESS", "false").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _automatic_login_credentials() -> tuple[str, str] | None:
    email = os.getenv("TAKEDA_LOGIN_EMAIL", "").strip()
    password = os.getenv("TAKEDA_LOGIN_PASSWORD", "")
    if not email and not password:
        return None
    if not email or not password:
        raise RuntimeError(
            "Takeda-Logのメールアドレスとパスワードを両方設定してください。"
        )
    return email, password


def _open_login_context(playwright, profile_dir: Path):
    profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        accept_downloads=True,
        locale="ja-JP",
        timezone_id="Asia/Tokyo",
        **_browser_launch_options(headless=False),
    )


def _profile_has_browser_state(profile_dir: Path) -> bool:
    if not profile_dir.is_dir():
        return False
    return any(path.name != ".auth-required" for path in profile_dir.iterdir())


def _apply_stealth(context) -> None:
    # Takeda-Logはfingerprintjs2等で自動操作を検知しており、navigator.webdriver
    # がtrueだと期間選択欄などの一部UIが意図的に機能しなくなることが実機比較で判明した。
    # ページのスクリプト実行前にwebdriverフラグを隠す。
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    )


def _apply_cdnjs_workaround(context) -> None:
    # Takeda-Logはcdnjs.com（cdnjs.cloudflare.comの別名）を直接参照しており、
    # ChromeのORB（Opaque Response Blocking）でスクリプト取得がブロックされる。
    # 同じパスをcdnjs.cloudflare.comへ差し替えて取得し直すことで回避する。
    def handler(route):
        request = route.request
        parsed = urlsplit(request.url)
        if parsed.netloc != "cdnjs.com":
            route.continue_()
            return
        fixed_url = urlunsplit(("https", "cdnjs.cloudflare.com", parsed.path, parsed.query, ""))
        try:
            response = route.fetch(url=fixed_url)
            route.fulfill(response=response)
        except Exception:
            route.continue_()

    context.route("https://cdnjs.com/**", handler)


def _open_download_context(
    playwright,
    profile_dir: Path,
    auth_state_path: Path | None = None,
):
    context_options = {
        "accept_downloads": True,
        "locale": "ja-JP",
        "timezone_id": "Asia/Tokyo",
    }
    launch_options = _browser_launch_options(headless=_download_headless())

    if _profile_has_browser_state(profile_dir):
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            **context_options,
            **launch_options,
        )
        _apply_stealth(context)
        _apply_cdnjs_workaround(context)
        return None, context

    # storage_stateはOS固有のChromiumプロフィールと違い、MacからLinuxへ移せる。
    if auth_state_path is not None and auth_state_path.is_file():
        browser = playwright.chromium.launch(**launch_options)
        context = browser.new_context(
            storage_state=str(auth_state_path),
            **context_options,
        )
        _apply_stealth(context)
        _apply_cdnjs_workaround(context)
        return browser, context

    # OracleではMacのブラウザ状態を移さず、空のブラウザから必要時だけ自動ログインする。
    if _automatic_login_credentials() is not None:
        browser = playwright.chromium.launch(**launch_options)
        context = browser.new_context(**context_options)
        _apply_stealth(context)
        _apply_cdnjs_workaround(context)
        return browser, context

    raise AuthenticationRequired(
        "Takeda-Logのログイン情報がありません。自動ログイン設定または--loginを実行してください。"
    )


def _save_auth_state(context, auth_state_path: Path) -> None:
    auth_state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary_path = auth_state_path.with_suffix(".tmp")
    # 認証トークンがIndexedDBに保存されるシステムにも対応する。
    context.storage_state(path=str(temporary_path), indexed_db=True)
    os.chmod(temporary_path, 0o600)
    os.replace(temporary_path, auth_state_path)


def _auth_required_marker(profile_dir: Path) -> Path:
    return profile_dir / ".auth-required"


def _mark_authentication_required(profile_dir: Path) -> None:
    profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = _auth_required_marker(profile_dir)
    marker.write_text(
        "Takeda-Logへの手動再ログインが必要です。\n",
        encoding="utf-8",
    )
    os.chmod(marker, 0o600)


def _clear_authentication_required(profile_dir: Path) -> None:
    _auth_required_marker(profile_dir).unlink(missing_ok=True)


def _try_automatic_login(page, history_url: str) -> bool:
    credentials = _automatic_login_credentials()
    if credentials is None:
        return False

    staff_button = page.get_by_role("button", name="校舎担当者", exact=True)
    email_input = page.get_by_placeholder("メールアドレス", exact=True)
    password_input = page.get_by_placeholder("パスワード", exact=True)

    # Oracle E2（実RAM約500MB）ではTakeda-Log（Bubble.io製SPA）の初期描画・
    # 内部リダイレクトが2分以上かかることが実測で確認された。
    # ログイン画面と確認できるまで待ち、認証情報の送信を急がない。
    deadline = monotonic() + 280
    while monotonic() < deadline:
        if email_input.count() == 1 and password_input.count() == 1:
            break
        if staff_button.count() == 1:
            staff_button.click()
            email_input.wait_for(state="visible", timeout=60_000)
            password_input.wait_for(state="visible", timeout=60_000)
            break
        page.wait_for_timeout(500)

    # ログイン画面だと確認できた場合だけ認証情報を送る。
    if email_input.count() != 1 or password_input.count() != 1:
        return False

    email, password = credentials
    email_input.fill(email)
    password_input.fill(password)

    login_button = page.get_by_role("button", name="管理ログイン", exact=True)
    if login_button.count() != 1:
        return False
    login_page_url = page.url
    login_button.click()

    # 低スペックVMではログイン通信に数十秒かかることがある。
    # 固定1秒後に履歴URLへ移動すると、認証通信を中断してしまう。
    login_deadline = monotonic() + 200
    while monotonic() < login_deadline:
        email_visible = email_input.count() == 1 and email_input.is_visible()
        password_visible = password_input.count() == 1 and password_input.is_visible()
        if page.url != login_page_url or not (email_visible and password_visible):
            break
        page.wait_for_timeout(500)
    else:
        raise AuthenticationRequired(
            "Takeda-Logのログイン画面が時間内に切り替わりませんでした。"
            "認証情報を確認してください。"
        )

    # 「期間を選択」欄はプレースホルダー属性でうまく特定できないことがある。
    # CSV出力ボタンは画面上で確実に存在が確認できているため、到達判定は
    # こちらを基準にする（実際のCSV取得時にも同じボタンを使う）。
    csv_button = page.get_by_role("button", name="CSV出力", exact=True)

    # BubbleなどSPA系サイトは、認証直後のURLへブラウザの完全な再読み込みで
    # 直接ジャンプすると正しく初期化されないことがある。
    # まずログイン後の画面自体が持つナビゲーションリンクを探してクリックし、
    # 見つからない場合だけ従来どおりURLへ強制遷移する。
    if _click_history_navigation(page):
        try:
            csv_button.wait_for(state="visible", timeout=250_000)
            return True
        except Exception:
            pass

    page.goto(history_url, wait_until="domcontentloaded", timeout=60_000)

    try:
        csv_button.wait_for(state="visible", timeout=280_000)
    except Exception as exc:
        # 1回失敗したら認証マーカーを作ってサービスを止め、ロックを避ける。
        raise AuthenticationRequired(
            "Takeda-Logへ自動ログインできなかったため、自動取得を停止しました。"
            "認証情報を確認してください。"
        ) from exc
    return True


_HISTORY_NAV_KEYWORDS = ("登下校履歴", "履歴", "登下校", "入退室", "出席", "打刻")


def _dump_nav_labels(page) -> None:
    """ナビゲーション特定のため、リンク/ボタンのラベル名だけを記録する。

    画面構成が変わって履歴ページへの導線が見つからないときの調査用。
    生徒名やCSV内容など個人情報は含まない、サイト固定のUI文言のみを記録する。
    """

    try:
        texts = page.locator("a, button").all_inner_texts()
    except Exception as exc:
        print(f"NAVラベル取得失敗: {type(exc).__name__}")
        return

    seen: set[str] = set()
    labels: list[str] = []
    for text in texts:
        label = " ".join(text.split()).strip()[:24]
        if label and label not in seen:
            seen.add(label)
            labels.append(label)

    print(f"NAVラベル一覧（{len(labels)}件、重複除去済み、最大24文字）:")
    for label in labels[:60]:
        print(f"  - {label!r}")


def _click_history_navigation(page) -> bool:
    """ログイン後の画面自体のナビゲーションから履歴ページへの導線を探す。

    ラベル名（ナビゲーション項目の名称）のみを記録し、個人情報は扱わない。
    """

    _dump_nav_labels(page)

    for role in ("link", "button"):
        for keyword in _HISTORY_NAV_KEYWORDS:
            candidate = page.get_by_role(role, name=keyword)
            try:
                count = candidate.count()
            except Exception:
                continue
            if count == 1:
                print(f"NAV候補発見: role={role} keyword={keyword}")
                try:
                    candidate.click(timeout=60_000)
                    return True
                except Exception as exc:
                    print(f"NAVクリック失敗: role={role} keyword={keyword} error={type(exc).__name__}")
                    continue
    print("NAV候補見つからず。URL強制遷移にフォールバックします。")
    return False


def _history_page(context, history_url: str):
    # Chromiumの初回案内や復元タブに横取りされないよう、操作専用タブを毎回作る。
    page = context.new_page()
    page.bring_to_front()
    response = page.goto(history_url, wait_until="domcontentloaded", timeout=60_000)

    # 「期間を選択」欄はプレースホルダー属性でうまく特定できないことがある。
    # CSV出力ボタンは画面上で確実に存在が確認できているため、到達判定は
    # こちらを基準にする。
    csv_button = page.get_by_role("button", name="CSV出力", exact=True)
    try:
        csv_button.wait_for(state="visible", timeout=280_000)
    except Exception as exc:
        if _try_automatic_login(page, history_url):
            return page
        current = urlsplit(page.url)
        target = urlsplit(history_url)
        if page.url.startswith("chrome://"):
            location = "ブラウザの初期画面"
        elif current.netloc != target.netloc:
            location = "ログイン先など別サイト"
        elif current.path != target.path:
            location = "Takeda-Log内の別画面"
        else:
            location = "登下校履歴URL"
        status = response.status if response is not None else "不明"
        raise AuthenticationRequired(
            "Takeda-Logのログイン状態を確認できません。"
            f"（到達先: {location}、HTTP状態: {status}）"
            "自動ログイン設定または--loginを実行してください。"
        ) from exc
    if csv_button.count() != 1:
        raise RuntimeError("CSV出力ボタンを一意に特定できませんでした。")
    return page


def _period_input_state(period_input) -> str:
    count = period_input.count()
    if count != 1:
        return f"count={count}"
    try:
        info = period_input.evaluate(
            "el => ({"
            "display: getComputedStyle(el).display,"
            "visibility: getComputedStyle(el).visibility,"
            "opacity: getComputedStyle(el).opacity,"
            "w: el.offsetWidth,"
            "h: el.offsetHeight"
            "})"
        )
    except Exception as exc:
        return f"count=1 evaluate失敗={type(exc).__name__}"
    return f"count=1 {info}"


def _find_date_cell(page, target: date, *, max_months: int = 3):
    """カレンダー上で目的の日付セルを探す。

    月をまたぐ期間（例: 7/27〜8/2）では、目的の日が別の月にあり
    現在表示中のカレンダーには存在しない。その場合はカレンダーを
    前後に送りながら探す。見つからなければNoneを返す。

    月初は開始日が前月（戻る方向）、終了日が当月になり、
    月末は終了日が翌月（進む方向）になるため、両方向に対応する。
    """

    selector = _date_cell_selector(target)

    def _visible_cell():
        cell = page.locator(selector)
        return cell if cell.count() == 1 else None

    found = _visible_cell()
    if found is not None:
        return found

    # まず翌月方向、次に前月方向へ探索する（現在位置へ戻してから反対方向へ）。
    for action, label, steps in (
        ("next", "翌月", max_months),
        ("prev", "前月", max_months * 2),
    ):
        button = page.locator(
            f".air-datepicker.-active- .air-datepicker-nav--action[data-action='{action}']"
        )
        if button.count() != 1:
            continue
        for step in range(1, steps + 1):
            button.click()
            page.wait_for_timeout(1_500)
            found = _visible_cell()
            if found is not None:
                print(f"カレンダーを{label}方向へ{step}回送って対象日を見つけました。")
                return found
    return None


def _select_period(page, date_from: date, date_to: date) -> None:
    period_input = page.get_by_placeholder("期間を選択", exact=True)

    # 実測により、この<input>自体はheight:0で意図的に非表示化されており、
    # 見た目のグレーの箱（クリック対象）は親要素が担っていることが判明した。
    # 値の読み取り(input_value)にはこのinputを使い、クリックは親要素へ行う。
    period_input.wait_for(state="attached", timeout=200_000)
    print(f"期間入力欄の状態: {_period_input_state(period_input)}")

    # この環境ではページ側スクリプトが入力欄の高さを0に計算してしまい、
    # 通常のクリックでカレンダーを開けない。実寸をこちらから復元してから操作する。
    period_input.evaluate(
        "el => {"
        "el.style.setProperty('height', '45px', 'important');"
        "el.style.setProperty('min-height', '45px', 'important');"
        "el.style.setProperty('width', '328px', 'important');"
        "const p = el.parentElement;"
        "if (p) {"
        "p.style.setProperty('height', '45px', 'important');"
        "p.style.setProperty('min-height', '45px', 'important');"
        "}"
        "}"
    )
    print(f"高さ強制適用後: {_period_input_state(period_input)}")

    period_wrapper = period_input.locator("xpath=..")
    # 座標計算に依存しないJS直接click()を試し、失敗時のみ従来方式にフォールバックする。
    try:
        period_wrapper.evaluate("el => el.click()")
    except Exception:
        period_wrapper.click(timeout=60_000)

    # クリックが効かない場合に備え、入力欄自身へのfocus/クリックも試す。
    try:
        period_input.evaluate(
            "el => { el.focus(); el.click(); "
            "el.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); "
            "el.dispatchEvent(new MouseEvent('mouseup', {bubbles: true})); }"
        )
    except Exception as exc:
        print(f"入力欄への直接操作に失敗: {type(exc).__name__}")

    # カレンダー部品自体がページ内に生成されているかを切り分ける。
    datepicker_count = page.locator(".air-datepicker").count()
    active_count = page.locator(".air-datepicker.-active-").count()
    print(f"カレンダー要素数: 全体={datepicker_count} アクティブ={active_count}")

    # 低スペックVMではカレンダーの描画自体に時間がかかることがあるため、
    # 個別の日付セルを探す前にカレンダー本体の出現を待つ。
    calendar = page.locator(".air-datepicker.-active-")
    try:
        calendar.wait_for(state="visible", timeout=60_000)
        print("カレンダー表示: 成功")
    except Exception:
        print(
            "カレンダー表示: 確認できず（そのまま日付セルを探索します）"
            f" 再確認: 全体={page.locator('.air-datepicker').count()}"
            f" アクティブ={page.locator('.air-datepicker.-active-').count()}"
        )

    expected_from = date_from.strftime("%Y/%m/%d")
    expected_to = date_to.strftime("%Y/%m/%d")

    def wait_for_value(*tokens: str, timeout_ms: int = 5_000) -> str:
        deadline = monotonic() + timeout_ms / 1_000
        selected = period_input.input_value()
        while monotonic() < deadline:
            if all(token in selected for token in tokens):
                return selected
            page.wait_for_timeout(100)
            selected = period_input.input_value()
        return selected

    first_cell = _find_date_cell(page, date_from)
    if first_cell is None:
        raise RuntimeError("期間選択の開始日を一意に特定できませんでした。")
    first_cell.click()
    if expected_from not in wait_for_value(expected_from):
        raise RuntimeError("CSV出力期間の開始日を設定できませんでした。")

    # 開始日と終了日が別の月にまたがる場合、終了日のセルはまだ描画されていない。
    # その場合はカレンダーを次の月へ送ってから探す。
    second_cell = _find_date_cell(page, date_to)
    if second_cell is None:
        raise RuntimeError("期間選択の終了日を一意に特定できませんでした。")
    second_cell.click()
    selected_value = wait_for_value(expected_from, expected_to)
    if expected_from not in selected_value or expected_to not in selected_value:
        raise RuntimeError("CSV出力期間を正しく設定できませんでした。")


def _download_with_context(
    context,
    *,
    history_url: str,
    csv_path: Path,
    auth_state_path: Path,
    now: datetime,
) -> None:
    date_to = now.date()
    date_from = date_to - timedelta(days=6)
    page = None
    temporary_path: Path | None = None

    try:
        page = _history_page(context, history_url)
        _select_period(page, date_from, date_to)

        csv_button = page.get_by_role("button", name="CSV出力", exact=True)
        if csv_button.count() != 1:
            raise RuntimeError("CSV出力ボタンを一意に特定できませんでした。")

        with page.expect_download(timeout=60_000) as download_info:
            csv_button.click()

        download = download_info.value
        with tempfile.NamedTemporaryFile(
            prefix="takeda-log-",
            suffix=".csv",
            dir=csv_path.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

        download.save_as(str(temporary_path))
        snapshot = load_snapshot(temporary_path, today=date_to)
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, csv_path)
        temporary_path = None
        _write_metadata(
            csv_path,
            date_from=date_from,
            date_to=date_to,
            row_count=len(snapshot.records),
        )
        _save_auth_state(context, auth_state_path)
        print(
            f"CSV更新完了: {date_from.isoformat()}〜{date_to.isoformat()} "
            f"({len(snapshot.records)}件)"
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        if page is not None:
            page.close()


def _update_interval_seconds() -> int:
    try:
        minutes = int(os.getenv("UPDATE_INTERVAL_MINUTES", "10"))
    except ValueError as exc:
        raise RuntimeError("UPDATE_INTERVAL_MINUTESは整数で設定してください。") from exc
    if not 5 <= minutes <= 60:
        raise RuntimeError("UPDATE_INTERVAL_MINUTESは5〜60分で設定してください。")
    return minutes * 60


def _runtime_paths() -> tuple[str, Path, Path, Path]:
    history_url = _require_env("TAKEDA_HISTORY_URL")
    csv_path = Path(os.getenv("TAKEDA_CSV_PATH", "data/latest.csv")).expanduser().resolve()
    profile_dir = Path(os.getenv("TAKEDA_PROFILE_DIR", ".takeda-profile")).expanduser().resolve()
    auth_state_path = Path(
        os.getenv("TAKEDA_AUTH_STATE", ".takeda-auth.json")
    ).expanduser().resolve()
    csv_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    return history_url, csv_path, profile_dir, auth_state_path


def download_once(*, force: bool = False) -> int:
    load_dotenv()

    now = datetime.now()
    if not force and not _within_update_window(now):
        print("開校時間外のためCSV更新を行いません。")
        return 0

    history_url, csv_path, profile_dir, auth_state_path = _runtime_paths()

    if _auth_required_marker(profile_dir).exists():
        raise AuthenticationRequired(
            "自動取得は停止中です。--loginでTakeda-Logへ再ログインしてください。"
        )

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("playwrightがインストールされていません。") from exc

    with sync_playwright() as playwright:
        browser = None
        context = None
        try:
            try:
                browser, context = _open_download_context(
                    playwright,
                    profile_dir,
                    auth_state_path,
                )
            except AuthenticationRequired:
                _mark_authentication_required(profile_dir)
                raise
            _download_with_context(
                context,
                history_url=history_url,
                csv_path=csv_path,
                auth_state_path=auth_state_path,
                now=now,
            )
            return 0
        except PlaywrightTimeoutError as exc:
            raise RuntimeError("Takeda-Logの画面またはCSV出力が時間内に応答しませんでした。") from exc
        finally:
            if context is not None:
                context.close()
            if browser is not None:
                browser.close()


def run_forever() -> int:
    load_dotenv()
    history_url, csv_path, profile_dir, auth_state_path = _runtime_paths()
    interval_seconds = _update_interval_seconds()

    if _auth_required_marker(profile_dir).exists():
        raise AuthenticationRequired(
            "自動取得は停止中です。--loginでTakeda-Logへ再ログインしてください。"
        )

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("playwrightがインストールされていません。") from exc

    with sync_playwright() as playwright:
        while True:
            browser = None
            context = None
            try:
                browser, context = _open_download_context(
                    playwright,
                    profile_dir,
                    auth_state_path,
                )
                print("Takeda-Log自動更新を開始しました。")

                while True:
                    now = datetime.now()
                    if _within_update_window(now):
                        _download_with_context(
                            context,
                            history_url=history_url,
                            csv_path=csv_path,
                            auth_state_path=auth_state_path,
                            now=now,
                        )
                        sleep(interval_seconds)
                    else:
                        # ブラウザを維持したまま、開校時間外はTakeda-Logへアクセスしない。
                        sleep(min(interval_seconds, 60))
            except AuthenticationRequired:
                _mark_authentication_required(profile_dir)
                raise
            except KeyboardInterrupt:
                print("Takeda-Log自動更新を停止しました。")
                return 0
            except (PlaywrightTimeoutError, CsvFormatError, RuntimeError, OSError) as exc:
                print(
                    "CSV更新失敗。5分後にブラウザを再起動します。"
                    f"（種類: {type(exc).__name__}）",
                    file=sys.stderr,
                )
                sleep(300)
            finally:
                if context is not None:
                    context.close()
                if browser is not None:
                    browser.close()


def login_once() -> int:
    load_dotenv()
    history_url = _require_env("TAKEDA_HISTORY_URL")
    profile_dir = Path(os.getenv("TAKEDA_PROFILE_DIR", ".takeda-profile")).expanduser().resolve()
    auth_state_path = Path(
        os.getenv("TAKEDA_AUTH_STATE", ".takeda-auth.json")
    ).expanduser().resolve()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("playwrightがインストールされていません。") from exc

    with sync_playwright() as playwright:
        context = _open_login_context(playwright, profile_dir)
        try:
            page = context.new_page()
            page.bring_to_front()
            page.goto(history_url, wait_until="domcontentloaded", timeout=60_000)
            print("専用ブラウザでTakeda-Logへログインしてください。")
            input("登下校履歴画面が表示されたら、ターミナルでEnterを押してください: ")
            if page.get_by_placeholder("期間を選択", exact=True).count() != 1:
                raise AuthenticationRequired("登下校履歴画面を確認できませんでした。")
            _save_auth_state(context, auth_state_path)
            _clear_authentication_required(profile_dir)
            print("ログイン状態を専用プロフィールと移行用認証ファイルへ保存しました。")
            return 0
        finally:
            context.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Takeda-LogのCSVを安全に更新します。")
    parser.add_argument("--login", action="store_true", help="初回ログイン用ブラウザを開く")
    parser.add_argument("--force", action="store_true", help="開校時間外でも1回更新する")
    parser.add_argument("--loop", action="store_true", help="ブラウザを維持して定期更新する")
    args = parser.parse_args()

    try:
        if args.login:
            return login_once()
        if args.loop:
            return run_forever()
        return download_once(force=args.force)
    except AuthenticationRequired as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (CsvFormatError, RuntimeError, OSError) as exc:
        print(f"CSV更新失敗: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
