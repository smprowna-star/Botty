import sqlite3
import threading
import time


class Database:
    def __init__(self, path="bot.db"):
        self.path = path
        self.lock = threading.RLock()
        with self.connect() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                xp INTEGER NOT NULL DEFAULT 0,
                coins INTEGER NOT NULL DEFAULT 0,
                daily_at REAL NOT NULL DEFAULT 0,
                work_at REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS tickets (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                open INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS giveaways (
                message_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                prize TEXT NOT NULL,
                winners INTEGER NOT NULL,
                ends_at REAL NOT NULL,
                finished INTEGER NOT NULL DEFAULT 0
            );
            """)

    def connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    def ensure_profile(self, guild_id, user_id):
        with self.lock, self.connect() as con:
            con.execute("INSERT OR IGNORE INTO profiles(guild_id,user_id) VALUES(?,?)", (guild_id, user_id))

    @staticmethod
    def level_for(xp):
        return int((xp / 100) ** 0.5)

    def add_xp(self, guild_id, user_id, amount):
        with self.lock, self.connect() as con:
            con.execute("INSERT OR IGNORE INTO profiles(guild_id,user_id) VALUES(?,?)", (guild_id, user_id))
            con.execute("UPDATE profiles SET xp=xp+? WHERE guild_id=? AND user_id=?", (amount, guild_id, user_id))

    def get_xp_level(self, guild_id, user_id):
        self.ensure_profile(guild_id, user_id)
        with self.connect() as con:
            row = con.execute("SELECT xp FROM profiles WHERE guild_id=? AND user_id=?", (guild_id, user_id)).fetchone()
        xp = row["xp"]
        return xp, self.level_for(xp)

    def get_level(self, guild_id, user_id):
        return self.get_xp_level(guild_id, user_id)[1]

    def leaderboard(self, guild_id, limit=10):
        with self.connect() as con:
            rows = con.execute("SELECT user_id,xp FROM profiles WHERE guild_id=? ORDER BY xp DESC LIMIT ?", (guild_id, limit)).fetchall()
        return [(r["user_id"], r["xp"], self.level_for(r["xp"])) for r in rows]

    def balance(self, guild_id, user_id):
        self.ensure_profile(guild_id, user_id)
        with self.connect() as con:
            return con.execute("SELECT coins FROM profiles WHERE guild_id=? AND user_id=?", (guild_id, user_id)).fetchone()["coins"]

    def claim_daily(self, guild_id, user_id, amount):
        now = time.time()
        with self.lock, self.connect() as con:
            con.execute("INSERT OR IGNORE INTO profiles(guild_id,user_id) VALUES(?,?)", (guild_id, user_id))
            row = con.execute("SELECT daily_at FROM profiles WHERE guild_id=? AND user_id=?", (guild_id, user_id)).fetchone()
            if now - row["daily_at"] < 86400:
                return 0, False
            con.execute("UPDATE profiles SET coins=coins+?, daily_at=? WHERE guild_id=? AND user_id=?", (amount, now, guild_id, user_id))
            return amount, True

    def claim_work(self, guild_id, user_id, amount, cooldown):
        now = time.time()
        with self.lock, self.connect() as con:
            con.execute("INSERT OR IGNORE INTO profiles(guild_id,user_id) VALUES(?,?)", (guild_id, user_id))
            row = con.execute("SELECT work_at FROM profiles WHERE guild_id=? AND user_id=?", (guild_id, user_id)).fetchone()
            if now - row["work_at"] < cooldown:
                return False
            con.execute("UPDATE profiles SET coins=coins+?, work_at=? WHERE guild_id=? AND user_id=?", (amount, now, guild_id, user_id))
            return True

    def transfer(self, guild_id, sender, receiver, amount):
        with self.lock, self.connect() as con:
            con.execute("INSERT OR IGNORE INTO profiles(guild_id,user_id) VALUES(?,?)", (guild_id, sender))
            con.execute("INSERT OR IGNORE INTO profiles(guild_id,user_id) VALUES(?,?)", (guild_id, receiver))
            row = con.execute("SELECT coins FROM profiles WHERE guild_id=? AND user_id=?", (guild_id, sender)).fetchone()
            if row["coins"] < amount:
                return False
            con.execute("UPDATE profiles SET coins=coins-? WHERE guild_id=? AND user_id=?", (amount, guild_id, sender))
            con.execute("UPDATE profiles SET coins=coins+? WHERE guild_id=? AND user_id=?", (amount, guild_id, receiver))
            return True

    def get_open_ticket(self, guild_id, user_id):
        with self.connect() as con:
            row = con.execute("SELECT channel_id FROM tickets WHERE guild_id=? AND user_id=? AND open=1", (guild_id, user_id)).fetchone()
        return row["channel_id"] if row else None

    def open_ticket(self, guild_id, user_id, channel_id):
        with self.lock, self.connect() as con:
            con.execute("INSERT OR REPLACE INTO tickets(guild_id,user_id,channel_id,open) VALUES(?,?,?,1)", (guild_id, user_id, channel_id))

    def close_ticket(self, guild_id, channel_id):
        with self.lock, self.connect() as con:
            con.execute("UPDATE tickets SET open=0 WHERE guild_id=? AND channel_id=?", (guild_id, channel_id))

    def add_giveaway(self, guild_id, channel_id, message_id, prize, winners, ends_at):
        with self.lock, self.connect() as con:
            con.execute("INSERT OR REPLACE INTO giveaways(message_id,guild_id,channel_id,prize,winners,ends_at,finished) VALUES(?,?,?,?,?,?,0)", (message_id, guild_id, channel_id, prize, winners, ends_at))

    def due_giveaways(self, now):
        with self.connect() as con:
            rows = con.execute("SELECT * FROM giveaways WHERE finished=0 AND ends_at<=?", (now,)).fetchall()
        return [dict(row) for row in rows]

    def finish_giveaway(self, message_id):
        with self.lock, self.connect() as con:
            con.execute("UPDATE giveaways SET finished=1 WHERE message_id=?", (message_id,))
