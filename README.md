# 👁️ Infinity Security Bot — Full Edition

**Infinity Security** is the Gojo/JJK-style Discord security bot with moderation, dispute mediation, raid/nuke protection, owner alerts, giveaway claim assistance, voice monitoring, JJK features, and the original reaction-video system.

Made with ❤️ by Stilo.

## 🎬 Your old reaction edits are included

The package contains the real old MP4 reaction uploads in `assets/reactions/`, compressed so they are easy to keep in GitHub and send through Discord while keeping audio:

- `raid_convoy.mp4` — raid / anti-nuke reaction
- `limitless_burst.mp4` — critical moderation reaction
- `six_eyes_calm.mp4` — calmer warning / mediation reaction
- `purple_finish.mp4` — critical catch / timeout reaction
- `purple_hands_extra.mp4` — later extra purple reaction edit

Default autoplay settings:

- Normal reactions: **65%**
- Critical reactions: **80%**
- Raid reactions: **85%**
- Mediation reactions: **65%**
- Video cooldown: **20 seconds**

Nothing needs FFmpeg on Railway: the MP4 files are already prepared.

## 🛡️ Security features

- Context-aware AI moderation
- Local fallback moderation if no AI key is configured
- Anti-spam with the `owo` exception
- Users are timed out for normal moderation instead of instantly banned
- Raid join detection
- High-risk new-account detection
- Anti-nuke audit-log protection for rapid channel/role deletion or mass banning
- Honeypot channel
- Security Levels 1–5
- Lockdown button
- Owner DMs for important actions
- Re-invite DM attempt if Infinity is removed from a server
- Fancy-font-tolerant channel matching during setup
- Security logs
- Voice join/leave/move logs
- Voice join-burst detection

## ⚖️ Dispute system

Infinity can detect arguments and scam accusations without instantly deciding who is right.

- Asks whether the involved users want AI mediation
- If at least one involved user accepts, Infinity can create a private dispute channel
- Both sides can explain their version and submit evidence
- The AI separates claims, agreed facts, disputed facts and missing evidence
- It is instructed **not** to simply say “you are right” without evidence
- If mediation is declined, the declining user gets a 24h review timeout so an owner/mod can check it
- Agreement → 10-minute cooldown for involved users
- Close without agreement → 30-minute cooldown for involved users

## 🎁 Giveaway claim helper

Use `/setclaimuser @user` or set `CLAIM_USER_ID`.

When a message contains `giveaway` and the configured user is pinged, Infinity searches likely ticket/claim/support channels and writes the claim message there.

**Discord API limitation:** a normal bot cannot click another bot's button as if it were a human user. Infinity therefore automates the supported part: detection, ticket lookup and claim message posting.

## 🎬 `/edit` reaction-video commands

- `/edit list` — shows all clips, categories, frequency and cooldown
- `/edit test clip:<id>` — sends one video immediately
- `/edit frequency category:<...> percent:<0-100>` — changes autoplay probability
- `/edit autoplay enabled:<true/false>` — global video reactions on/off
- `/edit cooldown seconds:<0-600>` — changes anti-spam cooldown for edits
- `/edit clip clip:<id> enabled:<true/false>` — enable/disable one edit
- `/edit category clip:<id> category:<...>` — move a clip to another reaction category
- `/edit sort category:<...> clips:<comma-separated ids>` — save the category clip order

Clip IDs:

- `raid_convoy`
- `limitless_burst`
- `six_eyes_calm`
- `purple_finish`
- `purple_hands_extra`

## 👹 JJK features

- `/jjk` — mini battle with Blue, Red and Hollow Purple
- `/boss` — gives 3 tasks with a 24-hour deadline
- `/bossstatus` — shows the active boss challenge
- Gojo/Six Eyes/Domain-style messages and Security Panel

## 🤖 AI / learning

- `/learn scope:server text:...` — teaches Infinity a note for that server
- `/learn scope:global text:...` — owner-only global note
- AI moderation only wakes up for suspicious messages to reduce unnecessary AI calls
- Without an OpenAI key, the bot still has basic local moderation and dispute detection

## Main commands

- `/setup`
- `/panel`
- `/status`
- `/securitylevel`
- `/timeout`
- `/untimeout`
- `/dispute`
- `/setclaimuser`
- `/learn`
- `/boss`
- `/bossstatus`
- `/jjk`
- `/continueai`
- `/invite`
- `/edit ...`

## 🚀 GitHub + Railway setup

### Discord Developer Portal

Create your bot and enable:

- Server Members Intent
- Message Content Intent

For easiest initial testing, invite the bot with Administrator permission. The bot role must be **above roles it needs to moderate** or Anti-Nuke/Timeout actions cannot affect those members.

### Railway variables

Set:

```env
DISCORD_TOKEN=YOUR_BOT_TOKEN
OWNER_ID=YOUR_DISCORD_USER_ID
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
AI_MODEL=gpt-5-mini
CLAIM_USER_ID=OPTIONAL_USER_ID
```

`OPENAI_API_KEY` and `CLAIM_USER_ID` are optional.

The included `railway.json` already starts the bot with:

```text
python main.py
```

### First server setup

Run:

```text
/setup
```

Infinity creates/fetches:

- `infinity-logs`
- `⚖️ INFINITY DISPUTES`
- `honeypot`

Then run:

```text
/panel
```

## Persistent settings on Railway

Settings are saved in `infinity_data.json`. Railway deployments can have temporary filesystem storage. If you want `/learn` and per-server settings to survive every redeploy, attach a Railway Volume and set for example:

```env
DATA_PATH=/data/infinity_data.json
```

## Important Discord limitations

Infinity cannot make itself literally impossible to kick or ban. If Discord removes the bot from a server, it can only react through events Discord still delivers, such as attempting to DM the owner with a re-invite URL.

Infinity also cannot legally/officially impersonate a user to click another bot's interaction buttons.
