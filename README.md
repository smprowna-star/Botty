# All-in-One Discord Bot for Render (fixed database path)

This package fixes the crash `PermissionError: [Errno 13] Permission denied: '/data'` by defaulting SQLite to `/tmp/bot.sqlite3`, which is writable on Render. **The `/tmp` database is temporary** and can be cleared on restarts/redeploys. To keep data permanently, attach a Render Persistent Disk mounted at `/data` and set `DATABASE_PATH=/data/bot.sqlite3`.

## Upload to GitHub
Upload these files to the repository root: `main.py`, `requirements.txt`, `apt.txt`, and `Dockerfile`.

## Render setup (matches the Python 3 service in your screenshot)
Create/use a **Web Service** with runtime **Python 3**. Leave Root Directory empty. Set:

- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python main.py`

Add environment variable:
- `DISCORD_TOKEN` = your Discord bot token

Optional variables:
- `BOT_PREFIX` = `!`
- `WELCOME_CHANNEL_ID` = your welcome channel's numeric ID
- `DATABASE_PATH` = `/data/bot.sqlite3` only if you attached a persistent disk mounted at `/data`

The `apt.txt` file requests FFmpeg for music playback on Render's native Python runtime. The included Dockerfile also installs FFmpeg if you choose Docker runtime instead.

## Dashboard
The service serves the dashboard at `/` and health status at `/health`. Render supplies the `PORT` variable; the app binds to `0.0.0.0`.

## Discord setup
1. Create a bot at https://discord.com/developers/applications.
2. Enable **Message Content Intent** and **Server Members Intent** under Bot > Privileged Gateway Intents.
3. Invite it with the permissions it needs (View Channels, Send Messages, Embed Links, Read Message History, Manage Messages, Kick/Ban/Moderate Members, Connect and Speak).
4. Never put your bot token in GitHub or in the source code.

## Commands
General: `!help`, `!ping`, `!server`, `!userinfo`
Moderation: `!kick @member [reason]`, `!ban @member [reason]`, `!timeout @member 10 [reason]`, `!clear 10`, `!warn @member [reason]`, `!warnings @member`
Restaurant demo: `!menu`, `!order biryani 2`, `!myorders`, `!orders` (Manage Server permission)
Economy: `!balance`, `!daily`, `!pay @member 50`
Games: `!games`, `!coinflip heads`, `!dice 4`, `!rps rock`, `!guess 7`, `!slots`, `!trivia`, `!riddle`, `!8ball will I win?`, `!gamestats`
Music: `!play song name or URL`, `!queue`, `!pause`, `!resume`, `!skip`, `!stop`

## Notes
- Restaurant orders are demo records; no restaurant is contacted and no payment is taken.
- Music queue is in memory and resets when the process restarts. Audio-source availability can change.
- SQLite records stored in `/tmp` are not durable. Use a persistent disk for data you need to retain.
- Prefix commands require Message Content Intent enabled in the Developer Portal.
