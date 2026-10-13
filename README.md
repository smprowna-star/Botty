import os
import random
import asyncio
import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

spam_tracker = {}
ticket_users = set()

@bot.event
async def on_ready():
    print(f"✅ Himu Bot is online as {bot.user}")

@bot.event
async def on_member_join(member):
    channel = member.guild.system_channel
    if channel:
        await channel.send(
            f"👋 Welcome {member.mention} to {member.guild.name}!"
        )

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    key = (message.guild.id, message.author.id) if message.guild else None

    if key:
        now = asyncio.get_running_loop().time()
        timestamps = spam_tracker.get(key, [])
        timestamps = [t for t in timestamps if now - t < 5]
        timestamps.append(now)
        spam_tracker[key] = timestamps

        if len(timestamps) >= 6:
            try:
                await message.author.timeout(
                    discord.timedelta(seconds=30),
                    reason="Anti-spam"
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            spam_tracker[key] = []
            return

    await bot.process_commands(message)

@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! `{round(bot.latency * 1000)} ms`")

@bot.command()
async def joke(ctx):
    jokes = [
        "Why did the computer get cold? It left its Windows open!",
        "Why was the math book sad? It had too many problems!",
        "Why do programmers prefer dark mode? Because light attracts bugs!"
    ]
    await ctx.send(random.choice(jokes))

@bot.command(name="8ball")
async def eightball(ctx, *, question: str):
    answers = [
        "Definitely yes! 🎉",
        "Probably! 👍",
        "Ask me later. 🤔",
        "I don't think so. 😅",
        "Absolutely not! ❌"
    ]
    await ctx.send(f"🎱 {random.choice(answers)}")

@bot.command()
async def coinflip(ctx):
    await ctx.send(random.choice(["🪙 Heads!", "🪙 Tails!"]))

@bot.command()
async def server(ctx):
    guild = ctx.guild
    await ctx.send(
        f"📊 **{guild.name}**\n"
        f"Members: {guild.member_count}\n"
        f"Channels: {len(guild.channels)}"
    )

@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    await ctx.send(
        f"👤 **{member.display_name}**\n"
        f"User ID: `{member.id}`\n"
        f"Account created: {member.created_at:%Y-%m-%d}"
    )

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.ban(reason=reason)
    await ctx.send(f"🔨 Banned {member} | Reason: {reason}")

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.kick(reason=reason)
    await ctx.send(f"👢 Kicked {member} | Reason: {reason}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    if not 1 <= amount <= 100:
        await ctx.send("Choose a number between 1 and 100.")
        return

    deleted = await ctx.channel.purge(limit=amount + 1)
    await ctx.send(
        f"🧹 Deleted {len(deleted) - 1} messages.",
        delete_after=5
    )

@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int = 10):
    if not 1 <= minutes <= 10080:
        await ctx.send("Choose 1–10080 minutes.")
        return

    await member.timeout(
        discord.utils.utcnow() + discord.timedelta(minutes=minutes),
        reason=f"Requested by {ctx.author}"
    )
    await ctx.send(f"⏳ Timed out {member} for {minutes} minutes.")

@bot.command()
async def ticket(ctx):
    guild = ctx.guild
    if guild is None:
        await ctx.send("Use this command inside a server.")
        return

    existing = discord.utils.get(
        guild.text_channels,
        name=f"ticket-{ctx.author.id}"
    )
    if existing:
        await ctx.send(f"You already have a ticket: {existing.mention}")
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False
        ),
        ctx.author: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True
        )
    }

    channel = await guild.create_text_channel(
        f"ticket-{ctx.author.id}",
        overwrites=overwrites,
        reason="Support ticket created"
    )
    await channel.send(
        f"🎫 Welcome {ctx.author.mention}! Describe your issue here.\n"
        "Staff can close this ticket when finished."
    )
    await ctx.send(f"Ticket created: {channel.mention}")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def close(ctx):
    if ctx.channel.name.startswith("ticket-"):
        await ctx.send("🔒 Closing ticket in 5 seconds...")
        await asyncio.sleep(5)
        await ctx.channel.delete(reason="Ticket closed")
    else:
        await ctx.send("Use this command inside a ticket channel.")

@bot.command()
async def help(ctx):
    await ctx.send(
        "**🤖 HIMU BOT COMMANDS**\n\n"
        "**Moderation:** `!ban`, `!kick`, `!clear`, `!timeout`\n"
        "**Tickets:** `!ticket`, `!close`\n"
        "**Fun:** `!joke`, `!8ball <question>`, `!coinflip`\n"
        "**Info:** `!server`, `!userinfo [@user]`\n"
        "**Utility:** `!ping`, `!help`"
    )

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use that command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ You're missing a required argument. Try `!help`.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Member not found.")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        print(f"Command error: {error}")
        await ctx.send("⚠️ Something went wrong while running that command.")

if not TOKEN:
    raise RuntimeError("Set the DISCORD_TOKEN environment variable!")

bot.run(TOKEN)
