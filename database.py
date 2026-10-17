import sqlite3

DB_NAME = "bot.db"


def connect():
    return sqlite3.connect(DB_NAME)


def setup():
    db = connect()

    db.execute("""
        CREATE TABLE IF NOT EXISTS guilds (
            guild_id INTEGER PRIMARY KEY,
            prefix TEXT NOT NULL DEFAULT '!'
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            guild_id INTEGER PRIMARY KEY,
            welcome_enabled INTEGER DEFAULT 0,
            welcome_channel INTEGER DEFAULT 0,
            logs_enabled INTEGER DEFAULT 0,
            logs_channel INTEGER DEFAULT 0
        )
    """)

    db.commit()
    db.close()


def get_prefix(guild_id):
    db = connect()

    row = db.execute(
        "SELECT prefix FROM guilds WHERE guild_id = ?",
        (guild_id,)
    ).fetchone()

    db.close()

    return row[0] if row else "!"


def set_prefix(guild_id, prefix):
    db = connect()

    db.execute("""
        INSERT INTO guilds (guild_id, prefix)
        VALUES (?, ?)
        ON CONFLICT(guild_id)
        DO UPDATE SET prefix = excluded.prefix
    """, (guild_id, prefix))

    db.commit()
    db.close()


def get_settings(guild_id):
    db = connect()

    row = db.execute("""
        SELECT welcome_enabled,
               welcome_channel,
               logs_enabled,
               logs_channel
        FROM settings
        WHERE guild_id = ?
    """, (guild_id,)).fetchone()

    db.close()

    if not row:
        return {
            "welcome_enabled": False,
            "welcome_channel": 0,
            "logs_enabled": False,
            "logs_channel": 0
        }

    return {
        "welcome_enabled": bool(row[0]),
        "welcome_channel": row[1],
        "logs_enabled": bool(row[2]),
        "logs_channel": row[3]
    }


def save_settings(
    guild_id,
    welcome_enabled,
    welcome_channel,
    logs_enabled,
    logs_channel
):
    db = connect()

    db.execute("""
        INSERT INTO settings (
            guild_id,
            welcome_enabled,
            welcome_channel,
            logs_enabled,
            logs_channel
        )
        VALUES (?, ?, ?, ?, ?)

        ON CONFLICT(guild_id)
        DO UPDATE SET
            welcome_enabled = excluded.welcome_enabled,
            welcome_channel = excluded.welcome_channel,
            logs_enabled = excluded.logs_enabled,
            logs_channel = excluded.logs_channel
    """, (
        guild_id,
        int(welcome_enabled),
        welcome_channel,
        int(logs_enabled),
        logs_channel
    ))

    db.commit()
    db.close()
