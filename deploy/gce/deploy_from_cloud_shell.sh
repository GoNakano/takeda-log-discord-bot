#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ID="${1:-}"
ARCHIVE="${2:-takeda-log-bot-gce.tar.gz}"
ZONE="us-west1-b"
REGION="us-west1"
INSTANCE="takeda-log-discord-bot"
NETWORK="takeda-log-net"
SUBNET="takeda-log-subnet"

if [[ -z "$PROJECT_ID" ]]; then
    echo "使い方: FREE_TRIAL_CONFIRMED=YES $0 GoogleCloudのプロジェクトID [転送ファイル]" >&2
    exit 1
fi
if [[ "${FREE_TRIAL_CONFIRMED:-}" != "YES" ]]; then
    echo "無料トライアル中であることを確認してから実行してください。" >&2
    exit 1
fi
if [[ ! -f "$ARCHIVE" ]]; then
    echo "転送ファイルがCloud Shellにありません: $ARCHIVE" >&2
    exit 1
fi

gcloud config set project "$PROJECT_ID"
gcloud services enable compute.googleapis.com iap.googleapis.com

if ! gcloud compute networks describe "$NETWORK" >/dev/null 2>&1; then
    gcloud compute networks create "$NETWORK" \
        --subnet-mode=custom \
        --bgp-routing-mode=regional
fi
if ! gcloud compute networks subnets describe "$SUBNET" --region="$REGION" >/dev/null 2>&1; then
    gcloud compute networks subnets create "$SUBNET" \
        --network="$NETWORK" \
        --region="$REGION" \
        --range=10.20.0.0/24 \
        --enable-private-ip-google-access
fi

if ! gcloud compute instances describe "$INSTANCE" --zone="$ZONE" >/dev/null 2>&1; then
    gcloud compute instances create "$INSTANCE" \
        --zone="$ZONE" \
        --machine-type=e2-micro \
        --provisioning-model=STANDARD \
        --image-family=debian-12 \
        --image-project=debian-cloud \
        --boot-disk-size=10GB \
        --boot-disk-type=pd-standard \
        --network="$NETWORK" \
        --subnet="$SUBNET" \
        --network-tier=STANDARD \
        --no-service-account \
        --no-scopes \
        --metadata=enable-oslogin=TRUE \
        --tags=takeda-log-bot \
        --shielded-secure-boot \
        --shielded-vtpm \
        --shielded-integrity-monitoring \
        --labels=app=takeda-log-bot,cost-profile=free-trial
fi

if ! gcloud compute firewall-rules describe allow-iap-ssh-takeda-log-bot >/dev/null 2>&1; then
    gcloud compute firewall-rules create allow-iap-ssh-takeda-log-bot \
        --network="$NETWORK" \
        --action=ALLOW \
        --rules=tcp:22 \
        --source-ranges=35.235.240.0/20 \
        --target-tags=takeda-log-bot
fi

MACHINE_TYPE="$(gcloud compute instances describe "$INSTANCE" --zone="$ZONE" --format='value(machineType.basename())')"
DISK_SIZE="$(gcloud compute disks describe "$INSTANCE" --zone="$ZONE" --format='value(sizeGb)')"
DISK_TYPE="$(gcloud compute disks describe "$INSTANCE" --zone="$ZONE" --format='value(type.basename())')"
if [[ "$MACHINE_TYPE" != "e2-micro" || "$DISK_SIZE" -gt 30 || "$DISK_TYPE" != "pd-standard" ]]; then
    echo "無料枠条件外のVM設定を検出したため停止します。" >&2
    exit 1
fi

gcloud compute scp "$ARCHIVE" "$INSTANCE:~/takeda-log-bot-gce.tar.gz" \
    --zone="$ZONE" \
    --tunnel-through-iap
gcloud compute ssh "$INSTANCE" \
    --zone="$ZONE" \
    --tunnel-through-iap \
    --command='if [ -d ~/takeda-log-discord-bot ]; then mv ~/takeda-log-discord-bot ~/takeda-log-discord-bot.backup.$(date +%Y%m%d%H%M%S); fi && mkdir -p ~/takeda-log-discord-bot && tar -xzf ~/takeda-log-bot-gce.tar.gz -C ~/takeda-log-discord-bot --strip-components=1 && chmod +x ~/takeda-log-discord-bot/deploy/gce/*.sh && ~/takeda-log-discord-bot/deploy/gce/install_on_vm.sh && rm -f ~/takeda-log-bot-gce.tar.gz'

echo "GCEへの導入が完了しました。"
echo "無料トライアル終了前に、Mac継続かGCE継続かを必ず再判断してください。"
