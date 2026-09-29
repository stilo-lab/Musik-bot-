# START HERE 👁️

## Super-easy setup

### 1) Upload to GitHub
Create a new GitHub repository and upload **the complete contents of this folder**, including:

- `main.py`
- `requirements.txt`
- `railway.json`
- `.env.example`
- `assets/reactions/` with the MP4 edits

Do **not** upload a real `.env` file with your token.

### 2) Discord Developer Portal
Create a bot and enable these Privileged Gateway Intents:

- Server Members Intent
- Message Content Intent

For easiest testing, invite Infinity with **Administrator** permission. Later you can reduce the permissions if you want.

### 3) Railway
Create a Railway project → **Deploy from GitHub Repo** → select this repository.

Add these Variables:

- `DISCORD_TOKEN` = your Discord bot token
- `OWNER_ID` = your Discord user ID
- `OPENAI_API_KEY` = optional, but needed for full AI moderation/mediation
- `AI_MODEL` = `gpt-5-mini`
- `CLAIM_USER_ID` = optional user ID for the giveaway claim helper

The included `railway.json` already uses:

`python main.py`

### 4) First commands in Discord
Run:

`/setup`

Then:

`/panel`

To test the old Gojo edits immediately:

`/edit list`

and for example:

`/edit test clip:raid_convoy`

That's it. Read `README.md` for all commands and features.
