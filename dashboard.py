import hmac
import os
from aiohttp import web


def create_app(bot, db, secret):
    app = web.Application()
    app["bot"] = bot
    app["db"] = db
    app["secret"] = secret

    @web.middleware
    async def auth_middleware(request, handler):
        if request.path == "/health":
            return await handler(request)
        configured = request.app["secret"]
        if configured:
            supplied = request.headers.get("X-Dashboard-Secret", "")
            query_secret = request.query.get("key", "")
            if not (hmac.compare_digest(supplied, configured) or hmac.compare_digest(query_secret, configured)):
                raise web.HTTPUnauthorized(text="Set X-Dashboard-Secret header or ?key=... to access the dashboard.")
        return await handler(request)

    app.middlewares.append(auth_middleware)

    async def health(request):
        return web.json_response({"ok": True})

    async def index(request):
        bot = request.app["bot"]
        guilds = [{"id": str(g.id), "name": g.name, "members": g.member_count} for g in bot.guilds]
        return web.json_response({
            "name": "Discord Bot Dashboard API",
            "online": not bot.is_closed(),
            "bot_user": str(bot.user) if bot.user else None,
            "guild_count": len(guilds),
            "guilds": guilds,
            "endpoints": ["/api/stats", "/api/guilds/{guild_id}", "/api/guilds/{guild_id}/leaderboard"],
            "note": "This starter dashboard is a protected JSON API, not a full OAuth web UI."
        })

    async def stats(request):
        bot = request.app["bot"]
        return web.json_response({
            "online": not bot.is_closed(),
            "guild_count": len(bot.guilds),
            "member_count": sum(g.member_count or 0 for g in bot.guilds),
            "latency_ms": round(bot.latency * 1000) if bot.is_ready() else None,
        })

    async def guild_info(request):
        bot = request.app["bot"]
        guild = bot.get_guild(int(request.match_info["guild_id"]))
        if guild is None:
            raise web.HTTPNotFound(text="Guild not found.")
        return web.json_response({
            "id": str(guild.id),
            "name": guild.name,
            "member_count": guild.member_count,
            "channels": [{"id": str(c.id), "name": c.name, "type": str(c.type)} for c in guild.channels],
            "roles": [{"id": str(r.id), "name": r.name, "position": r.position} for r in guild.roles if not r.is_default()],
        })

    async def leaderboard(request):
        guild_id = int(request.match_info["guild_id"])
        rows = request.app["db"].leaderboard(guild_id, 10)
        return web.json_response([{"user_id": str(user_id), "xp": xp, "level": level} for user_id, xp, level in rows])

    app.router.add_get("/health", health)
    app.router.add_get("/", index)
    app.router.add_get("/api/stats", stats)
    app.router.add_get("/api/guilds/{guild_id}", guild_info)
    app.router.add_get("/api/guilds/{guild_id}/leaderboard", leaderboard)
    return app


async def run_dashboard(bot, db, host, port, secret):
    app = create_app(bot, db, secret)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"Dashboard API listening on {host}:{port}; secret protection {'enabled' if secret else 'DISABLED'}")
