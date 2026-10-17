import os
import random
import sqlite3
import asyncio
from datetime import datetime, timezone, date
from collections import defaultdict, deque

import discord
from discord.ext import commands
import yt_dlp
from aiohttp import web

# -------------------- CONFIG --------------------
TOKEN = os.getenv("DISCORD_TOKEN")
DB_PATH = os.getenv("DATABASE_PATH", "/tmp/bot.sqlite3")
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

# -------------------- EXTRA MINI GAMES --------------------
TRIVIA_QUESTIONS = [
    ("What is the largest planet in our solar system?", ["Earth", "Jupiter", "Mars", "Venus"], 1),
    ("How many sides does a hexagon have?", ["5", "6", "7", "8"], 1),
    ("Which ocean is the largest?", ["Atlantic", "Indian", "Arctic", "Pacific"], 3),
    ("What is the chemical symbol for water?", ["CO2", "O2", "H2O", "NaCl"], 2),
    ("How many days are in a leap year?", ["364", "365", "366", "367"], 2),
    ("Which animal is known as the fastest land animal?", ["Lion", "Cheetah", "Horse", "Leopard"], 1),
]

@bot.command()
async def trivia(ctx):
    question, options, answer_index = random.choice(TRIVIA_QUESTIONS)
    letters = ["A", "B", "C", "D"]
    text = "\n".join(f"**{letters[i]}.** {opt}" for i, opt in enumerate(options))
    msg = await ctx.reply(f"🧠 **Trivia!**\n{question}\n{text}\nReply with A, B, C, or D within 20 seconds.")

    def check(m):
        return (m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
                and m.content.strip().upper() in letters)

    try:
        answer = await bot.wait_for("message", timeout=20.0, check=check)
        if letters.index(answer.content.strip().upper()) == answer_index:
            await ctx.send(f"✅ Correct, {ctx.author.mention}! You earned 25 coins.")
            if ctx.guild:
                change_balance(ctx.guild.id, ctx.author.id, 25)
                record_game(ctx.guild.id, ctx.author.id, True)
        else:
            await ctx.send(f"❌ Not quite! The answer was **{letters[answer_index]}. {options[answer_index]}**.")
            if ctx.guild:
                record_game(ctx.guild.id, ctx.author.id, False)
    except asyncio.TimeoutError:
        await ctx.send(f"⌛ Time's up! The answer was **{letters[answer_index]}. {options[answer_index]}**.")

@bot.command()
@commands.guild_only()
async def slots(ctx):
    guild_id, user_id = ctx.guild.id, ctx.author.id
    wager = 10
    if get_balance(guild_id, user_id) < wager:
        return await ctx.reply("You need 10 coins to play. Try `!daily`.")
    change_balance(guild_id, user_id, -wager)
    symbols = ["🍒", "🍋", "🍇", "⭐", "7️⃣"]
    roll = [random.choice(symbols) for _ in range(3)]
    if roll[0] == roll[1] == roll[2]:
        prize, won = 100, True
    elif len(set(roll)) == 2:
        prize, won = 20, True
    else:
        prize, won = 0, False
    if prize:
        change_balance(guild_id, user_id, prize)
    record_game(guild_id, user_id, won)
    await ctx.reply(f"🎰 {' | '.join(roll)}\n" +
                    (f"You won **{prize} coins**!" if prize else "No win this time — you lost 10 coins.") +
                    f"\nBalance: **{get_balance(guild_id, user_id)} coins**.")

@bot.command(name="8ball")
async def eight_ball(ctx, *, question: str = None):
    if not question:
        return await ctx.reply("Ask a question. Example: `!8ball will I win?`")
    response = random.choice([
        "It is certain.", "Without a doubt.", "Most likely.", "Signs point to yes.",
        "Ask again later.", "Cannot predict now.", "Don't count on it.",
        "My sources say no.", "Very doubtful."
    ])
    await ctx.reply(f"🎱 **Question:** {question}\n**Answer:** {response}")

@bot.command()
@commands.guild_only()
async def riddle(ctx):
    question, answer = random.choice([
        ("What has keys but can't open locks?", "piano"),
        ("What gets wetter as it dries?", "towel"),
        ("What has a face and two hands but no arms or legs?", "clock"),
        ("What has to be broken before you can use it?", "egg"),
        ("What goes up but never comes down?", "age"),
    ])
    await ctx.reply(f"🧩 **Riddle:** {question}\nYou have 30 seconds to answer!")

    def check(m):
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

    try:
        answer_msg = await bot.wait_for("message", timeout=30.0, check=check)
        if answer_msg.content.strip().lower() == answer:
            await ctx.send("🎉 Correct! You earned 15 coins.")
            if ctx.guild:
                change_balance(ctx.guild.id, ctx.author.id, 15)
                record_game(ctx.guild.id, ctx.author.id, True)
        else:
            await ctx.send(f"Not quite! The answer was **{answer}**.")
            if ctx.guild:
                record_game(ctx.guild.id, ctx.author.id, False)
    except asyncio.TimeoutError:
        await ctx.send(f"⌛ Time's up! The answer was **{answer}**.")

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

# -------------------- WEB DASHBOARD / HEALTH CHECK --------------------
DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Discord Bot Dashboard</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--panel:#151d32;--muted:#aab6d3;--accent:#8b9cff}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:linear-gradient(135deg,#0b1020,#172343);color:#f5f7ff;min-height:100vh}
main{max-width:900px;margin:0 auto;padding:36px 18px}.hero{padding:28px;border:1px solid #344363;background:#151d32;border-radius:22px}
h1{margin:0 0 8px;font-size:clamp(28px,5vw,42px)}p{color:var(--muted);line-height:1.6}.pill{display:inline-block;padding:6px 10px;border-radius:99px;background:#143e35;color:#8df0c6;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-top:16px}.card{padding:20px;border-radius:16px;background:var(--panel);border:1px solid #293653}.card h2{margin:0 0 8px;font-size:18px}.card p{margin:0}.footer{margin-top:20px;font-size:13px}
a{color:#b8c5ff}code{color:#d6ddff}
</style>
</head>
<body><main>
<section class="hero">
<span class="pill">● Service endpoint online</span>
<h1>🤖 Discord Bot Dashboard</h1>
<p>Your bot's web process is responding. This page is a simple public status dashboard; it does not expose tokens, member data, or order records.</p>
</section>
<section class="grid">
<div class="card"><h2>🛡️ Moderation</h2><p>Kick, ban, timeout, clear messages, and warnings.</p></div>
<div class="card"><h2>🍔 Restaurant</h2><p>Menu, demo orders, and order history.</p></div>
<div class="card"><h2>🎵 Music</h2><p>Voice playback and queue controls, where supported.</p></div>
<div class="card"><h2>🎮 Games</h2><p>Coin flip, dice, RPS, number guess, slots, trivia, riddles, and 8-ball.</p></div>
<div class="card"><h2>🪙 Economy</h2><p>Daily rewards, balances, and coin transfers.</p></div>
<div class="card"><h2>💚 Health</h2><p>Check <a href="/health">/health</a> for machine-readable status.</p></div>
</section>
<p class="footer">Commands use the configured prefix (default <code>!</code>). Start with <code>!help</code> in Discord.</p>
</main></body></html>"""

async def dashboard(request):
    return web.Response(text=DASHBOARD_HTML, content_type="text/html")

async def health(request):
    return web.json_response({
        "status": "ok",
        "service": "discord-bot-dashboard",
        "discord_connected": bot.is_ready(),
        "bot_user": str(bot.user) if bot.user else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

async def start_web_app():
    app = web.Application()
    app.router.add_get("/", dashboard)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Dashboard listening on 0.0.0.0:{port}")
    return runner

async def main():
    init_db()
    runner = await start_web_app()
    try:
        async with bot:
            await bot.start(TOKEN)
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
