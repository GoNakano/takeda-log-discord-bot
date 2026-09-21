"""Seleniumで同じ現象が起きるか切り分けるための一時診断スクリプト。

認証情報の値は一切表示しない。記録するのは要素のサイズ等の安全な
技術情報のみ（生徒名・CSV内容は扱わない）。
"""

from __future__ import annotations

import os
import time

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By


def main() -> int:
    load_dotenv()
    email = os.getenv("TAKEDA_LOGIN_EMAIL", "").strip()
    password = os.getenv("TAKEDA_LOGIN_PASSWORD", "")
    history_url = os.getenv("TAKEDA_HISTORY_URL", "").strip()
    if not email or not password or not history_url:
        print("credentials/URL not configured")
        return 2

    options = webdriver.ChromeOptions()
    binary_location = os.getenv("SELENIUM_CHROME_BINARY", "").strip()
    if binary_location:
        options.binary_location = binary_location
    if os.getenv("SELENIUM_HEADLESS", "").strip() == "1":
        options.add_argument("--headless=new")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(history_url)

        staff_button = None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            buttons = driver.find_elements(By.XPATH, "//button[contains(., '校舎担当者')]")
            if buttons:
                staff_button = buttons[0]
                break
            time.sleep(0.5)
        if staff_button is None:
            print("staff button not found")
            return 1
        staff_button.click()

        deadline = time.monotonic() + 15
        email_input = None
        while time.monotonic() < deadline:
            inputs = driver.find_elements(By.CSS_SELECTOR, "input[placeholder='メールアドレス']")
            if inputs:
                email_input = inputs[0]
                break
            time.sleep(0.5)
        if email_input is None:
            print("email input not found")
            return 1
        password_input = driver.find_elements(By.CSS_SELECTOR, "input[placeholder='パスワード']")[0]
        email_input.send_keys(email)
        password_input.send_keys(password)

        login_button = driver.find_elements(By.XPATH, "//button[contains(., '管理ログイン')]")[0]
        login_button.click()
        time.sleep(3)

        deadline = time.monotonic() + 30
        nav_link = None
        while time.monotonic() < deadline:
            links = driver.find_elements(By.XPATH, "//*[contains(text(), '登下校履歴')]")
            if links:
                nav_link = links[0]
                break
            time.sleep(0.5)
        if nav_link is not None:
            nav_link.click()
        else:
            driver.get(history_url)

        deadline = time.monotonic() + 30
        csv_button = None
        while time.monotonic() < deadline:
            buttons = driver.find_elements(By.XPATH, "//button[contains(., 'CSV出力')]")
            if buttons:
                csv_button = buttons[0]
                break
            time.sleep(0.5)
        print(f"CSV出力ボタン発見: {csv_button is not None}")

        time.sleep(5)
        period_inputs = driver.find_elements(By.CSS_SELECTOR, "input[placeholder='期間を選択']")
        print(f"period_input count: {len(period_inputs)}")
        if period_inputs:
            info = driver.execute_script(
                "const el = arguments[0];"
                "const cs = getComputedStyle(el);"
                "return {display: cs.display, visibility: cs.visibility,"
                " w: el.offsetWidth, h: el.offsetHeight};",
                period_inputs[0],
            )
            print(f"period_input state: {info}")
        time.sleep(2)
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
