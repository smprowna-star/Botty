import os
import re
import time
import random
import asyncio
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database import Database
from music import MusicManager

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_PATH = os.getenv("DATABASE_PATH", "bot.db")
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", "0"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "0"))
TICKET_LOG_CHANNEL_ID = int(os.getenv("TICKET_LOG_CHANNEL_ID", "0"))
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "")
DASHBOARD_ENABLED = os.getenv("DASHBOARD_ENABLED", "true").lower() == "true"
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.getenv("PORT", "10000"))

if not TOKEN:
    raise RuntimeError("Set DISCORD_TOKEN in the environment.")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
db = Database(DATABASE_PATH)
music = MusicManager(bot)
spam_cache = {}
level_cooldowns = {}
giveaway_messages = {}
dashboard_task = None


def is_mod(member: discord.Member) -> bool:
    return member.guild_permissions.manage_guild or member.guild_permissions.administrator


async def ephemeral(interaction: discord.Interaction, content: str):
    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=True)
    else:
        await interaction.response.send_message(content, ephemeral=True)


class TicketPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="ticket:create")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if guild is None:
            return await ephemeral(interaction, "Use this button in a server.")
        existing = db.get_open_ticket(guild.id, interaction.user.id)
        if existing:
            channel = guild.get_channel(existing)
            return await ephemeral(interaction, f"You already have an open ticket: {channel.mention if channel else 'channel ID ' + str(existing)}")
        category = guild.get_channel(TICKET_CATEGORY_ID) if TICKET_CATEGORY_ID else None
        if category is not None and not isinstance(category, discord.CategoryChannel):
            category = None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
        }
        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True)
        for role in guild.roles:
            if role.permissions.manage_channels and not role.is_default():
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        safe_name = re.sub(r"[^a-z0-9-]", "", interaction.user.name.lower().replace(" ", "-"))[:18] or "member"
        channel = await guild.create_text_channel(
            name=f"ticket-{safe_name}",
            category=category,
            overwrites=overwrites,
            topic=f"Support ticket for {interaction.user} ({interaction.user.id})",
            reason="Ticket created from ticket panel",
        )
        db.open_ticket(guild.id, interaction.user.id, channel.id)
        view = TicketCloseView()
        await channel.send(f"{interaction.user.mention} Welcome! Describe your issue and staff will help you.", view=view)
        await interaction.response.send_message(f"Your ticket is ready: {channel.mention}", ephemeral=True)


class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket:close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel) or not channel.topic or "Support ticket for" not in channel.topic:
            return await ephemeral(interaction, "This does not look like a ticket channel.")
        owner_match = re.search(r"\((\d+)\)", channel.topic)
        owner_id = int(owner_match.group(1)) if owner_match else 0
        if interaction.user.id != owner_id and not is_mod(interaction.user):
            return await ephemeral(interaction, "Only the ticket creator or a moderator can close this ticket.")
        db.close_ticket(channel.guild.id, channel.id)
        await interaction.response.send_message("🔒 Ticket closed. This channel will be deleted in 5 seconds.")
        if TICKET_LOG_CHANNEL_ID:
            log_channel = channel.guild.get_channel(TICKET_LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(f"Ticket `{channel.name}` closed by {interaction.user.mention}.")
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.HTTPException:
            pass


@bot.event
async def on_ready():
    bot.add_view(TicketPanel())
    bot.add_view(TicketCloseView())
    try:
        if GUILD_ID:
            guild_obj = discord.Object(id=GUILD_ID)
            bot.tree.copy_global_to(guild=guild_obj)
            await bot.tree.sync(guild=guild_obj)
            print(f"Synced slash commands to guild {GUILD_ID}")
        else:
            await bot.tree.sync()
            print("Synced global slash commands")
    except Exception as exc:
        print(f"Command sync error: {exc!r}")
    if not giveaway_watcher.is_running():
        giveaway_watcher.start()
    if DASHBOARD_ENABLED:
        start_dashboard()
    print(f"Online as {bot.user} (ID: {bot.user.id})")


@bot.event
async def on_member_join(member: discord.Member):
    if WELCOME_CHANNEL_ID:
        channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
        if channel:
            await channel.send(f"Welcome {member.mention} to **{member.guild.name}**! 🎉")
    db.ensure_profile(member.guild.id, member.id)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    # Simple anti-spam: repeated messages or burst posting.
    key = (message.guild.id, message.author.id)
    now = time.monotonic()
    history = spam_cache.setdefault(key, [])
    history[:] = [entry for entry in history if now - entry[0] < 8]
    history.append((now, message.content))
    repeated = len(history) >= 5 and len({item[1] for item in history[-5:]}) <= 2
    burst = len(history) >= 7
    if (repeated or burst) and not message.author.guild_permissions.manage_messages:
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        until = datetime.now(timezone.utc) + timedelta(seconds=30)
        try:
            await message.author.timeout(until, reason="Automatic anti-spam timeout")
            notice = await message.channel.send(f"🚦 {message.author.mention} was timed out for 30 seconds for spam.")
            await asyncio.sleep(6)
            await notice.delete()
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            pass
        spam_cache[key] = []
        return
    # Leveling: XP only for normal messages, cooldown per user.
    cooldown_key = (message.guild.id, message.author.id)
    last = level_cooldowns.get(cooldown_key, 0)
    if now - last >= 60 and message.content.strip():
        level_cooldowns[cooldown_key] = now
        db.ensure_profile(message.guild.id, message.author.id)
        old_level = db.get_level(message.guild.id, message.author.id)
        gained = random.randint(15, 25)
        db.add_xp(message.guild.id, message.author.id, gained)
        new_level = db.get_level(message.guild.id, message.author.id)
        if new_level > old_level:
            await message.channel.send(f"🎉 {message.author.mention} reached level **{new_level}**!")
    await bot.process_commands(message)


@bot.tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! {round(bot.latency * 1000)} ms")


@bot.tree.command(name="help", description="Show the bot's features")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="Ultimate Bot Commands", color=discord.Color.blurple())
    embed.add_field(name="Utility", value="`/ping` `/userinfo` `/serverinfo` `/rank` `/leaderboard`", inline=False)
    embed.add_field(name="Moderation", value="`/kick` `/ban` `/timeout` `/clear`", inline=False)
    embed.add_field(name="Tickets & roles", value="`/ticketpanel` `/rolepanel`", inline=False)
    embed.add_field(name="Economy", value="`/balance` `/daily` `/work` `/pay`", inline=False)
    embed.add_field(name="Giveaways", value="`/giveaway`", inline=False)
    embed.add_field(name="Music", value="`/play` `/skip` `/stop` `/pause` `/resume` `/queue`", inline=False)
    embed.set_footer(text="Dashboard: open your Render service URL")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="userinfo", description="Show information about a member")
async def userinfo(interaction: discord.Interaction, member: discord.Member | None = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"User: {member}", color=discord.Color.blurple())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=str(member.id), inline=False)
    embed.add_field(name="Created", value=discord.utils.format_dt(member.created_at, style="D"))
    if member.joined_at:
        embed.add_field(name="Joined server", value=discord.utils.format_dt(member.joined_at, style="D"))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="serverinfo", description="Show server information")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        return await ephemeral(interaction, "Use this command in a server.")
    embed = discord.Embed(title=guild.name, color=discord.Color.green())
    embed.add_field(name="Members", value=str(guild.member_count or "Unknown"))
    embed.add_field(name="Server ID", value=str(guild.id))
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    await interaction.response.send_message(embed=embed)


def mod_check(interaction: discord.Interaction, member: discord.Member):
    if member.id == interaction.user.id:
        return "You cannot moderate yourself."
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        return "That member has an equal or higher role than yours."
    if interaction.guild.me and member.top_role >= interaction.guild.me.top_role:
        return "My role must be above that member's role."
    return None


@bot.tree.command(name="kick", description="Kick a member")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    issue = mod_check(interaction, member)
    if issue:
        return await ephemeral(interaction, issue)
    await member.kick(reason=reason)
    await interaction.response.send_message(f"👢 Kicked {member.mention}. Reason: {reason}")


@bot.tree.command(name="ban", description="Ban a member")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    issue = mod_check(interaction, member)
    if issue:
        return await ephemeral(interaction, issue)
    await member.ban(reason=reason)
    await interaction.response.send_message(f"🔨 Banned {member.mention}. Reason: {reason}")


@bot.tree.command(name="timeout", description="Timeout a member (max 7 days)")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 10080], reason: str = "No reason provided"):
    issue = mod_check(interaction, member)
    if issue:
        return await ephemeral(interaction, issue)
    await member.timeout(timedelta(minutes=minutes), reason=reason)
    await interaction.response.send_message(f"🔇 Timed out {member.mention} for {minutes} minutes.")


@bot.tree.command(name="clear", description="Delete 1–100 recent messages")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    channel = interaction.channel
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return await ephemeral(interaction, "This channel cannot be cleared.")
    await interaction.response.defer(ephemeral=True)
    deleted = await channel.purge(limit=amount)
    await interaction.followup.send(f"Deleted {len(deleted)} messages.", ephemeral=True)


@bot.tree.command(name="ticketpanel", description="Post the support ticket panel")
@app_commands.checks.has_permissions(manage_guild=True)
async def ticketpanel(interaction: discord.Interaction):
    embed = discord.Embed(title="Support Tickets", description="Press the button below to open a private support ticket.", color=discord.Color.blurple())
    await interaction.channel.send(embed=embed, view=TicketPanel())
    await interaction.response.send_message("Ticket panel posted.", ephemeral=True)


class RoleSelect(discord.ui.Select):
    def __init__(self, roles: list[discord.Role]):
        options = [discord.SelectOption(label=role.name[:100], value=str(role.id)) for role in roles[:25]]
        super().__init__(placeholder="Choose a role to toggle", min_values=1, max_values=1, options=options, custom_id="roles:select")

    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        role = interaction.guild.get_role(role_id)
        if role is None or role.is_default() or role.managed:
            return await ephemeral(interaction, "That role cannot be self-assigned.")
        if role >= interaction.guild.me.top_role:
            return await ephemeral(interaction, "The bot's role must be above the selectable role.")
        member = interaction.user
        if role in member.roles:
            await member.remove_roles(role, reason="Self-service reaction role panel")
            await ephemeral(interaction, f"Removed {role.mention}.")
        else:
            await member.add_roles(role, reason="Self-service role panel")
            await ephemeral(interaction, f"Added {role.mention}.")


class RolePanel(discord.ui.View):
    def __init__(self, roles: list[discord.Role]):
        super().__init__(timeout=None)
        self.add_item(RoleSelect(roles))


@bot.tree.command(name="rolepanel", description="Create a self-assignable role menu")
@app_commands.checks.has_permissions(manage_roles=True)
async def rolepanel(interaction: discord.Interaction, role1: discord.Role, role2: discord.Role | None = None, role3: discord.Role | None = None):
    roles = [r for r in (role1, role2, role3) if r]
    if any(r.is_default() or r.managed or r >= interaction.guild.me.top_role for r in roles):
        return await ephemeral(interaction, "All selectable roles must be unmanaged and below the bot's top role.")
    embed = discord.Embed(title="Choose Your Roles", description="Select a role from the menu to add or remove it.", color=discord.Color.green())
    await interaction.channel.send(embed=embed, view=RolePanel(roles))
    await interaction.response.send_message("Role panel posted.", ephemeral=True)


@bot.tree.command(name="rank", description="Show your level and XP")
async def rank(interaction: discord.Interaction, member: discord.Member | None = None):
    member = member or interaction.user
    db.ensure_profile(interaction.guild_id, member.id)
    xp, level = db.get_xp_level(interaction.guild_id, member.id)
    await interaction.response.send_message(f"🏅 **{member.display_name}** — Level **{level}**, XP **{xp}** (next level at {(level + 1) ** 2 * 100} XP)")


@bot.tree.command(name="leaderboard", description="Show the server XP leaderboard")
async def leaderboard(interaction: discord.Interaction):
    rows = db.leaderboard(interaction.guild_id, 10)
    if not rows:
        return await interaction.response.send_message("No XP data yet.")
    lines = []
    for position, (user_id, xp, level) in enumerate(rows, start=1):
        lines.append(f"**{position}.** <@{user_id}> — Level {level} ({xp} XP)")
    await interaction.response.send_message(embed=discord.Embed(title="🏆 XP Leaderboard", description="\n".join(lines), color=discord.Color.gold()))


@bot.tree.command(name="balance", description="Check your coin balance")
async def balance(interaction: discord.Interaction, member: discord.Member | None = None):
    member = member or interaction.user
    db.ensure_profile(interaction.guild_id, member.id)
    await interaction.response.send_message(f"🪙 {member.mention} has **{db.balance(interaction.guild_id, member.id):,}** coins.")


@bot.tree.command(name="daily", description="Claim your daily coins")
async def daily(interaction: discord.Interaction):
    amount, success = db.claim_daily(interaction.guild_id, interaction.user.id, 250)
    if success:
        await interaction.response.send_message(f"🎁 You claimed **{amount}** coins! Come back tomorrow.")
    else:
        await interaction.response.send_message("⏳ You already claimed your daily coins. Try again later.", ephemeral=True)


@bot.tree.command(name="work", description="Work to earn coins")
async def work(interaction: discord.Interaction):
    amount = random.randint(20, 100)
    success = db.claim_work(interaction.guild_id, interaction.user.id, amount, 3600)
    if not success:
        return await ephemeral(interaction, "You worked recently. Try again in an hour.")
    await interaction.response.send_message(f"💼 You earned **{amount}** coins!")


@bot.tree.command(name="pay", description="Pay coins to another member")
async def pay(interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, 1, 1000000]):
    if member.bot or member.id == interaction.user.id:
        return await ephemeral(interaction, "Choose another human member.")
    if db.transfer(interaction.guild_id, interaction.user.id, member.id, amount):
        await interaction.response.send_message(f"💸 Sent **{amount:,}** coins to {member.mention}.")
    else:
        await ephemeral(interaction, "You don't have enough coins.")


@bot.tree.command(name="giveaway", description="Start a giveaway in this channel")
@app_commands.checks.has_permissions(manage_guild=True)
async def giveaway(interaction: discord.Interaction, prize: str, minutes: app_commands.Range[int, 1, 10080], winners: app_commands.Range[int, 1, 10] = 1):
    ends = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    embed = discord.Embed(title="🎉 GIVEAWAY 🎉", description=f"**Prize:** {prize}\nReact with 🎉 to enter!\n**Winners:** {winners}\nEnds {discord.utils.format_dt(ends, style='R')}", color=discord.Color.magenta())
    await interaction.response.defer(ephemeral=True)
    message = await interaction.channel.send(embed=embed)
    await message.add_reaction("🎉")
    db.add_giveaway(interaction.guild_id, interaction.channel_id, message.id, prize, winners, ends.timestamp())
    await interaction.followup.send(f"Giveaway started: {message.jump_url}", ephemeral=True)


@tasks.loop(seconds=20)
async def giveaway_watcher():
    for item in db.due_giveaways(time.time()):
        guild = bot.get_guild(item["guild_id"])
        channel = guild.get_channel(item["channel_id"]) if guild else None
        message = None
        if channel:
            try:
                message = await channel.fetch_message(item["message_id"])
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        entrants = []
        if message:
            for reaction in message.reactions:
                if str(reaction.emoji) == "🎉":
                    async for user in reaction.users():
                        if not user.bot:
                            entrants.append(user)
        unique = {user.id: user for user in entrants}
        winners = random.sample(list(unique.values()), min(item["winners"], len(unique))) if unique else []
        if channel:
            if winners:
                await channel.send(f"🎉 Congratulations {', '.join(w.mention for w in winners)}! You won **{item['prize']}**.")
            else:
                await channel.send(f"Giveaway ended for **{item['prize']}**, but there were no valid entries.")
        db.finish_giveaway(item["message_id"])


@giveaway_watcher.before_loop
async def before_giveaway_watcher():
    await bot.wait_until_ready()


@bot.tree.command(name="play", description="Play a song from a supported URL or search query")
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    try:
        result = await music.play(interaction, query)
        await interaction.followup.send(result)
    except Exception as exc:
        print(f"Music error: {exc!r}")
        await interaction.followup.send(f"Could not play that track: {exc}")


@bot.tree.command(name="skip", description="Skip the current track")
async def skip(interaction: discord.Interaction):
    await interaction.response.send_message(await music.skip(interaction))


@bot.tree.command(name="stop", description="Stop music and clear queue")
async def stop(interaction: discord.Interaction):
    await interaction.response.send_message(await music.stop(interaction))


@bot.tree.command(name="pause", description="Pause music")
async def pause(interaction: discord.Interaction):
    await interaction.response.send_message(await music.pause(interaction))


@bot.tree.command(name="resume", description="Resume music")
async def resume(interaction: discord.Interaction):
    await interaction.response.send_message(await music.resume(interaction))


@bot.tree.command(name="queue", description="Show queued music")
async def queue(interaction: discord.Interaction):
    await interaction.response.send_message(await music.show_queue(interaction))


def start_dashboard():
    global dashboard_task
    if dashboard_task and not dashboard_task.done():
        return
    async def runner():
        try:
            from dashboard import run_dashboard
            await run_dashboard(bot, db, DASHBOARD_HOST, DASHBOARD_PORT, DASHBOARD_SECRET)
        except Exception as exc:
            print(f"Dashboard failed to start: {exc!r}")
    dashboard_task = asyncio.create_task(runner())


if __name__ == "__main__":
    bot.run(TOKEN)


def run_web():
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

Thread(target=run_web, daemon=True).start()

if __name__ == "__main__":
    bot.run(TOKEN)
