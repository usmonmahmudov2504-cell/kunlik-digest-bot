"""Morning Box — Master Bot kirish nuqtasi.

Rejimlar (CLI):
  python master_bot.py init   -> DB yaratish + demo ma'lumot
  python master_bot.py tick   -> bitta yurish (tashqi cron har daqiqada chaqiradi)
  python master_bot.py serve  -> doimiy worker (apscheduler; faqat always-on muhitda)

Free Tier tavsiyasi: `tick` + tashqi cron (cron-job.org / GitHub Actions).
"""
from __future__ import annotations
import sys
import asyncio

import db
import scheduler


def cmd_init():
    db.init_db()
    db.seed_demo()
    print("✅ DB tayyor + demo ma'lumot:", db.DB_PATH)


def cmd_tick():
    asyncio.run(scheduler.tick())


def cmd_serve():
    """Doimiy worker (ixtiyoriy). Har daqiqada tick chaqiradi."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except Exception:
        print("apscheduler yo'q. `pip install apscheduler` yoki `tick` + tashqi cron ishlating.")
        return
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    sch = AsyncIOScheduler(event_loop=loop, job_defaults={"coalesce": True,
                                                          "misfire_grace_time": 120})
    sch.add_job(lambda: asyncio.ensure_future(scheduler.tick()), "cron", minute="*")
    sch.start()
    print("🟢 Doimiy worker ishga tushdi (har daqiqada tick). Ctrl+C to'xtatadi.")
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tick"
    {"init": cmd_init, "tick": cmd_tick, "serve": cmd_serve}.get(cmd, cmd_tick)()
