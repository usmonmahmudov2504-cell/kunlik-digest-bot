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
import datetime
import requests
import feedparser
from bs4 import BeautifulSoup

from render_card import (
    render_day_card, render_news_card, render_weather_card,
    render_currency_overview_card, render_currency_card, render_advice_card,
)

# API kaliti IXTIYORIY. Bo'lsa -> Claude jonli caption yozadi.
# Bo'lmasa -> oddiy shablon ishlatiladi (bepul, hammasi baribir ishlaydi).
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHANNEL = os.environ["TELEGRAM_CHANNEL"]

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


def get_business_news(limit: int = 5) -> list[dict]:
    """Biznes sarlavhalarini {"title","link"} ko'rinishida qaytaradi.

    link -- maqola manzili; undan keyinroq banner rasmi (og:image) olinadi.
    """
    biz, other, seen = [], [], set()
    for url, all_biz in BUSINESS_FEEDS:
        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            print(f"Biznes RSS xato ({url}): {e}")
            continue
        for e in parsed.entries[:15]:
            title = (e.get("title") or "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            item = {"title": title, "link": e.get("link", "")}
            if all_biz or any(k in title.lower() for k in BIZ_KW):
                biz.append(item)
            else:
                other.append(item)
    result = biz[:limit]
    if len(result) < limit:                # yetmasa, umumiy bilan to'ldiramiz
        result += other[: limit - len(result)]
    return result


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


# ------------------------------------------------------------------ TEZKOR XABAR (holat)
# Allaqachon post qilingan xabarlar ro'yxati shu faylda saqlanadi (takror oldini olish).
# GitHub Actions har ish oxirida bu faylni repoga commit qiladi.
_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "posted_news.json")
MAX_ALERTS = 2        # bitta ishda ko'pi bilan necha yangi xabar post qilinadi
STATE_KEEP = 200      # holatda saqlanadigan oxirgi yozuvlar soni


def _news_key(item: dict) -> str:
    return (item.get("link") or item.get("title") or "").strip()


def load_posted() -> list[str]:
    try:
        with open(_STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_posted(keys: list[str]) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(keys[-STATE_KEEP:], f, ensure_ascii=False, indent=0)
    except Exception as e:
        print("Holatni saqlashda xato:", e)


# Kunlik postlar (A/B/D) qaysi sanada chiqarilganini saqlaydi (kuniga bir marta).
_DAILY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "posted_daily.json")


def load_daily() -> dict:
    try:
        with open(_DAILY_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_daily(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_DAILY_PATH), exist_ok=True)
        with open(_DAILY_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=0)
    except Exception as e:
        print("Kunlik holatni saqlashda xato:", e)


# Oldingi (kechagi) rasmiy kurslar -> kunlik o'zgarishni (▲/▼) hisoblash uchun.
_RATES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "prev_rates.json")


def load_prev_rates() -> dict:
    try:
        with open(_RATES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_prev_rates(rates: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_RATES_PATH), exist_ok=True)
        with open(_RATES_PATH, "w", encoding="utf-8") as f:
            json.dump(rates, f, ensure_ascii=False, indent=0)
    except Exception as e:
        print("Kurs holatini saqlashda xato:", e)


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
    """Har post tagiga bosiladigan kanal havolasi."""
    ch = str(TELEGRAM_CHANNEL).strip()
    if ch.startswith("@"):
        uname = ch[1:]
        return f'\n\n\U0001F449 <a href="https://t.me/{uname}">{ch}</a>'
    return ""


def _append_footer(text: str) -> str:
    footer = _channel_footer()
    return (text[:1024 - len(footer)] + footer) if footer else text[:1024]


def _finish(parts) -> str:
    """Caption qatorlarini yig'ib, kanal havolasini qo'shadi (limit ichida)."""
    return _append_footer("\n".join(parts))


def weather_caption(date_label, weather) -> str:
    """Ob-havo posti uchun elegant, emoji bilan caption (barcha viloyatlar)."""
    parts = [f"\U0001F326\ufe0f <b>Ob-havo</b> \u2014 {date_label}", ""]
    for region, (temp, desc) in weather.items():
        parts.append(f"{_wx_emoji(desc)} {region} \u2014 <b>{round(temp)}\u00b0</b>  <i>{desc}</i>")
    parts.append("")
    parts.append("Hammaga xayrli kun! \u2600\ufe0f")
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

    if client is not None:                 # B rejimi: kalit bo'lsa Claude boyitadi
        try:
            hol = ", ".join(info["holidays"]) or "maxsus bayram yo'q"
            prompt = (
                f"Bugun {date_label}, {info['weekday']}, {info['season']} fasli. "
                f"Bayram/sana: {hol}. Telegram 'Bugun qanaqa kun' posti uchun QISQA, "
                "qiziqarli caption yoz (o'zbekcha, Telegram HTML faqat <b>, 600 belgidan kam). "
                "Tuzilishi: emoji bilan sarlavha; sana/fasl; agar bayram bo'lsa u haqida 1 jumla "
                "qiziqarli fakt; oxirida xayrli kun tilagi. Faqat matnni qaytar."
            )
            resp = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text").strip() or text
        except Exception as e:
            print("Claude caption xato (bugun):", e)
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


def breaking_caption(date_label, item) -> str:
    """Tezkor (real-vaqt) bitta biznes xabari uchun caption."""
    title = item["title"] if isinstance(item, dict) else item
    parts = [f"\U0001F534 <b>Tezkor xabar</b> \u2014 biznes", "",
             f"<b>{title}</b>", "",
             f"<i>{date_label}</i>",
             "\U0001F4E2 Batafsil \u2014 manbalarda"]
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
    return _finish(parts)


def advice_caption(date_label, tip) -> str:
    """6-post: kun maslahati/hikmati caption."""
    kind = tip.get("kind", "Maslahat")
    icon = "\U0001F4A1" if kind == "Maslahat" else "\u2728"
    label = "Kun maslahati" if kind == "Maslahat" else "Kun hikmati"
    parts = [f"{icon} <b>{label}</b> \u2014 {date_label}", ""]
    parts.append(f"\u00ab{tip['text']}\u00bb")
    parts.append("")
    parts.append("Kuningiz unumli o'tsin! \U0001F4AA")
    return _finish(parts)


def currency_caption(date_label, cbu_rate, banks, extra_rates=None) -> str:
    """Dollar kursi posti uchun elegant, tartibli caption (monospace jadval)."""
    extra_rates = extra_rates or []
    valid = [b for b in banks if b.get("buy") and b.get("sell")]
    best_sell = min(valid, key=lambda b: b["sell"], default=None)
    best_buy = max(valid, key=lambda b: b["buy"], default=None)

    head = [f"\U0001F4B5 <b>Dollar kursi</b> \u2014 {date_label}", ""]
    head.append(f"\U0001F3E6 Markaziy bank (rasmiy): <b>{cbu_rate}</b>")
    head.append("")
    if best_buy and best_sell:
        head.append("\U0001F7E2 <b>Sotmoqchilarga</b> \u2014 eng qimmat oladi:")
        head.append(f"   {best_buy['bank']} \u00b7 <b>{best_buy['buy']:,}</b> so'm".replace(",", " "))
        head.append("\U0001F535 <b>Olmoqchilarga</b> \u2014 eng arzon sotadi:")
        head.append(f"   {best_sell['bank']} \u00b7 <b>{best_sell['sell']:,}</b> so'm".replace(",", " "))
        head.append("")
    head.append("\U0001F4CA <b>Banklar</b> (olish / sotish):")
    head_text = "\n".join(head)

    # Boshqa valyutalar (oxirida)
    flags = {"EUR": "\U0001F1EA\U0001F1FA", "RUB": "\U0001F1F7\U0001F1FA",
             "GBP": "\U0001F1EC\U0001F1E7", "KZT": "\U0001F1F0\U0001F1FF",
             "CNY": "\U0001F1E8\U0001F1F3"}
    tail = []
    if extra_rates:
        tail.append("")
        tail.append("\U0001F4B6 <b>Boshqa valyutalar</b> (rasmiy):")
        pairs = [f"{flags.get(e['code'], '')} {e['code']} {e['rate']}" for e in extra_rates]
        # ikkitadan qatorga
        for i in range(0, len(pairs), 2):
            tail.append("   ".join(pairs[i:i + 2]))
    tail.append("")
    tail.append("To'liq jadval rasmda \u2b06\ufe0f")
    tail_text = "\n".join(tail)

    # Monospace jadval (raqamlar ustun bo'lib tekislanadi)
    NAME_W = 14
    budget = 1024 - len(head_text) - len(tail_text) - len(_channel_footer()) - 30
    rows, used = [], 0
    for b in valid:
        nm = html.escape(b["bank"][:NAME_W])
        row = f"{nm:<{NAME_W}}{b['buy']:>6}{b['sell']:>7}"
        block = "<pre>" + "\n".join(rows + [row]) + "</pre>"
        if len(block) > budget:
            break
        rows.append(row)
        used += 1
    table = "<pre>" + "\n".join(rows) + "</pre>" if rows else ""
    remainder = ""
    if used < len(valid):
        remainder = f"\n\u2022 <i>yana {len(valid) - used} ta bank \u2014 rasmda</i>"

    text = head_text + "\n" + table + remainder + "\n" + tail_text
    return _append_footer(text)


# ------------------------------------------------------------------ TELEGRAM
def post_photo(image_path: str, caption: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

    def _send(cap, html=True):
        data = {"chat_id": TELEGRAM_CHANNEL, "caption": cap}
        if html:
            data["parse_mode"] = "HTML"
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
GROUP_TARGET_HOUR = {"A": 7.0, "B": 7.5, "D": 10.0}
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
    if group == "ALL":                   # qo'lda ishga tushirish -> doim chiqsin
        return True
    if group in ("AUTO", "C"):           # heartbeat/tezkor -> faol-soat oynasi
        return NEWS_ACTIVE[0] <= now.hour < NEWS_ACTIVE[1]
    target = GROUP_TARGET_HOUR.get(group)
    if target is None:                   # noma'lum guruh -> to'smaymiz
        return True
    cur = now.hour + now.minute / 60.0   # now -- Toshkent vaqti (UTC+5)
    return target <= cur <= target + MAX_DELAY_HOURS


def daily_due(group: str, now, daily_state: dict) -> bool:
    """AUTO rejimida: guruh bugun hali chiqmagan va vaqti kelganmi?

    Mo'ljal vaqtidan keyin MAX_DELAY_HOURS ichida birinchi heartbeat post qiladi.
    Bitta aniq cron o'rniga 15 daqiqalik urinishlar -> GitHub kechikishiga chidamli.
    """
    if daily_state.get(group) == now.strftime("%Y-%m-%d"):
        return False                     # bugun allaqachon chiqarilgan
    target = GROUP_TARGET_HOUR.get(group)
    if target is None:
        return False
    cur = now.hour + now.minute / 60.0
    return target <= cur <= target + MAX_DELAY_HOURS


def main() -> None:
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5)))
    date_label = f"{now.day}-{UZ_MONTHS[now.month]}, {now.year} \u00b7 {UZ_DAYS[now.weekday()]}"
    ch = str(TELEGRAM_CHANNEL)

    # POST_GROUP rejimlari:
    #   AUTO = heartbeat (har 15 daq): vaqti kelgan kunlik postlar (A/B/D) + tezkor (C).
    #          Aniq cron'ga ishonmaydi -> GitHub kechikishiga chidamli.
    #   A = Bugun + Kun maslahati (~07:00) | B = Ob-havo (~07:30)
    #   C = Tezkor biznes xabarlari       | D = Kurslar + Dollar (~10:00)
    #   ALL = hammasi (qo'lda test)
    group = os.environ.get("POST_GROUP", "all").strip().upper() or "ALL"

    # Darvoza: faol oynadan tashqarida (masalan tunda) post tashlamaymiz. Xato emas -> exit 0.
    if not within_window(group, now):
        clock = f"{now.hour:02d}:{now.minute:02d}"
        print(f"Guruh {group}: faol oynadan tashqarida (hozir {clock} "
              f"Toshkent). Post tashlanmadi. Majburlash uchun FORCE_POST=1.")
        return

    today = now.strftime("%Y-%m-%d")
    daily_state = load_daily() if group == "AUTO" else {}

    if group == "AUTO":
        # heartbeat: tezkor (C) doim, kunlik (A/B/D) faqat vaqti kelganda va bugun chiqmagan bo'lsa
        due = {"C"} | {g for g in ("A", "B", "D") if daily_due(g, now, daily_state)}
        print(f"AUTO (hozir {now.hour:02d}:{now.minute:02d}) -> chiqariladigan: {sorted(due)}")

        def want(g):
            return g in due
    else:
        def want(g):
            return group == "ALL" or group == g

    results = []
    done_today = []   # AUTO rejimida bugun chiqarilgan kunlik guruhlar

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

    # --- C guruh: Tezkor biznes xabarlari (real-vaqt, faqat yangilarini) ---
    if want("C"):
        business = get_business_news(limit=10)
        posted = load_posted()
        seen = set(posted)
        fresh = [it for it in business if _news_key(it) and _news_key(it) not in seen]
        fresh = fresh[:MAX_ALERTS]
        if not fresh:
            print("Yangi biznes xabar yo'q (takror oldini olindi).")
        for it in fresh:
            banner = fetch_news_image([it], "news_banner.png")
            ok = safe_post(
                lambda it=it, banner=banner: render_news_card(
                    "Biznes", date_label, [it], "p2.png", ch,
                    "Manba: spot.uz, kun.uz, daryo.uz", banner),
                breaking_caption(date_label, it), "Tezkor xabar")
            results.append(ok)
            if ok:
                posted.append(_news_key(it))
        if fresh:
            save_posted(posted)

    # --- D guruh: Kurslar + Dollar ---
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
        # bugungi kurslarni keyingi kun uchun saqlaymiz (kurslar posti chiqqan bo'lsa)
        if ok_rates:
            save_prev_rates({r["code"]: r["value"] for r in overview})
        done_today.append("D")

    # AUTO rejimida: bugun chiqarilgan kunlik guruhlarni belgilab qo'yamiz (qayta chiqmasin)
    if group == "AUTO" and done_today:
        for g in done_today:
            daily_state[g] = today
        save_daily(daily_state)

    ok = sum(results)
    print(f"\nGuruh: {group} | Natija: {ok}/{len(results)} post yuborildi.")
    # Faqat haqiqiy post xatosi bo'lsa 1 bilan chiqamiz. Hech post bo'lmasligi
    # (masalan tezkor kuzatuvchida yangi xabar yo'qligi) -> normal holat (exit 0).
    if results and ok < len(results):
        import sys
        sys.exit(1)


if __name__ == "__main__":
    main()
