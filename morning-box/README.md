# 📦 Morning Box — Master Bot (multi-tenant)

Bitta bot orqali **ko'plab mijoz kanallarini** boshqaradigan, **bepul infratuzilmada** ishlaydigan yengil tizim. Manba kanallardan post oladi → **AI'siz algoritmik** tahrirlaydi (Morning Box brendi) → belgilangan kanallarga tarqatadi.

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

## Arxitektura (Free Tier uchun)
```
Tashqi cron (har 1 daq) ─▶ master_bot.py tick
        │
        ├─ DB'dan "due" jadvallar (next_run<=now)
        ├─ scraper: manbadan post
        ├─ rewriter: Morning Box brendi (AI'siz)
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

## Yangi mijoz qo'shish
`clients` → `channels` (pattern_id bilan) → `sources` → `channel_sources` → `schedules` jadvallariga yozuv qo'shiladi (kelajakda admin-panel/bot buyruqlari orqali).
