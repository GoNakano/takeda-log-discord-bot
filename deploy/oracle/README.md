# Oracle Always Free導入手順

既存のPython版Discord BotとPlaywright取得処理を、完全無料のOracle Cloud Always Freeで常時動かすための手順です。

## 無料固定条件

- アカウント: Free Tierのまま使用し、Pay As You Goへアップグレードしない
- ホームリージョン: Japan East (Tokyo)
- シェイプ: `VM.Standard.A1.Flex`
- OCPU: 1
- メモリ: 4GB
- OS: Ubuntu 24.04 ARM64
- ブートボリューム: 50GB
- GPU、ロードバランサ、NAT Gateway、有料バックアップ: 使用しない
- VM: 1台だけ

インストールスクリプトはOracleのインスタンス情報を直接確認します。A1・1 OCPU・4GB以下でなければ、依存ソフトを入れる前に停止します。

## Macで準備する

1. Discord Developer Portalで、以前チャットへ貼ったTokenをReset Tokenする。
2. `Discord Tokenだけ更新.command`を実行し、新しいTokenだけを保存する。
3. `Takeda-Log自動ログイン設定.command`を実行し、専用アカウントのメールアドレスとパスワードを非表示で保存する。
4. Macのログイン状態を使わない自動ログイン・CSV取得テストが成功したことを確認する。
5. `Oracle用転送ファイルを作る.command`を実行する。
6. `dist`内に2ファイルができたことだけ確認する。中身は開かない。

転送ファイルにはDiscord TokenとTakeda-Log専用アカウントの認証情報が含まれます。GitHub、Discord、メールには置きません。MacのブラウザCookieやCSVは含めません。

## OracleでVMを作る

1. Oracle Cloud Free Tierアカウントを作る。
2. 有料アカウントへアップグレードしない。
3. Computeのインスタンス作成を開く。
4. `VM.Standard.A1.Flex`、1 OCPU、4GBを選ぶ。
5. Ubuntu 24.04 ARM64と50GBブートボリュームを選ぶ。
6. Always Free対象であることを画面上で確認してから作成する。
7. SSHは作業時だけ自分の接続元IPから許可し、Web用ポートは開けない。

A1の空きがない場合は有料シェイプを選ばず、時間を置いて再試行します。

## 秘密ファイルを転送して導入する

VMへSSH接続できる状態で、Macの`dist`にある2ファイルだけをVMへ転送します。転送後、VM上で次を実行します。

```bash
chmod 700 install_on_oracle.sh
./install_on_oracle.sh takeda-log-bot-oracle.tar.gz
```

スクリプトは無料条件を確認してから、Python、Chromium、仮想画面、systemdを設定し、CSV取得を1回試します。成功後にBotと10分更新を自動起動します。転送に使った圧縮ファイルはVMから削除されます。

## 動作確認

VM上では次を実行します。

```bash
~/takeda-log-discord-bot/deploy/oracle/check_status.sh
```

Discordでは次を確認します。

1. `/status`でBotがオンラインになる。
2. 10分以上待ち、CSV最終更新が進む。
3. `/log`で自分のテストサーバーに直近1週間が表示される。
4. VMを再起動し、5分以内にBotと更新処理が戻る。

## セキュリティ

- VMにはDiscord/Takeda-Logからの受信ポートを開けない。
- `.env`、`.takeda-auth.json`、CSVは所有者だけが読める権限にする。
- CSVはGitHub、Oracle Object Storage、Discordへ添付しない。
- ログへ生徒名、CSV内容、Token、URLを出さない。
- 認証切れ時は専用アカウントで1回だけ自動ログインする。
- 自動ログインに失敗した場合はマーカーを作り、自動アクセスを停止する。
- 認証情報を変更した場合はMacで`.env`を更新し、新しい転送ファイルで安全に差し替える。

## 無料運用の監視

- Oracle Cost Analysisが0円であることを導入直後と月1回確認する。
- Always Free以外のリソースを作らない。
- OCI Monitoringでインスタンス停止のメール通知を作る。
- Always Free枠内の暗号化済みブートボリュームバックアップを1つだけ保持する。
- Oracleの無料条件が変更された場合、有料継続せずBotを停止する。

Oracleは7日間低負荷のAlways Free VMを回収する場合があります。ブラウザをログイン維持のため常駐させ、systemdと5分監視でアプリ停止には自動復旧します。VM自体が回収された場合は、バックアップから無料VMを作り直します。
