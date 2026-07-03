"""AvtoPost — Scraper (manba kanallardan post olish).

- tg manbalar: Telethon (MTProto user session) — ochiq kanalni o'qiy oladi.
- rss manbalar: feedparser (ixtiyoriy).
Hisob ma'lumotlari yo'q bo'lsa -> bo'sh ro'yxat (bot to'xtamaydi).

ENV: MB_TG_API_ID, MB_TG_API_HASH, MB_TG_SESSION (StringSession matni).
"""
from __future__ import annotations
import os
import re
import db

API_ID = os.environ.get("MB_TG_API_ID", "")
API_HASH = os.environ.get("MB_TG_API_HASH", "")
SESSION = os.environ.get("MB_TG_SESSION", "")
PER_SOURCE = 5            # har manbadan ko'pi bilan nechta so'nggi xabar tekshiriladi

_client = None            # bitta sessiyani qayta ishlatamiz

# Manba nomlari: hostdagi KALIT so'z -> chiroyli nom (post oxiridagi "Manba: ..." uchun).
_SRC_NAMES = {
    "gazeta": "Gazeta.uz", "kun.uz": "Kun.uz", "daryo": "Daryo", "spot": "Spot.uz",
    "bbc": "BBC", "reuters": "Reuters", "apnews": "AP", "cnn": "CNN",
    "techcrunch": "TechCrunch", "nationalgeographic": "National Geographic",
    "natgeo": "National Geographic", "aljazeera": "Al Jazeera", "theverge": "The Verge",
    "euronews": "Euronews", "nytimes": "NY Times", "guardian": "The Guardian",
}


def _src_name(ref: str) -> str:
    ref = ref or ""
    if ref.startswith("@"):
        return ref
    m = re.search(r"https?://([^/]+)", ref)
    host = (m.group(1) if m else ref).lower()
    host = re.sub(r"^(feeds?|rss|www)\.", "", host)      # feeds.bbci.co.uk -> bbci.co.uk
    for key, name in _SRC_NAMES.items():
        if key in host:
            return name
    return host.split(".")[0].capitalize() if host else "Manba"


def _entry_image(e) -> str:
    """RSS yozuvidan rasm URL (media/enclosure/<img>). Topilmasa bo'sh."""
    url = ""
    for key in ("media_content", "media_thumbnail"):
        media = e.get(key)
        if media and isinstance(media, list) and media[0].get("url"):
            url = media[0]["url"]; break
    if not url:
        for l in e.get("links", []):
            if l.get("rel") == "enclosure" and "image" in (l.get("type") or ""):
                url = l.get("href", ""); break
    if not url:
        m = re.search(r'<img[^>]+src=["\']([^"\']+)', e.get("summary", "") or "")
        url = m.group(1) if m else ""
    if url and "ichef.bbci" in url:              # BBC kichik -> katta o'lcham
        url = re.sub(r"/(?:standard|news)/\d+/", "/standard/976/", url)
    return url


def _og_image(url: str) -> str:
    """Maqola sahifasidan og:image (RSS'da rasm bo'lmasa). Xato -> bo'sh."""
    import urllib.request
    if not url:
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read(200000).decode("utf-8", "ignore")
        m = (re.search(r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)', html, re.I)
             or re.search(r'content=["\']([^"\']+)["\'][^>]*property=["\']og:image', html, re.I))
        return m.group(1) if m else ""
    except Exception:
        return ""


def _translate_uz(text: str) -> str:
    """Bepul Google Translate (kalitsiz) -> o'zbekcha. Xato -> asl matn."""
    import urllib.request, urllib.parse, json
    if not text or not text.strip():
        return text
    try:
        q = urllib.parse.quote(text[:4500])
        url = ("https://translate.googleapis.com/translate_a/single"
               f"?client=gtx&sl=auto&tl=uz&dt=t&q={q}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        return "".join(seg[0] for seg in data[0] if seg and seg[0]).strip() or text
    except Exception as e:
        print("  Tarjima xato:", e)
        return text


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


async def _fetch_tg(client, ref: str, keywords: str, source_id: int, translate: int = 0) -> list[dict]:
    out = []
    name = _src_name(ref)
    try:
        async for msg in client.iter_messages(ref, limit=PER_SOURCE):
            txt = msg.message or ""
            if len(txt) >= 40 and _passes(txt, keywords):
                out.append({"text": txt, "msg_id": msg.id, "source_id": source_id,
                            "source_name": name, "translate": translate})
    except Exception as e:
        print(f"  Manba o'qishda xato ({ref}): {e}")
    return out


def _fetch_rss(ref: str, keywords: str, source_id: int, translate: int = 0) -> list[dict]:
    try:
        import feedparser
    except Exception:
        return []
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"   # UA'siz ba'zi RSS bloklaydi
    name = _src_name(ref)
    out = []
    for e in feedparser.parse(ref, agent=ua).entries[:PER_SOURCE]:
        txt = (e.get("title", "") + "\n" + e.get("summary", "")).strip()
        if len(txt) >= 40 and _passes(txt, keywords):
            out.append({"text": txt, "msg_id": None, "source_id": source_id,
                        "source_name": name, "translate": translate,
                        "image": _entry_image(e), "link": e.get("link", "")})
    return out


def _tr_flag(s) -> int:
    try:
        return int(s["translate"] or 0)
    except Exception:
        return 0


async def fetch_for_channel(database, channel_id: int) -> list[dict]:
    """Kanalga biriktirilgan barcha manbalardan nomzod postlarni yig'adi."""
    srcs = db.get_channel_sources(database, channel_id)
    if not srcs:
        return []
    items: list[dict] = []
    client = None
    for s in srcs:
        tr = _tr_flag(s)
        if s["kind"] == "rss":
            items += _fetch_rss(s["ref"], s["keywords"], s["id"], tr)
        else:
            client = client or await _get_client()
            if client:
                items += await _fetch_tg(client, s["ref"], s["keywords"], s["id"], tr)
    return items
