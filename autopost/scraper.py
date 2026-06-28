"""AvtoPost — Scraper (manba kanallardan post olish).

- tg manbalar: Telethon (MTProto user session) — ochiq kanalni o'qiy oladi.
- rss manbalar: feedparser (ixtiyoriy).
Hisob ma'lumotlari yo'q bo'lsa -> bo'sh ro'yxat (bot to'xtamaydi).

ENV: MB_TG_API_ID, MB_TG_API_HASH, MB_TG_SESSION (StringSession matni).
"""
from __future__ import annotations
import os
import db

API_ID = os.environ.get("MB_TG_API_ID", "")
API_HASH = os.environ.get("MB_TG_API_HASH", "")
SESSION = os.environ.get("MB_TG_SESSION", "")
PER_SOURCE = 5            # har manbadan ko'pi bilan nechta so'nggi xabar tekshiriladi

_client = None            # bitta sessiyani qayta ishlatamiz


async def _get_client():
    global _client
    if _client is not None:
        return _client
    if not (API_ID and API_HASH and SESSION):
        return None
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        _client = TelegramClient(StringSession(SESSION), int(API_ID), API_HASH)
        await _client.connect()
        return _client
    except Exception as e:
        print(f"  Telethon ulanmadi: {e}")
        return None


def _passes(text: str, keywords: str) -> bool:
    """Filtr: keywords bo'sh -> hammasi; aks holda biror kalit so'z bo'lsa o'tadi."""
    kws = [k.strip().lower() for k in (keywords or "").split(",") if k.strip()]
    if not kws:
        return True
    low = (text or "").lower()
    return any(k in low for k in kws)


async def _fetch_tg(client, ref: str, keywords: str, source_id: int) -> list[dict]:
    out = []
    try:
        async for msg in client.iter_messages(ref, limit=PER_SOURCE):
            txt = msg.message or ""
            if len(txt) >= 40 and _passes(txt, keywords):
                out.append({"text": txt, "msg_id": msg.id, "source_id": source_id})
    except Exception as e:
        print(f"  Manba o'qishda xato ({ref}): {e}")
    return out


def _fetch_rss(ref: str, keywords: str, source_id: int) -> list[dict]:
    try:
        import feedparser
    except Exception:
        return []
    out = []
    for e in feedparser.parse(ref).entries[:PER_SOURCE]:
        txt = (e.get("title", "") + "\n" + e.get("summary", "")).strip()
        if len(txt) >= 40 and _passes(txt, keywords):
            out.append({"text": txt, "msg_id": None, "source_id": source_id})
    return out


async def fetch_for_channel(database, channel_id: int) -> list[dict]:
    """Kanalga biriktirilgan barcha manbalardan nomzod postlarni yig'adi."""
    srcs = db.get_channel_sources(database, channel_id)
    if not srcs:
        return []
    items: list[dict] = []
    client = None
    for s in srcs:
        if s["kind"] == "rss":
            items += _fetch_rss(s["ref"], s["keywords"], s["id"])
        else:
            client = client or await _get_client()
            if client:
                items += await _fetch_tg(client, s["ref"], s["keywords"], s["id"])
    return items
