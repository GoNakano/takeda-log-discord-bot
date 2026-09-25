from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

from csv_store import AttendanceRecord, CsvFormatError, load_snapshot


load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID", "").strip()
# コマンドを受け付けるサーバーID（カンマ区切り）。未設定ならDISCORD_GUILD_IDを使う。
# 設定されている場合、他のサーバーやDMからのコマンドは拒否する。
ALLOWED_GUILD_IDS_RAW = (
    os.getenv("DISCORD_ALLOWED_GUILD_IDS", "").strip() or DISCORD_GUILD_ID
)
CSV_PATH = Path(os.getenv("TAKEDA_CSV_PATH", "data/latest.csv")).expanduser()

# 監視通知は、ここで指定した1人のDMだけへ送る。未設定なら通知しない。
ALERT_USER_ID = os.getenv("DISCORD_ALERT_USER_ID", "").strip()
# CSVがこの分数以上更新されていなければ異常とみなす。
ALERT_AFTER_MINUTES = int(os.getenv("ALERT_AFTER_MINUTES", "60"))
# 異常が続く間、この間隔を空けて再通知する（鳴らしっぱなしを避ける）。
ALERT_REPEAT_HOURS = int(os.getenv("ALERT_REPEAT_HOURS", "6"))
# 開校時間外はCSVが更新されないため、監視も行わない。
ALERT_START_HOUR = int(os.getenv("UPDATE_START_HOUR", "9"))
ALERT_END_HOUR = int(os.getenv("UPDATE_END_HOUR", "23"))


def parse_guild_ids(raw: str) -> frozenset[int]:
    """カンマ区切りのサーバーIDを読み取る。数字以外が含まれていればValueError。"""

    guild_ids = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            raise ValueError(f"サーバーIDは数字だけで設定してください: {part}")
        guild_ids.add(int(part))
    return frozenset(guild_ids)


def is_allowed_guild(guild_id: int | None, allowed_guild_ids: frozenset[int]) -> bool:
    """許可リストが空なら全て許可する。設定済みなら、そのサーバー内だけ許可する（DMは拒否）。"""

    if not allowed_guild_ids:
        return True
    return guild_id is not None and guild_id in allowed_guild_ids


try:
    ALLOWED_GUILD_IDS = parse_guild_ids(ALLOWED_GUILD_IDS_RAW)
except ValueError:
    ALLOWED_GUILD_IDS = frozenset()  # main()で起動を止める。


class GuildRestrictedTree(app_commands.CommandTree):
    """許可していないサーバーやDMからのスラッシュコマンドを拒否する。"""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_allowed_guild(interaction.guild_id, ALLOWED_GUILD_IDS):
            return True
        print(f"許可していない場所からのコマンドを拒否しました（guild_id={interaction.guild_id}）")
        await interaction.response.send_message(
            "このBotは許可されたサーバーでのみ利用できます。",
            ephemeral=True,
        )
        return False


intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents, tree_cls=GuildRestrictedTree)


def create_status_message(updated_at: datetime, *, now: datetime | None = None) -> str:
    reference_time = now or datetime.now()
    age = max(reference_time - updated_at, timedelta())
    age_minutes = int(age.total_seconds() // 60)
    updated_text = updated_at.strftime("%Y/%m/%d %H:%M")

    if age_minutes <= 20:
        return f"✅ Botはオンラインです。CSV最終更新: {updated_text}（{age_minutes}分前）"
    return f"⚠️ Botはオンラインですが、CSV更新が古くなっています。最終更新: {updated_text}（{age_minutes}分前）"


def create_log_embed(
    student_id: str,
    student_name: str,
    records: tuple[AttendanceRecord, ...],
    updated_at: datetime,
) -> discord.Embed | None:
    student_logs = [record for record in records if record.student_id == student_id]
    if not student_logs:
        return None

    grouped_logs: dict[int, dict[int, list[AttendanceRecord]]] = defaultdict(
        lambda: defaultdict(list)
    )
    total_minutes = 0

    for record in sorted(student_logs, key=lambda item: item.entrance_time):
        grouped_logs[record.entrance_time.year][record.entrance_time.month].append(record)
        if record.duration_minutes is not None:
            total_minutes += record.duration_minutes

    message_lines = [
        f"**直近1週間の合計滞在時間: {total_minutes // 60}時間{total_minutes % 60}分**\n"
    ]
    weekday_map = ["月", "火", "水", "木", "金", "土", "日"]

    for year in sorted(grouped_logs):
        message_lines.append(f"**{year}年**")
        for month in sorted(grouped_logs[year]):
            message_lines.append(f"**{month}月**")
            for record in grouped_logs[year][month]:
                entrance = record.entrance_time
                weekday = weekday_map[entrance.weekday()]
                end_text = record.exit_time.strftime("%H:%M") if record.exit_time else "未退室"

                if record.duration_minutes is None:
                    duration_text = "滞在中"
                else:
                    duration_text = (
                        f"{record.duration_minutes // 60}時間"
                        f"{record.duration_minutes % 60}分"
                    )

                message_lines.append(
                    f"{entrance.day}日（{weekday}） {duration_text} "
                    f"{entrance.strftime('%H:%M')} → {end_text}"
                )

    embed = discord.Embed(
        title=f"{student_name} の入退室ログ",
        description="\n".join(message_lines),
        color=discord.Color.teal(),
    )
    embed.set_footer(
        text=(
            f"最終更新: {updated_at.strftime('%Y/%m/%d %H:%M')} | "
            "powered by Takeda-Log × Discord Bot"
        )
    )
    return embed


class StudentSelectView(discord.ui.View):
    def __init__(
        self,
        student_list: list[tuple[str, str]],
        records: tuple[AttendanceRecord, ...],
        updated_at: datetime,
    ) -> None:
        super().__init__(timeout=60)
        self.records = records
        self.updated_at = updated_at

        # DiscordのSelectは1つにつき25件まで。
        for index in range(0, len(student_list), 25):
            options = [
                discord.SelectOption(label=student_name, value=student_id)
                for student_id, student_name in student_list[index : index + 25]
            ]
            self.add_item(StudentSelect(options, self.records, self.updated_at))


class StudentSelect(discord.ui.Select):
    def __init__(
        self,
        options: list[discord.SelectOption],
        records: tuple[AttendanceRecord, ...],
        updated_at: datetime,
    ) -> None:
        super().__init__(
            placeholder="生徒を選んでください",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.records = records
        self.updated_at = updated_at

    async def callback(self, interaction: discord.Interaction) -> None:
        student_id = self.values[0]
        student_name = next(
            (option.label for option in self.options if option.value == student_id),
            "Unknown",
        )
        embed = create_log_embed(
            student_id,
            student_name,
            self.records,
            self.updated_at,
        )

        if embed:
            await interaction.response.send_message(embed=embed, ephemeral=False)
        else:
            await interaction.response.send_message(
                "該当ログがありません。",
                ephemeral=False,
            )


@bot.tree.command(name="log", description="直近1週間の入退室ログを表示します")
@app_commands.describe(name="生徒名を入力してください（必須）")
async def log(interaction: discord.Interaction, name: str) -> None:
    await interaction.response.defer(thinking=True, ephemeral=False)

    try:
        snapshot = load_snapshot(CSV_PATH)
    except FileNotFoundError:
        await interaction.followup.send(
            "Takeda-LogのCSVがまだ取得されていません。",
            ephemeral=False,
        )
        return
    except CsvFormatError:
        await interaction.followup.send(
            "Takeda-LogのCSV形式を確認できませんでした。管理者へ連絡してください。",
            ephemeral=False,
        )
        return

    student_map = snapshot.student_map
    filtered = [
        (student_id, student_name)
        for student_id, student_name in student_map.items()
        if name in student_name
    ]

    if not filtered:
        await interaction.followup.send(
            f"「{name}」に一致する直近1週間の記録が見つかりませんでした。",
            ephemeral=False,
        )
        return

    filtered.sort(key=lambda item: item[1])
    filtered = filtered[:25]

    view = StudentSelectView(filtered, snapshot.records, snapshot.updated_at)
    await interaction.followup.send(
        "生徒を選んでください：",
        view=view,
        ephemeral=False,
    )


@bot.tree.command(name="status", description="BotとCSV更新の状態を確認します")
async def status(interaction: discord.Interaction) -> None:
    try:
        snapshot = load_snapshot(CSV_PATH)
    except FileNotFoundError:
        message = "⚠️ Botはオンラインですが、CSVはまだ取得されていません。"
    except CsvFormatError:
        message = "⚠️ Botはオンラインですが、CSV形式を確認できません。"
    else:
        message = create_status_message(snapshot.updated_at)

    await interaction.response.send_message(message, ephemeral=True)


def diagnose_csv_health(*, now: datetime | None = None) -> tuple[bool, str]:
    """CSVの健全性を判定する。戻り値は(正常か, 説明文)。"""

    reference_time = now or datetime.now()
    try:
        snapshot = load_snapshot(CSV_PATH)
    except FileNotFoundError:
        return False, "CSVがまだ一度も取得できていません。"
    except CsvFormatError:
        return False, "CSVの形式を確認できません。取得処理が壊れている可能性があります。"

    age_minutes = int(
        max(reference_time - snapshot.updated_at, timedelta()).total_seconds() // 60
    )
    if age_minutes >= ALERT_AFTER_MINUTES:
        updated_text = snapshot.updated_at.strftime("%Y/%m/%d %H:%M")
        return False, (
            f"CSVが{age_minutes}分間更新されていません。"
            f"（最終更新: {updated_text}）\n"
            "Takeda-Logのセッション切れ、または取得処理の停止が考えられます。"
        )
    return True, ""


# 直前に通知した時刻と、異常状態が続いているかを覚えておく。
_alert_state: dict[str, object] = {"last_sent": None, "in_alert": False}


async def _send_alert_dm(message: str) -> None:
    if not ALERT_USER_ID:
        return
    try:
        user = await bot.fetch_user(int(ALERT_USER_ID))
        await user.send(message)
    except Exception as exc:  # DM拒否設定などで失敗してもBot本体は止めない。
        print(f"監視通知の送信に失敗: {type(exc).__name__}")


@tasks.loop(minutes=15)
async def monitor_csv_health() -> None:
    if not ALERT_USER_ID:
        return

    now = datetime.now()
    # 開校時間外は更新されないので監視しない（開始直後の猶予も見る）。
    if not (ALERT_START_HOUR < now.hour < ALERT_END_HOUR):
        return

    healthy, detail = diagnose_csv_health(now=now)
    last_sent = _alert_state.get("last_sent")

    if healthy:
        if _alert_state.get("in_alert"):
            _alert_state["in_alert"] = False
            _alert_state["last_sent"] = None
            await _send_alert_dm("✅ Takeda-Log Bot: CSVの自動更新が復旧しました。")
        return

    # 異常時は初回に通知し、その後はALERT_REPEAT_HOURSごとに再通知する。
    if last_sent is not None:
        elapsed_hours = (now - last_sent).total_seconds() / 3600
        if elapsed_hours < ALERT_REPEAT_HOURS:
            return

    _alert_state["in_alert"] = True
    _alert_state["last_sent"] = now
    await _send_alert_dm(f"⚠️ Takeda-Log Bot からのお知らせ\n\n{detail}")


@monitor_csv_health.before_loop
async def _before_monitor() -> None:
    await bot.wait_until_ready()


@bot.event
async def on_guild_join(guild: discord.Guild) -> None:
    # 許可リスト外のサーバーに追加された場合は、そのサーバーから退出する。
    if is_allowed_guild(guild.id, ALLOWED_GUILD_IDS):
        return
    print(f"許可していないサーバーに追加されたため退出します（guild_id={guild.id}）")
    await guild.leave()


@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    if not ALLOWED_GUILD_IDS:
        print("警告: DISCORD_ALLOWED_GUILD_IDSが未設定のため、全てのサーバーからのコマンドを受け付けます。")
    if ALERT_USER_ID and not monitor_csv_health.is_running():
        monitor_csv_health.start()
        print("CSV監視を開始しました（通知先: 指定ユーザーのDMのみ）")
    try:
        if DISCORD_GUILD_ID:
            guild = discord.Object(id=int(DISCORD_GUILD_ID))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            sync_scope = "test guild"
        else:
            synced = await bot.tree.sync()
            sync_scope = "global"
        print(f"Synced {len(synced)} commands ({sync_scope}).")
    except Exception as exc:  # Discord側の接続エラーをターミナルへ記録する。
        print(f"Failed to sync commands: {exc}")


def main() -> None:
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKENが設定されていません。")
    if DISCORD_GUILD_ID and not DISCORD_GUILD_ID.isdigit():
        raise RuntimeError("DISCORD_GUILD_IDは数字だけで設定してください。")
    try:
        parse_guild_ids(ALLOWED_GUILD_IDS_RAW)
    except ValueError as exc:
        raise RuntimeError(f"DISCORD_ALLOWED_GUILD_IDSの形式が正しくありません。{exc}") from exc
    if ALERT_USER_ID and not ALERT_USER_ID.isdigit():
        raise RuntimeError("DISCORD_ALERT_USER_IDは数字だけで設定してください。")
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
