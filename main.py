import os
import re
import json
import time
import random
import asyncio
import unicodedata
from collections import defaultdict, deque
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

try:
    from openai import AsyncOpenAI
except Exception:
    AsyncOpenAI = None


# ============================================================
# Infinity Security • Made with ❤️ by Stilo
# ============================================================

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
REACTION_DIR = BASE_DIR / "assets" / "reactions"
DATA_PATH_ENV = os.getenv("DATA_PATH", "").strip()
DATA_PATH = Path(DATA_PATH_ENV) if DATA_PATH_ENV else (BASE_DIR / "infinity_data.json")
DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
AI_MODEL = os.getenv("AI_MODEL", "gpt-5-mini").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0") or 0)
ENV_CLAIM_USER_ID = int(os.getenv("CLAIM_USER_ID", "0") or 0)

DEFAULT_PREFIX = "!"
SPAM_WINDOW = 8
SPAM_LIMIT = 7
NUKE_WINDOW = 20
NUKE_LIMIT = 4
RAID_JOIN_WINDOW = 12
RAID_JOIN_LIMIT = 8
VOICE_BURST_WINDOW = 10
VOICE_BURST_LIMIT = 6

REACTION_FILES = {
    "raid_convoy": "raid_convoy.mp4",
    "limitless_burst": "limitless_burst.mp4",
    "six_eyes_calm": "six_eyes_calm.mp4",
    "purple_finish": "purple_finish.mp4",
    "purple_hands_extra": "purple_hands_extra.mp4",
}

DEFAULT_GUILD_CONFIG = {
    "log_channel_id": 0,
    "dispute_category_id": 0,
    "claim_user_id": ENV_CLAIM_USER_ID,
    "security_level": 2,
    "ai_enabled": True,
    "anti_spam": True,
    "anti_nuke": True,
    "raid_protection": True,
    "voice_protection": True,
    "honeypot_channel_id": 0,
    "protected_role_ids": [],
    "learned_server": [],
    "video_reactions": {
        "enabled": True,
        "cooldown_seconds": 20,
        "frequencies": {
            "normal": 65,
            "critical": 80,
            "raid": 85,
            "mediation": 65,
        },
        "clips": {
            "raid_convoy": {"enabled": True, "category": "raid"},
            "limitless_burst": {"enabled": True, "category": "critical"},
            "six_eyes_calm": {"enabled": True, "category": "mediation"},
            "purple_finish": {"enabled": True, "category": "critical"},
            "purple_hands_extra": {"enabled": True, "category": "critical"},
        },
        "sort": {
            "normal": ["six_eyes_calm"],
            "critical": ["limitless_burst", "purple_finish", "purple_hands_extra"],
            "raid": ["raid_convoy"],
            "mediation": ["six_eyes_calm"],
        },
    },
}

GOJO_LINES = [
    "Six Eyes online. 👁️",
    "Infinity is active. Nothing suspicious gets through.",
    "Domain Expansion: Unlimited Security. 🌀",
    "Relax. Infinity is watching the server.",
    "Security level increased. Gojo mode active.",
]

DISPUTE_WORDS = [
    "scam", "scammer", "gescammt", "betrüger", "betrueger",
    "halt die fresse", "hurensohn", "huso", "idiot", "opfer",
    "lügner", "luegner", "geklaut", "betrug", "abgezogen",
]

SEVERE_WORDS = [
    "kys", "kill yourself", "bring dich um",
]

SUSPICIOUS_WORDS = DISPUTE_WORDS + SEVERE_WORDS + [
    "drohung", "threat", "leak", "dox", "token", "raid", "nuke",
    "fick dich", "fuck you", "arschloch", "bastard",
]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.voice_states = True
intents.moderation = True

bot = commands.Bot(command_prefix=DEFAULT_PREFIX, intents=intents)
tree = bot.tree

AI_CLIENT = AsyncOpenAI(api_key=OPENAI_API_KEY) if (OPENAI_API_KEY and AsyncOpenAI) else None

message_buckets = defaultdict(lambda: deque(maxlen=30))
join_buckets = defaultdict(lambda: deque(maxlen=50))
voice_join_buckets = defaultdict(lambda: deque(maxlen=50))
nuke_buckets = defaultdict(lambda: deque(maxlen=30))
channel_context = defaultdict(lambda: deque(maxlen=10))
reaction_last_sent = defaultdict(float)
_views_added = False


def load_data():
    if not DATA_PATH.exists():
        return {"guilds": {}, "boss": {}, "global_learned": []}
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"guilds": {}, "boss": {}, "global_learned": []}


DATA = load_data()


def save_data():
    try:
        tmp = DATA_PATH.with_suffix(DATA_PATH.suffix + ".tmp")
        tmp.write_text(json.dumps(DATA, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(DATA_PATH)
    except Exception as exc:
        print("Could not save data:", exc)


def merge_defaults(target: dict, defaults: dict):
    for key, value in defaults.items():
        if key not in target:
            target[key] = deepcopy(value)
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            merge_defaults(target[key], value)
    return target


def guild_cfg(guild_id: int):
    gid = str(guild_id)
    DATA.setdefault("guilds", {})
    DATA["guilds"].setdefault(gid, {})
    merge_defaults(DATA["guilds"][gid], DEFAULT_GUILD_CONFIG)
    return DATA["guilds"][gid]


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9äöüÄÖÜß@#._\- ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def is_staff(member: discord.Member) -> bool:
    p = member.guild_permissions
    return p.administrator or p.manage_guild or p.manage_messages or p.moderate_members


def is_involved(interaction: discord.Interaction, participant_ids: set[int]) -> bool:
    if not participant_ids:
        return True
    if interaction.user.id in participant_ids:
        return True
    return isinstance(interaction.user, discord.Member) and is_staff(interaction.user)


async def owner_user():
    if OWNER_ID:
        try:
            return await bot.fetch_user(OWNER_ID)
        except Exception:
            pass
    try:
        app = await bot.application_info()
        return app.owner
    except Exception:
        return None


async def owner_dm(text: str):
    user = await owner_user()
    if not user:
        return
    try:
        await user.send(text[:1900])
    except Exception:
        pass


async def get_log_channel(guild: discord.Guild):
    cfg = guild_cfg(guild.id)
    channel = guild.get_channel(cfg.get("log_channel_id", 0))
    if isinstance(channel, discord.TextChannel):
        return channel

    preferred = {"infinity logs", "security logs", "infinity-logs", "security-logs", "logs"}
    for ch in guild.text_channels:
        if normalize_text(ch.name) in preferred:
            cfg["log_channel_id"] = ch.id
            save_data()
            return ch
    return None


async def log_event(guild: discord.Guild, title: str, description: str, color=discord.Color.blurple()):
    channel = await get_log_channel(guild)
    embed = discord.Embed(
        title=title,
        description=description[:3900],
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="Infinity Security • Made with ❤️ by Stilo")
    if channel:
        try:
            await channel.send(embed=embed)
        except Exception:
            pass


async def reaction_channel_for(guild: discord.Guild):
    ch = await get_log_channel(guild)
    if ch:
        return ch
    me = guild.me
    if me and guild.system_channel and guild.system_channel.permissions_for(me).send_messages:
        return guild.system_channel
    if me:
        for c in guild.text_channels:
            if c.permissions_for(me).send_messages:
                return c
    return None


def reaction_candidates(cfg: dict, category: str):
    vr = cfg["video_reactions"]
    clips_cfg = vr["clips"]
    ordered = vr.get("sort", {}).get(category, [])

    result = []
    for name in ordered:
        meta = clips_cfg.get(name, {})
        if meta.get("enabled") and meta.get("category") == category and name in REACTION_FILES:
            result.append(name)

    for name, meta in clips_cfg.items():
        if name not in result and meta.get("enabled") and meta.get("category") == category and name in REACTION_FILES:
            result.append(name)

    # Normal can reuse the calm mediation edit.
    if category == "normal" and not result:
        if clips_cfg.get("six_eyes_calm", {}).get("enabled"):
            result.append("six_eyes_calm")
    return result


async def send_video_reaction(
    guild: discord.Guild,
    category: str,
    channel=None,
    *,
    force: bool = False,
    clip_name: str | None = None,
):
    cfg = guild_cfg(guild.id)
    vr = cfg["video_reactions"]

    if not force and not vr.get("enabled", True):
        return False

    now = time.monotonic()
    cooldown = max(0, int(vr.get("cooldown_seconds", 20)))
    if not force and now - reaction_last_sent[guild.id] < cooldown:
        return False

    if not force:
        chance = int(vr.get("frequencies", {}).get(category, 65))
        if random.randint(1, 100) > max(0, min(chance, 100)):
            return False

    if clip_name:
        candidates = [clip_name] if clip_name in REACTION_FILES else []
    else:
        candidates = reaction_candidates(cfg, category)

    if not candidates:
        return False

    selected = random.choice(candidates)
    path = REACTION_DIR / REACTION_FILES[selected]
    if not path.exists():
        return False

    if channel is None:
        channel = await reaction_channel_for(guild)
    if channel is None:
        return False

    try:
        await channel.send(file=discord.File(path, filename=path.name))
        reaction_last_sent[guild.id] = now
        return True
    except Exception as exc:
        print("Video reaction failed:", exc)
        return False


async def safe_timeout(
    member: discord.Member,
    minutes: int,
    reason: str,
    *,
    source_channel=None,
    reaction_category: str = "critical",
):
    if member.bot or is_staff(member):
        return False
    try:
        until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        await member.timeout(until, reason=reason)
        await log_event(
            member.guild,
            "⏳ Timeout",
            f"{member.mention} • {minutes} min\nReason: {reason}",
            discord.Color.orange(),
        )
        await owner_dm(
            f"Infinity Security timeouted {member} ({member.id}) for {minutes} min "
            f"in {member.guild.name}. Reason: {reason}"
        )
        await send_video_reaction(member.guild, reaction_category, source_channel)
        return True
    except Exception:
        return False


async def ai_json(prompt: str):
    if not AI_CLIENT:
        return None
    try:
        response = await AI_CLIENT.responses.create(model=AI_MODEL, input=prompt)
        raw = (response.output_text or "").strip()
        match = re.search(r"\{.*\}", raw, re.S)
        if match:
            return json.loads(match.group(0))
    except Exception as exc:
        print("AI JSON error:", exc)
    return None


async def ai_text(prompt: str):
    if not AI_CLIENT:
        return None
    try:
        response = await AI_CLIENT.responses.create(model=AI_MODEL, input=prompt)
        return (response.output_text or "").strip()
    except Exception as exc:
        print("AI text error:", exc)
        return None


def suspicious_enough_for_ai(content: str) -> bool:
    text = normalize_text(content)
    if any(word in text for word in SUSPICIOUS_WORDS):
        return True
    if len(re.findall(r"[!?]", content)) >= 5:
        return True
    if content.count("<@") >= 4:
        return True
    return False


async def classify_message(message: discord.Message):
    txt = message.content[:2500]
    normalized = normalize_text(txt)

    if any(word in normalized for word in SEVERE_WORDS):
        return {
            "action": "timeout",
            "minutes": 30,
            "reason": "Severe harassment / self-harm encouragement",
            "dispute": True,
        }

    if not AI_CLIENT:
        if any(word in normalized for word in DISPUTE_WORDS):
            return {
                "action": "warn",
                "minutes": 0,
                "reason": "Possible dispute detected",
                "dispute": True,
            }
        return {"action": "none", "minutes": 0, "reason": "No issue detected", "dispute": False}

    key = (message.guild.id, message.channel.id)
    recent_context = "\n".join(channel_context[key])
    learned = guild_cfg(message.guild.id).get("learned_server", [])[-10:]
    global_learned = DATA.get("global_learned", [])[-10:]

    prompt = f"""
You are Infinity Security, a calm, context-aware Discord moderation classifier.
Do not overreact. Do not punish harmless jokes, friendly banter, normal bot chatter, or the word "owo".
AI moderation may timeout normal users, but should not auto-punish staff.
Accusations like "you scammed me" should normally start mediation instead of deciding who is right.

Recent channel context:
{recent_context}

Current message:
{message.author}: {txt}

Server notes:
{learned}

Global owner notes:
{global_learned}

Return ONLY JSON:
{{
  "action": "none" | "warn" | "timeout",
  "minutes": 0-60,
  "reason": "short factual reason",
  "dispute": true | false
}}

Use timeout only for clear severe harassment, threats, repeated targeted abuse, scam attempts, or obvious dangerous behavior.
If two people appear to be arguing, prefer dispute=true and warn rather than immediate punishment unless the behavior is clearly severe.
"""
    result = await ai_json(prompt)
    return result or {"action": "none", "minutes": 0, "reason": "AI unavailable", "dispute": False}


def counterpart_id(message: discord.Message):
    for mention in message.mentions:
        if mention.id != message.author.id and not mention.bot:
            return mention.id
    if message.reference and isinstance(message.reference.resolved, discord.Message):
        other = message.reference.resolved.author
        if other.id != message.author.id and not other.bot:
            return other.id
    return None


class DisputeView(discord.ui.View):
    def __init__(self, starter_id: int, other_id: int | None = None):
        super().__init__(timeout=300)
        self.starter_id = starter_id
        self.other_id = other_id
        self.participant_ids = {starter_id}
        if other_id:
            self.participant_ids.add(other_id)

    async def make_room(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        if not is_involved(interaction, self.participant_ids):
            await interaction.response.send_message("Only the involved users or staff can use this.", ephemeral=True)
            return

        guild = interaction.guild
        cfg = guild_cfg(guild.id)
        category = guild.get_channel(cfg.get("dispute_category_id", 0))
        if not isinstance(category, discord.CategoryChannel):
            category = discord.utils.find(
                lambda c: "dispute" in normalize_text(c.name), guild.categories
            )
        if not category:
            try:
                category = await guild.create_category("⚖️ INFINITY DISPUTES", reason="Infinity Security dispute system")
                cfg["dispute_category_id"] = category.id
                save_data()
            except Exception:
                category = None

        starter = guild.get_member(self.starter_id)
        other = guild.get_member(self.other_id) if self.other_id else None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                read_message_history=True,
            ),
        }
        for member in [starter, other]:
            if member:
                overwrites[member] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True, attach_files=True
                )

        try:
            channel = await guild.create_text_channel(
                name=f"dispute-{starter.name if starter else interaction.user.name}"[:90],
                category=category,
                overwrites=overwrites,
                reason="Infinity Security dispute room",
            )
        except Exception:
            await interaction.response.send_message("I couldn't create the private dispute room.", ephemeral=True)
            return

        embed = discord.Embed(
            title="⚖️ Infinity Dispute Room",
            description=(
                "Both sides: explain what happened calmly and send screenshots/evidence if available.\n\n"
                "Infinity will **not** instantly decide who is right. It compares both sides, separates facts from claims, "
                "asks for missing evidence, and proposes a solution."
            ),
            color=discord.Color.blurple(),
        )
        mentions = " ".join(m.mention for m in [starter, other] if m)
        await channel.send(content=mentions or None, embed=embed, view=DisputeCloseView())
        await interaction.response.send_message(f"Private dispute room created: {channel.mention}", ephemeral=True)
        await log_event(guild, "⚖️ Dispute room created", f"Opened by {interaction.user.mention} → {channel.mention}")
        await send_video_reaction(guild, "mediation", channel)

    @discord.ui.button(label="Yes • AI mediation", style=discord.ButtonStyle.success, emoji="✅")
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.make_room(interaction)

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger, emoji="❌")
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Declined.", ephemeral=True)
            return
        if not is_involved(interaction, self.participant_ids):
            await interaction.response.send_message("Only the involved users or staff can use this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await safe_timeout(
            interaction.user,
            1440,
            "AI dispute mediation declined; awaiting owner/mod review",
            source_channel=interaction.channel,
            reaction_category="critical",
        )
        await owner_dm(
            f"{interaction.user} declined AI dispute mediation in "
            f"{interaction.guild.name if interaction.guild else 'unknown guild'}. "
            "A 24h timeout was applied; use /untimeout after review."
        )
        await interaction.followup.send(
            "AI mediation declined. A 24h timeout was applied while the owner/mod team reviews the dispute.",
            ephemeral=True,
        )


class DisputeCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Ask Infinity to mediate",
        style=discord.ButtonStyle.primary,
        emoji="👁️",
        custom_id="inf_mediate",
    )
    async def mediate(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if not isinstance(interaction.channel, discord.TextChannel):
            return

        messages = []
        async for msg in interaction.channel.history(limit=80, oldest_first=True):
            if not msg.author.bot:
                attachment_note = ""
                if msg.attachments:
                    attachment_note = f" [attachments: {len(msg.attachments)}]"
                messages.append(f"{msg.author}: {msg.content}{attachment_note}")
        transcript = "\n".join(messages)[-14000:]

        prompt = f"""
You are Infinity Security mediating a Discord dispute.
Remain neutral. Never say someone is right just because they sound confident.
Do not invent what screenshots show if you cannot inspect them.
Produce:
1. each side's claim,
2. facts both appear to agree on,
3. disputed claims,
4. evidence that is present or still needed,
5. a calm proposed next step.

Transcript:
{transcript}
"""
        answer = await ai_text(prompt)
        if not answer:
            answer = (
                "AI is unavailable right now. Both sides should state: (1) what happened, "
                "(2) what evidence they have, and (3) what outcome they want. A moderator can then review it."
            )
        await interaction.followup.send(f"**Six Eyes mediation:**\n{answer[:1900]}")

    @discord.ui.button(
        label="Resolved",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="inf_resolved",
    )
    async def resolved(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel or not interaction.guild:
            return
        members = [m for m in interaction.channel.members if not m.bot and not is_staff(m)]
        for member in members[:2]:
            await safe_timeout(
                member,
                10,
                "Post-dispute cooldown after agreement",
                source_channel=interaction.channel,
                reaction_category="mediation",
            )
        await interaction.response.send_message(
            "Resolved. The involved users received the planned 10-minute cooldown. This room will close shortly."
        )
        await send_video_reaction(interaction.guild, "mediation", interaction.channel)
        await asyncio.sleep(4)
        try:
            await interaction.channel.delete(reason="Infinity dispute resolved")
        except Exception:
            pass

    @discord.ui.button(
        label="Close • no agreement",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="inf_noagreement",
    )
    async def no_agreement(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel or not interaction.guild:
            return
        members = [m for m in interaction.channel.members if not m.bot and not is_staff(m)]
        for member in members[:2]:
            await safe_timeout(
                member,
                30,
                "Dispute closed without agreement",
                source_channel=interaction.channel,
                reaction_category="critical",
            )
        await interaction.response.send_message(
            "No agreement reached. The involved users received a 30-minute cooldown."
        )
        await send_video_reaction(interaction.guild, "critical", interaction.channel)
        await asyncio.sleep(4)
        try:
            await interaction.channel.delete(reason="Infinity dispute closed without agreement")
        except Exception:
            pass


class SecurityPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Security status", style=discord.ButtonStyle.primary, emoji="🛡️")
    async def status(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = guild_cfg(interaction.guild.id)
        vr = cfg["video_reactions"]
        await interaction.response.send_message(
            f"**Infinity Security Level:** {cfg['security_level']}/5\n"
            f"AI: {'ON' if cfg['ai_enabled'] else 'OFF'}\n"
            f"Anti-Spam: {'ON' if cfg['anti_spam'] else 'OFF'}\n"
            f"Anti-Nuke: {'ON' if cfg['anti_nuke'] else 'OFF'}\n"
            f"Raid Protection: {'ON' if cfg['raid_protection'] else 'OFF'}\n"
            f"Video Reactions: {'ON' if vr['enabled'] else 'OFF'}",
            ephemeral=True,
        )

    @discord.ui.button(label="Lockdown", style=discord.ButtonStyle.danger, emoji="🔒")
    async def lockdown(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You need Manage Server.", ephemeral=True)
            return
        guild = interaction.guild
        await interaction.response.defer(ephemeral=True)
        changed = 0
        for channel in guild.text_channels:
            try:
                overwrite = channel.overwrites_for(guild.default_role)
                overwrite.send_messages = False
                await channel.set_permissions(guild.default_role, overwrite=overwrite, reason="Infinity Security lockdown")
                changed += 1
            except Exception:
                pass
        await log_event(
            guild,
            "🔒 LOCKDOWN",
            f"{interaction.user.mention} locked {changed} text channels.",
            discord.Color.red(),
        )
        await send_video_reaction(guild, "raid", interaction.channel)
        await interaction.followup.send(f"Locked {changed} channels.", ephemeral=True)

    @discord.ui.button(label="Gojo line", style=discord.ButtonStyle.secondary, emoji="👁️")
    async def gojo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(random.choice(GOJO_LINES), ephemeral=True)


class ContinueSupportView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Continue with AI",
        style=discord.ButtonStyle.primary,
        emoji="🤖",
        custom_id="inf_continue_ai",
    )
    async def continue_ai(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "AI support is active again. Send your next message and Infinity will continue helping.",
            ephemeral=True,
        )


class JJKView(discord.ui.View):
    def __init__(self, player_id: int):
        super().__init__(timeout=60)
        self.player_id = player_id
        self.hp = 100
        self.enemy_hp = 100

    async def check(self, interaction):
        if interaction.user.id != self.player_id:
            await interaction.response.send_message("This fight belongs to someone else.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Blue", style=discord.ButtonStyle.primary, emoji="🔵")
    async def blue(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check(interaction):
            return
        damage = random.randint(12, 22)
        self.enemy_hp -= damage
        await self.turn(interaction, f"🔵 Blue hit for **{damage}**.")

    @discord.ui.button(label="Red", style=discord.ButtonStyle.danger, emoji="🔴")
    async def red(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check(interaction):
            return
        damage = random.randint(16, 28)
        self.enemy_hp -= damage
        await self.turn(interaction, f"🔴 Red hit for **{damage}**.")

    @discord.ui.button(label="Hollow Purple", style=discord.ButtonStyle.secondary, emoji="🟣")
    async def purple(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check(interaction):
            return
        damage = random.randint(25, 40)
        self.enemy_hp -= damage
        await self.turn(interaction, f"🟣 Hollow Purple hit for **{damage}**.")

    async def turn(self, interaction: discord.Interaction, text: str):
        if self.enemy_hp <= 0:
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(
                content=f"{text}\n\n**Enemy defeated. Infinity wins. 👁️**", view=self
            )
            return

        enemy_damage = random.randint(8, 18)
        self.hp -= enemy_damage
        if self.hp <= 0:
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(
                content=f"{text}\nEnemy hit for {enemy_damage}.\n\n**You were defeated.**",
                view=self,
            )
            return

        await interaction.response.edit_message(
            content=(
                f"{text}\nEnemy hit for **{enemy_damage}**.\n\n"
                f"❤️ You: {self.hp} HP\n👹 Enemy: {self.enemy_hp} HP"
            ),
            view=self,
        )


@bot.event
async def on_ready():
    global _views_added
    if not _views_added:
        bot.add_view(DisputeCloseView())
        bot.add_view(ContinueSupportView())
        _views_added = True
    try:
        synced = await tree.sync()
        print(f"Infinity Security online as {bot.user} | synced {len(synced)} commands")
    except Exception as exc:
        print("Command sync failed:", exc)


@bot.event
async def on_guild_join(guild: discord.Guild):
    await owner_dm(f"Infinity Security joined **{guild.name}** ({guild.id}).")
    try:
        await auto_setup(guild)
    except Exception:
        pass


@bot.event
async def on_guild_remove(guild: discord.Guild):
    client_id = bot.user.id if bot.user else ""
    invite = (
        f"https://discord.com/oauth2/authorize?client_id={client_id}"
        "&permissions=8&scope=bot%20applications.commands"
    )
    await owner_dm(f"⚠️ Infinity Security was removed from **{guild.name}**.\nRe-invite: {invite}")


@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    cfg = guild_cfg(guild.id)

    account_age = datetime.now(timezone.utc) - member.created_at
    risk = 0
    reasons = []
    if account_age < timedelta(days=3):
        risk += 2
        reasons.append("account < 3 days old")
    elif account_age < timedelta(days=14):
        risk += 1
        reasons.append("account < 14 days old")

    now = time.monotonic()
    bucket = join_buckets[guild.id]
    bucket.append(now)
    recent = [t for t in bucket if now - t <= RAID_JOIN_WINDOW]

    if cfg.get("raid_protection") and len(recent) >= RAID_JOIN_LIMIT:
        risk += 3
        reasons.append(f"{len(recent)} joins in {RAID_JOIN_WINDOW}s")
        await log_event(guild, "🚨 Possible raid", f"{len(recent)} joins detected quickly.", discord.Color.red())
        await owner_dm(f"Possible raid in {guild.name}: {len(recent)} joins in {RAID_JOIN_WINDOW}s.")
        await send_video_reaction(guild, "raid")

    if risk >= 3:
        await log_event(
            guild,
            "⚠️ High-risk join",
            f"{member.mention}\n" + ", ".join(reasons),
            discord.Color.orange(),
        )


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if member.bot:
        return
    guild = member.guild
    cfg = guild_cfg(guild.id)

    if before.channel != after.channel:
        action = "joined" if after.channel and not before.channel else "left" if before.channel and not after.channel else "moved"
        target = after.channel.mention if after.channel else (before.channel.mention if before.channel else "voice")
        await log_event(guild, "🎙️ Voice activity", f"{member.mention} {action} {target}")

        if cfg.get("voice_protection") and after.channel:
            now = time.monotonic()
            bucket = voice_join_buckets[(guild.id, after.channel.id)]
            bucket.append(now)
            recent = [t for t in bucket if now - t <= VOICE_BURST_WINDOW]
            if len(recent) >= VOICE_BURST_LIMIT:
                await log_event(
                    guild,
                    "🎙️ Voice burst detected",
                    f"{len(recent)} voice joins in {VOICE_BURST_WINDOW}s in {after.channel.mention}.",
                    discord.Color.orange(),
                )
                await send_video_reaction(guild, "normal")
                bucket.clear()


@bot.event
async def on_message(message: discord.Message):
    if not message.guild or message.author.bot:
        return

    guild = message.guild
    cfg = guild_cfg(guild.id)
    normalized = normalize_text(message.content)
    ctx_key = (guild.id, message.channel.id)
    channel_context[ctx_key].append(f"{message.author}: {message.content[:500]}")

    # Honeypot
    if cfg.get("honeypot_channel_id") and message.channel.id == cfg["honeypot_channel_id"]:
        if isinstance(message.author, discord.Member) and not is_staff(message.author):
            await safe_timeout(
                message.author,
                60,
                "Honeypot triggered",
                source_channel=message.channel,
                reaction_category="critical",
            )
            try:
                await message.delete()
            except Exception:
                pass
            return

    # Anti-spam. Normal bot chatter and the explicit "owo" exception are ignored.
    if cfg.get("anti_spam") and "owo" not in normalized:
        key = (guild.id, message.author.id)
        now = time.monotonic()
        bucket = message_buckets[key]
        bucket.append(now)
        recent = [t for t in bucket if now - t <= SPAM_WINDOW]
        if len(recent) >= SPAM_LIMIT and isinstance(message.author, discord.Member):
            await safe_timeout(
                message.author,
                5,
                "Message spam",
                source_channel=message.channel,
                reaction_category="critical",
            )
            bucket.clear()
            return

    # Giveaway claim helper. Discord's official bot API does not allow us to press
    # another bot's button as if we were a user, so we do the supported automatic part.
    if "giveaway" in normalized and message.mentions:
        claim_user_id = cfg.get("claim_user_id", 0)
        claim_user = guild.get_member(claim_user_id) if claim_user_id else None
        if claim_user and any(member.id == claim_user.id for member in message.mentions):
            ticket_channels = [
                c for c in guild.text_channels
                if any(x in normalize_text(c.name) for x in ["ticket", "claim", "support"])
            ]
            target = ticket_channels[0] if ticket_channels else message.channel
            try:
                await target.send(f"{claim_user.mention} WÜRDE GERNE CLAIMEN")
                if target.id != message.channel.id:
                    await message.channel.send(f"{claim_user.mention} würde gerne claimen.")
            except Exception:
                pass

    # Context-aware AI moderation only wakes up for suspicious messages.
    if cfg.get("ai_enabled") and len(message.content) >= 3 and suspicious_enough_for_ai(message.content):
        result = await classify_message(message)
        other_id = counterpart_id(message)

        if result.get("dispute"):
            embed = discord.Embed(
                title="⚖️ Possible dispute detected",
                description=(
                    "Infinity detected a possible argument. Do you want private AI mediation? "
                    "It will ask both sides for their version and evidence."
                ),
                color=discord.Color.blurple(),
            )
            try:
                await message.reply(
                    embed=embed,
                    view=DisputeView(message.author.id, other_id),
                    mention_author=False,
                )
                await send_video_reaction(guild, "mediation", message.channel)
            except Exception:
                pass

        if result.get("action") == "timeout" and isinstance(message.author, discord.Member):
            minutes = max(1, min(int(result.get("minutes", 10)), 60))
            await safe_timeout(
                message.author,
                minutes,
                str(result.get("reason", "AI moderation")),
                source_channel=message.channel,
                reaction_category="critical",
            )
        elif result.get("action") == "warn":
            try:
                await message.reply(
                    f"⚠️ Infinity warning: {result.get('reason', 'Please keep it calm.')}",
                    mention_author=False,
                )
            except Exception:
                pass

    await bot.process_commands(message)


async def nuke_watch(guild: discord.Guild, user_id: int, action: str):
    cfg = guild_cfg(guild.id)
    if not cfg.get("anti_nuke"):
        return

    now = time.monotonic()
    key = (guild.id, user_id)
    nuke_buckets[key].append(now)
    recent = [t for t in nuke_buckets[key] if now - t <= NUKE_WINDOW]

    if len(recent) >= NUKE_LIMIT:
        member = guild.get_member(user_id)
        if (
            member
            and member.id != guild.owner_id
            and member.id != (bot.user.id if bot.user else 0)
            and guild.me
            and guild.me.top_role > member.top_role
        ):
            try:
                await member.ban(reason=f"Infinity Anti-Nuke: {len(recent)} destructive actions")
                await owner_dm(
                    f"🚨 Anti-Nuke banned {member} in {guild.name} after "
                    f"{len(recent)} destructive actions ({action})."
                )
                await log_event(
                    guild,
                    "🌀 ANTI-NUKE TRIGGERED",
                    f"{member} was banned after {len(recent)} destructive actions.",
                    discord.Color.red(),
                )
                await send_video_reaction(guild, "raid")
            except Exception:
                pass
            nuke_buckets[key].clear()


@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    guild = channel.guild
    await asyncio.sleep(1)
    try:
        async for entry in guild.audit_logs(limit=4, action=discord.AuditLogAction.channel_delete):
            if entry.target and entry.target.id == channel.id and entry.user:
                await nuke_watch(guild, entry.user.id, "channel_delete")
                await log_event(guild, "🧨 Channel deleted", f"{channel.name} • by {entry.user}")
                break
    except Exception:
        pass


@bot.event
async def on_guild_role_delete(role: discord.Role):
    guild = role.guild
    await asyncio.sleep(1)
    try:
        async for entry in guild.audit_logs(limit=4, action=discord.AuditLogAction.role_delete):
            if entry.target and entry.target.id == role.id and entry.user:
                await nuke_watch(guild, entry.user.id, "role_delete")
                await log_event(guild, "🧨 Role deleted", f"{role.name} • by {entry.user}")
                break
    except Exception:
        pass


@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    await asyncio.sleep(1)
    try:
        async for entry in guild.audit_logs(limit=4, action=discord.AuditLogAction.ban):
            if entry.target and entry.target.id == user.id and entry.user:
                await nuke_watch(guild, entry.user.id, "member_ban")
                break
    except Exception:
        pass


async def auto_setup(guild: discord.Guild):
    cfg = guild_cfg(guild.id)

    def find_text(names):
        wanted = {normalize_text(x) for x in names}
        return next((c for c in guild.text_channels if normalize_text(c.name) in wanted), None)

    log_channel = find_text(["infinity-logs", "security-logs", "security logs", "infinity logs"])
    if not log_channel:
        log_channel = await guild.create_text_channel("infinity-logs", reason="Infinity Security setup")
    cfg["log_channel_id"] = log_channel.id

    category = next((c for c in guild.categories if "dispute" in normalize_text(c.name)), None)
    if not category:
        category = await guild.create_category("⚖️ INFINITY DISPUTES", reason="Infinity Security setup")
    cfg["dispute_category_id"] = category.id

    honeypot = find_text(["honeypot", "do-not-type-here", "trap", "do not type here"])
    if not honeypot:
        honeypot = await guild.create_text_channel("honeypot", reason="Infinity Security setup")
        try:
            await honeypot.send("⚠️ Security test channel. Normal members should not type here.")
        except Exception:
            pass
    cfg["honeypot_channel_id"] = honeypot.id

    if not cfg.get("claim_user_id") and ENV_CLAIM_USER_ID:
        cfg["claim_user_id"] = ENV_CLAIM_USER_ID

    save_data()
    await log_event(
        guild,
        "✅ Infinity Security setup complete",
        random.choice(GOJO_LINES),
        discord.Color.green(),
    )
    await send_video_reaction(guild, "normal", log_channel)


# ============================================================
# Slash commands
# ============================================================

@tree.command(name="setup", description="Automatically sets up Infinity Security.")
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await auto_setup(interaction.guild)
    await interaction.followup.send("✅ Infinity Security setup complete. Use `/panel` next.", ephemeral=True)


@tree.command(name="panel", description="Open the Infinity Security panel.")
async def panel_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="👁️ Infinity Security",
        description="Six Eyes are online.\nUse the controls below.",
        color=discord.Color.blurple(),
    )
    embed.set_footer(text="Made with ❤️ by Stilo")
    await interaction.response.send_message(embed=embed, view=SecurityPanel())


@tree.command(name="securitylevel", description="Set Infinity security level from 1 to 5.")
@app_commands.describe(level="1 = relaxed, 5 = maximum security")
@app_commands.checks.has_permissions(manage_guild=True)
async def securitylevel(interaction: discord.Interaction, level: app_commands.Range[int, 1, 5]):
    cfg = guild_cfg(interaction.guild.id)
    cfg["security_level"] = int(level)
    cfg["anti_spam"] = level >= 2
    cfg["raid_protection"] = level >= 3
    cfg["anti_nuke"] = level >= 3
    cfg["voice_protection"] = level >= 2
    cfg["ai_enabled"] = True
    save_data()
    await interaction.response.send_message(f"🛡️ Security level set to **{level}/5**.", ephemeral=True)


@tree.command(name="setclaimuser", description="Set the user Infinity should auto-claim giveaway alerts for.")
@app_commands.checks.has_permissions(manage_guild=True)
async def setclaimuser(interaction: discord.Interaction, member: discord.Member):
    cfg = guild_cfg(interaction.guild.id)
    cfg["claim_user_id"] = member.id
    save_data()
    await interaction.response.send_message(f"Giveaway claim target set to {member.mention}.", ephemeral=True)


@tree.command(name="learn", description="Teach Infinity something for this server or globally.")
@app_commands.describe(scope="server or global", text="What Infinity should learn")
async def learn(interaction: discord.Interaction, scope: str, text: str):
    scope = scope.lower().strip()
    if scope == "global" and OWNER_ID and interaction.user.id != OWNER_ID:
        await interaction.response.send_message("Only the owner can teach global knowledge.", ephemeral=True)
        return

    understood = text.strip()
    if scope == "server":
        cfg = guild_cfg(interaction.guild.id)
        cfg.setdefault("learned_server", []).append(understood)
        cfg["learned_server"] = cfg["learned_server"][-100:]
        save_data()
        await interaction.response.send_message(
            f"✅ I understood this for **this server**:\n> {understood}", ephemeral=True
        )
    elif scope == "global":
        DATA.setdefault("global_learned", []).append(understood)
        DATA["global_learned"] = DATA["global_learned"][-100:]
        save_data()
        await interaction.response.send_message(
            f"✅ I understood this **globally**:\n> {understood}", ephemeral=True
        )
    else:
        await interaction.response.send_message("Use scope `server` or `global`.", ephemeral=True)


@tree.command(name="boss", description="Get 3 JJK boss tasks with a 24 hour deadline.")
async def boss_cmd(interaction: discord.Interaction):
    tasks = random.sample(
        [
            "Help one member without being asked.",
            "Stay active for 20 minutes without spamming.",
            "Win a JJK minigame fight.",
            "Send one useful suggestion.",
            "Report one real security problem.",
            "Invite one trusted friend.",
            "Use the Security Panel and check the status.",
        ],
        3,
    )
    deadline = datetime.now(timezone.utc) + timedelta(days=1)
    DATA.setdefault("boss", {})[str(interaction.user.id)] = {
        "tasks": tasks,
        "deadline": deadline.isoformat(),
    }
    save_data()

    embed = discord.Embed(
        title="👹 /boss • 24h Challenge",
        description="\n".join(f"**{i + 1}.** {task}" for i, task in enumerate(tasks)),
        color=discord.Color.red(),
    )
    embed.add_field(name="Deadline", value=f"<t:{int(deadline.timestamp())}:R>")
    await interaction.response.send_message(embed=embed)


@tree.command(name="bossstatus", description="Show your current JJK boss challenge.")
async def bossstatus_cmd(interaction: discord.Interaction):
    entry = DATA.get("boss", {}).get(str(interaction.user.id))
    if not entry:
        await interaction.response.send_message("You have no active boss challenge. Use `/boss`.", ephemeral=True)
        return
    deadline = datetime.fromisoformat(entry["deadline"])
    embed = discord.Embed(
        title="👹 Your Boss Challenge",
        description="\n".join(f"**{i + 1}.** {task}" for i, task in enumerate(entry["tasks"])),
        color=discord.Color.red(),
    )
    embed.add_field(name="Deadline", value=f"<t:{int(deadline.timestamp())}:R>")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="jjk", description="Start the Infinity JJK minigame.")
async def jjk_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        "❤️ You: 100 HP\n👹 Enemy: 100 HP\n\nChoose your technique:",
        view=JJKView(interaction.user.id),
    )


@tree.command(name="dispute", description="Start a private AI dispute mediation.")
async def dispute_cmd(interaction: discord.Interaction, member: discord.Member | None = None):
    embed = discord.Embed(
        title="⚖️ Infinity Mediation",
        description="Do you want Infinity AI to create a private dispute room?",
        color=discord.Color.blurple(),
    )
    await interaction.response.send_message(
        embed=embed,
        view=DisputeView(interaction.user.id, member.id if member else None),
        ephemeral=True,
    )


@tree.command(name="invite", description="Get Infinity Security's invite link.")
async def invite_cmd(interaction: discord.Interaction):
    link = (
        f"https://discord.com/oauth2/authorize?client_id={bot.user.id}"
        "&permissions=8&scope=bot%20applications.commands"
    )
    await interaction.response.send_message(link, ephemeral=True)


@tree.command(name="status", description="Show Infinity Security status.")
async def status_cmd(interaction: discord.Interaction):
    cfg = guild_cfg(interaction.guild.id)
    vr = cfg["video_reactions"]
    ai = "ON" if AI_CLIENT else "Fallback mode"
    embed = discord.Embed(title="👁️ Infinity Security Status", color=discord.Color.green())
    embed.add_field(name="Security Level", value=f"{cfg['security_level']}/5")
    embed.add_field(name="AI Engine", value=ai)
    embed.add_field(name="Anti-Spam", value="ON" if cfg["anti_spam"] else "OFF")
    embed.add_field(name="Anti-Nuke", value="ON" if cfg["anti_nuke"] else "OFF")
    embed.add_field(name="Raid Protection", value="ON" if cfg["raid_protection"] else "OFF")
    embed.add_field(name="Voice Protection", value="ON" if cfg["voice_protection"] else "OFF")
    embed.add_field(name="Video Reactions", value="ON" if vr["enabled"] else "OFF")
    embed.add_field(name="Reaction Cooldown", value=f"{vr['cooldown_seconds']}s")
    embed.set_footer(text="Infinity Security • Made with ❤️ by Stilo")
    await interaction.response.send_message(embed=embed)


@tree.command(name="continueai", description="Show the Continue with AI support button.")
async def continueai_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        "A human moderator can take over. If you still want AI help, press Continue.",
        view=ContinueSupportView(),
    )


@tree.command(name="timeout", description="Timeout a member.")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout_cmd(
    interaction: discord.Interaction,
    member: discord.Member,
    minutes: app_commands.Range[int, 1, 10080],
    reason: str = "No reason provided",
):
    await interaction.response.defer(ephemeral=True)
    ok = await safe_timeout(
        member,
        int(minutes),
        reason,
        source_channel=interaction.channel,
        reaction_category="critical",
    )
    await interaction.followup.send("Done." if ok else "I couldn't timeout that member.", ephemeral=True)


@tree.command(name="untimeout", description="Remove a member timeout.")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout_cmd(interaction: discord.Interaction, member: discord.Member):
    try:
        await member.timeout(None, reason=f"Removed by {interaction.user}")
        await interaction.response.send_message(f"Removed timeout from {member.mention}.", ephemeral=True)
    except Exception:
        await interaction.response.send_message("I couldn't remove that timeout.", ephemeral=True)


# ============================================================
# /edit video reaction management
# ============================================================

edit_group = app_commands.Group(name="edit", description="Manage Infinity's video reactions.")


@edit_group.command(name="list", description="Show all reaction clips and settings.")
async def edit_list(interaction: discord.Interaction):
    cfg = guild_cfg(interaction.guild.id)
    vr = cfg["video_reactions"]
    lines = []
    for name, filename in REACTION_FILES.items():
        meta = vr["clips"].get(name, {"enabled": False, "category": "unknown"})
        path = REACTION_DIR / filename
        size = path.stat().st_size / 1024 / 1024 if path.exists() else 0
        lines.append(
            f"• `{name}` — {meta.get('category')} — "
            f"{'ON' if meta.get('enabled') else 'OFF'} — {size:.1f} MB"
        )

    freq = vr["frequencies"]
    embed = discord.Embed(
        title="🎬 Infinity Reaction Edits",
        description="\n".join(lines),
        color=discord.Color.purple(),
    )
    embed.add_field(name="Autoplay", value="ON" if vr["enabled"] else "OFF")
    embed.add_field(name="Cooldown", value=f"{vr['cooldown_seconds']} seconds")
    embed.add_field(
        name="Frequency",
        value=(
            f"Normal: {freq['normal']}%\nCritical: {freq['critical']}%\n"
            f"Raid: {freq['raid']}%\nMediation: {freq['mediation']}%"
        ),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@edit_group.command(name="test", description="Send one reaction video now.")
@app_commands.describe(clip="Clip ID, e.g. raid_convoy")
async def edit_test(interaction: discord.Interaction, clip: str):
    clip = clip.strip().lower()
    if clip not in REACTION_FILES:
        await interaction.response.send_message(
            "Unknown clip. Use `/edit list` to see the IDs.", ephemeral=True
        )
        return
    await interaction.response.defer(ephemeral=True)
    ok = await send_video_reaction(
        interaction.guild,
        "normal",
        interaction.channel,
        force=True,
        clip_name=clip,
    )
    await interaction.followup.send(
        "✅ Test video sent." if ok else "❌ I couldn't send that video.", ephemeral=True
    )


@edit_group.command(name="frequency", description="Set how often a category sends a video.")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(category="normal, critical, raid, or mediation", percent="0-100")
async def edit_frequency(
    interaction: discord.Interaction,
    category: str,
    percent: app_commands.Range[int, 0, 100],
):
    category = category.lower().strip()
    if category not in {"normal", "critical", "raid", "mediation"}:
        await interaction.response.send_message(
            "Category must be `normal`, `critical`, `raid`, or `mediation`.", ephemeral=True
        )
        return
    cfg = guild_cfg(interaction.guild.id)
    cfg["video_reactions"]["frequencies"][category] = int(percent)
    save_data()
    await interaction.response.send_message(
        f"🎬 `{category}` reaction frequency = **{percent}%**.", ephemeral=True
    )


@edit_group.command(name="autoplay", description="Turn automatic video reactions on or off.")
@app_commands.checks.has_permissions(manage_guild=True)
async def edit_autoplay(interaction: discord.Interaction, enabled: bool):
    cfg = guild_cfg(interaction.guild.id)
    cfg["video_reactions"]["enabled"] = enabled
    save_data()
    await interaction.response.send_message(
        f"🎬 Video autoplay is now **{'ON' if enabled else 'OFF'}**.", ephemeral=True
    )


@edit_group.command(name="cooldown", description="Set the reaction-video cooldown.")
@app_commands.checks.has_permissions(manage_guild=True)
async def edit_cooldown(
    interaction: discord.Interaction,
    seconds: app_commands.Range[int, 0, 600],
):
    cfg = guild_cfg(interaction.guild.id)
    cfg["video_reactions"]["cooldown_seconds"] = int(seconds)
    save_data()
    await interaction.response.send_message(
        f"🎬 Reaction cooldown = **{seconds}s**.", ephemeral=True
    )


@edit_group.command(name="clip", description="Enable or disable one reaction clip.")
@app_commands.checks.has_permissions(manage_guild=True)
async def edit_clip(interaction: discord.Interaction, clip: str, enabled: bool):
    clip = clip.lower().strip()
    if clip not in REACTION_FILES:
        await interaction.response.send_message("Unknown clip. Use `/edit list`.", ephemeral=True)
        return
    cfg = guild_cfg(interaction.guild.id)
    cfg["video_reactions"]["clips"][clip]["enabled"] = enabled
    save_data()
    await interaction.response.send_message(
        f"🎬 `{clip}` is now **{'ON' if enabled else 'OFF'}**.", ephemeral=True
    )


@edit_group.command(name="category", description="Move a clip to a reaction category.")
@app_commands.checks.has_permissions(manage_guild=True)
async def edit_category(interaction: discord.Interaction, clip: str, category: str):
    clip = clip.lower().strip()
    category = category.lower().strip()
    if clip not in REACTION_FILES:
        await interaction.response.send_message("Unknown clip. Use `/edit list`.", ephemeral=True)
        return
    if category not in {"normal", "critical", "raid", "mediation"}:
        await interaction.response.send_message(
            "Category must be `normal`, `critical`, `raid`, or `mediation`.", ephemeral=True
        )
        return

    cfg = guild_cfg(interaction.guild.id)
    vr = cfg["video_reactions"]
    old_category = vr["clips"][clip].get("category")
    vr["clips"][clip]["category"] = category

    for cat, order in vr["sort"].items():
        vr["sort"][cat] = [name for name in order if name != clip]
    vr["sort"].setdefault(category, []).append(clip)
    save_data()
    await interaction.response.send_message(
        f"🎬 `{clip}` moved from `{old_category}` to **`{category}`**.", ephemeral=True
    )


@edit_group.command(name="sort", description="Set clip order for one category.")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(clips="Comma-separated clip IDs in the order you want")
async def edit_sort(interaction: discord.Interaction, category: str, clips: str):
    category = category.lower().strip()
    if category not in {"normal", "critical", "raid", "mediation"}:
        await interaction.response.send_message(
            "Category must be `normal`, `critical`, `raid`, or `mediation`.", ephemeral=True
        )
        return

    names = [x.strip().lower() for x in clips.split(",") if x.strip()]
    unknown = [x for x in names if x not in REACTION_FILES]
    if unknown:
        await interaction.response.send_message(
            "Unknown clip(s): " + ", ".join(f"`{x}`" for x in unknown), ephemeral=True
        )
        return

    cfg = guild_cfg(interaction.guild.id)
    cfg["video_reactions"]["sort"][category] = names
    save_data()
    await interaction.response.send_message(
        f"🎬 `{category}` order saved: " + " → ".join(f"`{x}`" for x in names),
        ephemeral=True,
    )


tree.add_command(edit_group)


@tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    msg = "Something went wrong."
    if isinstance(error, app_commands.MissingPermissions):
        msg = "You don't have permission to use that command."
    elif isinstance(error, app_commands.CommandOnCooldown):
        msg = "That command is on cooldown."
    else:
        print("Slash command error:", repr(error))

    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing. Put it in your .env file or Railway Variables.")
    bot.run(TOKEN)
