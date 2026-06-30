"""AvtoPost — TICK scheduler.

Tashqi cron (cron-job.org / GitHub Actions) har daqiqada `tick()` ni chaqiradi.
Always-on jarayon SHART EMAS -> Free Tier uchun ideal.

next_run hisoblash zero-dependency (croniter shart emas): daqiqa-ba-daqiqa
oldinga yurib, cron'ning minute+hour maydonlariga mos kelishini tekshiradi
(kun/oy/hafta '*' deb olinadi — bizning jadval shakllariga yetarli).
"""
from __future__ import annotations
import asyncio
import datetime as dt

import db


def _field(expr: str):
    expr = (expr or "*").strip()
    if expr == "*":
        return None
    if expr.startswith("*/"):
        return ("step", int(expr[2:]))
    return ("val", int(expr))


def _match(spec, value: int) -> bool:
    if spec is None:
        return True
    kind, n = spec
    return (value % n == 0) if kind == "step" else (value == n)


def next_run(cron: str, base: dt.datetime) -> dt.datetime:
    """base'dan keyingi mos vaqt (UTC). cron: 'min hour dom mon dow' (dom/mon/dow=*)."""
    parts = (cron or "*/30 * * * *").split()
    mn = _field(parts[0] if len(parts) > 0 else "*")
    hr = _field(parts[1] if len(parts) > 1 else "*")
    t = (base + dt.timedelta(minutes=1)).replace(second=0, microsecond=0)
    for _ in range(2 * 24 * 60):           # ko'pi bilan 2 kun oldinga qaraymiz
        if _match(mn, t.minute) and _match(hr, t.hour):
            return t
        t += dt.timedelta(minutes=1)
    return base + dt.timedelta(minutes=30)  # zaxira


async def handle_job(database, job) -> None:
    """Bitta jadval ishini bajaradi: scrape -> rewrite -> publish.

    Hisob ma'lumotlari (Telethon/Bot token) bo'lmasa — bosqichlar jim o'tadi."""
    from rewriter import brandify
    pattern = db.get_pattern(database, job["pattern_id"])
    pat = dict(pattern) if pattern else {}
    channel = job["tg_chat"]

    try:
        import scraper, publisher
    except Exception as e:
        print(f"  [{channel}] modul yuklanmadi: {e}")
        return

    MAX_PER_TICK = 3                        # bir yurishda ko'pi bilan -> kanal toshib ketmasin
    items = await scraper.fetch_for_channel(database, job["channel_id"])
    posted = 0
    for it in items:
        if posted >= MAX_PER_TICK:
            break
        c_hash = db.content_hash(it["text"])
        if db.is_duplicate(database, job["channel_id"], c_hash):
            continue
        text = brandify(it["text"], pat, channel, markup=job["markup"])
        ok = await publisher.send(channel, text)
        if ok:
            db.mark_posted(database, job["channel_id"], it.get("source_id"),
                           it.get("msg_id"), c_hash)
            posted += 1
    print(f"  [{channel}] {posted} ta post yuborildi ({len(items)} nomzoddan).")


async def tick() -> None:
    """Bitta yurish: vaqti kelgan jadvallarni bajaradi va next_run'ni yangilaydi."""
    db.init_db()
    database = db.connect()
    now = dt.datetime.now(dt.timezone.utc)
    due = db.get_due_schedules(database, now.isoformat())
    print(f"TICK {now:%H:%M} -> {len(due)} ta jadval due")

    sem = asyncio.Semaphore(5)             # parallellik cheklovi (xotira/limit)

    async def run(job):
        async with sem:
            try:
                await handle_job(database, job)
            except Exception as e:
                print(f"  Job {job['id']} XATO: {e}")
            db.set_next_run(database, job["id"], next_run(job["cron"], now).isoformat())

    await asyncio.gather(*(run(j) for j in due))
    database.commit()
    database.close()


if __name__ == "__main__":
    asyncio.run(tick())
