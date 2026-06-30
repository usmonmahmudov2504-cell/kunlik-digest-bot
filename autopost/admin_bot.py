"""AvtoPost — Tugmali (knopka) Admin panel (aiogram 3).

Hammasi BOT ICHIDA, tugmalar bilan:
  📢 Kanallar  — post tushadigan kanallar (qo'shish/o'chirish)
  📡 Manbalar  — qayerdan olinadi (RSS yoki Telegram kanal)
  🔗 Bog'lash  — qaysi MANBADAN qaysi KANALGA + kalit so'z filtri
  ⏰ Jadval    — har qancha vaqtda post (tugma orqali)

Ishga tushirish:  python admin_bot.py   (ENV: MB_BOT_TOKEN, MB_ADMIN_ID)
"""
from __future__ import annotations
import os
import asyncio
import db

TOKEN = os.environ.get("MB_BOT_TOKEN", "")
ADMIN = int(os.environ.get("MB_ADMIN_ID", "0") or 0)

# Jadval presetlari (tugma matni -> cron). Vaqtga bog'liq emas (interval).
CRONS = {
    "Har 30 daqiqa": "*/30 * * * *",
    "Har 1 soat": "0 * * * *",
    "Har 3 soat": "0 */3 * * *",
    "Har 6 soat": "0 */6 * * *",
}


# ---- DB yordamchilari (oddiy SQL) ----
def q(sql, args=()):
    d = db.connect(); cur = d.execute(sql, args); d.commit()
    rid = cur.lastrowid; d.close(); return rid


def rows(sql, args=()):
    d = db.connect(); rs = d.execute(sql, args).fetchall(); d.close(); return rs


def main():
    if not TOKEN:
        print("MB_BOT_TOKEN yo'q."); return
    from aiogram import Bot, Dispatcher, F
    from aiogram.types import Message, CallbackQuery
    from aiogram.filters import Command
    from aiogram.enums import ParseMode
    from aiogram.client.default import DefaultBotProperties
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.state import State, StatesGroup
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    db.init_db()
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    class St(StatesGroup):
        add_channel = State()
        add_source = State()      # data: kind
        link_keywords = State()   # data: channel_id, source_id

    def is_admin(uid):
        return ADMIN and uid == ADMIN

    # ---- Klaviaturalar ----
    def kb_home():
        b = InlineKeyboardBuilder()
        b.button(text="📢 Kanallar", callback_data="m:ch")
        b.button(text="📡 Manbalar", callback_data="m:src")
        b.button(text="🔗 Bog'lash", callback_data="m:link")
        b.button(text="⏰ Jadval", callback_data="m:sch")
        b.adjust(2, 2)
        return b.as_markup()

    def kb_back():
        b = InlineKeyboardBuilder()
        b.button(text="⬅️ Asosiy menyu", callback_data="home")
        return b.as_markup()

    def kb_channels():
        b = InlineKeyboardBuilder()
        for r in rows("SELECT id,tg_chat FROM channels WHERE is_active=1"):
            b.button(text=f"🗑 {r['tg_chat']}", callback_data=f"chdel:{r['id']}")
        b.button(text="➕ Kanal qo'shish", callback_data="chadd")
        b.button(text="⬅️ Orqaga", callback_data="home")
        b.adjust(1)
        return b.as_markup()

    def kb_sources():
        b = InlineKeyboardBuilder()
        for r in rows("SELECT id,ref,kind FROM sources WHERE is_active=1"):
            b.button(text=f"🗑 [{r['kind']}] {r['ref'][:30]}", callback_data=f"srcdel:{r['id']}")
        b.button(text="➕ RSS qo'shish", callback_data="srcadd:rss")
        b.button(text="➕ TG kanal qo'shish", callback_data="srcadd:tg")
        b.button(text="⬅️ Orqaga", callback_data="home")
        b.adjust(1)
        return b.as_markup()

    def kb_pick(prefix, data, items, label):
        b = InlineKeyboardBuilder()
        for r in items:
            b.button(text=label(r), callback_data=f"{prefix}:{r['id']}")
        b.button(text="⬅️ Orqaga", callback_data="home")
        b.adjust(1)
        return b.as_markup()

    HOME_TXT = ("🚀 <b>AvtoPost — Boshqaruv</b>\n\n"
                "Qaysi MANBADAN qaysi KANALGA post tashlashni shu yerda sozlaysiz.\n"
                "Quyidagi tugmalardan tanlang 👇")

    # ---- Handlerlar ----
    @dp.message(Command("start"))
    async def start(m: Message, state: FSMContext):
        await state.clear()
        if not is_admin(m.from_user.id):
            return await m.answer("⛔ Ruxsat yo'q.")
        await m.answer(HOME_TXT, reply_markup=kb_home())

    @dp.callback_query(F.data == "home")
    async def home(c: CallbackQuery, state: FSMContext):
        await state.clear()
        await c.message.edit_text(HOME_TXT, reply_markup=kb_home())
        await c.answer()

    # --- Kanallar ---
    @dp.callback_query(F.data == "m:ch")
    async def m_ch(c: CallbackQuery):
        await c.message.edit_text("📢 <b>Kanallar</b>\nPost tushadigan kanallar. 🗑 = o'chirish.",
                                  reply_markup=kb_channels())
        await c.answer()

    @dp.callback_query(F.data == "chadd")
    async def chadd(c: CallbackQuery, state: FSMContext):
        await state.set_state(St.add_channel)
        await c.message.edit_text("Kanal <b>@username</b>'ini yuboring (bot o'sha kanalga ADMIN bo'lsin):",
                                  reply_markup=kb_back())
        await c.answer()

    @dp.message(St.add_channel)
    async def chadd_save(m: Message, state: FSMContext):
        chat = m.text.strip()
        q("INSERT INTO channels(client_id,pattern_id,tg_chat,title) VALUES(1,1,?,?)", (chat, chat))
        await state.clear()
        await m.answer(f"✅ Kanal qo'shildi: {chat}", reply_markup=kb_channels())

    @dp.callback_query(F.data.startswith("chdel:"))
    async def chdel(c: CallbackQuery):
        cid = int(c.data.split(":")[1])
        q("UPDATE channels SET is_active=0 WHERE id=?", (cid,))
        await c.message.edit_text("🗑 O'chirildi.", reply_markup=kb_channels())
        await c.answer("O'chirildi")

    # --- Manbalar ---
    @dp.callback_query(F.data == "m:src")
    async def m_src(c: CallbackQuery):
        await c.message.edit_text("📡 <b>Manbalar</b>\nRSS yoki Telegram kanal. 🗑 = o'chirish.",
                                  reply_markup=kb_sources())
        await c.answer()

    @dp.callback_query(F.data.startswith("srcadd:"))
    async def srcadd(c: CallbackQuery, state: FSMContext):
        kind = c.data.split(":")[1]
        await state.set_state(St.add_source)
        await state.update_data(kind=kind)
        hint = "RSS havolasini (https://...) yuboring:" if kind == "rss" else "Manba @username'ini yuboring:"
        await c.message.edit_text(hint, reply_markup=kb_back())
        await c.answer()

    @dp.message(St.add_source)
    async def srcadd_save(m: Message, state: FSMContext):
        d = await state.get_data()
        q("INSERT INTO sources(kind,ref) VALUES(?,?)", (d["kind"], m.text.strip()))
        await state.clear()
        await m.answer(f"✅ Manba qo'shildi ({d['kind']}): {m.text.strip()}", reply_markup=kb_sources())

    @dp.callback_query(F.data.startswith("srcdel:"))
    async def srcdel(c: CallbackQuery):
        sid = int(c.data.split(":")[1])
        q("UPDATE sources SET is_active=0 WHERE id=?", (sid,))
        await c.message.edit_text("🗑 O'chirildi.", reply_markup=kb_sources())
        await c.answer("O'chirildi")

    # --- Bog'lash: kanal -> manba -> kalit so'z ---
    @dp.callback_query(F.data == "m:link")
    async def m_link(c: CallbackQuery):
        chs = rows("SELECT id,tg_chat FROM channels WHERE is_active=1")
        if not chs:
            return await c.answer("Avval kanal qo'shing", show_alert=True)
        await c.message.edit_text("🔗 <b>Bog'lash</b> — qaysi KANALGA?",
                                  reply_markup=kb_pick("lk", "ch", chs, lambda r: r["tg_chat"]))
        await c.answer()

    @dp.callback_query(F.data.startswith("lk:"))
    async def link_src(c: CallbackQuery, state: FSMContext):
        cid = int(c.data.split(":")[1])
        srcs = rows("SELECT id,ref,kind FROM sources WHERE is_active=1")
        if not srcs:
            return await c.answer("Avval manba qo'shing", show_alert=True)
        await state.update_data(channel_id=cid)
        b = InlineKeyboardBuilder()
        for r in srcs:
            b.button(text=f"[{r['kind']}] {r['ref'][:28]}", callback_data=f"lks:{r['id']}")
        b.button(text="⬅️ Orqaga", callback_data="home")
        b.adjust(1)
        await c.message.edit_text("Qaysi MANBADAN olsin?", reply_markup=b.as_markup())
        await c.answer()

    @dp.callback_query(F.data.startswith("lks:"))
    async def link_kw(c: CallbackQuery, state: FSMContext):
        sid = int(c.data.split(":")[1])
        await state.update_data(source_id=sid)
        await state.set_state(St.link_keywords)
        b = InlineKeyboardBuilder()
        b.button(text="Hammasi (filtr yo'q)", callback_data="lkw:all")
        b.button(text="⬅️ Orqaga", callback_data="home")
        b.adjust(1)
        await c.message.edit_text(
            "Kalit so'z filtri? Vergul bilan yozing (mas. <code>ai,startup</code>)\n"
            "yoki <b>Hammasi</b> tugmasini bosing:", reply_markup=b.as_markup())
        await c.answer()

    async def _save_link(channel_id, source_id, kw):
        q("INSERT OR REPLACE INTO channel_sources(channel_id,source_id,keywords) VALUES(?,?,?)",
          (channel_id, source_id, kw))
        # jadval bo'lmasa -> standart har 30 daqiqa qo'shamiz
        ex = rows("SELECT 1 FROM schedules WHERE channel_id=?", (channel_id,))
        if not ex:
            q("INSERT INTO schedules(channel_id,post_type,cron,next_run) VALUES(?,?,?,NULL)",
              (channel_id, "scrape", "*/30 * * * *"))

    @dp.callback_query(F.data == "lkw:all", St.link_keywords)
    async def link_all(c: CallbackQuery, state: FSMContext):
        d = await state.get_data()
        await _save_link(d["channel_id"], d["source_id"], "")
        await state.clear()
        await c.message.edit_text("✅ Bog'landi! (filtr yo'q · jadval: har 30 daqiqa)\n"
                                  "Endi shu manbadagi yangiliklar kanalga avtomatik tushadi.",
                                  reply_markup=kb_home())
        await c.answer("Bog'landi")

    @dp.message(St.link_keywords)
    async def link_kw_save(m: Message, state: FSMContext):
        d = await state.get_data()
        await _save_link(d["channel_id"], d["source_id"], m.text.strip())
        await state.clear()
        await m.answer(f"✅ Bog'landi! (filtr: {m.text.strip()} · jadval: har 30 daqiqa)",
                       reply_markup=kb_home())

    # --- Jadval ---
    @dp.callback_query(F.data == "m:sch")
    async def m_sch(c: CallbackQuery):
        chs = rows("SELECT id,tg_chat FROM channels WHERE is_active=1")
        if not chs:
            return await c.answer("Avval kanal qo'shing", show_alert=True)
        await c.message.edit_text("⏰ <b>Jadval</b> — qaysi kanal uchun?",
                                  reply_markup=kb_pick("schc", "ch", chs, lambda r: r["tg_chat"]))
        await c.answer()

    @dp.callback_query(F.data.startswith("schc:"))
    async def sch_pick(c: CallbackQuery):
        cid = int(c.data.split(":")[1])
        b = InlineKeyboardBuilder()
        for label in CRONS:
            b.button(text=label, callback_data=f"schset:{cid}:{label}")
        b.button(text="⬅️ Orqaga", callback_data="home")
        b.adjust(1)
        await c.message.edit_text("Har qancha vaqtda post tashlansin?", reply_markup=b.as_markup())
        await c.answer()

    @dp.callback_query(F.data.startswith("schset:"))
    async def sch_set(c: CallbackQuery):
        _, cid, label = c.data.split(":", 2)
        cron = CRONS.get(label, "*/30 * * * *")
        ex = rows("SELECT id FROM schedules WHERE channel_id=?", (int(cid),))
        if ex:
            q("UPDATE schedules SET cron=?, next_run=NULL WHERE channel_id=?", (cron, int(cid)))
        else:
            q("INSERT INTO schedules(channel_id,post_type,cron,next_run) VALUES(?,?,?,NULL)",
              (int(cid), "scrape", cron))
        await c.message.edit_text(f"✅ Jadval o'rnatildi: <b>{label}</b>", reply_markup=kb_home())
        await c.answer("Saqlandi")

    print("🟢 AvtoPost admin (tugmali) ishga tushdi.")
    asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    main()
