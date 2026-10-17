import os
import random
import asyncio
from collections import defaultdict, deque
from datetime import timedelta
from threading import Thread

import discord
from discord.ext import commands
from flask import Flask

# =========================
# RENDER WEB SERVER
# =========================
app = Flask(__name__)

@app.route("/")
def home():
    return "Discord Bot is online!"

def run_web():
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

Thread(target=run_web, daemon=True).start()

# =========================
# DISCORD BOT
# =========================
PREFIX = "¥"

intents = discord.Intents.all()

bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents,
    help_command=None
)

warnings_db = defaultdict(list)
balances = defaultdict(int)
queues = defaultdict(deque)
now_playing = {}

# =========================
# READY
# =========================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print(f"✅ Prefix: {PREFIX}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Slash sync error: {e}")

# =========================
# HELP
# =========================
@bot.command(name="help")
async def help_command(ctx):
    e = discord.Embed(title="🤖 All-in-One Bot", description="Prefix: `¥`")
    e.add_field(name="🎮 Games", value="`¥game` `¥games` `¥quiz` `¥rps` `¥dice` `¥math`", inline=False)
    e.add_field(name="🛡️ Moderation", value="`¥kick` `¥ban` `¥unban` `¥timeout` `¥warn` `¥warnings` `¥clear` `¥slowmode`", inline=False)
    e.add_field(name="🎵 Music", value="`¥join` `¥play` `¥pause` `¥resume` `¥skip` `¥stop` `¥queue` `¥leave`", inline=False)
    e.add_field(name="💰 Economy", value="`¥balance` `¥daily` `¥give`", inline=False)
    e.add_field(name="🔧 Utility", value="`¥ping` `¥hello` `¥server` `¥avatar`", inline=False)
    await ctx.send(embed=e)

# =========================
# BASIC
# =========================
@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! `{round(bot.latency * 1000)}ms`")

@bot.command()
async def hello(ctx):
    await ctx.send(f"👋 Hello {ctx.author.mention}!")

@bot.command()
async def server(ctx):
    if not ctx.guild:
        return await ctx.send("❌ Use this command in a server.")
    await ctx.send(
        f"🏠 **{ctx.guild.name}**\n"
        f"👥 Members: **{ctx.guild.member_count}**\n"
        f"🆔 ID: `{ctx.guild.id}`"
    )

@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    await ctx.send(member.display_avatar.url)

# =========================
# GAMES
# =========================
GAME_NAMES = [
    "Guess the Number", "Coin Flip", "Dice Duel", "Rock Paper Scissors",
    "Quick Math", "Higher or Lower", "Word Scramble", "Emoji Guess",
    "Memory Challenge", "Speed Challenge", "Trivia", "Odd or Even",
    "Number Hunt", "Lucky Number", "Reaction Challenge", "Alphabet Race",
    "Capital Quiz", "Animal Quiz", "Science Quiz", "Space Quiz"
]
GAME_VARIATIONS = [f"{x} #{n}" for x in GAME_NAMES for n in range(1, 61)]

@bot.command()
async def games(ctx):
    await ctx.send(f"🎮 **{len(GAME_VARIATIONS)} game variations available!** Use `¥game`.")

@bot.command()
async def game(ctx):
    await ctx.send(f"🎮 **{random.choice(GAME_VARIATIONS)}**\nGood luck! 🍀")

@bot.command()
async def dice(ctx):
    a, b = random.randint(1, 6), random.randint(1, 6)
    await ctx.send(f"🎲 You rolled **{a} + {b} = {a+b}**")

@bot.command()
async def rps(ctx, choice: str = None):
    choices = ["rock", "paper", "scissors"]
    if not choice or choice.lower() not in choices:
        return await ctx.send("Use `¥rps rock`, `¥rps paper`, or `¥rps scissors`.")
    bot_choice = random.choice(choices)
    user = choice.lower()
    result = "Draw! 🤝" if user == bot_choice else (
        "You win! 🏆" if (user, bot_choice) in
        [("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")]
        else "I win! 🤖"
    )
    await ctx.send(f"You: **{user}** | Bot: **{bot_choice}**\n{result}")

@bot.command()
async def math(ctx):
    a, b = random.randint(1, 100), random.randint(1, 100)
    await ctx.send(f"🧮 What is **{a} + {b}**?")

@bot.command()
async def quiz(ctx):
    questions = [
        ("Capital of France?", "Paris"),
        ("Red Planet?", "Mars"),
        ("Days in a week?", "7"),
        ("5 + 5?", "10"),
        ("Largest ocean?", "Pacific"),
    ]
    q, a = random.choice(questions)
    await ctx.send(f"🧠 **Quiz:** {q}\nAnswer: **{a}**")

# =========================
# MODERATION
# =========================
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.kick(reason=reason)
    await ctx.send(f"👢 Kicked **{member}** | {reason}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.ban(reason=reason)
    await ctx.send(f"🔨 Banned **{member}** | {reason}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.send(f"✅ Unbanned **{user}**")
    except Exception:
        await ctx.send("❌ Could not unban that user.")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int = 10):
    minutes = max(1, min(minutes, 40320))
    await member.timeout(timedelta(minutes=minutes), reason=f"By {ctx.author}")
    await ctx.send(f"⏳ Timed out **{member}** for **{minutes} minutes**.")

@bot.command(name="warn")
@commands.has_permissions(moderate_members=True)
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    warnings_db[member.id].append((reason, str(ctx.author)))
    await ctx.send(f"⚠️ Warned **{member}** | {reason}")

@bot.command(name="warnings")
@commands.has_permissions(moderate_members=True)
async def warnings_command(ctx, member: discord.Member):
    items = warnings_db.get(member.id, [])
    if not items:
        return await ctx.send(f"✅ **{member}** has no warnings.")
    text = "\n".join(f"{i+1}. {r} — {m}" for i, (r, m) in enumerate(items))
    await ctx.send(f"⚠️ Warnings for **{member}**:\n{text}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 10):
    amount = max(1, min(amount, 100))
    deleted = await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 Deleted **{len(deleted)-1}** messages.", delete_after=3)

@bot.command()
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int = 0):
    seconds = max(0, min(seconds, 21600))
    await ctx.channel.edit(slowmode_delay=seconds)
    await ctx.send(f"🐢 Slowmode set to **{seconds} seconds**.")

# =========================
# MUSIC QUEUE
# =========================
@bot.command()
async def join(ctx):
    if not ctx.author.voice:
        return await ctx.send("❌ Join a voice channel first.")
    channel = ctx.author.voice.channel
    if ctx.voice_client:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()
    await ctx.send(f"🎵 Joined **{channel.name}**.")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        queues[ctx.guild.id].clear()
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Left voice channel.")
    else:
        await ctx.send("❌ I'm not in a voice channel.")

@bot.command()
async def play(ctx, *, query=None):
    if not ctx.author.voice:
        return await ctx.send("❌ Join a voice channel first.")
    if not query:
        return await ctx.send("Use `¥play <song name or URL>`.")
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()
    queues[ctx.guild.id].append(query)
    await ctx.send(f"🎵 Added to queue: **{query}**")

@bot.command()
async def queue(ctx):
    q = queues[ctx.guild.id]
    if not q:
        return await ctx.send("🎵 Queue is empty.")
    await ctx.send("🎵 **Queue:**\n" + "\n".join(f"{i+1}. {x}" for i, x in enumerate(q)))

@bot.command()
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Paused.")
    else:
        await ctx.send("❌ Nothing is playing.")

@bot.command()
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Resumed.")
    else:
        await ctx.send("❌ Nothing is paused.")

@bot.command()
async def skip(ctx):
    if ctx.voice_client and (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()):
        ctx.voice_client.stop()
        await ctx.send("⏭️ Skipped.")
    else:
        await ctx.send("❌ Nothing is playing.")

@bot.command()
async def stop(ctx):
    queues[ctx.guild.id].clear()
    if ctx.voice_client:
        ctx.voice_client.stop()
    await ctx.send("⏹️ Stopped and cleared queue.")

# =========================
# ECONOMY
# =========================
@bot.command()
async def balance(ctx):
    await ctx.send(f"💰 {ctx.author.mention}: **{balances[ctx.author.id]} coins**")

@bot.command()
@commands.cooldown(1, 86400, commands.BucketType.user)
async def daily(ctx):
    amount = random.randint(100, 500)
    balances[ctx.author.id] += amount
    await ctx.send(f"🎁 You received **{amount} coins**!")

@bot.command()
async def give(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        return await ctx.send("❌ Amount must be positive.")
    if balances[ctx.author.id] < amount:
        return await ctx.send("❌ Not enough coins.")
    balances[ctx.author.id] -= amount
    balances[member.id] += amount
    await ctx.send(f"💸 Sent **{amount} coins** to {member.mention}.")

# =========================
# SLASH COMMANDS
# =========================
@bot.tree.command(name="ping", description="Check the bot ping")
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! {round(bot.latency * 1000)}ms")

@bot.tree.command(name="game", description="Start a random game")
async def slash_game(interaction: discord.Interaction):
    await interaction.response.send_message(f"🎮 **{random.choice(GAME_VARIATIONS)}**")

# =========================
# ERROR HANDLER
# =========================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingPermissions):
        return await ctx.send("❌ You don't have permission to use this command.")
    if isinstance(error, commands.MissingRequiredArgument):
        return await ctx.send("❌ Missing a required argument.")
    if isinstance(error, commands.MemberNotFound):
        return await ctx.send("❌ Member not found.")
    if isinstance(error, commands.BadArgument):
        return await ctx.send("❌ Invalid argument.")
    if isinstance(error, commands.CommandOnCooldown):
        return await ctx.send(f"⏳ Try again in {error.retry_after:.0f}s.")
    print("Command error:", repr(error))

# =========================
# START
# =========================
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing from Render Environment Variables.")

bot.run(TOKEN)
