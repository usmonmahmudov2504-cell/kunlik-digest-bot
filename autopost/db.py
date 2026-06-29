"""AvtoPost — SQLite yordamchisi (yengil, stdlib sqlite3).

TICK qisqa muddatli ishlagani uchun sync sqlite3 yetarli (ORM shart emas).
"""
from __future__ import annotations
import os
import sqlite3
import hashlib
import datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("MB_DB", os.path.join(HERE, "box.db"))
SCHEMA = os.path.join(HERE, "schema.sql")


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db() -> None:
    """schema.sql ni qo'llaydi (mavjud jadvallarga tegmaydi — IF NOT EXISTS)."""
    with open(SCHEMA, encoding="utf-8") as f:
        sql = f.read()
    db = connect()
    db.executescript(sql)
    db.commit()
    db.close()


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def content_hash(text: str) -> str:
    """Takror tekshiruv uchun normallashtirilgan matn sha1."""
    import re
    norm = re.sub(r"\W+", "", (text or "").lower())
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


# ---- TICK so'rovlari ----
def get_due_schedules(db, now: str) -> list[sqlite3.Row]:
    """Vaqti kelgan (next_run<=now) faol jadvallar — kanal/qolip bilan birga."""
    return db.execute("""
        SELECT s.*, c.tg_chat, c.title AS ch_title, c.pattern_id, c.id AS channel_id
        FROM schedules s
        JOIN channels c ON c.id = s.channel_id
        WHERE s.is_active = 1 AND c.is_active = 1
          AND (s.next_run IS NULL OR s.next_run <= ?)
    """, (now,)).fetchall()


def get_pattern(db, pattern_id: int) -> sqlite3.Row | None:
    if not pattern_id:
        return None
    return db.execute("SELECT * FROM patterns WHERE id=?", (pattern_id,)).fetchone()


def get_channel_sources(db, channel_id: int) -> list[sqlite3.Row]:
    return db.execute("""
        SELECT cs.keywords, src.*
        FROM channel_sources cs
        JOIN sources src ON src.id = cs.source_id
        WHERE cs.channel_id = ? AND src.is_active = 1
    """, (channel_id,)).fetchall()


def is_duplicate(db, channel_id: int, c_hash: str) -> bool:
    row = db.execute(
        "SELECT 1 FROM posts_log WHERE channel_id=? AND content_hash=? LIMIT 1",
        (channel_id, c_hash)).fetchone()
    return row is not None


def mark_posted(db, channel_id, source_id, src_msg_id, c_hash) -> None:
    db.execute("""INSERT INTO posts_log(channel_id, source_id, src_msg_id, content_hash)
                  VALUES (?,?,?,?)""", (channel_id, source_id, src_msg_id, c_hash))


def set_next_run(db, sched_id: int, next_run: str) -> None:
    db.execute("UPDATE schedules SET next_run=? WHERE id=?", (next_run, sched_id))


# ---- Demo ma'lumot (test/boshlash uchun) ----
def seed_demo() -> None:
    db = connect()
    cur = db.execute("SELECT COUNT(*) AS n FROM patterns").fetchone()
    if cur["n"]:
        db.close()
        return
    db.execute("""INSERT INTO patterns(id,name,header,footer,hashtags,rewrite_lvl)
        VALUES (1,'AvtoPost-default','🚀 <b>AvtoPost</b>',
                '👉 {channel} · obuna bo''ling 🔔','#AvtoPost',1)""")
    db.execute("INSERT INTO clients(id,name) VALUES (1,'Demo mijoz')")
    db.execute("""INSERT INTO channels(id,client_id,pattern_id,tg_chat,title)
                  VALUES (1,1,1,'@morningbox','HAYA COLLECTION')""")
    # RSS manba -> Telethon/session SHART EMAS (login kerak emas).
    db.execute("INSERT INTO sources(id,kind,ref) VALUES (1,'rss','https://www.gazeta.uz/uz/rss/')")
    db.execute("""INSERT INTO channel_sources(channel_id,source_id,keywords)
                  VALUES (1,1,'')""")
    db.execute("""INSERT INTO schedules(id,channel_id,post_type,cron,next_run)
                  VALUES (1,1,'scrape','*/30 * * * *',NULL)""")
    db.commit()
    db.close()


if __name__ == "__main__":
    init_db()
    seed_demo()
    print("DB tayyor:", DB_PATH)
