"""Morning Box — Admin bot (aiogram 3).

Mijoz/kanal/manba/jadvalni Telegram buyruqlari orqali boshqarish (DB'ga qo'lda
SQL yozish shart emas). Faqat MB_ADMIN_ID egasiga ruxsat.

Ishga tushirish (always-on yoki lokal):  python admin_bot.py
ENV: MB_BOT_TOKEN, MB_ADMIN_ID
"""
from __future__ import annotations
import os
import asyncio
import db

TOKEN = os.environ.get("MB_BOT_TOKEN", "")
ADMIN = int(os.environ.get("MB_ADMIN_ID", "0") or 0)

HELP = (
    "📦 <b>Morning Box — Admin</b>\n\n"
    "/add_client <ism>\n"
    "/add_channel <client_id> <@kanal> [pattern_id]\n"
    "/add_source <@manba|rss_url> [rss]\n"
    "/link <channel_id> <source_id> [kalit,so'z]\n"
    "/schedule <channel_id> <tur> <cron>\n"
    "    misol: /schedule 1 scrape */30 * * * *\n"
    "/channels   /sources   /schedules\n"
)


def _exec(sql, args=()):
    d = db.connect(); cur = d.execute(sql, args); d.commit()
    rid = cur.lastrowid; d.close(); return rid


def _rows(sql, args=()):
    d = db.connect(); rs = d.execute(sql, args).fetchall(); d.close(); return rs


def main():
    if not TOKEN:
        print("MB_BOT_TOKEN yo'q."); return
    try:
        from aiogram import Bot, Dispatcher
        from aiogram.filters import Command
        from aiogram.enums import ParseMode
        from aiogram.client.default import DefaultBotProperties
    except Exception:
        print("aiogram yo'q -> `pip install aiogram`"); return

    db.init_db()
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    def ok(m):                                # faqat admin
        return ADMIN and m.from_user and m.from_user.id == ADMIN

    @dp.message(Command("start", "help"))
    async def _h(m):
        await m.answer(HELP if ok(m) else "Ruxsat yo'q.")

    @dp.message(Command("add_client"))
    async def _ac(m):
        if not ok(m): return
        name = m.text.split(maxsplit=1)[1] if len(m.text.split()) > 1 else "Mijoz"
        rid = _exec("INSERT INTO clients(name) VALUES(?)", (name,))
        await m.answer(f"✅ Mijoz #{rid}: {name}")

    @dp.message(Command("add_channel"))
    async def _ach(m):
        if not ok(m): return
        p = m.text.split()
        if len(p) < 3:
            return await m.answer("/add_channel <client_id> <@kanal> [pattern_id]")
        cid, chat = int(p[1]), p[2]
        pat = int(p[3]) if len(p) > 3 else 1
        rid = _exec("INSERT INTO channels(client_id,pattern_id,tg_chat,title) VALUES(?,?,?,?)",
                    (cid, pat, chat, chat))
        await m.answer(f"✅ Kanal #{rid}: {chat} (pattern {pat})")

    @dp.message(Command("add_source"))
    async def _as(m):
        if not ok(m): return
        p = m.text.split()
        if len(p) < 2:
            return await m.answer("/add_source <@manba|rss_url> [rss]")
        kind = "rss" if (len(p) > 2 and p[2] == "rss") else "tg"
        rid = _exec("INSERT INTO sources(kind,ref) VALUES(?,?)", (kind, p[1]))
        await m.answer(f"✅ Manba #{rid}: {p[1]} ({kind})")

    @dp.message(Command("link"))
    async def _lk(m):
        if not ok(m): return
        p = m.text.split(maxsplit=3)
        if len(p) < 3:
            return await m.answer("/link <channel_id> <source_id> [kalit,so'z]")
        kw = p[3] if len(p) > 3 else ""
        _exec("INSERT OR REPLACE INTO channel_sources(channel_id,source_id,keywords) VALUES(?,?,?)",
              (int(p[1]), int(p[2]), kw))
        await m.answer(f"✅ Kanal {p[1]} ⟵ manba {p[2]} (filtr: {kw or 'hammasi'})")

    @dp.message(Command("schedule"))
    async def _sc(m):
        if not ok(m): return
        p = m.text.split(maxsplit=3)
        if len(p) < 4:
            return await m.answer("/schedule <channel_id> <tur> <cron>")
        rid = _exec("INSERT INTO schedules(channel_id,post_type,cron,next_run) VALUES(?,?,?,NULL)",
                    (int(p[1]), p[2], p[3]))
        await m.answer(f"✅ Jadval #{rid}: kanal {p[1]}, '{p[3]}'")

    @dp.message(Command("channels"))
    async def _lc(m):
        if not ok(m): return
        rs = _rows("SELECT id,tg_chat,pattern_id FROM channels")
        await m.answer("\n".join(f"#{r['id']} {r['tg_chat']} (pat {r['pattern_id']})"
                                 for r in rs) or "Bo'sh")

    @dp.message(Command("sources"))
    async def _ls(m):
        if not ok(m): return
        rs = _rows("SELECT id,ref,kind FROM sources")
        await m.answer("\n".join(f"#{r['id']} {r['ref']} ({r['kind']})" for r in rs) or "Bo'sh")

    @dp.message(Command("schedules"))
    async def _lsc(m):
        if not ok(m): return
        rs = _rows("SELECT id,channel_id,post_type,cron FROM schedules")
        await m.answer("\n".join(f"#{r['id']} ch{r['channel_id']} {r['post_type']} '{r['cron']}'"
                                 for r in rs) or "Bo'sh")

    print("🟢 Admin bot ishga tushdi.")
    asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    main()
