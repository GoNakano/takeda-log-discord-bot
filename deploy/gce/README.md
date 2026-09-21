# GCE無料試験用

このフォルダは、Takeda-Log Discord BotをGoogle Compute Engineで試験運用するためのものです。

## 無料優先の固定条件

- マシンタイプ: `e2-micro`
- リージョン: Oregon `us-west1`
- ゾーン: `us-west1-b`
- OS: Debian 12
- ディスク: `pd-standard` 10GB
- GPU / TPU: 使用しない
- VM: 1台だけ
- Google Cloud Marketplace: 使用しない
- Cloud NAT、ロードバランサ、固定IP: 使用しない

作成スクリプトは、マシンタイプ、ディスク種別、ディスク容量が条件外の場合に停止します。

## 料金上の注意

Google CloudのCompute Engine無料枠には、対象米国リージョンの`e2-micro` 1台と標準ディスク30GBが含まれます。ただしBotがDiscordとTakeda-Logへ接続するための外部IPv4は別料金です。2026-07-17時点のGoogle公式料金は、標準VMで使用中の外部IPv4が1時間あたり`$0.005`です。

外部IPv6は無料ですが、2026-07-17時点でDiscordとTakeda-Logの接続先にIPv6 DNSレコードがないため、IPv6だけの構成にはできません。したがって、無料トライアル終了後のGCE常時運用は完全無料になりません。

新規アカウントの無料トライアル中は、無料クレジット内で試験します。無料トライアルを有料アカウントへアップグレードしない限り、自動課金されない状態で確認します。無料トライアル終了前に、無料のMac運用へ戻すか、外部IPv4料金を承認してGCEを継続するかを必ず判断します。

## Macで先に行うこと

1. 新しいDiscord Bot Tokenを`.env`へ保存する。
2. Takeda-Logへ専用Chromeで手動ログインする。
3. `python takeda_updater.py --force`でCSV取得を確認する。
4. Discordで`/status`と`/log`を確認する。
5. `python prepare_gce_bundle.py`で転送ファイルを作る。

転送ファイルは`dist/takeda-log-bot-gce.tar.gz`です。Tokenとログイン情報を含むため、GitHubへ置かず、GCE導入後にMacとCloud Shellから削除します。

## 明日Cloud Shellで行うこと

1. 新しいGoogleアカウントでGoogle Cloudへログインする。
2. 無料トライアル中であることを画面で確認する。
3. Cloud Shellを開き、転送ファイルと`deploy_from_cloud_shell.sh`をアップロードする。
4. 次を実行する。

```bash
chmod +x deploy_from_cloud_shell.sh
FREE_TRIAL_CONFIRMED=YES ./deploy_from_cloud_shell.sh PROJECT_ID takeda-log-bot-gce.tar.gz
```

完了後、Discordで`/status`を実行し、10分以上経っても更新が続くか確認します。
