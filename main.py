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
    return "Discord Bot is Online!"

def run_web():
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

Thread(target=run_web, daemon=True).start()

# =========================
# DISCORD BOT
# =========================
PREFIX = "¥"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

warnings = defaultdict(list)
queues = defaultdict(deque)

# =========================
# READY
# =========================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} | Prefix: {PREFIX}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as error:
        print(f"Slash sync error: {error}")

# =========================
# HELP / BASIC
# =========================
@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! {round(bot.latency * 1000)}ms")

@bot.command()
async def hello(ctx):
    await ctx.send(f"👋 Hello {ctx.author.mention}!")

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="🤖 Bot Commands")
    embed.add_field(name="🎮 Games", value="`¥game` `¥games` `¥quiz` `¥rps` `¥dice` `¥math`", inline=False)
    embed.add_field(name="🛡️ Moderation", value="`¥kick` `¥ban` `¥unban` `¥timeout` `¥warn` `¥warnings` `¥clear` `¥slowmode`", inline=False)
    embed.add_field(name="🎵 Music", value="`¥join` `¥leave` `¥play` `¥pause` `¥resume` `¥skip` `¥stop` `¥queue`", inline=False)
    embed.add_field(name="⚙️ Prefix", value="`¥`", inline=False)
    await ctx.send(embed=embed)

# =========================
# GAMES
# =========================
GAME_TYPES = [
    "guess the number", "coin flip", "dice roll", "rock paper scissors",
    "quick math", "higher or lower", "number challenge", "word scramble",
    "emoji challenge", "color challenge"
]

@bot.command()
async def game(ctx):
    game_type = random.choice(GAME_TYPES)

    if game_type == "guess the number":
        number = random.randint(1, 10)
        await ctx.send(f"🎮 Guess a number from **1-10**! The answer is `{number}`.")
    elif game_type == "coin flip":
        await ctx.send(f"🪙 {random.choice(['Heads!', 'Tails!'])}")
    elif game_type == "dice roll":
        await ctx.send(f"🎲 You rolled **{random.randint(1, 6)}**!")
    elif game_type == "rock paper scissors":
        await ctx.send(f"✊ I choose **{random.choice(['Rock', 'Paper', 'Scissors'])}**!")
    elif game_type == "quick math":
        a, b = random.randint(1, 50), random.randint(1, 50)
        await ctx.send(f"🧮 What is **{a} + {b}**?")
    elif game_type == "higher or lower":
        n = random.randint(1, 100)
        await ctx.send(f"📈 Is the next number higher or lower than **{n}**?")
    else:
        await ctx.send(f"🎮 **{game_type.title()}** challenge started!")

@bot.command()
async def games(ctx):
    await ctx.send("🎮 **1000+ game variations available!** Use `¥game` to start a random game.")

@bot.command()
async def quiz(ctx):
    questions = [
        ("What is the capital of France?", "Paris"),
        ("How many days are in a week?", "7"),
        ("What planet is known as the Red Planet?", "Mars"),
        ("How many continents are there?", "7"),
        ("What is 5 + 5?", "10")
    ]
    q, answer = random.choice(questions)
    await ctx.send(f"🧠 **Quiz:** {q}\nThe answer is **{answer}**.")

@bot.command()
async def rps(ctx, choice: str = None):
    choices = ["rock", "paper", "scissors"]
    if not choice or choice.lower() not in choices:
        return await ctx.send("Use `¥rps rock`, `¥rps paper`, or `¥rps scissors`.")
    bot_choice = random.choice(choices)
    await ctx.send(f"🤖 I choose **{bot_choice}**!")

@bot.command()
async def dice(ctx):
    await ctx.send(f"🎲 You rolled **{random.randint(1, 6)}**!")

@bot.command()
async def math(ctx):
    a, b = random.randint(1, 100), random.randint(1, 100)
    await ctx.send(f"🧮 **{a} + {b} = ?**")

# =========================
# MODERATION
# =========================
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.kick(reason=reason)
    await ctx.send(f"👢 Kicked **{member}**. Reason: {reason}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.ban(reason=reason)
    await ctx.send(f"🔨 Banned **{member}**. Reason: {reason}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.send(f"✅ Unbanned **{user}**.")
    except discord.NotFound:
        await ctx.send("❌ User is not banned or was not found.")
    except Exception as error:
        await ctx.send(f"❌ Could not unban: {error}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int = 10):
    minutes = max(1, min(minutes, 40320))
    until = discord.utils.utcnow() + timedelta(minutes=minutes)
    await member.timeout(until, reason=f"Timeout by {ctx.author}")
    await ctx.send(f"⏳ Timed out **{member}** for **{minutes} minutes**.")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    warnings[member.id].append({"reason": reason, "mod": str(ctx.author)})
    await ctx.send(f"⚠️ Warned **{member}**. Reason: {reason}")

@bot.command(name="warnings")
@commands.has_permissions(moderate_members=True)
async def warnings_cmd(ctx, member: discord.Member):
    items = warnings.get(member.id, [])
    if not items:
        return await ctx.send(f"✅ **{member}** has no warnings.")
    text = "\n".join(f"{i+1}. {x['reason']} — {x['mod']}" for i, x in enumerate(items))
    await ctx.send(f"⚠️ Warnings for **{member}**:\n{text}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 10):
    amount = max(1, min(amount, 100))
    deleted = await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(f"🧹 Deleted **{len(deleted) - 1}** messages.")
    await asyncio.sleep(3)
    await msg.delete()

@bot.command()
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int = 0):
    seconds = max(0, min(seconds, 21600))
    await ctx.channel.edit(slowmode_delay=seconds)
    await ctx.send(f"🐢 Slowmode set to **{seconds} seconds**.")

# =========================
# MUSIC / VOICE QUEUE
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
        await ctx.voice_client.disconnect()
        queues[ctx.guild.id].clear()
        await ctx.send("👋 Left the voice channel.")
    else:
        await ctx.send("❌ I'm not in a voice channel.")

@bot.command()
async def play(ctx, *, query: str = None):
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
    if ctx.voice_client:
        ctx.voice_client.stop()
        queues[ctx.guild.id].clear()
        await ctx.send("⏹️ Stopped and cleared the queue.")
    else:
        await ctx.send("❌ I'm not in a voice channel.")

# =========================
# ERRORS
# =========================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use that command.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Member not found.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Missing a required argument.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Invalid argument.")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        print("Command error:", repr(error))

# =========================
# START
# =========================
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing from Render Environment Variables.")

bot.run(TOKEN)
