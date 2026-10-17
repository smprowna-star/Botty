# Fixed All-in-One Discord Bot

Prefix: ¥

Commands:
¥help
¥ping
¥hello
¥server
¥avatar
¥game
¥games
¥quiz
¥rps rock
¥dice
¥math
¥kick @user
¥ban @user
¥unban USER_ID
¥timeout @user 10
¥warn @user reason
¥warnings @user
¥clear 10
¥slowmode 5
¥join
¥play song-or-url
¥pause
¥resume
¥skip
¥stop
¥queue
¥leave
¥balance
¥daily
¥give @user amount

Slash commands:
 /ping
 /game

RENDER:
Build Command: pip install -r requirements.txt
Start Command: python main.py

IMPORTANT:
For ¥ prefix commands, enable Message Content Intent in Discord Developer Portal:
Bot -> Privileged Gateway Intents -> Message Content Intent ON.
Also enable Server Members Intent for moderation/member commands.

Then redeploy on Render.
