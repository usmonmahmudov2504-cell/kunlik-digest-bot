"""
Kunlik digest bot (v2): barcha viloyatlar ob-havosi + banklar dollar kursi
(olish/sotish) + kunning yangiliklari -> rangli rasm (info-card) -> Telegram kanal.

Ishlash tartibi:
1. Open-Meteo'dan 14 viloyat uchun harorat olinadi (bitta so'rovda, bepul, kalitsiz).
2. cbu.uz'dan Markaziy bankning rasmiy USD kursi olinadi.
3. bankrate.uz'dan barcha banklarning olish/sotish kursi olinadi.
4. Ma'lumotlar rangli PNG kartaga aylantiriladi (render_card.py):
   - eng arzon SOTADIGAN bank (min sotish) -> yashil
   - eng qimmat OLADIGAN bank (max olish)  -> oltin rang
5. Claude qisqa caption (sarlavha + yangiliklar) yozadi.
6. Rasm + caption Telegram Bot API (sendPhoto) orqali kanalga yuboriladi.

O'rnatish:
    pip install -r requirements.txt --break-system-packages

Environment variable'lar:
    ANTHROPIC_API_KEY   - Claude API kaliti
    TELEGRAM_BOT_TOKEN  - @BotFather token
    TELEGRAM_CHANNEL    - kanal username (@...) yoki chat ID (bot admin bo'lishi shart)
"""

from __future__ import annotations
import os
import io
import re
import html
import json
import random
import hashlib
import datetime
import requests
import feedparser
from bs4 import BeautifulSoup

from render_card import (
    render_day_card, render_news_card, render_weather_card,
    render_currency_overview_card, render_currency_card, render_advice_card,
    render_market_card, render_fixtures_card, render_results_card, render_standings_card,
    render_goal_card,
)

# API kaliti IXTIYORIY. Bo'lsa -> Claude jonli caption yozadi.
# Bo'lmasa -> oddiy shablon ishlatiladi (bepul, hammasi baribir ishlaydi).
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
# Gemini (Google AI Studio) kaliti — IXTIYORIY, bepul tarif. Bo'lsa tarjima/caption
# uchun BIRINCHI ishlatiladi (Claude'dan oldin). Model env orqali o'zgartiriladi.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()   # secret'dagi bo'shliq/yangi qatorni kesamiz
# DIQQAT: gemini-2.0-flash 2026-06-01 da o'chirilgan. Bir nechta amaldagi modelni ketma-ket
# sinaymiz -> biri ishlamasa (404/limit) keyingisiga o'tadi. GEMINI_MODEL berilsa -> birinchi sinaladi.
_GEMINI_USER = os.environ.get("GEMINI_MODEL", "").strip()
GEMINI_MODELS = list(dict.fromkeys(([_GEMINI_USER] if _GEMINI_USER else []) + [
    "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-latest", "gemini-3.5-flash"]))
# Token/kanal: bitta kanal bo'lsa env'dan; ko'p kanal bo'lsa channels.json'dan
# (har kanal uchun run_channel() ichida qayta o'rnatiladi). .get -> import qulashmaydi.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "")

HERE = os.path.dirname(os.path.abspath(__file__))
CHANNEL_KEY = "default"        # joriy kanal kaliti (state/<key>/ papkasi uchun)
CHANNEL_NAME = "Kunlik digest"  # joriy kanal ko'rinadigan nomi (Instant View muallifi uchun)
# Footer'dagi xizmatlar qatori (har kanal config'dan o'zgartirishi mumkin).
FOOTER_SERVICES = "🌤 Ob-havo · 💵 Kurslar · ⚡ Yangiliklar"


def _sp(name: str) -> str:
    """Joriy kanal uchun state fayli yo'li: state/<kanal>/<name>."""
    return os.path.join(HERE, "state", CHANNEL_KEY, name)


def load_channels() -> list:
    """channels.json'dan kanallar ro'yxati. Bo'lmasa -> env'dan bitta kanal (orqaga moslik).

    Har kanal: {channel, token_env, groups, footer_services?, name?}.
    Tokenlar channels.json'ga YOZILMAYDI -> token_env faqat secret/env NOMINI bildiradi.
    """
    p = os.path.join(HERE, "channels.json")
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        chans = [c for c in data if c.get("channel")]
        if chans:
            return chans
    except FileNotFoundError:
        pass
    except Exception as e:
        print("channels.json o'qishda xato:", e)
    return [{"channel": TELEGRAM_CHANNEL, "token_env": "TELEGRAM_BOT_TOKEN",
             "groups": ["A", "B", "C", "D", "M"]}]


def _apply_channel(cfg: dict) -> None:
    """Kanal kontekstini global'larga o'rnatadi (token, kanal, state kaliti, footer)."""
    global TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL, CHANNEL_KEY, FOOTER_SERVICES, CHANNEL_NAME
    TELEGRAM_CHANNEL = cfg["channel"]
    TELEGRAM_BOT_TOKEN = os.environ.get(cfg.get("token_env", "TELEGRAM_BOT_TOKEN"),
                                        os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    CHANNEL_KEY = re.sub(r"[^A-Za-z0-9_]", "_", str(cfg["channel"]).lstrip("@")) or "default"
    CHANNEL_NAME = cfg.get("name") or str(cfg["channel"]).lstrip("@")
    FOOTER_SERVICES = cfg.get("footer_services", "🌤 Ob-havo · 💵 Kurslar · ⚡ Yangiliklar")

UA = {"User-Agent": "Mozilla/5.0 (digest-bot)"}
# Maqola sahifalaridan rasm (og:image) olishda haqiqiy brauzer UA ishonchliroq.
UA_WEB = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

client = None
if ANTHROPIC_API_KEY:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    except Exception as e:
        print("anthropic ulanmadi, shablonga o'tildi:", e)

# ------------------------------------------------------------------ OB-HAVO
# 14 viloyat markazlari (lat, lon). Tartib rasmda ham shu tartibda chiqadi.
REGIONS = {
    "Toshkent sh.":       (41.31, 69.24),
    "Toshkent vil.":      (41.00, 69.34),
    "Andijon":            (40.78, 72.34),
    "Buxoro":             (39.77, 64.42),
    "Farg'ona":           (40.39, 71.78),
    "Jizzax":             (40.12, 67.84),
    "Namangan":           (41.00, 71.67),
    "Navoiy":             (40.10, 65.38),
    "Qashqadaryo":        (38.86, 65.79),
    "Qoraqalpog'iston":   (42.46, 59.61),
    "Samarqand":          (39.65, 66.96),
    "Sirdaryo":           (40.49, 68.78),
    "Surxondaryo":        (37.22, 67.28),
    "Xorazm":             (41.55, 60.63),
}

WEATHER_CODES = {
    0: "ochiq", 1: "asosan ochiq", 2: "qisman bulutli", 3: "bulutli",
    45: "tuman", 48: "tuman", 51: "yengil yomg'ir", 53: "yomg'ir",
    55: "yomg'ir", 61: "yomg'ir", 63: "kuchli yomg'ir", 65: "kuchli yomg'ir",
    71: "qor", 73: "qor", 75: "kuchli qor", 80: "jala", 81: "jala",
    82: "kuchli jala", 95: "momaqaldiroq", 96: "momaqaldiroq", 99: "momaqaldiroq",
}


def get_all_weather() -> dict[str, tuple]:
    """14 viloyat uchun (harorat, holat)ni bitta Open-Meteo so'rovida oladi."""
    lats = ",".join(str(v[0]) for v in REGIONS.values())
    lons = ",".join(str(v[1]) for v in REGIONS.values())
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lats}&longitude={lons}"
        "&current=temperature_2m,weather_code&timezone=Asia/Tashkent"
    )
    data = requests.get(url, headers=UA, timeout=20).json()
    # Bir nechta koordinata -> javob ro'yxat bo'lib qaytadi
    if isinstance(data, dict):
        data = [data]
    out: dict[str, tuple] = {}
    for region, item in zip(REGIONS, data):
        cur = item["current"]
        desc = WEATHER_CODES.get(cur["weather_code"], "ochiq")
        out[region] = (cur["temperature_2m"], desc)
    return out


# ------------------------------------------------------------------ CBU
# Umumiy kurslar postida ko'rsatiladigan valyutalar (USD birinchi).
OVERVIEW_CCY = ["USD", "EUR", "GBP", "RUB", "KZT", "CNY", "JPY", "TRY", "AED", "KRW"]
# Dollar postidagi "boshqa valyutalar" qatori uchun (caption)
EXTRA_CCY = ["EUR", "RUB", "GBP", "KZT", "CNY"]
CCY_NAMES = {
    "USD": "AQSH dollari", "EUR": "Yevro", "GBP": "Funt sterling", "RUB": "Rubl",
    "KZT": "Tenge", "CNY": "Yuan", "JPY": "Yaponiya iyenasi", "TRY": "Turk lirasi",
    "AED": "BAA dirhami", "KRW": "Koreya voni",
}


def _fmt_sum(rate: float) -> str:
    return f"{rate:,.2f}".replace(",", " ").replace(".", ",")


def _ccy_row(it: dict) -> dict:
    code = it.get("Ccy")
    rate = float(it["Rate"])
    nominal = str(it.get("Nominal", "1")).strip() or "1"
    unit = f"{nominal} {code}" if nominal != "1" else f"1 {code}"
    return {"code": code, "name": CCY_NAMES.get(code, code), "unit": unit,
            "rate": _fmt_sum(rate), "value": rate}


def get_cbu_rates() -> tuple[str, list[dict], list[dict]]:
    """CBU'dan valyutalarni bitta so'rovda oladi.

    Qaytaradi: (USD matni, overview_rows, extra_rows).
      overview_rows -> umumiy kurslar posti (USD + boshqalar)
      extra_rows    -> dollar posti caption uchun (EUR, RUB, ...)
    """
    url = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"
    data = requests.get(url, headers=UA, timeout=15).json()
    by = {item.get("Ccy"): item for item in data}

    usd_rate = float(by["USD"]["Rate"]) if "USD" in by else 0.0
    usd_text = f"{_fmt_sum(usd_rate)} so'm"

    overview = [_ccy_row(by[c]) for c in OVERVIEW_CCY if c in by]
    extras = [_ccy_row(by[c]) for c in EXTRA_CCY if c in by]
    return usd_text, overview, extras


# ------------------------------------------------------------------ BANKLAR
# Manba: goldenpages.uz (server-render, barcha banklarning olish/sotish kursi jadvali).
# Eslatma: avvalgi bankrate.uz domeni muddati o'tib ishlamay qoldi.
GP_URLS = [
    "https://www.goldenpages.uz/uz/kurs-obmena-dollara-v-uzbekistane/",
    "https://www.goldenpages.uz/en/kurs-obmena-dollara-v-uzbekistane/",
]
_RATE = re.compile(r"1[1-3]\s?\d{3}")  # 11000-13999 oralig'idagi kurs raqami

# Uzun nomlarni qisqartirish (rasmda chiroyli ko'rinishi uchun)
_RENAME = {
    "NATIONAL BANK OF UZBEKISTAN": "NBU",
    "O'ZBEKISTON MILLIY BANKI": "NBU",
    "ASIA ALLIANCE BANK": "Asia Alliance",
    "ORIENT FINANS BANK": "Orient Finans",
    "MICROCREDITBANK": "Mikrokreditbank",
    "MIKROKREDITBANK": "Mikrokreditbank",
}


def _clean_name(n: str) -> str:
    n = re.sub(r"\s+", " ", n).strip()
    up = n.upper()
    if up in _RENAME:
        return _RENAME[up]
    name = n.title() if n.isupper() else n
    return name[:20]


def _parse_rate_cell(text: str):
    """Bitta katakdan dastlabki ikki kurs raqamini (olish, sotish) oladi."""
    text = text.replace("\xa0", " ").replace("\u202f", " ")
    nums = [int(m.group().replace(" ", "")) for m in _RATE.finditer(text)]
    return nums[:2] if len(nums) >= 2 else None


def get_bank_rates() -> list[dict]:
    """goldenpages.uz jadvalidan banklarning bugungi olish/sotish kursini yig'adi."""
    html = None
    for url in GP_URLS:
        try:
            resp = requests.get(url, headers=UA, timeout=20)
            resp.raise_for_status()
            html = resp.text
            break
        except Exception as e:
            print(f"goldenpages xato ({url}):", e)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    banks: list[dict] = []
    seen: set[str] = set()

    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            name = cells[0].get_text(" ", strip=True)
            # bank nomi: asosan katta harfli, 3-40 belgi
            if not re.match(r"^[A-Za-z\u0400-\u04FF][\w .&'\u2019\u0400-\u04FF-]{2,39}$", name):
                continue
            # nomdan keyingi dastlabki ikki kursli katak = bugungi olish/sotish
            pair = None
            for c in cells[1:]:
                pair = _parse_rate_cell(c.get_text(" ", strip=True))
                if pair:
                    break
            if not pair:
                continue
            buy, sell = pair
            # mantiqiy tekshiruv: sotish > olish bo'lishi kerak
            if not (10000 < buy < sell < 14000):
                continue
            key = _clean_name(name)
            if key in seen:
                continue
            seen.add(key)
            banks.append({"bank": key, "buy": buy, "sell": sell})

    return banks


# ------------------------------------------------------------------ BOZOR (oltin + kripto)
def _fmt_usd(v: float) -> str:
    if v >= 1000:
        return f"{v:,.0f}".replace(",", " ")
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


# Ko'rsatiladigan coinlar: (CoinGecko id, ichki kalit, ko'rinadigan nom, belgi).
# Tartib shu yerda -> kartada ham shu tartibda chiqadi (BTC, ETH, TON, BNB, SOL, XRP).
COINS = [
    ("bitcoin", "btc", "Bitcoin", "BTC"),
    ("ethereum", "eth", "Ethereum", "ETH"),
    ("the-open-network", "ton", "Toncoin", "TON"),
    ("binancecoin", "bnb", "BNB", "BNB"),
    ("solana", "sol", "Solana", "SOL"),
    ("ripple", "xrp", "XRP", "XRP"),
]


def get_market_data() -> dict:
    """Oltin (XAU $/oz) + coinlar ($, 24h%) + USD/UZS (gramm so'm uchun)."""
    out = {"gold": None, "usd_uzs": None}
    try:
        data = requests.get("https://cbu.uz/uz/arkhiv-kursov-valyut/json/", headers=UA, timeout=15).json()
        for it in data:
            if it.get("Ccy") == "USD":
                out["usd_uzs"] = float(it["Rate"])
                break
    except Exception as e:
        print("USD kursi (bozor) xato:", e)
    try:
        g = requests.get("https://api.gold-api.com/price/XAU", headers=UA_WEB, timeout=15).json()
        out["gold"] = float(g["price"])
    except Exception as e:
        print("Oltin narxi xato:", e)
    try:
        ids = ",".join(c[0] for c in COINS)
        id2key = {c[0]: c[1] for c in COINS}
        c = requests.get(
            f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={ids}",
            headers=UA_WEB, timeout=20).json()
        for coin in c:
            key = id2key.get(coin.get("id"))
            if key:
                out[key] = {"usd": float(coin["current_price"]),
                            "chg": coin.get("price_change_percentage_24h")}
    except Exception as e:
        print("Kripto narxi xato:", e)
    return out


def market_rows(m: dict, prev_gold=None) -> list[dict]:
    """Bozor ma'lumotini karta/caption uchun qatorlarga aylantiradi."""
    rows = []
    if m.get("gold"):
        sub = "1 untsiya (oz)"
        if m.get("usd_uzs"):
            gram = m["gold"] / 31.1035 * m["usd_uzs"]
            sub = f"1 gramm ≈ {gram:,.0f} so'm".replace(",", " ")
        chg = ((m["gold"] - prev_gold) / prev_gold * 100) if prev_gold else None
        rows.append({"name": "Oltin", "sub": sub, "value": f"${_fmt_usd(m['gold'])}",
                     "chg": chg, "kind": "gold"})
    for _id, key, name, sub in COINS:
        c = m.get(key)
        if c:
            rows.append({"name": name, "sub": sub, "value": f"${_fmt_usd(c['usd'])}",
                         "chg": c.get("chg"), "kind": key})
    return rows


# ------------------------------------------------------------------ YANGILIKLAR
def get_top_news(limit: int = 4) -> list[str]:
    feeds = ["https://www.gazeta.uz/uz/rss/", "https://daryo.uz/rss"]
    headlines: list[str] = []
    for url in feeds:
        try:
            parsed = feedparser.parse(url)
            headlines += [e.title for e in parsed.entries[:limit]]
        except Exception as e:
            print(f"RSS xato ({url}): {e}")
    return headlines[:limit]


# Biznes yangiliklari: spot.uz (biznes nashri) + kalit so'z bo'yicha filtr
BUSINESS_FEEDS = [
    ("https://www.spot.uz/uz/rss/", True),    # True = butun feed biznes
    ("https://kun.uz/uz/rss", False),
    ("https://daryo.uz/rss", False),
    ("https://www.gazeta.uz/uz/rss/", False),
]
BIZ_KW = ["biznes", "iqtisod", "iqtisodiy", "soliq", "valyuta", "eksport", "import",
          "investitsiya", "bank", "byudjet", "narx", "tarif", "kredit", "savdo", "bozor",
          "kompaniya", "infl", "foiz", "ishlab chiqar", "tadbirkor", "pul", "aksiya",
          "qonun", "qaror", "farmon", "bojxona", "litsenziya", "imtiyoz", "subsidiya",
          "deklaratsiya", "norma", "reglament", "to'lov", "ish o'rni", "ish haqi",
          "lizing", "soliqlar", "byudjetdan", "tovar", "narxlar", "tender"]


# Futbol uchun kalit so'zlar (o'zbek/rus/ingliz) -- umumiy feeddan futbolni ajratish.
FOOTBALL_KW = ["futbol", "футбол", "liga", "лига", "chempion", "чемпион", "messi", "месси",
               "ronaldo", "роналду", "terma jamoa", "сборная", "uefa", "уефа", "fifa", "фифа",
               "transfer", "трансфер", "barcelona", "барселона", "real madrid", "реал",
               "gol ", "гол", "match", "матч", "stadion", "стадион", "superliga", "суперлига",
               "afc", "premier", "лига чемпионов", "mancheste", "ливерпуль", "bayern", "psg"]

# Futbol manbalari: championat.com (jahon, RUS, ishonchli) + O'zbek umumiy (filtr bilan).
FOOTBALL_FEEDS = [
    ("https://www.championat.com/rss/news/football/", True),   # butun feed futbol
    ("https://www.gazeta.uz/uz/rss/", False),                  # O'zbek -> futbolni filtrlaymiz
    ("https://kun.uz/uz/rss", False),
    ("https://daryo.uz/rss/sport", False),
]

# Yangilik "presetlari" -> kanal config'da news_preset bilan tanlanadi.
NEWS_PRESETS = {
    "business": {"feeds": BUSINESS_FEEDS, "keywords": BIZ_KW},
    "football": {"feeds": FOOTBALL_FEEDS, "keywords": FOOTBALL_KW},
}


def get_news(feeds, keywords, limit: int = 5) -> list[dict]:
    """Berilgan feed'lar va kalit so'zlardan yangiliklarni {"title","link"} qaytaradi.

    feeds: [(url, butun_feed_mosmi), ...]. Mos kelganlar oldinga, qolgani to'ldiruvchi.
    """
    hit, other, seen = [], [], set()
    for url, all_relevant in feeds:
        try:
            parsed = feedparser.parse(url, agent=UA_WEB["User-Agent"])
        except Exception as e:
            print(f"RSS xato ({url}): {e}")
            continue
        for e in parsed.entries[:15]:
            title = html.unescape((e.get("title") or "").strip())
            if not title or title in seen:
                continue
            seen.add(title)
            item = {"title": title, "link": e.get("link", "")}
            if all_relevant or any(k in title.lower() for k in keywords):
                hit.append(item)
            else:
                other.append(item)
    result = hit[:limit]
    if len(result) < limit:                # yetmasa, umumiy bilan to'ldiramiz
        result += other[: limit - len(result)]
    return result


def get_business_news(limit: int = 5) -> list[dict]:
    """Biznes sarlavhalari (orqaga moslik uchun -- get_news ustiga o'ralgan)."""
    return get_news(BUSINESS_FEEDS, BIZ_KW, limit)


def _translate_google(text: str, target: str = "uz") -> str:
    """Bepul, kalitsiz Google Translate endpoint. Xato bo'lsa -> original matn.

    ANTHROPIC_API_KEY bo'lmasa ham (yoki Claude xato bersa) rus/boshqa til
    o'zbekchaga o'giriladi -> kanal hech qachon ruscha chiqib qolmaydi."""
    if not text:
        return text
    try:
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "auto", "tl": target, "dt": "t", "q": text},
            headers=UA_WEB, timeout=15)
        data = r.json()
        out = "".join(seg[0] for seg in data[0] if seg and seg[0]).strip()
        return out or text
    except Exception as e:
        print("Google tarjima xato:", e)
        return text


def _gemini_generate(prompt: str, max_tokens: int = 400) -> str | None:
    """Gemini REST (bepul tarif). Amaldagi modellarni ketma-ket sinaydi.

    Model 404 (o'chirilgan/noma'lum) yoki 429 (limit) -> keyingi modelga o'tadi.
    400 (kalit xato) / 403 (API yoqilmagan) -> boshqa model yordam bermaydi, to'xtaydi.
    """
    if not GEMINI_API_KEY:
        print("Gemini: kalit yo'q (GEMINI_API_KEY o'rnatilmagan).")
        return None
    # thinkingBudget=0 -> Gemini 2.5 "o'ylash" tokenlarini o'chiramiz, aks holda ular
    # maxOutputTokens'ni yeb qo'yadi va javob yarim uzilib qoladi (matn kesik chiqadi).
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7,
                                 "thinkingConfig": {"thinkingBudget": 0}}}
    for model in GEMINI_MODELS:
        try:
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model}:generateContent?key={GEMINI_API_KEY}")
            r = requests.post(url, json=body, timeout=25)
            if r.status_code != 200:
                print(f"Gemini [{model}] {r.status_code}: {r.text[:160]}")
                continue                            # har qanday xato -> keyingi modelni sinab ko'ramiz
            cands = (r.json().get("candidates") or [])
            if not cands:
                print(f"Gemini [{model}]: nomzod yo'q (ehtimol xavfsizlik bloki).")
                continue
            parts = (cands[0].get("content") or {}).get("parts") or []
            txt = "".join(p.get("text", "") for p in parts).strip()
            if txt:
                return txt
        except Exception as e:
            print(f"Gemini [{model}] xato:", e)
    return None


def llm_text(prompt: str, max_tokens: int = 600) -> str | None:
    """Matn generatsiya: avval Gemini (bepul), keyin Claude. Ikkalasi yo'q/xato -> None."""
    t = _gemini_generate(prompt, max_tokens)
    if t:
        return t
    if client is not None:
        try:
            resp = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}])
            return "".join(b.text for b in resp.content if b.type == "text").strip() or None
        except Exception as e:
            print("Claude xato:", e)
    return None


def blogify(title: str, desc: str = "", body: str = "", focus: str = "",
            persona: str = "") -> str | None:
    """Yangilikni BATAFSIL, MA'LUMOTLI post sifatida tabiiy O'zbekchaga aylantiradi.

    body (maqolaning to'liq matni) berilsa -> post uzunroq va mazmunliroq bo'ladi.
    focus (voice_focus) -> qo'shimcha yo'nalish/urg'u. persona (voice_persona) -> kim yozayotgani.
    voice="blog" kanallari uchun. LLM yo'q/xato -> None (chaqiruvchi standart formatga qaytadi).
    """
    src = title.strip()
    if body and body.strip():
        src += "\n\n" + body.strip()
    elif desc:
        src += "\n" + desc.strip()
    persona = (persona or "").strip() or "zamonaviy startap, AI va texnologiya blogeri"
    focus_line = (f"- YO'NALISH (eng muhim): {focus.strip()}\n") if focus and focus.strip() else ""
    prompt = (
        f"Sen O'zbek tilida (lotin alifbosida) yozadigan {persona}san. "
        "Quyidagi xorijiy yangilik asosida o'z kanalingga BATAFSIL, MA'LUMOTLI post yoz. Talablar:\n"
        "- AVVAL ASOSIY MA'LUMOTNI ber: nima/kim/qachon/qayerda, hisob, raqamlar, "
        "kontekst. Manba sarlavhasi savol shaklida bo'lsa ham, sen JAVOBNI va FAKTLARNI yoz "
        "— faqat savol berib qo'yma, o'quvchi postning o'zidan to'liq tushunsin.\n"
        "- Tabiiy, jonli ohang; nega bu qiziq yoki muhimligini ham qisqa izohla.\n"
        "- 2-4 abzas, 6-10 jumla. To'liq va ma'lumotli, lekin suvsiz.\n"
        "- Ko'pi bilan 2-3 mos emoji ishlat, ortiqcha emas.\n"
        "- HTML, markdown, yulduzcha (*) yoki sarlavha ishlatma. Faqat oddiy matn.\n"
        "- Manba nomi, havola yoki sayt nomini (techcrunch, championat va h.k.) yozma.\n"
        + focus_line +
        "- Faqat tayyor post matnini qaytar, hech qanday izoh qo'shma.\n\n"
        f"Yangilik:\n{src}\n\nPost:"
    )
    out = llm_text(prompt, max_tokens=900)
    if not out:
        return None
    out = out.strip().strip('"').strip()
    out = out.replace("**", "").replace("__", "").replace("*", "")
    return out[:950] or None       # Telegram rasm-caption limiti (1024) ichida qolsin


def _article_text(link: str, max_paras: int = 12, max_chars: int = 3500) -> str:
    """Maqolaning asosiy matnini (paragraflar) manbadan oladi -> blog uchun kontekst."""
    if not link:
        return ""
    try:
        html_ = requests.get(link, headers=UA_WEB, timeout=15).text
    except Exception as e:
        print("Maqola matni xato:", e)
        return ""
    soup = BeautifulSoup(html_, "html.parser")
    for bad in soup(["script", "style", "noscript", "figure", "iframe"]):
        bad.decompose()
    container = (soup.find("article")
                 or soup.find(attrs={"itemprop": "articleBody"})
                 or soup.find(class_=re.compile(r"article|content|news|post|body", re.I))
                 or soup)
    paras, seen = [], set()
    for p in container.find_all("p"):
        t = p.get_text(" ", strip=True)
        if len(t) >= 40 and t not in seen:
            seen.add(t)
            paras.append(t)
        if len(paras) >= max_paras:
            break
    return "\n".join(paras)[:max_chars]


def translate_to_uz(text: str) -> str:
    """Sarlavhani tabiiy O'zbek (lotin) tiliga tarjima qiladi.

    Tartib: Gemini -> Claude -> bepul Google Translate. Hammasi yiqilsa original qoladi.
    Shu sabab kanal hech qachon ruscha/tarjimasiz chiqib qolmaydi."""
    if not text:
        return text
    prompt = ("Quyidagi sport/futbol yangiligi sarlavhasini tabiiy, jonli O'zbek "
              "tiliga (lotin alifbosida) tarjima qil. Faqat tarjimani qaytar, "
              f"izoh va qo'shtirnoqsiz:\n\n{text}")
    t = llm_text(prompt, 200)        # Gemini -> Claude
    if t:
        t = t.strip().strip('"«»').strip()
        if t:
            return t
    return _translate_google(text, "uz")   # oxirgi zaxira (bepul, kalitsiz)


def translate_paras_uz(paras: list[str]) -> list[str]:
    """Paragraflar ro'yxatini o'zbekchaga tarjima qiladi (Instant View ichi uchun).

    Avval LLM (Gemini -> Claude) butun matnni BITTA chaqiruvda tarjima qiladi
    (paragraf tuzilishini saqlaydi); bo'lmasa har paragraf bepul Google bilan."""
    paras = [p for p in paras if p and p.strip()]
    if not paras:
        return paras
    joined = "\n\n".join(paras)
    prompt = ("Quyidagi yangilik matnini tabiiy, ravon O'zbek tiliga (lotin alifbosida) "
              "tarjima qil. Har bir paragrafni bo'sh qator bilan ajratib saqla, "
              "paragraflar sonini o'zgartirma. Faqat tarjimani qaytar, izohsiz:\n\n" + joined)
    out = llm_text(prompt, 4096)
    if out:
        parts = [p.strip() for p in out.split("\n\n") if p.strip()]
        if parts:
            return parts
    return [_translate_google(p, "uz") for p in paras]   # zaxira: bittalab (bepul)


# ------------------------------------------------------------------ FUTBOL (JCH-2026)
# Asosiy manba: football-data.org (FOOTBALL_API_KEY) -> to'liq ma'lumot.
# Zaxira: TheSportsDB (kalitsiz, namuna). Logolar SVG bo'lgani uchun jamoa nomidan
# mamlakat BAYROG'I (flagcdn PNG) ishlatamiz.
FOOTBALL_API_KEY = os.environ.get("FOOTBALL_API_KEY", "")
FD_BASE = "https://api.football-data.org/v4"
FD_COMP = "WC"
TSDB = "https://www.thesportsdb.com/api/v1/json/3"
WC_LEAGUE = "4429"
WC_SEASON = "2026"

# Qo'llab-quvvatlanadigan turnirlar: FD kodi -> (ko'rinadigan nom, hashtag).
# Kanal config'idagi "competitions" ro'yxati shu kodlarni tanlaydi.
COMPETITIONS = {
    "WC":  ("JCH-2026", "#JCH2026"),
    "CL":  ("Chempionlar ligasi", "#ChempionlarLigasi"),
    "PL":  ("Angliya Premyer-ligasi", "#APL"),
    "PD":  ("Ispaniya La Liga", "#LaLiga"),
    "SA":  ("Italiya Seriya A", "#SeriyaA"),
    "BL1": ("Germaniya Bundesliga", "#Bundesliga"),
    "FL1": ("Fransiya Ligue 1", "#Ligue1"),
}


def _comp_name(comp: str) -> str:
    return COMPETITIONS.get(comp, (comp, ""))[0]


def _comp_tag(comp: str) -> str:
    return COMPETITIONS.get(comp, (comp, f"#{comp}"))[1] or f"#{comp}"


def _within_hours(utc: str, hours: float, future: bool) -> bool:
    """utcDate berilgan oyna ichidami? future=True -> kelajak (o'yinlar), False -> o'tgan (natija).

    Oz miqdorda (6 soat) qarama-qarshi tomonni ham qamraydi (bugun boshlangan/tugagan o'yin)."""
    try:
        dt = datetime.datetime.fromisoformat((utc or "").replace("Z", "+00:00"))
    except Exception:
        return True   # vaqtni o'qib bo'lmasa -> kesib tashlamaymiz
    diff = (dt - datetime.datetime.now(datetime.timezone.utc)).total_seconds() / 3600.0
    return (-6 <= diff <= hours) if future else (-hours <= diff <= 6)

# Jamoa nomi -> flagcdn ISO kodi (barcha FIFA mamlakatlari, to'liq).
WC_FLAGS = {
    # Osiyo
    "iran": "ir", "iraq": "iq", "qatar": "qa", "saudi arabia": "sa", "japan": "jp",
    "south korea": "kr", "korea republic": "kr", "north korea": "kp", "dpr korea": "kp",
    "australia": "au", "uzbekistan": "uz", "united arab emirates": "ae", "uae": "ae",
    "china": "cn", "china pr": "cn", "jordan": "jo", "oman": "om", "bahrain": "bh",
    "kuwait": "kw", "syria": "sy", "lebanon": "lb", "palestine": "ps", "india": "in",
    "indonesia": "id", "thailand": "th", "vietnam": "vn", "kyrgyzstan": "kg", "tajikistan": "tj",
    "turkmenistan": "tm", "kazakhstan": "kz", "malaysia": "my", "philippines": "ph", "yemen": "ye",
    # Afrika
    "morocco": "ma", "senegal": "sn", "tunisia": "tn", "egypt": "eg", "algeria": "dz",
    "nigeria": "ng", "ghana": "gh", "cameroon": "cm", "ivory coast": "ci", "cote d'ivoire": "ci",
    "côte d'ivoire": "ci", "cape verde": "cv", "cape verde islands": "cv", "south africa": "za",
    "mali": "ml", "burkina faso": "bf", "dr congo": "cd", "congo dr": "cd", "congo": "cg",
    "angola": "ao", "zambia": "zm", "kenya": "ke", "uganda": "ug", "tanzania": "tz",
    "ethiopia": "et", "sudan": "sd", "libya": "ly", "gabon": "ga", "benin": "bj", "togo": "tg",
    "mauritania": "mr", "guinea": "gn", "guinea-bissau": "gw", "equatorial guinea": "gq",
    "namibia": "na", "zimbabwe": "zw", "mozambique": "mz", "madagascar": "mg", "comoros": "km",
    "gambia": "gm", "sierra leone": "sl", "liberia": "lr", "niger": "ne", "rwanda": "rw",
    # Yevropa
    "england": "gb-eng", "scotland": "gb-sct", "wales": "gb-wls", "northern ireland": "gb-nir",
    "france": "fr", "germany": "de", "spain": "es", "portugal": "pt", "italy": "it",
    "netherlands": "nl", "belgium": "be", "croatia": "hr", "switzerland": "ch", "sweden": "se",
    "denmark": "dk", "norway": "no", "poland": "pl", "austria": "at", "ukraine": "ua",
    "serbia": "rs", "turkey": "tr", "turkiye": "tr", "türkiye": "tr", "czechia": "cz",
    "czech republic": "cz", "greece": "gr", "hungary": "hu", "romania": "ro", "bulgaria": "bg",
    "slovakia": "sk", "slovenia": "si", "finland": "fi", "iceland": "is", "ireland": "ie",
    "albania": "al", "north macedonia": "mk", "montenegro": "me", "bosnia and herzegovina": "ba",
    "bosnia": "ba", "bosnia-herzegovina": "ba", "bosnia & herzegovina": "ba", "kosovo": "xk",
    "moldova": "md", "georgia": "ge", "armenia": "am",
    "azerbaijan": "az", "belarus": "by", "estonia": "ee", "latvia": "lv", "lithuania": "lt",
    "luxembourg": "lu", "cyprus": "cy", "malta": "mt", "israel": "il", "russia": "ru",
    # Shimoliy/Markaziy Amerika
    "usa": "us", "united states": "us", "mexico": "mx", "canada": "ca", "costa rica": "cr",
    "honduras": "hn", "panama": "pa", "jamaica": "jm", "el salvador": "sv", "guatemala": "gt",
    "nicaragua": "ni", "haiti": "ht", "trinidad and tobago": "tt", "curacao": "cw",
    "curaçao": "cw", "cuba": "cu", "dominican republic": "do", "suriname": "sr", "guyana": "gy",
    "grenada": "gd", "antigua and barbuda": "ag", "barbados": "bb", "bermuda": "bm", "belize": "bz",
    # Janubiy Amerika
    "argentina": "ar", "brazil": "br", "uruguay": "uy", "colombia": "co", "chile": "cl",
    "peru": "pe", "ecuador": "ec", "paraguay": "py", "bolivia": "bo", "venezuela": "ve",
    # Okeaniya
    "new zealand": "nz", "fiji": "fj", "papua new guinea": "pg", "tahiti": "pf",
    "solomon islands": "sb", "vanuatu": "vu", "new caledonia": "nc",
}


def _flag_url(team: str):
    code = WC_FLAGS.get((team or "").strip().lower())
    return f"https://flagcdn.com/w80/{code}.png" if code else None


# Jamoa (mamlakat) nomi -> o'zbekcha (bayroq inglizcha nomdan, ko'rsatish o'zbekcha)
UZ_TEAMS = {
    "argentina": "Argentina", "australia": "Avstraliya", "austria": "Avstriya",
    "belgium": "Belgiya", "bolivia": "Boliviya", "bosnia and herzegovina": "Bosniya",
    "bosnia": "Bosniya", "bosnia-herzegovina": "Bosniya", "bosnia & herzegovina": "Bosniya",
    "brazil": "Braziliya", "bulgaria": "Bolgariya", "cameroon": "Kamerun",
    "canada": "Kanada", "cape verde": "Kabo-Verde", "cape verde islands": "Kabo-Verde",
    "chile": "Chili", "china": "Xitoy", "china pr": "Xitoy", "colombia": "Kolumbiya",
    "costa rica": "Kosta-Rika", "croatia": "Xorvatiya", "cuba": "Kuba", "curacao": "Kyurasao",
    "curaçao": "Kyurasao", "cyprus": "Kipr", "czechia": "Chexiya", "czech republic": "Chexiya",
    "dr congo": "KDR", "congo dr": "KDR", "congo": "Kongo", "denmark": "Daniya",
    "dominican republic": "Dominikana", "ecuador": "Ekvador", "egypt": "Misr",
    "england": "Angliya", "estonia": "Estoniya", "ethiopia": "Efiopiya", "finland": "Finlyandiya",
    "france": "Fransiya", "gabon": "Gabon", "georgia": "Gruziya", "germany": "Germaniya",
    "ghana": "Gana", "greece": "Gretsiya", "guatemala": "Gvatemala", "guinea": "Gvineya",
    "haiti": "Gaiti", "honduras": "Gonduras", "hungary": "Vengriya", "iceland": "Islandiya",
    "india": "Hindiston", "indonesia": "Indoneziya", "iran": "Eron", "iraq": "Iroq",
    "ireland": "Irlandiya", "israel": "Isroil", "italy": "Italiya", "ivory coast": "Kot-d'Ivuar",
    "cote d'ivoire": "Kot-d'Ivuar", "côte d'ivoire": "Kot-d'Ivuar", "jamaica": "Yamayka",
    "japan": "Yaponiya", "jordan": "Iordaniya", "kazakhstan": "Qozog'iston", "kenya": "Keniya",
    "kosovo": "Kosovo", "kuwait": "Quvayt", "kyrgyzstan": "Qirg'iziston", "latvia": "Latviya",
    "lebanon": "Livan", "libya": "Liviya", "lithuania": "Litva", "luxembourg": "Lyuksemburg",
    "malaysia": "Malayziya", "mali": "Mali", "malta": "Malta", "mexico": "Meksika",
    "moldova": "Moldova", "montenegro": "Chernogoriya", "morocco": "Marokash",
    "mozambique": "Mozambik", "namibia": "Namibiya", "netherlands": "Niderlandiya",
    "new zealand": "Yangi Zelandiya", "nigeria": "Nigeriya", "north korea": "Shimoliy Koreya",
    "dpr korea": "Shimoliy Koreya", "north macedonia": "Shim. Makedoniya",
    "northern ireland": "Shim. Irlandiya", "norway": "Norvegiya", "oman": "Ummon",
    "palestine": "Falastin", "panama": "Panama", "paraguay": "Paragvay", "peru": "Peru",
    "poland": "Polsha", "portugal": "Portugaliya", "qatar": "Qatar", "romania": "Ruminiya",
    "russia": "Rossiya", "rwanda": "Ruanda", "saudi arabia": "Saudiya Arab.",
    "scotland": "Shotlandiya", "senegal": "Senegal", "serbia": "Serbiya",
    "sierra leone": "Syerra-Leone", "slovakia": "Slovakiya", "slovenia": "Sloveniya",
    "solomon islands": "Solomon o.", "south africa": "JAR", "south korea": "Janubiy Koreya",
    "korea republic": "Janubiy Koreya", "spain": "Ispaniya", "sudan": "Sudan",
    "sweden": "Shvetsiya", "switzerland": "Shveytsariya", "syria": "Suriya", "tahiti": "Taiti",
    "tajikistan": "Tojikiston", "tanzania": "Tanzaniya", "thailand": "Tailand", "togo": "Togo",
    "trinidad and tobago": "Trinidad", "tunisia": "Tunis", "turkey": "Turkiya",
    "turkiye": "Turkiya", "türkiye": "Turkiya", "turkmenistan": "Turkmaniston",
    "uae": "BAA", "united arab emirates": "BAA", "uganda": "Uganda", "ukraine": "Ukraina",
    "united states": "AQSH", "usa": "AQSH", "uruguay": "Urugvay", "uzbekistan": "O'zbekiston",
    "venezuela": "Venesuela", "vietnam": "Vyetnam", "wales": "Uels", "yemen": "Yaman",
    "zambia": "Zambiya", "zimbabwe": "Zimbabve", "algeria": "Jazoir", "albania": "Albaniya",
    "armenia": "Armaniston", "azerbaijan": "Ozarbayjon", "bahrain": "Bahrayn", "belarus": "Belarus",
    "burkina faso": "Burkina-Faso", "fiji": "Fiji", "new caledonia": "Yangi Kaledoniya",
    "papua new guinea": "Papua-Yangi Gvineya", "vanuatu": "Vanuatu",
}


def _uz_team(name: str) -> str:
    return UZ_TEAMS.get((name or "").strip().lower(), name or "")


def _team_meta(name: str):
    """(o'zbekcha_nom, bayroq_url) -> bayroq inglizcha nomdan, nom o'zbekcha."""
    return _uz_team(name), _flag_url(name)


def _flag_emoji(name: str) -> str:
    """Jamoa nomidan bayroq EMOJI (matnli gol postlari uchun). gb-* uchun bo'sh."""
    code = WC_FLAGS.get((name or "").strip().lower(), "")
    if len(code) == 2 and code.isalpha():
        return "".join(chr(0x1F1E6 + ord(c) - ord("a")) for c in code.lower())
    return ""


def get_live() -> list:
    """Hozir o'ynalayotgan JCH o'yinlari (joriy hisob bilan). FD kaliti kerak."""
    d = _fd(f"/competitions/{FD_COMP}/matches?status=IN_PLAY") or {}
    out = []
    for m in d.get("matches", []):
        hn, an = m["homeTeam"]["name"], m["awayTeam"]["name"]
        sc = (m.get("score", {}) or {}).get("fullTime", {}) or {}
        out.append({"id": m.get("id"), "home": _uz_team(hn), "away": _uz_team(an),
                    "he": _flag_emoji(hn), "ae": _flag_emoji(an),
                    "hs": sc.get("home") or 0, "as": sc.get("away") or 0,
                    "minute": m.get("minute")})
    return out


def _match_time_uz(ts: str) -> str:
    """UTC timestamp -> Toshkent HH:MM."""
    try:
        dt = datetime.datetime.fromisoformat(ts.replace("Z", "")) + datetime.timedelta(hours=5)
        return dt.strftime("%H:%M")
    except Exception:
        return "--:--"


def _fd(path: str):
    """football-data.org so'rovi (kalit bo'lsa). Xato/kalitsiz -> None."""
    if not FOOTBALL_API_KEY:
        return None
    try:
        r = requests.get(f"{FD_BASE}{path}", headers={"X-Auth-Token": FOOTBALL_API_KEY}, timeout=20)
        if r.status_code == 200:
            return r.json()
        print(f"football-data.org {r.status_code}: {r.text[:120]}")
    except Exception as e:
        print("football-data.org xato:", e)
    return None


def _tsdb(path: str) -> dict:
    try:
        return requests.get(f"{TSDB}/{path}", headers=UA_WEB, timeout=20).json() or {}
    except Exception as e:
        print("TheSportsDB xato:", e)
        return {}


def _mk_match(hn, an, time=None, hs=None, as_=None, rnd=None, hcrest=None, acrest=None):
    # Milliy jamoa -> mamlakat bayrog'i; klub (bayroq yo'q) -> FD'dan logo (crest).
    h_uz, hb = _team_meta(hn)
    a_uz, ab = _team_meta(an)
    d = {"home": h_uz, "away": a_uz, "hb": hb or hcrest, "ab": ab or acrest, "round": rnd}
    if time is not None:
        d["time"] = time
    if hs is not None or as_ is not None:
        d["hs"], d["as"] = hs, as_
    return d


def _fd_named(m: dict) -> bool:
    """FD o'yinida ikkala jamoa ham aniq (TBD/placeholder — bo'sh nom — emas)."""
    return bool((m.get("homeTeam") or {}).get("name") and (m.get("awayTeam") or {}).get("name"))


def get_fixtures(limit: int = 10, comp: str = None, soon_hours: float = None) -> list:
    """comp turniri uchun yaqin o'yinlar. soon_hours berilsa -> faqat shu oyna ichidagilar."""
    comp = comp or FD_COMP
    d = _fd(f"/competitions/{comp}/matches?status=SCHEDULED")
    if d and d.get("matches"):
        ms = [m for m in sorted(d["matches"], key=lambda m: m.get("utcDate", ""))
              if _fd_named(m) and (soon_hours is None
                                   or _within_hours(m.get("utcDate", ""), soon_hours, True))][:limit]
        return [_mk_match(m["homeTeam"]["name"], m["awayTeam"]["name"],
                          time=_match_time_uz(m.get("utcDate", "")), rnd=m.get("matchday"),
                          hcrest=m["homeTeam"].get("crest"), acrest=m["awayTeam"].get("crest"))
                for m in ms]
    if comp != FD_COMP:           # TSDB zaxira faqat JCH uchun
        return []
    ev = [e for e in (_tsdb(f"eventsnextleague.php?id={WC_LEAGUE}").get("events") or [])
          if e.get("strHomeTeam") and e.get("strAwayTeam")][:limit]
    return [_mk_match(e.get("strHomeTeam", ""), e.get("strAwayTeam", ""),
                      time=_match_time_uz(e.get("strTimestamp", "")), rnd=e.get("intRound"))
            for e in ev]


def get_results(limit: int = 10, comp: str = None, recent_hours: float = None) -> list:
    """comp turniri uchun so'nggi natijalar. recent_hours berilsa -> faqat shu oyna ichidagilar."""
    comp = comp or FD_COMP
    d = _fd(f"/competitions/{comp}/matches?status=FINISHED")
    if d and d.get("matches"):
        ms = [m for m in sorted(d["matches"], key=lambda m: m.get("utcDate", ""), reverse=True)
              if _fd_named(m) and (recent_hours is None
                                   or _within_hours(m.get("utcDate", ""), recent_hours, False))][:limit]
        return [_mk_match(m["homeTeam"]["name"], m["awayTeam"]["name"],
                          hs=m["score"]["fullTime"].get("home"), as_=m["score"]["fullTime"].get("away"),
                          rnd=m.get("matchday"),
                          hcrest=m["homeTeam"].get("crest"), acrest=m["awayTeam"].get("crest")) for m in ms]
    if comp != FD_COMP:
        return []
    ev = [e for e in (_tsdb(f"eventspastleague.php?id={WC_LEAGUE}").get("events") or [])
          if e.get("strHomeTeam") and e.get("strAwayTeam")][:limit]
    return [_mk_match(e.get("strHomeTeam", ""), e.get("strAwayTeam", ""),
                      hs=e.get("intHomeScore"), as_=e.get("intAwayScore"), rnd=e.get("intRound"))
            for e in ev]


def get_standings(comp: str = None) -> dict:
    """Guruh/jadval -> [{rank, team, badge, p, gd, pts}] (tartiblangan). comp turniri."""
    comp = comp or FD_COMP
    groups: dict = {}
    d = _fd(f"/competitions/{comp}/standings")
    if d and d.get("standings"):
        for s in d["standings"]:
            if s.get("type") != "TOTAL":
                continue
            g = (s.get("group") or "").replace("GROUP_", "Group ").strip() or "—"
            for r in s.get("table", []):
                tm = r["team"]["name"]
                groups.setdefault(g, []).append({
                    "rank": r.get("position"), "team": _uz_team(tm),
                    "badge": _flag_url(tm) or r["team"].get("crest"),   # milliy -> bayroq; klub -> logo
                    "p": r.get("playedGames"), "gd": r.get("goalDifference"), "pts": r.get("points")})
        if groups:
            return dict(sorted(groups.items()))
    rows = _tsdb(f"lookuptable.php?l={WC_LEAGUE}&s={WC_SEASON}").get("table") or []
    for r in rows:
        g = r.get("strGroup", "") or "—"
        tm = r.get("strTeam", "")
        groups.setdefault(g, []).append({
            "rank": r.get("intRank"), "team": _uz_team(tm), "badge": _flag_url(tm),
            "p": r.get("intPlayed"), "gd": r.get("intGoalDifference"), "pts": r.get("intPoints")})
    for g in groups:
        groups[g].sort(key=lambda x: int(x["rank"] or 99))
    return dict(sorted(groups.items()))


def _og_image_url(article_url: str) -> str | None:
    """Maqola sahifasidan og:image (yoki twitter:image) manzilini oladi."""
    try:
        resp = requests.get(article_url, headers=UA_WEB, timeout=15)
        resp.raise_for_status()
    except Exception:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    for prop in ("og:image", "twitter:image"):
        tag = (soup.find("meta", attrs={"property": prop})
               or soup.find("meta", attrs={"name": prop}))
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _og_desc(article_url: str) -> str:
    """Maqolaning qisqa tavsifi (og:description). Topilmasa bo'sh."""
    try:
        resp = requests.get(article_url, headers=UA_WEB, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for prop in ("og:description", "description", "twitter:description"):
            tag = (soup.find("meta", attrs={"property": prop})
                   or soup.find("meta", attrs={"name": prop}))
            if tag and tag.get("content"):
                return tag["content"].strip()
    except Exception:
        pass
    return ""


def fetch_news_image(items: list[dict], out_path: str = "news_banner.png") -> str | None:
    """Sarlavhalardan birinchi mos maqolaning rasmini yuklab, PNG saqlaydi.

    Banner sifatida ishlatiladi. Hech qaysidan rasm topilmasa None qaytaradi
    (u holda karta oddiy, rasmsiz chiqadi)."""
    for it in items[:6]:
        link = it.get("link") if isinstance(it, dict) else None
        if not link:
            continue
        src = _og_image_url(link)
        if not src:
            continue
        try:
            r = requests.get(src, headers=UA_WEB, timeout=20)
            if r.status_code != 200 or "image" not in r.headers.get("content-type", ""):
                continue
            from PIL import Image
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            if im.width < 300 or im.height < 150:   # juda kichik/ikona rasmlarni o'tkazib yuboramiz
                continue
            im.save(out_path)
            print(f"Banner rasm: {src[:70]}")
            return out_path
        except Exception as e:
            print("Banner rasm olishda xato:", e)
            continue
    return None


# ------------------------------------------------------------------ INSTANT VIEW (telegra.ph)
# Maqola matnini telegra.ph sahifasiga ko'chiramiz -> Telegram'da avtomatik
# Instant View bilan ochiladi (obunachi ilovadan chiqmasdan to'liq o'qiydi).
_TG_TOKEN = None


def _telegraph_token():
    global _TG_TOKEN
    if _TG_TOKEN:
        return _TG_TOKEN
    try:
        r = requests.get("https://api.telegra.ph/createAccount",
                         params={"short_name": "AjoyibKun", "author_name": "Ajoyib Kun | Bugun"},
                         timeout=15).json()
        if r.get("ok"):
            _TG_TOKEN = r["result"]["access_token"]
    except Exception as e:
        print("Telegraph account xato:", e)
    return _TG_TOKEN


def make_instant_view(item, translate=None) -> str | None:
    """Maqolani telegra.ph sahifasiga ko'chiradi va URL qaytaradi (Instant View).

    translate="uz" -> sarlavha va butun maqola matni o'zbekchaga tarjima qilinadi.
    Xato bo'lsa None (u holda tugma oddiy maqola havolasiga tushadi)."""
    link = item.get("link") if isinstance(item, dict) else None
    title = (item.get("title") if isinstance(item, dict) else item) or "Xabar"
    if not link:
        return None
    token = _telegraph_token()
    if not token:
        return None
    try:
        html_ = requests.get(link, headers=UA_WEB, timeout=15).text
        soup = BeautifulSoup(html_, "html.parser")
        for bad in soup(["script", "style", "noscript", "figure", "iframe"]):
            bad.decompose()
        img = _og_image_url(link)
        container = (soup.find("article")
                     or soup.find(attrs={"itemprop": "articleBody"})
                     or soup.find(class_=re.compile(r"article|content|news|post|body", re.I))
                     or soup)
        paras, seen = [], set()
        for p in container.find_all("p"):
            t = p.get_text(" ", strip=True)
            if len(t) >= 40 and t not in seen:
                seen.add(t)
                paras.append(t)
            if len(paras) >= 40:
                break
        if not paras:
            paras = [title]
        if translate == "uz":                  # IV ichini ham o'zbekchaga o'giramiz
            title = translate_to_uz(title)
            paras = translate_paras_uz(paras)
        content = []
        if img:
            content.append({"tag": "figure", "children": [{"tag": "img", "attrs": {"src": img}}]})
        for t in paras:
            content.append({"tag": "p", "children": [t]})
        content.append({"tag": "p", "children": [
            {"tag": "a", "attrs": {"href": link}, "children": ["🔗 Manbada to‘liq o‘qish"]}]})
        ch = str(TELEGRAM_CHANNEL).lstrip("@")
        data = {"access_token": token, "title": title[:200],
                "author_name": CHANNEL_NAME, "author_url": f"https://t.me/{ch}",
                "content": json.dumps(content, ensure_ascii=False), "return_content": "false"}
        r = requests.post("https://api.telegra.ph/createPage", data=data, timeout=25).json()
        if r.get("ok"):
            return r["result"]["url"]
        print("Telegraph createPage xato:", r)
    except Exception as e:
        print("Instant View xato:", e)
    return None


# ------------------------------------------------------------------ TEZKOR XABAR (holat)
# Holat fayllari har kanal uchun alohida: state/<kanal>/... (takror, kunlik belgi, kurslar).
# GitHub Actions har ish oxirida state/ ni repoga commit qiladi.
MAX_ALERTS = 2        # bitta ishda ko'pi bilan necha yangi xabar post qilinadi
STATE_KEEP = 200      # holatda saqlanadigan oxirgi yozuvlar soni


def _news_key(item: dict) -> str:
    return (item.get("link") or item.get("title") or "").strip()


def _load_json(name, default):
    try:
        with open(_sp(name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(name, data):
    try:
        os.makedirs(os.path.dirname(_sp(name)), exist_ok=True)
        with open(_sp(name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=0)
    except Exception as e:
        print(f"Holat saqlashda xato ({name}):", e)


def load_posted() -> list:
    return _load_json("posted_news.json", [])


def save_posted(keys: list) -> None:
    _save_json("posted_news.json", keys[-STATE_KEEP:])


def load_daily() -> dict:
    return _load_json("posted_daily.json", {})


def save_daily(state: dict) -> None:
    _save_json("posted_daily.json", state)


def load_prev_rates() -> dict:
    return _load_json("prev_rates.json", {})


def save_prev_rates(rates: dict) -> None:
    _save_json("prev_rates.json", rates)


# Oltin narxining kunlik o'zgarishini hisoblash uchun (kechagi qiymat).
def load_prev_market() -> dict:
    return _load_json("prev_market.json", {})


def save_prev_market(state: dict) -> None:
    _save_json("prev_market.json", state)


# ------------------------------------------------------------------ BUGUN (taqvim)
SEASONS = {12: "Qish", 1: "Qish", 2: "Qish", 3: "Bahor", 4: "Bahor", 5: "Bahor",
           6: "Yoz", 7: "Yoz", 8: "Yoz", 9: "Kuz", 10: "Kuz", 11: "Kuz"}

# (oy, kun) -> bayram/muhim kun. O'zbekiston + xalqaro kunlar.
HOLIDAYS = {
    (1, 1): ["Yangi yil"],
    (1, 14): ["Vatan himoyachilari kuni"],
    (2, 14): ["Sevishganlar kuni"],
    (2, 21): ["Xalqaro ona tili kuni"],
    (3, 8): ["Xalqaro xotin-qizlar kuni"],
    (3, 20): ["Yer kuni (xalqaro)"],
    (3, 21): ["Navro'z bayrami"],
    (3, 22): ["Jahon suv kuni"],
    (4, 7): ["Jahon sog'liqni saqlash kuni"],
    (4, 12): ["Kosmonavtika kuni"],
    (4, 22): ["Xalqaro Yer kuni"],
    (5, 1): ["Xalqaro mehnatkashlar kuni"],
    (5, 9): ["Xotira va qadrlash kuni"],
    (6, 1): ["Bolalarni himoya qilish kuni"],
    (6, 5): ["Jahon atrof-muhit kuni"],
    (6, 21): ["Xalqaro yoga kuni", "Yozgi quyosh turishi"],
    (7, 1): ["Arxitektura kuni (xalqaro)"],
    (8, 31): ["Qatag'on qurbonlarini yod etish kuni"],
    (9, 1): ["Mustaqillik kuni"],
    (9, 21): ["Xalqaro tinchlik kuni"],
    (10, 1): ["O'qituvchi va murabbiylar kuni", "Keksalar kuni (xalqaro)"],
    (10, 5): ["Jahon o'qituvchilar kuni"],
    (11, 14): ["Diabetga qarshi kurash kuni"],
    (11, 21): ["Jahon televideniye kuni"],
    (12, 1): ["OITSga qarshi kurash kuni"],
    (12, 8): ["O'zbekiston Konstitutsiyasi kuni"],
    (12, 10): ["Inson huquqlari kuni"],
    (12, 31): ["Yil yakuni"],
}


def get_day_info(now):
    leap = now.year % 4 == 0 and (now.year % 100 != 0 or now.year % 400 == 0)
    total = 366 if leap else 365
    yday = now.timetuple().tm_yday
    return {
        "weekday": UZ_DAYS[now.weekday()],
        "season": SEASONS[now.month],
        "day_of_year": yday,
        "days_left": total - yday,
        "week_no": now.isocalendar()[1],
        "holidays": HOLIDAYS.get((now.month, now.day), []),
    }


# ------------------------------------------------------------------ KUN MASLAHATI
_TIPS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tips.json")


def get_daily_tip(now) -> dict:
    """tips.json'dan har kuni navbat bilan bittasini tanlaydi (takrorlanmas tartib)."""
    try:
        with open(_TIPS_PATH, encoding="utf-8") as f:
            tips = json.load(f)
    except Exception as e:
        print("tips.json o'qilmadi:", e)
        return {"kind": "Maslahat", "text": "Har kuni bir qadam — yilda katta yo'l."}
    if not tips:
        return {"kind": "Maslahat", "text": "Har kuni bir qadam — yilda katta yo'l."}
    # yil + kun bo'yicha aylanma indeks
    idx = (now.timetuple().tm_yday + (now.year - 2026) * 366) % len(tips)
    return tips[idx]


# ------------------------------------------------------------------ CAPTION
def _wx_emoji(desc: str) -> str:
    d = desc.lower()
    if "qor" in d:
        return "\u2744\ufe0f"          # ❄️
    if "yomg'ir" in d or "jala" in d:
        return "\U0001F327"            # 🌧
    if "momaqaldiroq" in d:
        return "\u26C8\ufe0f"          # ⛈
    if "tuman" in d:
        return "\U0001F32B\ufe0f"      # 🌫
    if "qisman bulut" in d:
        return "\U0001F324\ufe0f"      # 🌤
    if "bulut" in d:
        return "\u2601\ufe0f"          # ☁️
    return "\u2600\ufe0f"              # ☀️


def _channel_footer() -> str:
    """Har post tagidagi DOIMIY (bir xil) brend footeri: xizmatlar + obuna + ulashish."""
    ch = str(TELEGRAM_CHANNEL).strip()
    if not ch.startswith("@"):
        return ""
    uname = ch[1:]
    # Ko'rinadigan matn = chiroyli kanal nomi; havola esa o'sha kanalga (o'zgarmaydi).
    label = html.escape(CHANNEL_NAME or ch, quote=False)
    link = f'<a href="https://t.me/{uname}">{label}</a>'
    return ("\n\n━━━━━━━━━━━━━━"
            f"\n{FOOTER_SERVICES}"
            f"\n👉 {link} — obuna bo'ling 🔔 · ulashing 📢")


def _append_footer(text: str) -> str:
    footer = _channel_footer()
    return (text[:1024 - len(footer)] + footer) if footer else text[:1024]


def _finish(parts) -> str:
    """Caption qatorlarini yig'ib, kanal havolasini qo'shadi (limit ichida)."""
    return _append_footer("\n".join(parts))


# ---- Yakun iboralari: faqat TOZA, to'g'ri jumlalar (g'aliz/sun'iy iboralar yo'q) ----
# Faqat tabiiy o'rin bo'lgan postlarda (ob-havo, maslahat). Ma'lumot postlarida
# (kurs/dollar/bozor) yakun jumlasi yo'q -> sun'iy "xayrli kun" tilanmaydi.
_CLOSE = {
    "weather": ["Hammaga xayrli kun! ☀️", "Yaxshi kun tilaymiz!",
                "Kuningiz yaxshi o'tsin!", "Sog'-salomat bo'ling!"],
    "advice": ["Kuningiz unumli o'tsin! 💪", "Omad tilaymiz! 🙌",
               "Yaxshi kun tilaymiz!", "Bugun ham harakatda bo'ling!"],
}


def _vary(key) -> str:
    """Toza iboralar pulidan tasodifiy bittasi (faqat to'g'ri jumlalar)."""
    pool = _CLOSE.get(key, [])
    return random.choice(pool) if pool else ""


# Har post turi uchun QAT'IY (doim bir xil) hashtaglar -> tartibli, kategoriyalangan.
_TAGS = {
    "weather": "#ObHavo #Ozbekiston",
    "day": "#Bugun #Kun #Taqvim",
    "rates": "#ValyutaKurslari #Kurs #Markaziybank",
    "dollar": "#DollarKursi #Dollar #Kurs",
    "market": "#Oltin #Bitcoin #Bozor #Kripto",
    "news": "#TezkorXabar #Yangilik",
    "advice": "#Motivatsiya",
}


def _tags(key, extra=None) -> str:
    """Post turiga mos QAT'IY hashtaglar (doim bir xil)."""
    base = _TAGS.get(key, "")
    return f"{extra} {base}".strip() if extra else base


def weather_caption(date_label, weather) -> str:
    """Ob-havo posti uchun elegant, emoji bilan caption (barcha viloyatlar)."""
    parts = [f"\U0001F326\ufe0f <b>Ob-havo</b> \u2014 {date_label}", ""]
    for region, (temp, desc) in weather.items():
        parts.append(f"{_wx_emoji(desc)} {region} \u2014 <b>{round(temp)}\u00b0</b>  <i>{desc}</i>")
    parts.append("")
    parts.append(_vary("weather"))
    parts.append("")
    parts.append(_tags("weather"))
    return _finish(parts)


def day_caption(date_label, info) -> str:
    """1-post: Bugun qanaqa kun (A: hisoblangan + bayramlar; B: Claude boyitadi)."""
    parts = [f"\U0001F4C5 <b>Bugun</b> \u2014 {date_label}", ""]
    parts.append(f"\U0001F5D3 Hafta kuni: <b>{info['weekday']}</b>")
    parts.append(f"\U0001F343 Fasl: <b>{info['season']}</b>")
    parts.append(f"\U0001F522 Yilning <b>{info['day_of_year']}</b>-kuni \u00b7 "
                 f"oxiriga <b>{info['days_left']}</b> kun \u00b7 {info['week_no']}-hafta")
    if info["holidays"]:
        parts.append("")
        parts.append("\U0001F389 <b>Bugungi sana/bayram</b>")
        parts += [f"\u2022 {h}" for h in info["holidays"]]
    parts.append("")
    parts.append("Xayrli kun tilaymiz!")
    text = "\n".join(parts)

    # Kalit (Gemini yoki Claude) bo'lsa caption boyitiladi; bo'lmasa shablon qoladi.
    hol = ", ".join(info["holidays"]) or "maxsus bayram yo'q"
    prompt = (
        f"Bugun {date_label}, {info['weekday']}, {info['season']} fasli. "
        f"Bayram/sana: {hol}. Telegram 'Bugun qanaqa kun' posti uchun QISQA, "
        "qiziqarli caption yoz (o'zbekcha, Telegram HTML faqat <b>, 600 belgidan kam). "
        "Tuzilishi: emoji bilan sarlavha; sana/fasl; agar bayram bo'lsa u haqida 1 jumla "
        "qiziqarli fakt; oxirida xayrli kun tilagi. Faqat matnni qaytar."
    )
    enriched = llm_text(prompt, 600)       # Gemini -> Claude
    if enriched:
        text = enriched
    text += "\n\n" + _tags("day")
    return _append_footer(text)


def business_caption(date_label, headlines) -> str:
    """2-post: biznes yangiliklari caption."""
    parts = [f"\U0001F4BC <b>Biznes ma'lumotlari</b> \u2014 {date_label}", ""]
    if headlines:
        for i, h in enumerate(headlines[:6], 1):
            title = h["title"] if isinstance(h, dict) else h
            parts.append(f"<b>{i}.</b> {title}")
    else:
        parts.append("<i>Bugun biznes yangiligi topilmadi.</i>")
    parts.append("")
    parts.append("\U0001F4E2 Batafsil \u2014 manbalarda")
    return _finish(parts)


def breaking_caption(item) -> str:
    """Tezkor (real-vaqt) bitta xabar uchun caption. Rasm ichida matn yo'q ->
    sarlavha faqat shu yerda; to'liq o'qish uchun inline tugma qo'shiladi."""
    title = item["title"] if isinstance(item, dict) else item
    parts = ["\u26a1 <b>Tezkor xabar</b>", "", f"<b>{title}</b>", "", _tags("news")]
    return _finish(parts)


def currency_overview_caption(date_label, rows) -> str:
    """4-post: umumiy valyuta kurslari caption."""
    flags = {"USD": "\U0001F1FA\U0001F1F8", "EUR": "\U0001F1EA\U0001F1FA",
             "GBP": "\U0001F1EC\U0001F1E7", "RUB": "\U0001F1F7\U0001F1FA",
             "KZT": "\U0001F1F0\U0001F1FF", "CNY": "\U0001F1E8\U0001F1F3",
             "JPY": "\U0001F1EF\U0001F1F5", "TRY": "\U0001F1F9\U0001F1F7",
             "AED": "\U0001F1E6\U0001F1EA", "KRW": "\U0001F1F0\U0001F1F7"}
    parts = [f"\U0001F4B6 <b>Valyuta kurslari</b> \u2014 {date_label}", "",
             "<i>Markaziy bank rasmiy kursi (1 birlik uchun)</i>", ""]
    for r in rows:
        parts.append(f"{flags.get(r['code'], '')} <b>{r['code']}</b> "
                     f"({r['unit']}) \u2014 {r['rate']} so'm")
    parts.append("")
    parts.append("\U0001F4B5 Dollarning banklar bo'yicha kursi \u2014 keyingi postda")
    parts.append("")
    parts.append(_tags("rates"))
    return _finish(parts)


def advice_caption(date_label, tip) -> str:
    """6-post: kun maslahati/hikmati caption (sanasiz)."""
    kind = tip.get("kind", "Maslahat")
    icon = "\U0001F4A1" if kind == "Maslahat" else "\u2728"
    label = "Kun maslahati" if kind == "Maslahat" else "Kun hikmati"
    tag = "#Maslahat" if kind == "Maslahat" else "#Hikmat"
    parts = [f"{icon} <b>{label}</b>", ""]
    parts.append(f"\u00ab{tip['text']}\u00bb")
    parts.append("")
    parts.append(_vary("advice"))
    parts.append("")
    parts.append(_tags("advice", extra=tag))
    return _finish(parts)


def currency_caption(date_label, cbu_rate, banks, extra_rates=None) -> str:
    """Dollar posti caption: rasmiy kurs + eng yaxshi olish/sotish (to'liq jadval rasmda)."""
    extra_rates = extra_rates or []
    valid = [b for b in banks if b.get("buy") and b.get("sell")]
    best_sell = min(valid, key=lambda b: b["sell"], default=None)
    best_buy = max(valid, key=lambda b: b["buy"], default=None)

    parts = [f"\U0001F4B5 <b>Dollar kursi</b> \u2014 {date_label}", ""]
    parts.append(f"\U0001F3E6 Markaziy bank (rasmiy): <b>{cbu_rate}</b>")
    parts.append("")
    if best_buy and best_sell:
        parts.append("\U0001F7E2 <b>Sotmoqchilarga</b> \u2014 eng qimmat oladigan bank:")
        parts.append(f"   {best_buy['bank']} \u00b7 <b>{best_buy['buy']:,} so'm</b>".replace(",", " "))
        parts.append("")
        parts.append("\U0001F535 <b>Olmoqchilarga</b> \u2014 eng arzon sotadigan bank:")
        parts.append(f"   {best_sell['bank']} \u00b7 <b>{best_sell['sell']:,} so'm</b>".replace(",", " "))
        parts.append("")
    if extra_rates:
        flags = {"EUR": "\U0001F1EA\U0001F1FA", "RUB": "\U0001F1F7\U0001F1FA",
                 "GBP": "\U0001F1EC\U0001F1E7", "KZT": "\U0001F1F0\U0001F1FF",
                 "CNY": "\U0001F1E8\U0001F1F3"}
        pairs = [f"{flags.get(e['code'], '')} {e['code']} {e['rate']}" for e in extra_rates]
        parts.append("\U0001F4B6 <b>Boshqa valyutalar</b> (rasmiy): " + "   ".join(pairs[:3]))
        parts.append("")
    parts.append("\U0001F4CA To'liq banklar jadvali \u2014 rasmda \u2b06\ufe0f")
    parts.append("\U0001F7E2 yashil \u2014 eng qimmat oladi \u00b7 \U0001F535 ko'k \u2014 eng arzon sotadi")
    parts.append("")
    parts.append(_tags("dollar"))
    return _finish(parts)


def market_caption(date_label, rows) -> str:
    """Bozor (oltin + kripto) posti caption."""
    parts = [f"\U0001F4C8 <b>Jahon bozori</b> \u2014 {date_label}", ""]
    for r in rows:
        line = f"<b>{r['name']}</b>: {r['value']}"
        if r.get("chg") is not None:
            arrow = "\U0001F53A" if r["chg"] >= 0 else "\U0001F53B"
            line += f"  {arrow} {abs(r['chg']):.2f}%".replace(".", ",")
        parts.append(line)
        if "gramm" in r.get("sub", ""):
            parts.append(f"   <i>{r['sub']}</i>")
    parts.append("")
    parts.append("<i>Narxlar jahon bozori bo'yicha (USD)</i>")
    parts.append("")
    parts.append(_tags("market"))
    return _finish(parts)


def fixtures_caption(date_label, matches, comp="WC") -> str:
    parts = [f"⚽ <b>Bugungi o'yinlar</b> — {date_label}", "",
             f"<i>{_comp_name(comp)} · Toshkent vaqti</i>", ""]
    shown = [m for m in matches if m.get("home") and m.get("away")][:10]   # bo'sh jamoa -> tashlab ketamiz
    for m in shown:
        parts.append(f"🕐 <b>{m['time']}</b>  {m['home']} — {m['away']}")
    if not shown:
        parts.append("Yaqin kunlarda o'yin yo'q.")
    parts.append("")
    parts.append("📋 To'liq jadval — rasmda ⬆️")
    parts.append("")
    parts.append(f"#Futbol {_comp_tag(comp)} #Oyinlar")
    return _finish(parts)


def results_caption(date_label, matches, comp="WC") -> str:
    parts = [f"📊 <b>Natijalar</b> — {date_label}", "",
             f"<i>{_comp_name(comp)} · so'nggi o'yinlar</i>", ""]
    shown = [m for m in matches if m.get("home") and m.get("away")][:10]
    for m in shown:
        parts.append(f"⚽ {m['home']} <b>{m.get('hs', '')}:{m.get('as', '')}</b> {m['away']}")
    if not shown:
        parts.append("So'nggi natijalar topilmadi.")
    parts.append("")
    parts.append(f"#Futbol {_comp_tag(comp)} #Natijalar")
    return _finish(parts)


def standings_caption(date_label, groups, comp="WC") -> str:
    grp = f"{len(groups)} ta guruh" if len(groups) > 1 else "ochko jadvali"
    parts = [f"🏆 <b>Turnir jadvali</b> — {date_label}", "",
             f"<i>{_comp_name(comp)} · {grp}</i>", "",
             "📋 To'liq jadval — rasmda ⬆️", "",
             f"#Futbol {_comp_tag(comp)} #Jadval"]
    return _finish(parts)


def goal_caption(m, scorer="", scored="") -> str:
    """GOOOL posti (batafsil): qaysi jamoa, hisob, muallif, daqiqa, guruh."""
    he, ae = m.get("he", ""), m.get("ae", "")
    parts = ["⚽️ <b>GOOOL!</b>", ""]
    if scored:
        parts.append(f"🔥 <b>{scored}</b> gol urdi!")
        parts.append("")
    parts.append(f"{he} <b>{m['home']} {m['hs']} : {m['as']} {m['away']}</b> {ae}".strip())
    if scorer:
        parts.append(f"⚽️ Gol muallifi: <b>{scorer}</b>")
    if m.get("minute"):
        parts.append(f"⏱ {m['minute']}-daqiqa")
    parts.append("🏆 JCH-2026")
    text = "\n".join(p for p in parts if p is not None)
    ch = str(TELEGRAM_CHANNEL).strip()
    if ch.startswith("@"):
        label = html.escape(CHANNEL_NAME or ch, quote=False)
        text += (f"\n\n\U0001F449 <a href=\"https://t.me/{ch[1:]}\">{label}</a>"
                 " · obuna bo'ling \U0001F514")
    return text


def get_match_goals(match_id) -> list:
    """FD match detali -> gollar [{minute, scorer, team}]. Bo'lmasa []."""
    d = _fd(f"/matches/{match_id}") or {}
    out = []
    for g in d.get("goals", []) or []:
        out.append({"minute": g.get("minute"),
                    "scorer": (g.get("scorer") or {}).get("name", ""),
                    "team": (g.get("team") or {}).get("name", "")})
    return out


# ------------------------------------------------------------------ TELEGRAM
def _read_more_button(url):
    """Maqolaga 'To'liq o'qish' inline tugmasi (Telegram knopkasi)."""
    if not url:
        return None
    return {"inline_keyboard": [[{"text": "\U0001F4D6 To‘liq o‘qish", "url": url}]]}


def post_photo(image_path: str, caption: str, reply_markup=None) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

    def _send(cap, html=True):
        data = {"chat_id": TELEGRAM_CHANNEL, "caption": cap}
        if html:
            data["parse_mode"] = "HTML"
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        with open(image_path, "rb") as f:
            return requests.post(url, data=data, files={"photo": f}, timeout=60)

    resp = _send(caption, html=True)
    if not resp.ok:
        # Telegram'ning aniq sababini ko'rsatamiz
        print(f"  Telegram {resp.status_code}: {resp.text}")
        # Ehtimol HTML caption muammosi -> teglarsiz qayta urinamiz
        plain = re.sub(r"<[^>]+>", "", caption)
        resp2 = _send(plain, html=False)
        if not resp2.ok:
            print(f"  Qayta urinish ham xato {resp2.status_code}: {resp2.text}")
            resp2.raise_for_status()


def post_message(text: str, reply_markup=None, link_preview=None) -> None:
    """Matnli post (sendMessage). link_preview -> havola preview/Instant View kartasi."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHANNEL, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    if link_preview is not None:
        data["link_preview_options"] = json.dumps(link_preview)
    resp = requests.post(url, data=data, timeout=30)
    if not resp.ok:
        print(f"  Telegram {resp.status_code}: {resp.text}")
        data2 = {"chat_id": TELEGRAM_CHANNEL, "text": re.sub(r"<[^>]+>", "", text)}
        if link_preview is not None:
            data2["link_preview_options"] = json.dumps(link_preview)
        resp2 = requests.post(url, data=data2, timeout=30)
        if not resp2.ok:
            print(f"  Qayta urinish ham xato {resp2.status_code}: {resp2.text}")
            resp2.raise_for_status()


def post_breaking(item, translate=None, voice=None, focus=None, persona=None) -> bool:
    """Tezkor xabar (toza): rasm tepada + qisqa matn + pastda "Instant View" tugma.

    voice="blog" -> matn bir kishi yuritayotgan shaxsiy blog ovozida qayta yoziladi.
    Tugma telegra.ph IV sahifasini ochadi (to'liq maqola, ichida rasm bilan).
    """
    try:
        title = item["title"] if isinstance(item, dict) else item
        link = item.get("link") if isinstance(item, dict) else None
        desc = _og_desc(link) if link else ""
        if translate == "uz":                 # ruscha/boshqa -> O'zbekcha
            title = translate_to_uz(title)
            if desc:
                desc = translate_to_uz(desc[:300])
        # Tavsif sarlavhaga mazmunan o'xshash bo'lsa -> takrorni olib tashlaymiz.
        # So'zlar ustma-ustligi (token overlap) -> aniq nusxa emas, yaqin takror ham ushlanadi.
        if desc:
            _toks = lambda s: set(re.findall(r"\w+", (s or "").lower()))
            td, tt = _toks(desc), _toks(title)
            if td and tt and len(td & tt) / min(len(td), len(tt)) >= 0.6:
                desc = ""
        body = _article_text(link) if voice == "blog" else ""   # to'liq matn -> batafsilroq
        blog = blogify(title, desc, body, focus or "", persona or "") if voice == "blog" else None
        if blog:
            # Shaxsiy blog ovozi: AI yozgan tabiiy matn (HTML teglarsiz, xavfsiz)
            cap = html.escape(blog, quote=False)
        else:
            # Standart: sarlavha (+ qisqa tavsif)
            cap = f"\u26a1 <b>{html.escape(title, quote=False)}</b>"
            if desc:
                cap += f"\n\n{html.escape(desc[:400], quote=False)}"
        ch = str(TELEGRAM_CHANNEL).strip()
        # Ko'rinadigan matn = chiroyli kanal nomi; havola o'sha kanalga (o'zgarmaydi).
        label = html.escape(CHANNEL_NAME or ch, quote=False)
        if ch.startswith("@") and voice == "blog":
            cap += f"\n\n\u2014 <a href=\"https://t.me/{ch[1:]}\">{label}</a>"
        elif ch.startswith("@"):
            cap += (f"\n\n\U0001F449 <a href=\"https://t.me/{ch[1:]}\">{label}</a>"
                    " \u00b7 obuna bo'ling \U0001F514 \u00b7 ulashing \U0001F4E2")
        # Instant View sahifasi + pastdagi tugma (translate -> ichi ham o'zbekcha)
        iv_url = make_instant_view(item, translate=translate) or link
        button = ({"inline_keyboard": [[{"text": "\u26a1 Instant View", "url": iv_url}]]}
                  if iv_url else None)
        img = fetch_news_image([item], "news_banner.png")
        if img:
            post_photo(img, cap, reply_markup=button)            # rasm tepada
        else:
            post_message(cap, reply_markup=button, link_preview={"is_disabled": True})
        print("Tezkor xabar \u2713")
        return True
    except Exception as e:
        print(f"Tezkor xabar XATO: {e}")
        return False


def post_startup_stats(date_label, focus=None) -> bool:
    """Startupga moslangan kunlik raqamlar: USD/UZS, Bitcoin, Yevro + yengil prognoz.

    Prognoz oxirgi kunlardagi USD tarixidan (prev_stats.json) hisoblanadi -> sof
    taxmin, moliyaviy maslahat emas. Gemini bo'lsa qisqa blog-izoh ham qo'shiladi.
    """
    try:
        _, overview, _ = get_cbu_rates()
        usd = next((r["value"] for r in overview if r["code"] == "USD"), None)
        eur = next((r["value"] for r in overview if r["code"] == "EUR"), None)
        market = get_market_data()
        btc = market.get("btc")
        if not usd and not btc:
            print("Statistika: ma'lumot topilmadi.")
            return False

        st = _load_json("prev_stats.json", {})
        hist = st.get("usd_hist", [])        # [{"d": "YYYY-MM-DD", "v": float}, ...]
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5)))
        today = now.strftime("%Y-%m-%d")
        # kechagi qiymat (bugun yozilgan bo'lsa, undan oldingisini olamiz)
        prev_vals = [h["v"] for h in hist if h.get("d") != today]
        yest_v = prev_vals[-1] if prev_vals else None

        lines = [f"\U0001F4CA <b>Startup uchun raqamlar \u2014 {date_label}</b>", ""]
        if usd:
            chg = ""
            if yest_v:
                d = usd - yest_v
                if abs(d) >= 0.01:
                    arrow = "\u25b2" if d > 0 else "\u25bc"   # f-string {} ichida emas (Py3.11 backslash taqiqi)
                    chg = f"  {arrow} {abs(d):,.0f}".replace(",", " ") + " so'm (kecha)"
            lines.append(f"\U0001F4B5 Dollar (CBU): <b>{_fmt_sum(usd)}</b> so'm{chg}")
        if eur:
            lines.append(f"\U0001F4B6 Yevro: {_fmt_sum(eur)} so'm")
        if btc:
            bchg = btc.get("chg")
            if bchg is not None:
                barrow = "\u25b2" if (bchg or 0) >= 0 else "\u25bc"
                bc = f"  {barrow} {abs(bchg):.1f}% (24s)"
            else:
                bc = ""
            lines.append(f"\U0001FA99 Bitcoin: <b>${_fmt_usd(btc['usd'])}</b>{bc}")

        # --- yengil prognoz (deterministik, USD tarixidan) ---
        forecast = ""
        series = [v for v in ([h["v"] for h in hist[-6:]] + ([usd] if usd else [])) if v]
        if usd and len(series) >= 3:
            deltas = [b - a for a, b in zip(series, series[1:])]
            avg = sum(deltas) / len(deltas)
            nxt = usd + avg
            dirw = ("ko'tarilishi" if avg > 0.5 else
                    "pasayishi" if avg < -0.5 else "barqaror qolishi")
            forecast = (f"\n\n\U0001F4C8 <i>Taxminiy yo'nalish:</i> dollar yaqin kunlarda "
                        f"{dirw} mumkin (\u2248 {_fmt_sum(nxt)} so'm). "
                        f"Bu prognoz \u2014 moliyaviy maslahat emas.")

        body = "\n".join(lines) + forecast

        # --- ixtiyoriy: startup nuqtai nazaridan qisqa blog-izoh (Gemini bo'lsa) ---
        if focus:
            note = llm_text(
                "Quyidagi bugungi raqamlar asosida startap tadbirkorlari uchun 1-2 jumlalik "
                "qisqa, jonli amaliy izoh yoz (xarajat, investitsiya yoki bozor kayfiyati "
                "nuqtai nazaridan). Oddiy matn, HTML yo'q, ko'pi bilan 1 emoji. Faqat izohni "
                "qaytar:\n" + "\n".join(lines), max_tokens=300)
            if note:
                clean = html.escape(note.strip().replace("*", ""), quote=False)
                body += "\n\n" + clean

        ch = str(TELEGRAM_CHANNEL).strip()
        if ch.startswith("@"):
            body += f"\n\n\u2014 <a href=\"https://t.me/{ch[1:]}\">{ch}</a>"

        post_message(body, link_preview={"is_disabled": True})

        # tarix\u043d\u0438 yangilaymiz (kuniga bitta yozuv)
        if usd:
            if hist and hist[-1].get("d") == today:
                hist[-1]["v"] = usd
            else:
                hist.append({"d": today, "v": usd})
            st["usd_hist"] = hist[-14:]
            _save_json("prev_stats.json", st)
        print("Statistika \u2713")
        return True
    except Exception as e:
        print(f"Statistika XATO: {e}")
        return False


# Original blog mavzulari (aylanma) \u2014 yangilikka bog'liq emas, bloggerning o'z fikri.
BLOG_THEMES = [
    "biznes strategiyasi va barqaror o'sish",
    "marketing, brending va mijoz psixologiyasi",
    "shaxsiy rivojlanish, odatlar va o'z ustida ishlash",
    "karyera o'sishi va kasbiy mahorat",
    "munosabatlar, networking va kuchli jamoa qurish",
    "startap yo'li: sinov, xato va saboqlar",
    "ichki kechinmalar va o'z-o'zini anglash (refleksiya)",
    "donolik va hayotiy aqlli fikrlar",
    "motivatsiya, intizom va maqsadga sodiqlik",
    "liderlik va og'ir qarorlar qabul qilish",
    "vaqtni boshqarish, fokus va produktivlik",
    "muvaffaqiyatsizlikni qabul qilish va undan o'sish",
    "moliyaviy savodxonlik va pulni oqilona boshqarish",
    "ijodkorlik va g'oyani amalga aylantirish",
]

# Format xilma-xilligi -> postlar bir xil ko'rinmasin, tirik tuyulsin.
BLOG_FORMATS = [
    "qisqa esse (2-3 abzas), shaxsiy kuzatuv yoki hikoyacha bilan",
    "3-4 ta amaliy maslahat, har biri bitta jonli izoh bilan",
    "bitta kuchli fikr atrofida chuqur mulohaza (2 qisqa abzas)",
    "shaxsiy refleksiya \u2014 'men shuni angladim...' ohangida",
    "bitta hayotiy savol va unga ochiq, samimiy javob",
]


def post_original_blog(focus=None, themes=None, persona=None) -> bool:
    """Yangilikka bog'lanmagan ORIGINAL blog-post (biznes, motivatsiya, refleksiya...).

    persona -> yozuvchining ovozi/identifikatsiyasi (masalan "kitobsevar ziyoli bloger").
    Aylanma mavzu + format; yaqinda ishlatilganini takrorlamaydi (blog_state.json).
    LLM (Gemini->Claude) bo'lmasa -> post yo'q (False), bot davom etadi.
    """
    try:
        pool = themes or BLOG_THEMES
        st = _load_json("blog_state.json", {})
        recent = st.get("recent", [])
        choices = [t for t in pool if t not in recent[-6:]] or pool
        theme = random.choice(choices)
        fmt = random.choice(BLOG_FORMATS)
        who = persona or "tajribali, samimiy bloger"
        focus_line = (f"Kanal yo'nalishi (e'tiborga ol): {focus}\n" if focus else "")
        prompt = (
            f"Sen O'zbek tilida (lotin alifbosida) yozadigan {who}san. "
            "O'quvching \u2014 fikrlaydigan, o'zini rivojlantirishni istagan odamlar.\n"
            f"Bugun '{theme}' mavzusida ORIGINAL post yoz \u2014 hech qaysi yangilikka bog'lanmagan, "
            "faqat o'z fikring va tajribang.\n"
            f"Format: {fmt}.\n"
            "Talablar:\n"
            "- Tirik, insoniy, samimiy ohang; xuddi bir odam o'z kanalida yozayotgandek.\n"
            "- Aniq, foydali va chuqur bo'l; quruq, umumiy iboralardan qoch.\n"
            "- Kuchli birinchi jumla bilan boshla; oxirida kichik xulosa yoki o'ylantiruvchi savol qoldir.\n"
            "- 90-160 so'z. Faqat oddiy matn \u2014 HTML, markdown yoki yulduzcha (*) ishlatma.\n"
            "- 1-3 ta mos emoji bo'lsa bo'ladi, ortiqcha emas.\n"
            "- Sarlavha yoki 'Mavzu:' yozma \u2014 to'g'ridan-to'g'ri post matnini ber.\n"
            + focus_line
        )
        text = llm_text(prompt, max_tokens=900)
        if not text:
            print("Original blog: LLM javob bermadi (Gemini/Claude).")
            return False
        text = text.strip().strip('"').replace("**", "").replace("__", "").replace("*", "").strip()
        body = html.escape(text[:1600], quote=False)
        ch = str(TELEGRAM_CHANNEL).strip()
        if ch.startswith("@"):
            body += f"\n\n\u2014 <a href=\"https://t.me/{ch[1:]}\">{ch}</a>"
        post_message(body, link_preview={"is_disabled": True})
        recent.append(theme)
        st["recent"] = recent[-10:]
        _save_json("blog_state.json", st)
        print(f"Original blog \u2713 ({theme})")
        return True
    except Exception as e:
        print(f"Original blog XATO: {e}")
        return False


def safe_post(render_fn, caption, label):
    """Bitta post xato bersa, butun ishni to'xtatmaydi."""
    try:
        img = render_fn()
        post_photo(img, caption)
        print(f"{label} \u2713")
        return True
    except Exception as e:
        print(f"{label} XATO: {e}")
        return False



# ------------------------------------------------------------------ MAIN
UZ_DAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
UZ_MONTHS = ["", "yanvar", "fevral", "mart", "aprel", "may", "iyun",
             "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]

# Jadval bo'yicha guruhlarning mo'ljal vaqti (Toshkent soati, kasrli). C guruh
# endi tezkor kuzatuvchi (har 15 daqiqa) -> u jadval emas, faol-soat oynasi bilan ishlaydi.
GROUP_TARGET_HOUR = {"A": 7.0, "B": 7.5, "D": 10.0, "M": 11.0,
                     "F": 9.0, "R": 21.0, "S": 22.0, "P": 9.0}   # F=o'yinlar, R=natijalar, S=jadval, P=statistika
# Mo'ljaldan keyin shu qancha soatgacha kechikkan run baribir post tashlaydi.
# GitHub'ning odatdagi kechikishini yutish uchun saxiy, lekin tunni qoplamaydi.
MAX_DELAY_HOURS = 5.0
# Tezkor xabarlar (C guruh) faol bo'ladigan soatlar oynasi (Toshkent). Tunda jim.
NEWS_ACTIVE = (7, 23)


def within_window(group: str, now) -> bool:
    """Run hozir post tashlashga ruxsat etilgan oynadami?

    - AUTO/C (heartbeat/kuzatuvchi): faqat faol soatlarda (07-23) ishlasin.
    - A/B/D (qo'lda aniq guruh): GitHub kechikishi tunga cho'zilsa post chiqmasin.
    """
    if os.environ.get("FORCE_POST"):     # majburiy yuborish (qo'lda test uchun)
        return True
    if group in ("ALL", "G"):            # qo'lda / gol-kuzatuvchi -> doim (gol tunda ham)
        return True
    if group in ("AUTO", "C"):           # heartbeat/tezkor -> faol-soat oynasi
        return NEWS_ACTIVE[0] <= now.hour < NEWS_ACTIVE[1]
    target = GROUP_TARGET_HOUR.get(group)
    if target is None:                   # noma'lum guruh -> to'smaymiz
        return True
    cur = now.hour + now.minute / 60.0   # now -- Toshkent vaqti (UTC+5)
    return target <= cur <= target + MAX_DELAY_HOURS


def _jitter_h(now, key, max_min=40) -> float:
    """Sana+key bo'yicha barqaror tasodifiy ofset (soatda). Post vaqti har kuni
    biroz farq qiladi -> 'aynan bir xil daqiqa' mexanik ko'rinishi yo'qoladi."""
    s = f"{now.strftime('%Y-%m-%d')}|{key}"
    d = int(hashlib.md5(s.encode()).hexdigest(), 16) % (max_min + 1)
    return d / 60.0


def daily_due(group: str, now, daily_state: dict) -> bool:
    """AUTO rejimida: guruh bugun hali chiqmagan va vaqti kelganmi?

    Mo'ljal vaqtidan keyin MAX_DELAY_HOURS ichida birinchi heartbeat post qiladi.
    Boshlanishiga kunlik jitter qo'shiladi (tabiiy, har kuni boshqa daqiqada).
    """
    if daily_state.get(group) == now.strftime("%Y-%m-%d"):
        return False                     # bugun allaqachon chiqarilgan
    target = GROUP_TARGET_HOUR.get(group)
    if target is None:
        return False
    cur = now.hour + now.minute / 60.0
    return target + _jitter_h(now, f"{group}|{CHANNEL_KEY}") <= cur <= target + MAX_DELAY_HOURS


# Kurslar/Dollar kuniga bir necha marta chiqadi (kurs kun davomida o'zgaradi).
D_SLOTS = (9.5, 13.0, 17.0)              # mo'ljal vaqtlari (Toshkent) -> 3 marta
O_SLOTS = (11.5, 19.5)                    # original blog -> kuniga 2 marta (ertalab/kechqurun)
SLOT_WINDOW = 2.0                        # har slot oynasi (slotlar 3.5+ soat oralig'ida -> ustma-ust emas)


def due_multi(group: str, now, daily_state: dict, slots) -> list:
    """Ko'p slotli guruh (D/M...) uchun: bugun hali chiqmagan va vaqti kelgan slot indekslari.

    Holatda har slot alohida belgilanadi: "<group><i>" (mas. "D0", "M1").
    """
    cur = now.hour + now.minute / 60.0
    today = now.strftime("%Y-%m-%d")
    out = []
    for i, slot in enumerate(slots):
        if daily_state.get(f"{group}{i}") == today:
            continue
        if slot + _jitter_h(now, f"{group}{i}|{CHANNEL_KEY}") <= cur <= slot + SLOT_WINDOW:
            out.append(i)
    return out


def run_channel(now, date_label, group, cfg) -> list:
    """Bitta kanal uchun postlarni bajaradi (kontekst _apply_channel orqali o'rnatilgan).

    cfg["groups"] -> shu kanal qaysi turdagi postlarni oladi (A/B/C/D/M)."""
    ch = str(TELEGRAM_CHANNEL)
    groups_on = set(cfg.get("groups", ["A", "B", "C", "D", "M"]))
    slots_cfg = cfg.get("slots", {})        # har-kanal jadval: {"D":[...], "M":[...]}
    today = now.strftime("%Y-%m-%d")
    daily_state = load_daily() if group == "AUTO" else {}

    if group == "AUTO":
        # heartbeat: tezkor (C) doim, kunlik (A/B/F/R/S) bir marta, ko'p slotlilar jadval bo'yicha
        d_slots = slots_cfg.get("D", list(D_SLOTS))   # standart: D kuniga 3 marta
        m_slots = slots_cfg.get("M")                  # bo'lsa M ko'p marta; bo'lmasa kuniga 1
        o_slots = slots_cfg.get("O", list(O_SLOTS))   # original blog: standart kuniga 2 marta
        d_due = due_multi("D", now, daily_state, d_slots) if "D" in groups_on else []
        m_due = due_multi("M", now, daily_state, m_slots) if (m_slots and "M" in groups_on) else []
        o_due = due_multi("O", now, daily_state, o_slots) if "O" in groups_on else []
        due = {g for g in ("A", "B", "F", "R", "S", "P")
               if g in groups_on and daily_due(g, now, daily_state)}
        # M: slotli kanal -> m_due; aks holda kuniga bir marta (daily_due)
        if "M" in groups_on and not m_slots and daily_due("M", now, daily_state):
            due.add("M")
        if m_due:
            due.add("M")
        if "C" in groups_on:
            due.add("C")
        if "G" in groups_on:
            due.add("G")
        if d_due:
            due.add("D")
        if o_due:
            due.add("O")
        print(f"  [{ch}] {now.hour:02d}:{now.minute:02d} -> {sorted(due)}"
              + (f" (D-slot {d_due})" if d_due else "")
              + (f" (M-slot {m_due})" if m_due else "")
              + (f" (O-slot {o_due})" if o_due else ""))

        def want(g):
            return g in due
    else:
        d_due = [0]   # qo'lda: D bir marta
        m_due = [0]   # qo'lda: M bir marta
        o_due = [0]   # qo'lda: original blog bir marta
        def want(g):
            return (group == "ALL" or group == g) and g in groups_on

    results = []
    done_today = []        # AUTO: bugun chiqarilgan kunlik guruhlar (A/B/M)
    state_changed = False  # daily_state o'zgardimi (D slot/saqlash uchun)

    # --- A guruh: Bugun + Kun maslahati ---
    if want("A"):
        day_info = get_day_info(now)
        tip = get_daily_tip(now)
        results.append(safe_post(
            lambda: render_day_card(date_label, day_info["weekday"], day_info["season"],
                                    day_info["day_of_year"], day_info["days_left"],
                                    day_info["week_no"], day_info["holidays"], "p1.png", ch),
            day_caption(date_label, day_info), "Bugun"))
        results.append(safe_post(
            lambda: render_advice_card(date_label, tip["kind"], tip["text"], "p3.png", ch),
            advice_caption(date_label, tip), "Kun maslahati"))
        done_today.append("A")

    # --- B guruh: Ob-havo ---
    if want("B"):
        weather = get_all_weather()
        results.append(safe_post(
            lambda: render_weather_card(date_label, weather, "p4.png", ch),
            weather_caption(date_label, weather), "Ob-havo"))
        done_today.append("B")

    # --- C guruh: Tezkor xabarlar (real-vaqt, faqat yangilarini) ---
    # Manba kanal config'idan: news_preset (business/football) yoki news_feeds/keywords.
    if want("C"):
        preset = NEWS_PRESETS.get(cfg.get("news_preset", "business"), NEWS_PRESETS["business"])
        feeds = cfg.get("news_feeds", preset["feeds"])
        kw = cfg.get("news_keywords", preset["keywords"])
        translate = cfg.get("translate")      # masalan "uz" -> ruscha sarlavhani tarjima
        voice = cfg.get("voice")              # "blog" -> ma'lumotli post ovozida qayta yozish
        focus = cfg.get("voice_focus")        # blog uchun qo'shimcha yo'nalish/urg'u (marketing, psixologiya...)
        persona = cfg.get("voice_persona")    # kim yozayotgani (mas. "sport jurnalisti")
        news = get_news(feeds, kw, limit=10)
        block = [w.lower() for w in cfg.get("news_block", [])]   # reklama/begona sarlavhalarni kesish
        if block:
            news = [it for it in news
                    if not any(w in (it.get("title") or "").lower() for w in block)]
        posted = load_posted()
        seen = set(posted)
        fresh = [it for it in news if _news_key(it) and _news_key(it) not in seen]
        fresh = fresh[:MAX_ALERTS]
        if not fresh:
            print("Yangi xabar yo'q (takror oldini olindi).")
        for it in fresh:
            ok = post_breaking(it, translate=translate, voice=voice, focus=focus, persona=persona)
            results.append(ok)
            if ok:
                posted.append(_news_key(it))
        if fresh:
            save_posted(posted)

    # --- P guruh: Startup uchun statistika (USD, Bitcoin, Yevro + yengil prognoz) ---
    if want("P"):
        results.append(post_startup_stats(date_label, focus=cfg.get("voice_focus")))
        done_today.append("P")

    # --- O guruh: Original blog (yangilikka bog'liq emas — biznes, motivatsiya, ...) ---
    if want("O"):
        results.append(post_original_blog(focus=cfg.get("voice_focus"),
                                          themes=cfg.get("blog_themes"),
                                          persona=cfg.get("voice_persona")))
        if group == "AUTO":
            for i in o_due:
                daily_state[f"O{i}"] = today
            state_changed = True

    # --- G guruh: real-vaqt GOLLAR (jonli o'yinlarda hisob o'zgarsa GOOOL post) ---
    if want("G"):
        live = get_live()
        prev = _load_json("live_scores.json", {})
        new_prev = {}
        for m in live:
            k = str(m.get("id"))
            cur_sum = (m["hs"] or 0) + (m["as"] or 0)
            new_prev[k] = {"sum": cur_sum, "s": f"{m['hs']}-{m['as']}"}
            old = prev.get(k)
            # birinchi ko'rishda jim (mavjud hisobni e'lon qilmaymiz); keyin gol bo'lsa post
            if old is not None and cur_sum > old.get("sum", 0):
                try:
                    # qaysi jamoa gol urdi (eski hisob bilan solishtirib)
                    oh, oa = (old.get("s", "0-0").split("-") + ["0", "0"])[:2]
                    scored = m["home"] if m["hs"] > int(oh or 0) else m["away"]
                    # gol muallifi (FD detalidan, bo'lsa)
                    scorer = ""
                    gs = get_match_goals(m.get("id"))
                    if gs:
                        scorer = gs[-1].get("scorer", "")
                        if gs[-1].get("minute"):
                            m["minute"] = gs[-1]["minute"]
                    # tayyor GOOOL rasmi (assets/goal.*) bo'lsa shuni, bo'lmasa rendered karta
                    fixed = next((p for p in (
                        os.path.join(HERE, "assets", "goal.png"),
                        os.path.join(HERE, "assets", "goal.jpg")) if os.path.exists(p)), None)
                    img = fixed or render_goal_card(m, "p11.png", ch)
                    post_photo(img, goal_caption(m, scorer=scorer, scored=scored))
                    print(f"GOOOL ✓ {m['home']} {m['hs']}-{m['as']} {m['away']}")
                    results.append(True)
                except Exception as e:
                    print("Gol post xato:", e)
                    results.append(False)
        _save_json("live_scores.json", new_prev)

    # --- D guruh: Kurslar + Dollar (kuniga 3 marta; kurs kun davomida o'zgaradi) ---
    if want("D"):
        cbu_text, overview, _ = get_cbu_rates()
        banks = get_bank_rates()
        prev_rates = load_prev_rates()                 # kechagi kurslar (o'zgarish uchun)
        prev_usd = prev_rates.get("USD")
        usd_value = next((r["value"] for r in overview if r["code"] == "USD"), None)
        ok_rates = safe_post(
            lambda: render_currency_overview_card(date_label, overview, "p5.png", ch, prev_rates),
            currency_overview_caption(date_label, overview), "Kurslar")
        results.append(ok_rates)
        results.append(safe_post(
            lambda: render_currency_card(date_label, cbu_text, banks, "p6.png", ch,
                                         usd_value=usd_value, prev_usd=prev_usd),
            currency_caption(date_label, cbu_text, banks), "Dollar"))
        # O'zgarish (▲/▼) doim KECHA bilan solishtirilsin -> kurslarni kuniga faqat
        # birinchi postda saqlaymiz (keyingi 2 post o'sha kungi kecha bilan taqqoslaydi).
        if ok_rates and daily_state.get("Dsaved") != today:
            save_prev_rates({r["code"]: r["value"] for r in overview})
            daily_state["Dsaved"] = today
            state_changed = True
        if group == "AUTO":
            for i in d_due:
                daily_state[f"D{i}"] = today
            state_changed = True

    # --- M guruh: Bozor (oltin + Bitcoin) ---
    if want("M"):
        m = get_market_data()
        prev_m = load_prev_market()
        rows = market_rows(m, prev_m.get("gold"))
        if rows:
            ok_m = safe_post(
                lambda: render_market_card(date_label, rows, "p7.png", ch),
                market_caption(date_label, rows), "Bozor")
            results.append(ok_m)
            if ok_m and m.get("gold"):
                save_prev_market({"gold": m["gold"]})
        else:
            print("Bozor ma'lumoti topilmadi.")
        if group == "AUTO":
            if m_due:                      # slotli kanal -> har slotni alohida belgilaymiz
                for i in m_due:
                    daily_state[f"M{i}"] = today
                state_changed = True
            else:
                done_today.append("M")     # kuniga bir marta

    # Kanal qaysi turnirlar bo'yicha (JCH + klublar). Standart: faqat JCH.
    comps = cfg.get("competitions", ["WC"])

    # --- F guruh: yaqin o'yinlar (har turnir; faqat o'yini borlari chiqadi) ---
    if want("F"):
        for comp in comps:
            fx = get_fixtures(10, comp=comp, soon_hours=30)
            if not fx:
                continue
            cn = _comp_name(comp)
            results.append(safe_post(
                lambda fx=fx, cn=cn: render_fixtures_card(date_label, fx, "p8.png", ch, comp=cn),
                fixtures_caption(date_label, fx, comp), f"O'yinlar ({cn})"))
        done_today.append("F")

    # --- R guruh: so'nggi natijalar (har turnir; faqat natijasi borlari chiqadi) ---
    if want("R"):
        for comp in comps:
            res = get_results(10, comp=comp, recent_hours=30)
            if not res:
                continue
            cn = _comp_name(comp)
            results.append(safe_post(
                lambda res=res, cn=cn: render_results_card(date_label, res, "p9.png", ch, comp=cn),
                results_caption(date_label, res, comp), f"Natijalar ({cn})"))
        done_today.append("R")

    # --- S guruh: turnir jadvali (har turnir; jadvali borlari chiqadi) ---
    if want("S"):
        for comp in comps:
            st = get_standings(comp=comp)
            if not st:
                continue
            cn = _comp_name(comp)
            results.append(safe_post(
                lambda st=st, cn=cn: render_standings_card(date_label, st, "p10.png", ch, comp=cn),
                standings_caption(date_label, st, comp), f"Jadval ({cn})"))
        done_today.append("S")

    # AUTO rejimida: bugun chiqarilganlarni belgilab qo'yamiz (qayta chiqmasin)
    if group == "AUTO" and (done_today or state_changed):
        for g in done_today:
            daily_state[g] = today
        save_daily(daily_state)
    return results


def main() -> None:
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5)))
    date_label = f"{now.day}-{UZ_MONTHS[now.month]}"   # qisqa: yil/hafta kuni yo'q
    # POST_GROUP: AUTO (heartbeat har 15 daq) | A/B/C/D/M | ALL (qo'lda test)
    group = os.environ.get("POST_GROUP", "all").strip().upper() or "ALL"

    # LLM diagnostikasi (faqat qo'lda/FORCE run) -> blog ovozi ishlayaptimi log'da aniq ko'rinadi.
    if os.environ.get("FORCE_POST"):
        print(f"LLM kalitlari: GEMINI={'bor' if GEMINI_API_KEY else 'yoq'} "
              f"(modellar: {', '.join(GEMINI_MODELS)}) | ANTHROPIC={'bor' if client else 'yoq'}")
        _t = llm_text("Faqat 'OK' deb javob yoz.", max_tokens=5)
        print("LLM SINOV: " + ("✅ ishladi -> " + repr(_t) if _t
                                else "❌ ISHLAMADI (yuqorida 'Gemini ...' xato qatoriga qarang)"))

    # Darvoza: faol oynadan tashqarida (tunda) -> hech kanalga post yo'q. Xato emas (exit 0).
    if not within_window(group, now):
        print(f"Guruh {group}: faol oynadan tashqarida ({now.hour:02d}:{now.minute:02d} "
              f"Toshkent). Post yo'q. Majburlash: FORCE_POST=1.")
        return

    channels = load_channels()
    # ONLY_CHANNEL berilsa -> faqat shu kanal(lar)da post (qo'lda test uchun, masalan @Startupnews...).
    only = os.environ.get("ONLY_CHANNEL", "").strip().lstrip("@").lower()
    if only:
        channels = [c for c in channels if only in str(c.get("channel", "")).lstrip("@").lower()]
        print(f"Filtr ONLY_CHANNEL='{only}' -> {len(channels)} kanal")
    print(f"Guruh {group} | Kanallar soni: {len(channels)}")
    results = []
    for cfg in channels:
        try:
            _apply_channel(cfg)
            results += run_channel(now, date_label, group, cfg)
        except Exception as e:
            print(f"Kanal {cfg.get('channel')} XATO: {e}")

    ok = sum(results)
    print(f"\nGuruh: {group} | Jami natija: {ok}/{len(results)} post yuborildi.")
    if results and ok < len(results):
        import sys
        sys.exit(1)


if __name__ == "__main__":
    main()
