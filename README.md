# All-in-One Discord Bot for Render

## Files
- `main.py`: bot commands and SQLite database logic
- `requirements.txt`: Python dependencies
- `Dockerfile`: installs FFmpeg and runs the bot

## Discord Developer Portal
1. Create an application at https://discord.com/developers/applications.
2. Open **Bot** and create/reset the bot token.
3. Under **Privileged Gateway Intents**, enable **Message Content Intent** and **Server Members Intent**.
4. In **OAuth2 > URL Generator**, select `bot`; grant only the permissions needed:
   - View Channels
   - Send Messages
   - Embed Links
   - Read Message History
   - Manage Messages (for `!clear`)
   - Kick Members, Ban Members, Moderate Members (for moderation commands)
   - Connect and Speak (for music)
5. Open the generated invite URL and add the bot to your server.
6. Never commit your bot token to GitHub.

## GitHub
Upload `main.py`, `requirements.txt`, and `Dockerfile` to a repository.

## Render Background Worker
1. In https://dashboard.render.com/, choose **New > Background Worker**.
2. Connect the repository.
3. Choose the Docker runtime if asked. Render should detect the `Dockerfile`.
4. Add environment variable `DISCORD_TOKEN` with the bot token.
5. For persistent SQLite storage, add a Render Persistent Disk mounted at `/data` (if available for your plan/service):
   - Mount path: `/data`
   - Set `DATABASE_PATH=/data/bot.sqlite3`
   Without persistent storage, the database may be lost when the container is replaced or redeployed.
6. Optional environment variables:
   - `BOT_PREFIX` = `!`
   - `WELCOME_CHANNEL_ID` = the numeric ID of your welcome channel (enable Developer Mode in Discord and copy channel ID). If unset, the bot tries the server's system channel.
7. Deploy and check logs for `All-in-one bot is ready.`

## Commands
General: `!help`, `!ping`, `!server`, `!userinfo`
Moderation: `!kick @member [reason]`, `!ban @member [reason]`, `!timeout @member 10 [reason]`, `!clear 10`, `!warn @member [reason]`, `!warnings @member`
Restaurant demo: `!menu`, `!order biryani 2`, `!myorders`, `!orders` (Manage Server permission)
Economy: `!balance`, `!daily`, `!pay @member 50`
Games: `!games`, `!coinflip heads`, `!dice 4`, `!rps rock`, `!guess 7`, `!gamestats`
Music: `!play song name or URL`, `!queue`, `!pause`, `!resume`, `!skip`, `!stop`

## Important limitations
- Restaurant orders are demo records; no restaurant is contacted and no payment is taken.
- Music queue is in memory and clears on restart. Audio-source availability may change; use sources you are allowed to access.
- SQLite persistence requires a persistent disk. Without it, order history, warnings, and balances can be lost on redeploy.
- Prefix commands require Message Content Intent enabled in both the Developer Portal and the code.
- Give the bot only the server permissions it needs.
