import os
import random
import sqlite3
import asyncio
from datetime import datetime, timezone, date
from collections import defaultdict, deque

import discord
from discord.ext import commands
import yt_dlp

# -------------------- CONFIG --------------------
TOKEN = os.getenv("DISCORD_TOKEN")
DB_PATH = os.getenv("DATABASE_PATH", "/data/bot.sqlite3")
PREFIX = os.getenv("BOT_PREFIX", "!")
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", "0") or 0)

if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN environment variable.")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or(PREFIX),
                   intents=intents, help_command=None)

# -------------------- DATABASE --------------------
def connect_db():
    folder = os.path.dirname(DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with connect_db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            total INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS economy (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            coins INTEGER NOT NULL DEFAULT 0,
            last_daily TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (guild_id, user_id)
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS game_stats (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )""")

def get_balance(guild_id, user_id):
    with connect_db() as db:
        row = db.execute("SELECT coins FROM economy WHERE guild_id=? AND user_id=?",
                         (guild_id, user_id)).fetchone()
        return int(row["coins"]) if row else 0

def change_balance(guild_id, user_id, delta):
    with connect_db() as db:
        db.execute("INSERT OR IGNORE INTO economy(guild_id,user_id,coins) VALUES(?,?,0)",
                   (guild_id, user_id))
        db.execute("UPDATE economy SET coins=coins+? WHERE guild_id=? AND user_id=?",
                   (delta, guild_id, user_id))

MENU = {
    "burger": 120,
    "pizza": 250,
    "fries": 80,
    "biryani": 180,
    "coke": 40,
    "sandwich": 100,
}

# Music queues are in memory and reset when the worker restarts.
music_queues = defaultdict(deque)
YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch1",
    "no_warnings": True,
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

# -------------------- EVENTS --------------------
@bot.event
async def on_ready():
    init_db()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Prefix: {PREFIX!r} | Database: {DB_PATH}")
    print("All-in-one bot is ready.")

@bot.event
async def on_member_join(member):
    channel = member.guild.get_channel(WELCOME_CHANNEL_ID) if WELCOME_CHANNEL_ID else None
    if channel is None:
        channel = member.guild.system_channel
    if channel:
        try:
            await channel.send(f"Welcome to **{member.guild.name}**, {member.mention}! 🎉")
        except discord.Forbidden:
            print(f"Cannot send welcome message in guild {member.guild.id}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply(f"Missing argument: `{error.param.name}`. Use `{PREFIX}help`.")
    elif isinstance(error, commands.BadArgument):
        await ctx.reply("I couldn't understand that argument. Check the command usage with `!help`.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.reply("❌ You don't have permission to use that command.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.reply("❌ I need additional permissions to do that.")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(f"⏳ Try again in {error.retry_after:.1f} seconds.")
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.reply("This command can only be used in a server.")
    else:
        print(f"Command error in {ctx.command}: {repr(error)}")
        await ctx.reply("Something went wrong. Check the Render logs for details.")

# -------------------- GENERAL --------------------
@bot.command(name="help", aliases=["commands"])
async def help_command(ctx):
    embed = discord.Embed(title="🤖 All-in-One Bot Commands", color=discord.Color.blurple())
    embed.add_field(name="General", value="`!ping` `!server` `!userinfo` `!help`", inline=False)
    embed.add_field(name="Moderation", value="`!kick @user [reason]` `!ban @user [reason]`\n`!timeout @user minutes [reason]` `!clear amount` `!warn @user reason` `!warnings @user`", inline=False)
    embed.add_field(name="Restaurant", value="`!menu` `!order item [quantity]` `!myorders`", inline=False)
    embed.add_field(name="Economy", value="`!balance [@user]` `!daily` `!pay @user amount`", inline=False)
    embed.add_field(name="Games", value="`!games` `!coinflip heads|tails` `!dice 1-6` `!rps rock|paper|scissors` `!guess 1-10` `!gamestats`", inline=False)
    embed.add_field(name="Music", value="`!play song or URL` `!queue` `!pause` `!resume` `!skip` `!stop`", inline=False)
    embed.set_footer(text=f"Prefix: {PREFIX} | Prefix also works when mentioning the bot")
    await ctx.reply(embed=embed)

@bot.command()
async def ping(ctx):
    await ctx.reply(f"🏓 Pong! Gateway latency: {round(bot.latency * 1000)} ms")

@bot.command()
@commands.guild_only()
async def server(ctx):
    g = ctx.guild
    embed = discord.Embed(title=g.name, color=discord.Color.blurple())
    embed.add_field(name="Members", value=str(g.member_count or "Unknown"))
    embed.add_field(name="Created", value=discord.utils.format_dt(g.created_at, style="D"))
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    await ctx.reply(embed=embed)

@bot.command()
@commands.guild_only()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"User info: {member}", color=discord.Color.blurple())
    embed.add_field(name="ID", value=str(member.id), inline=False)
    embed.add_field(name="Joined", value=discord.utils.format_dt(member.joined_at, style="D") if member.joined_at else "Unknown")
    embed.add_field(name="Account created", value=discord.utils.format_dt(member.created_at, style="D"))
    embed.set_thumbnail(url=member.display_avatar.url)
    await ctx.reply(embed=embed)

# -------------------- MODERATION --------------------
@bot.command()
@commands.guild_only()
@commands.has_guild_permissions(kick_members=True)
@commands.bot_has_guild_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    if member == ctx.author:
        return await ctx.reply("You can't kick yourself.")
    await member.kick(reason=f"{ctx.author}: {reason}")
    await ctx.reply(f"👢 Kicked **{member}**. Reason: {reason}")

@bot.command()
@commands.guild_only()
@commands.has_guild_permissions(ban_members=True)
@commands.bot_has_guild_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    if member == ctx.author:
        return await ctx.reply("You can't ban yourself.")
    await member.ban(reason=f"{ctx.author}: {reason}", delete_message_seconds=0)
    await ctx.reply(f"🔨 Banned **{member}**. Reason: {reason}")

@bot.command(name="timeout")
@commands.guild_only()
@commands.has_guild_permissions(moderate_members=True)
@commands.bot_has_guild_permissions(moderate_members=True)
async def timeout_member(ctx, member: discord.Member, minutes: int, *, reason="No reason provided"):
    if minutes < 1 or minutes > 40320:
        return await ctx.reply("Choose a timeout between 1 and 40320 minutes (28 days).")
    until = discord.utils.utcnow() + discord.timedelta(minutes=minutes) if hasattr(discord, "timedelta") else None
    # datetime.timedelta is used directly for broad discord.py compatibility.
    from datetime import timedelta
    await member.timeout(timedelta(minutes=minutes), reason=f"{ctx.author}: {reason}")
    await ctx.reply(f"⏳ Timed out **{member}** for {minutes} minute(s). Reason: {reason}")

@bot.command()
@commands.guild_only()
@commands.has_guild_permissions(manage_messages=True)
@commands.bot_has_guild_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    if amount < 1 or amount > 100:
        return await ctx.reply("Choose an amount between 1 and 100.")
    deleted = await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(f"🧹 Deleted {max(0, len(deleted) - 1)} message(s).")
    await asyncio.sleep(4)
    try:
        await msg.delete()
    except discord.NotFound:
        pass

@bot.command()
@commands.guild_only()
@commands.has_guild_permissions(moderate_members=True)
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    with connect_db() as db:
        db.execute("INSERT INTO warnings(guild_id,user_id,moderator_id,reason,created_at) VALUES(?,?,?,?,?)",
                   (ctx.guild.id, member.id, ctx.author.id, reason, datetime.now(timezone.utc).isoformat()))
    await ctx.reply(f"⚠️ Warned **{member}**. Reason: {reason}")

@bot.command()
@commands.guild_only()
@commands.has_guild_permissions(moderate_members=True)
async def warnings(ctx, member: discord.Member):
    with connect_db() as db:
        rows = db.execute("SELECT reason, moderator_id, created_at FROM warnings WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 10",
                          (ctx.guild.id, member.id)).fetchall()
    if not rows:
        return await ctx.reply(f"No warnings found for {member.mention}.")
    lines = [f"• {r['reason']} — moderator ID `{r['moderator_id']}`" for r in rows]
    await ctx.reply(f"**Latest warnings for {member}**\n" + "\n".join(lines))

# -------------------- RESTAURANT ORDERS --------------------
@bot.command()
async def menu(ctx):
    lines = [f"🍽️ **{name.title()}** — ₹{price}" for name, price in MENU.items()]
    await ctx.reply("**Restaurant Menu**\n" + "\n".join(lines) +
                    f"\n\nOrder with `{PREFIX}order biryani 2`.")

@bot.command()
@commands.guild_only()
async def order(ctx, item: str = None, quantity: int = 1):
    if not item or item.lower() not in MENU:
        return await ctx.reply(f"Choose an item from `{PREFIX}menu`.")
    if not 1 <= quantity <= 20:
        return await ctx.reply("Quantity must be between 1 and 20.")
    item = item.lower()
    total = MENU[item] * quantity
    with connect_db() as db:
        cur = db.execute("INSERT INTO orders(guild_id,user_id,item,quantity,total,created_at) VALUES(?,?,?,?,?,?)",
                         (ctx.guild.id, ctx.author.id, item, quantity, total, datetime.now(timezone.utc).isoformat()))
        order_id = cur.lastrowid
    await ctx.reply(f"✅ Demo order **#{order_id}** recorded for {ctx.author.mention}\n"
                    f"{item.title()} × {quantity} — **₹{total}**\n"
                    "This records an order in the bot only; it does not contact a restaurant or take payment.")

@bot.command()
@commands.guild_only()
async def myorders(ctx):
    with connect_db() as db:
        rows = db.execute("SELECT id,item,quantity,total,created_at FROM orders WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 10",
                          (ctx.guild.id, ctx.author.id)).fetchall()
    if not rows:
        return await ctx.reply("You have no saved orders yet. Try `!menu`.")
    lines = [f"**#{r['id']}** {r['item'].title()} × {r['quantity']} — ₹{r['total']}" for r in rows]
    await ctx.reply("**Your latest orders**\n" + "\n".join(lines))

@bot.command(name="orders")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def recent_orders(ctx):
    with connect_db() as db:
        rows = db.execute("SELECT id,user_id,item,quantity,total FROM orders WHERE guild_id=? ORDER BY id DESC LIMIT 10",
                          (ctx.guild.id,)).fetchall()
    if not rows:
        return await ctx.reply("No orders have been recorded.")
    lines = [f"#{r['id']} <@{r['user_id']}> — {r['item']} × {r['quantity']} — ₹{r['total']}" for r in rows]
    await ctx.reply("**Recent demo orders**\n" + "\n".join(lines))

# -------------------- ECONOMY --------------------
@bot.command()
@commands.guild_only()
async def balance(ctx, member: discord.Member = None):
    member = member or ctx.author
    amount = get_balance(ctx.guild.id, member.id)
    await ctx.reply(f"🪙 {member.display_name} has **{amount} coins**.")

@bot.command()
@commands.guild_only()
@commands.cooldown(1, 86400, commands.BucketType.user)
async def daily(ctx):
    today = date.today().isoformat()
    with connect_db() as db:
        db.execute("INSERT OR IGNORE INTO economy(guild_id,user_id,coins,last_daily) VALUES(?,?,0,'')",
                   (ctx.guild.id, ctx.author.id))
        row = db.execute("SELECT last_daily FROM economy WHERE guild_id=? AND user_id=?",
                         (ctx.guild.id, ctx.author.id)).fetchone()
        if row["last_daily"] == today:
            ctx.command.reset_cooldown(ctx)
            return await ctx.reply("You already claimed today's reward.")
        reward = random.randint(100, 250)
        db.execute("UPDATE economy SET coins=coins+?,last_daily=? WHERE guild_id=? AND user_id=?",
                   (reward, today, ctx.guild.id, ctx.author.id))
    await ctx.reply(f"🎁 You claimed **{reward} coins**! Use `{PREFIX}balance` to check your balance.")

@bot.command()
@commands.guild_only()
async def pay(ctx, member: discord.Member, amount: int):
    if member.bot or member.id == ctx.author.id:
        return await ctx.reply("Choose another human member.")
    if amount <= 0:
        return await ctx.reply("Amount must be greater than zero.")
    with connect_db() as db:
        db.execute("INSERT OR IGNORE INTO economy(guild_id,user_id,coins) VALUES(?,?,0)", (ctx.guild.id, ctx.author.id))
        db.execute("INSERT OR IGNORE INTO economy(guild_id,user_id,coins) VALUES(?,?,0)", (ctx.guild.id, member.id))
        sender = db.execute("SELECT coins FROM economy WHERE guild_id=? AND user_id=?", (ctx.guild.id, ctx.author.id)).fetchone()["coins"]
        if sender < amount:
            return await ctx.reply("You don't have enough coins.")
        db.execute("UPDATE economy SET coins=coins-? WHERE guild_id=? AND user_id=?", (amount, ctx.guild.id, ctx.author.id))
        db.execute("UPDATE economy SET coins=coins+? WHERE guild_id=? AND user_id=?", (amount, ctx.guild.id, member.id))
    await ctx.reply(f"💸 Sent **{amount} coins** to {member.mention}.")

# -------------------- MINI GAMES --------------------
def record_game(guild_id, user_id, won):
    with connect_db() as db:
        db.execute("INSERT OR IGNORE INTO game_stats(guild_id,user_id,wins,losses) VALUES(?,?,0,0)",
                   (guild_id, user_id))
        column = "wins" if won else "losses"
        db.execute(f"UPDATE game_stats SET {column}={column}+1 WHERE guild_id=? AND user_id=?",
                   (guild_id, user_id))

@bot.command(name="games")
async def games_help(ctx):
    await ctx.reply(
        "**🎮 Mini Games**\n"
        "`!coinflip heads` or `!coinflip tails` — wager 10 coins\n"
        "`!dice <1-6>` — wager 10 coins; guess the roll\n"
        "`!rps rock|paper|scissors` — play Rock Paper Scissors\n"
        "`!guess <1-10>` — guess a number; costs 5 coins\n"
        "`!gamestats [@member]` — see game wins and losses\n"
        "You can earn coins with `!daily`."
    )

@bot.command()
@commands.guild_only()
async def coinflip(ctx, choice: str):
    choice = choice.lower()
    if choice not in ("heads", "tails"):
        return await ctx.reply("Choose `heads` or `tails`. Example: `!coinflip heads`.")
    guild_id, user_id = ctx.guild.id, ctx.author.id
    if get_balance(guild_id, user_id) < 10:
        return await ctx.reply("You need at least 10 coins. Claim `!daily` first.")
    result = random.choice(("heads", "tails"))
    won = choice == result
    change_balance(guild_id, user_id, 10 if won else -10)
    record_game(guild_id, user_id, won)
    await ctx.reply(
        f"🪙 It landed on **{result}**. " +
        (f"You won 10 coins! Balance: {get_balance(guild_id, user_id)}." if won
         else f"You lost 10 coins. Balance: {get_balance(guild_id, user_id)}.")
    )

@bot.command()
@commands.guild_only()
async def dice(ctx, guess: int):
    if guess < 1 or guess > 6:
        return await ctx.reply("Guess a number from 1 to 6. Example: `!dice 4`.")
    guild_id, user_id = ctx.guild.id, ctx.author.id
    if get_balance(guild_id, user_id) < 10:
        return await ctx.reply("You need at least 10 coins. Claim `!daily` first.")
    roll = random.randint(1, 6)
    won = guess == roll
    change_balance(guild_id, user_id, 20 if won else -10)
    record_game(guild_id, user_id, won)
    await ctx.reply(
        f"🎲 The dice rolled **{roll}**. " +
        (f"Correct! You won 20 coins. Balance: {get_balance(guild_id, user_id)}."
         if won else f"Not this time — you lost 10 coins. Balance: {get_balance(guild_id, user_id)}.")
    )

@bot.command(name="rps")
@commands.guild_only()
async def rock_paper_scissors(ctx, choice: str):
    choice = choice.lower()
    choices = ("rock", "paper", "scissors")
    if choice not in choices:
        return await ctx.reply("Choose `rock`, `paper`, or `scissors`. Example: `!rps rock`.")
    bot_choice = random.choice(choices)
    if choice == bot_choice:
        outcome = "It's a tie!"
    elif (choice, bot_choice) in (("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")):
        outcome = "You win! 🎉"
    else:
        outcome = "I win this round! 🤖"
    await ctx.reply(f"You chose **{choice}**. I chose **{bot_choice}**. {outcome}")

@bot.command()
@commands.guild_only()
async def guess(ctx, number: int):
    if number < 1 or number > 10:
        return await ctx.reply("Choose a number from 1 to 10. Example: `!guess 7`.")
    guild_id, user_id = ctx.guild.id, ctx.author.id
    if get_balance(guild_id, user_id) < 5:
        return await ctx.reply("You need at least 5 coins. Claim `!daily` first.")
    answer = random.randint(1, 10)
    won = number == answer
    change_balance(guild_id, user_id, 15 if won else -5)
    record_game(guild_id, user_id, won)
    await ctx.reply(
        f"🔢 My number was **{answer}**. " +
        (f"You guessed it! You won 15 coins. Balance: {get_balance(guild_id, user_id)}."
         if won else f"Wrong guess — you lost 5 coins. Balance: {get_balance(guild_id, user_id)}.")
    )

@bot.command()
@commands.guild_only()
async def gamestats(ctx, member: discord.Member = None):
    member = member or ctx.author
    with connect_db() as db:
        row = db.execute("SELECT wins,losses FROM game_stats WHERE guild_id=? AND user_id=?",
                         (ctx.guild.id, member.id)).fetchone()
    wins = row["wins"] if row else 0
    losses = row["losses"] if row else 0
    await ctx.reply(f"🎮 **{member.display_name}'s Game Stats**\nWins: **{wins}** | Losses: **{losses}**")

# -------------------- MUSIC --------------------
async def resolve_track(query):
    loop = asyncio.get_running_loop()
    def extract():
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(query, download=False)
            if "entries" in info:
                info = next((entry for entry in info["entries"] if entry), None)
            if not info or not info.get("url"):
                raise ValueError("No playable track was found.")
            return {"title": info.get("title", "Unknown title"),
                    "url": info["url"],
                    "webpage": info.get("webpage_url", query)}
    return await loop.run_in_executor(None, extract)

async def start_next(ctx):
    queue = music_queues[ctx.guild.id]
    voice = ctx.guild.voice_client
    if not voice or not queue:
        return
    track = queue.popleft()
    try:
        source = discord.FFmpegPCMAudio(track["url"], **FFMPEG_OPTIONS)
        def after_play(error):
            if error:
                print(f"Audio playback error: {error}")
            future = asyncio.run_coroutine_threadsafe(start_next(ctx), bot.loop)
            try:
                future.result(timeout=0)
            except Exception:
                pass
        voice.play(source, after=after_play)
        await ctx.send(f"🎶 Now playing: **{track['title']}**")
    except Exception as exc:
        await ctx.send(f"Could not start audio: {exc}")

@bot.command()
@commands.guild_only()
async def play(ctx, *, query: str = None):
    if not query:
        return await ctx.reply(f"Usage: `{PREFIX}play song name or URL`")
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.reply("Join a voice channel first.")
    try:
        voice = ctx.guild.voice_client
        if voice is None:
            voice = await ctx.author.voice.channel.connect()
        elif voice.channel != ctx.author.voice.channel:
            return await ctx.reply("Join my current voice channel to add songs.")
        await ctx.send("🔎 Looking for audio...")
        track = await resolve_track(query)
        q = music_queues[ctx.guild.id]
        q.append(track)
        if not voice.is_playing() and not voice.is_paused() and len(q) == 1:
            await start_next(ctx)
        else:
            await ctx.send(f"➕ Queued: **{track['title']}**")
    except Exception as exc:
        await ctx.reply(f"Music error: {exc}")

@bot.command(name="queue")
@commands.guild_only()
async def show_queue(ctx):
    q = list(music_queues[ctx.guild.id])
    if not q:
        return await ctx.reply("The upcoming queue is empty.")
    lines = [f"{i}. {track['title']}" for i, track in enumerate(q[:15], 1)]
    await ctx.reply("**Upcoming tracks**\n" + "\n".join(lines))

@bot.command()
@commands.guild_only()
async def pause(ctx):
    voice = ctx.guild.voice_client
    if voice and voice.is_playing():
        voice.pause()
        await ctx.reply("⏸️ Paused.")
    else:
        await ctx.reply("Nothing is currently playing.")

@bot.command()
@commands.guild_only()
async def resume(ctx):
    voice = ctx.guild.voice_client
    if voice and voice.is_paused():
        voice.resume()
        await ctx.reply("▶️ Resumed.")
    else:
        await ctx.reply("Music is not paused.")

@bot.command()
@commands.guild_only()
async def skip(ctx):
    voice = ctx.guild.voice_client
    if voice and (voice.is_playing() or voice.is_paused()):
        voice.stop()
        await ctx.reply("⏭️ Skipped.")
    else:
        await ctx.reply("Nothing is currently playing.")

@bot.command()
@commands.guild_only()
async def stop(ctx):
    music_queues[ctx.guild.id].clear()
    voice = ctx.guild.voice_client
    if voice:
        if voice.is_playing() or voice.is_paused():
            voice.stop()
        await voice.disconnect()
        await ctx.reply("⏹️ Stopped playback, cleared the queue, and disconnected.")
    else:
        await ctx.reply("I'm not connected to a voice channel.")

# -------------------- START --------------------
init_db()
bot.run(TOKEN)
