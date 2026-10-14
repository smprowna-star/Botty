# Ultimate Python Discord Bot (Render)

A multi-feature starter bot with support tickets, anti-spam, XP leveling, coin economy, self-service roles, giveaways, music commands, moderation, and a protected JSON dashboard API.

## Files
- `main.py` — Discord commands and event handlers
- `database.py` — SQLite profiles, tickets, economy, XP and giveaways
- `music.py` — voice playback and queue (requires FFmpeg)
- `dashboard.py` — HTTP JSON dashboard API
- `requirements.txt` — Python packages
- `render.yaml` — Render Background Worker configuration

## Discord setup
1. Open https://discord.com/developers/applications and create an application.
2. Under **Bot**, create a bot user and copy its token. Never publish the token.
3. Enable **Server Members Intent** and **Message Content Intent** in the Bot page. Voice commands also need bot voice permissions.
4. Under **OAuth2 > URL Generator**, select `bot` and `applications.commands`.
5. Grant the needed permissions: View Channels, Send Messages, Embed Links, Read Message History, Manage Messages, Kick Members, Ban Members, Moderate Members, Manage Channels, Manage Roles, Connect, and Speak. Use least privilege where possible.
6. Invite the bot to your server. Move the bot role above roles it should manage or moderate.

## Local setup
Python 3.10+ is recommended. Music needs FFmpeg installed and available on PATH.

```bash
pip install -r requirements.txt
```

Set environment variables in your shell (do not put secrets in code):

Linux/macOS:
```bash
export DISCORD_TOKEN="your-token"
export DASHBOARD_SECRET="a-long-random-secret"
export DASHBOARD_ENABLED="true"
python main.py
```

Windows PowerShell:
```powershell
$env:DISCORD_TOKEN="your-token"
$env:DASHBOARD_SECRET="a-long-random-secret"
$env:DASHBOARD_ENABLED="true"
python main.py
```

Optional settings:
- `WELCOME_CHANNEL_ID`: text channel ID for welcome messages; `0` disables.
- `TICKET_CATEGORY_ID`: category ID for new tickets; `0` creates tickets at server root.
- `TICKET_LOG_CHANNEL_ID`: channel ID for ticket closure logs; `0` disables.
- `GUILD_ID`: your test server ID. When set, slash commands sync to that server for faster testing; use `0` for global sync.
- `DATABASE_PATH`: SQLite database file path; default `bot.db`.
- `DASHBOARD_ENABLED`: `true` or `false`.

## Render deployment
1. Push all project files to a GitHub repository.
2. In Render, create a **Background Worker** from the repository. You can use the included `render.yaml` Blueprint.
3. Add `DISCORD_TOKEN` as a secret environment variable. Set the channel/category IDs if desired.
4. Make sure `DASHBOARD_SECRET` is a long random secret. The Blueprint generates one; verify it exists in the service environment.
5. Deploy and inspect logs for `Online as ...`.

### Dashboard note
The included dashboard is a **JSON API**, not a complete visual OAuth dashboard. On a Render Background Worker, the HTTP API may not be reachable from the public internet because workers are not web services. If you need public browser access, deploy the dashboard as a separate Render Web Service and connect it to shared persistent storage or an authenticated API. Do not expose an unauthenticated dashboard. For a simple worker-only deployment, set `DASHBOARD_ENABLED=false`.

### Database persistence
The included SQLite database is fine for testing, but Render worker filesystems can be ephemeral. For persistent production data, attach a persistent disk if your Render plan supports it and set `DATABASE_PATH` to a path on that disk, or migrate the database to a managed PostgreSQL service. A disk mounted to a worker cannot automatically be shared with a separate dashboard service.

## Commands
- General: `/help`, `/ping`, `/userinfo`, `/serverinfo`
- Moderation: `/kick`, `/ban`, `/timeout`, `/clear`
- Tickets: `/ticketpanel` posts a button panel; users create private channels and close with the button.
- Reaction roles: `/rolepanel` takes 1–3 roles and posts a select menu to toggle them.
- Leveling: `/rank`, `/leaderboard`; XP is awarded once per 60 seconds.
- Economy: `/balance`, `/daily`, `/work`, `/pay`
- Giveaways: `/giveaway` starts a reaction giveaway with 🎉 entries.
- Music: `/play`, `/skip`, `/stop`, `/pause`, `/resume`, `/queue`

## Important limitations and safety
- Anti-spam is a simple in-memory heuristic and may occasionally flag legitimate rapid posting. Tune it for your community.
- XP cooldown and anti-spam counters reset on restart.
- `/warn` and full moderation audit persistence are not implemented in this upgraded project.
- Giveaways depend on the bot staying online to process endings; unfinished giveaways are checked after restart.
- Music search/playback relies on third-party extraction and can break as providers change. Use only sources you are authorized to play, and comply with provider terms.
- This is a starter dashboard API, not a full visual panel with Discord OAuth login or per-guild configuration UI.
- Review the code and test commands in a private server before using it in a large community.
