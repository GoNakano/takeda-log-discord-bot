# Takeda-Log Discord Bot

塾の入退室管理システム「Takeda-Log」の登下校履歴を自動で取得し、Discordのスラッシュコマンドから生徒ごとの直近1週間の入退室状況を確認できるようにするPython製Botです。

2026年7月29日から塾の本番Discordサーバーで稼働しています。前身は外部APIを使っていた [nyutai-discord-bot](https://github.com/GoNakano/nyutai-discord-bot) で、入退室管理システムの変更によりAPIが使えなくなったため、データ取得の仕組みを作り直しました。

## できること

- `/log 生徒名` … 部分一致で生徒を検索し、選択した生徒の直近1週間の入退室時刻・滞在時間・合計時間をEmbedで表示
- `/status` … Botが稼働しているか、CSVが最後にいつ更新されたかを表示（個人情報は出さない）
- 監視通知 … CSVの更新が60分以上止まると、管理者本人のDMにだけ警告を送り、復旧時にも通知

## 仕組み

```text
                    Oracle Cloud Always Free（VM.Standard.E2.1.Micro / Oracle Linux 9）
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │  systemd timer（10分ごと）                                                    │
 │     └─ takeda-log-updater.service（単発実行）                                 │
 │          └─ Xvfb（仮想画面）上の Chromium を Playwright で操作                  │
 │               1. 保存済みのセッション（Cookie）で Takeda-Log を開く             │
 │               2. 「登下校履歴」→ 期間に直近7日を指定 → 「CSV出力」              │
 │               3. CSV の形式を検証し、正しい場合だけ最新版と差し替える            │
 │                                   │                                          │
 │                                   ▼  data/latest.csv（所有者のみ読める）       │
 │  takeda-log-bot.service（常駐・停止時は自動再起動）                            │
 │     └─ discord.py: /log /status、15分ごとの健全性チェック                      │
 └──────────────────────────────────────────────────────────────────────────────┘
```

CSV取得とDiscord Botを別プロセスに分けているため、取得に失敗してもBotは前回の正常なデータで応答し続けます。

## 設計上の工夫

### APIがないシステムからデータを取る

開発時に利用可能な外部APIを確認できず、管理画面には期間を指定してCSVを出力する機能がありました。そこで、人が行う操作（ログイン → 登下校履歴 → 期間選択 → CSV出力）をPlaywrightで自動化しました。画面の表を読み取るのではなく、公式のCSV出力機能を使うことで、画面デザインの変化に比較的強くしています。

### 壊れたデータで上書きしない

ログイン切れやエラーのとき、CSVの代わりに空ファイルやエラーページが保存される可能性があります。取得したファイルはいったん一時ファイルに保存し、`csv_store.py` で列名・日時形式・文字コードを検証してから `os.replace` で差し替えます。検証に失敗した場合は前回の正常なCSVがそのまま残ります。

### ログインを連打しない

認証に失敗した場合は `.auth-required` という停止マーカーを作り、以後は人が再ログインするまで自動取得を止めます。短時間に何度もログインを試みてアカウントがロックされることを防ぐためです。

### 保存済みセッションを優先する

本番では、Macで作成したPlaywrightの保存済みセッション（`.takeda-auth.json`）をサーバーへ転送して利用します。設定値がそろっている場合は自動ログインも1回だけ試せる実装ですが、Oracle上では安定運用を確認できていないため、通常運用の前提にはしていません。セッションが切れた場合はMacで再ログインし、認証状態を更新します。

### 完全無料で常時稼働させる

GCE（外部IPv4が有料）やCloudflare Workers（大幅な作り直しが必要）と比較し、既存のPythonコードをほぼそのまま使えるOracle Cloud Always Freeを選びました。東京リージョンのA1（ARM）インスタンスは在庫不足で作成できなかったため、Always Free対象のE2.1.Micro（実メモリ約500MB）で動かしています。メモリが少ないため、ブラウザを常駐させず10分ごとに起動・終了する方式にしています。

### クラウド上でだけ起きる不具合への対処

同じコードがMacでは動くのにOracle上では失敗する問題がありました。調べると、期間選択欄の高さがOracle上でだけ0pxになり、クリックできなくなっていました。自動化ツール（Playwright/Selenium）やOS（Oracle Linux/Ubuntu）、フォント、画面サイズ、ブラウザのバージョンを変えても再現しました。送信元のネットワーク環境は有力な仮説の1つですが、根本原因は未確定です。現在は、操作前に要素の寸法をJavaScriptで復元する方法で回避しています（`takeda_updater.py` の `_select_period`）。

### 月をまたぐ期間

直近7日間が月をまたぐと、カレンダーに目的の日付が表示されていない状態になります。日付が見つからない場合はカレンダーを前後の月へ送って探すようにしています（`_find_date_cell`）。月末・月初の両方のパターンで確認済みです。

## 使用技術

- Python 3.9 / discord.py / Playwright / python-dotenv
- Oracle Cloud Infrastructure（Always Free、VM.Standard.E2.1.Micro、Oracle Linux 9）
- systemd（service / timer）、Xvfb
- pytest / unittest

## ファイル構成

```text
.
├── bot.py                    Discord Bot（/log, /status, 監視通知）
├── csv_store.py              CSVの読み込み・検証・直近7日の抽出
├── takeda_updater.py         Takeda-LogからのCSV自動取得（Playwright）
├── requirements.txt
├── .env.example              設定項目の見本（実際の値は含まない）
├── deploy/
│   ├── oracle-e2/systemd/    本番で使っているsystemd設定
│   ├── oracle/               開発途中のA1（ARM）向け導入スクリプト（参考）
│   └── gce/                  開発途中のGCE試験用スクリプト（参考）
├── launchd/                  開発初期にMacで常時起動していたときの設定（参考）
├── diagnostics/              Oracle上の不具合を切り分けたときの診断スクリプト
├── tests/                    自動テスト
├── *.command                 Macで初回設定・再ログインなどをダブルクリックで行うスクリプト
└── setup_config.py ほか      上記.commandから呼ばれる設定用スクリプト
```

## セットアップの概要

1. `.env.example` を `.env` にコピーし、Discord Bot Token、Takeda-Logの登下校履歴画面など必要な設定を行う（`.env` は権限600にする）
2. `python -m pip install -r requirements.txt` と `python -m playwright install chromium`
3. Macで `python takeda_updater.py --login` を実行して `.takeda-auth.json` を作り、安全な方法でサーバーへ転送する（Gitには追加しない）
4. `python takeda_updater.py --force` で1回取得できることを確認する
5. `deploy/oracle-e2/systemd/` のユニットを `/etc/systemd/system/` に配置し、`takeda-log-bot.service` と `takeda-log-updater.timer` を有効化する

## 設定項目（.env）

| 項目 | 内容 |
|---|---|
| `DISCORD_TOKEN` | Discord BotのToken |
| `TAKEDA_HISTORY_URL` | Takeda-Logの登下校履歴画面のURL |
| `TAKEDA_LOGIN_EMAIL` / `TAKEDA_LOGIN_PASSWORD` | 任意の自動ログイン用。失敗時は停止し、本番運用では保存済みセッションを優先 |
| `UPDATE_START_HOUR` / `UPDATE_END_HOUR` | 取得する時間帯（本番は9〜23時） |
| `DISCORD_ALERT_USER_ID` | 監視通知を送る相手（1人のDMのみ） |
| `ALERT_AFTER_MINUTES` / `ALERT_REPEAT_HOURS` | 異常とみなす時間（60分）と再通知間隔（6時間） |

## セキュリティ

- Token、パスワード、セッション（`.takeda-auth.json`）、ブラウザプロフィール、CSVはGitの管理対象外
- CSVと認証ファイルはサーバー上で所有者のみ読める権限（600）
- 生徒名やCSVの内容はログに出さない。`/status` も更新時刻だけを表示する
- CSVは直近7日分だけを保持し、Discordへ添付しない
- 監視通知は指定した1人のDMにのみ送る

## テスト

```bash
python -m pytest tests
```

`tests/test_takeda_updater.py` の一部は、ログイン画面が切り替わらない場合の待機時間を実時間で確認するため、完了まで数分かかります。

2026年9月22日の記録では36件中35件が成功し、1件（自動ログイン画面を模したモック）が失敗しています。本番で使用する保存済みセッション経路とは別ですが、テスト全件成功には未到達です。
