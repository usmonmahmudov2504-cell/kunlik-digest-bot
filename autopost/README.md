# 🚀 AvtoPost — Master Bot (multi-tenant)

Bitta bot orqali **ko'plab mijoz kanallarini** boshqaradigan, **bepul infratuzilmada** ishlaydigan yengil tizim. Manba kanallardan post oladi → **AI'siz algoritmik** tahrirlaydi (AvtoPost brendi) → belgilangan kanallarga tarqatadi.

## Tuzilma
| Fayl | Vazifa |
|------|--------|
| `schema.sql` | SQLite sxemasi (6 jadval) |
| `db.py` | DB yordamchisi + demo seed |
| `rewriter.py` | **AI'siz** tahrirlash quvuri (clean→restructure→brand) |
| `scraper.py` | Telethon/RSS bilan manbadan o'qish |
| `publisher.py` | Bot API bilan post tashlash |
| `scheduler.py` | TICK — vaqti kelgan jadvallarni bajaradi |
| `master_bot.py` | Kirish nuqtasi (init / tick / serve) |
| `admin_bot.py` | Telegram buyruqlari bilan boshqaruv (aiogram) |

## Arxitektura (Free Tier uchun)
```
Tashqi cron (har 1 daq) ─▶ master_bot.py tick
        │
        ├─ DB'dan "due" jadvallar (next_run<=now)
        ├─ scraper: manbadan post
        ├─ rewriter: AvtoPost brendi (AI'siz)
        ├─ publisher: kanalga yuborish
        └─ posts_log: dedup
```
**Always-on jarayon shart emas** — Render/Railway free uxlasa ham ishlaydi.

## Ishga tushirish
```bash
pip install -r requirements.txt

# 1) DB + demo
python master_bot.py init

# 2) Bitta yurish (tashqi cron shuni chaqiradi)
python master_bot.py tick
```

## ENV o'zgaruvchilari
| ENV | Nima |
|-----|------|
| `MB_BOT_TOKEN` | Master Bot tokeni (@BotFather) — kanallarga admin |
| `MB_TG_API_ID`, `MB_TG_API_HASH` | my.telegram.org dan (skraping) |
| `MB_TG_SESSION` | Telethon StringSession matni |
| `MB_DB` | DB fayl yo'li (ixtiyoriy, default `box.db`) |

## Masshtab (minglab kanal)
- TICK faqat `next_run<=now` ni o'qiydi (butun jadvalni emas) → tez.
- `Semaphore(5)` bir vaqtda 5 ta → xotira/limit nazorati.
- `patterns` qayta ishlatiladi → 1000 kanal bitta qolipni bo'lishadi.
- Telegram limiti: kerak bo'lsa partiya orasiga `asyncio.sleep` qo'shing.

## Yangi mijoz qo'shish (admin bot orqali)
```
python admin_bot.py           # MB_BOT_TOKEN + MB_ADMIN_ID kerak
```
Telegram'da:
```
/add_client Demo MMC
/add_channel 1 @mijoz_kanali 1
/add_source @manba_kanal
/link 1 1 ai,startup
/schedule 1 scrape */30 * * * *
```

## Deploy (GitHub Actions + cron-job.org)
1. Repo **Secrets**: `MB_BOT_TOKEN`, `MB_ADMIN_ID`, `MB_TG_API_ID`, `MB_TG_API_HASH`, `MB_TG_SESSION`.
2. Workflow: `.github/workflows/autopost.yml` (`workflow_dispatch`).
3. **cron-job.org** har daqiqada shu workflow'ni ishga tushiradi (GitHub API `workflow_dispatch`).
4. Holat (`box.db`) har yurishdan keyin repoga saqlanadi.

## Masshtab eslatmasi (muhim)
GitHub Actions runneri **vaqtinchalik** — shuning uchun `box.db` repoga commit qilinadi (kichik hajmda mayli). **Minglab kanal / yuqori chastota** uchun:
- **Turso (libSQL)** — bepul, SQLite-mos, **doimiy, tarmoq orqali** DB. `box.db` commit qilish shart bo'lmaydi, TICK butunlay stateless bo'ladi. `db.py` dagi `connect()` ni libSQL klientiga almashtirish kifoya.
- Yoki doimiy diskli host (Railway/Fly volume) + `serve` rejimi (apscheduler).
