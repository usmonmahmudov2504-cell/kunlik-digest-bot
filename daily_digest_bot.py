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
    return {"code": code, "name": CCY_NAMES.get(code, code), "unit": unit, "rate": _fmt_sum(rate)}


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
BIZ_KW = ["biznes", "iqtisod", "soliq", "valyuta", "eksport", "import", "investitsiya",
          "bank", "byudjet", "narx", "tarif", "kredit", "savdo", "bozor", "kompaniya",
          "infl", "foiz", "ishlab chiqar", "tadbirkor", "iqtisodiy", "pul", "aksiya"]


def get_business_news(limit: int = 5) -> list[str]:
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
            if all_biz or any(k in title.lower() for k in BIZ_KW):
                biz.append(title)
            else:
                other.append(title)
    result = biz[:limit]
    if len(result) < limit:                # yetmasa, umumiy bilan to'ldiramiz
        result += other[: limit - len(result)]
    return result


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


def weather_caption(date_label, weather) -> str:
    """Ob-havo posti uchun elegant, emoji bilan caption (barcha viloyatlar)."""
    parts = [f"\U0001F326\ufe0f <b>Ob-havo</b> \u2014 {date_label}", ""]
    for region, (temp, desc) in weather.items():
        parts.append(f"{_wx_emoji(desc)} {region} \u2014 <b>{round(temp)}\u00b0</b>  <i>{desc}</i>")
    parts.append("")
    parts.append("Hammaga xayrli kun! \u2600\ufe0f")
    return "\n".join(parts)[:1024]


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
    return text[:1024]


def business_caption(date_label, headlines) -> str:
    """2-post: biznes yangiliklari caption."""
    parts = [f"\U0001F4BC <b>Biznes ma'lumotlari</b> \u2014 {date_label}", ""]
    if headlines:
        for i, h in enumerate(headlines[:6], 1):
            parts.append(f"<b>{i}.</b> {h}")
    else:
        parts.append("<i>Bugun biznes yangiligi topilmadi.</i>")
    parts.append("")
    parts.append("\U0001F4E2 Batafsil \u2014 manbalarda")
    return "\n".join(parts)[:1024]


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
    return "\n".join(parts)[:1024]


def advice_caption(date_label, tip) -> str:
    """6-post: kun maslahati/hikmati caption."""
    kind = tip.get("kind", "Maslahat")
    icon = "\U0001F4A1" if kind == "Maslahat" else "\u2728"
    label = "Kun maslahati" if kind == "Maslahat" else "Kun hikmati"
    parts = [f"{icon} <b>{label}</b> \u2014 {date_label}", ""]
    parts.append(f"\u00ab{tip['text']}\u00bb")
    parts.append("")
    parts.append("Kuningiz unumli o'tsin! \U0001F4AA")
    return "\n".join(parts)[:1024]


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
    budget = 1024 - len(head_text) - len(tail_text) - 30
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
    return text[:1024]


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


def main() -> None:
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5)))
    date_label = f"{now.day}-{UZ_MONTHS[now.month]}, {now.year} \u00b7 {UZ_DAYS[now.weekday()]}"
    ch = str(TELEGRAM_CHANNEL)

    # Ma'lumotlarni yig'amiz
    day_info = get_day_info(now)
    business = get_business_news()
    weather = get_all_weather()
    cbu_text, overview, extra_rates = get_cbu_rates()
    banks = get_bank_rates()
    tip = get_daily_tip(now)

    print(f"Bugun: {len(day_info['holidays'])} bayram | Biznes: {len(business)} | "
          f"Ob-havo: {len(weather)} viloyat | Valyuta: {len(overview)} | Banklar: {len(banks)}")

    results = []
    # 1-POST: Bugun
    results.append(safe_post(
        lambda: render_day_card(date_label, day_info["weekday"], day_info["season"],
                                day_info["day_of_year"], day_info["days_left"],
                                day_info["week_no"], day_info["holidays"], "p1.png", ch),
        day_caption(date_label, day_info), "1/6 Bugun"))

    # 2-POST: Biznes
    results.append(safe_post(
        lambda: render_news_card("Biznes", date_label, business, "p2.png", ch,
                                 "Manba: spot.uz, kun.uz, daryo.uz"),
        business_caption(date_label, business), "2/6 Biznes"))

    # 3-POST: Kun maslahati
    results.append(safe_post(
        lambda: render_advice_card(date_label, tip["kind"], tip["text"], "p3.png", ch),
        advice_caption(date_label, tip), "3/6 Kun maslahati"))

    # 4-POST: Ob-havo
    results.append(safe_post(
        lambda: render_weather_card(date_label, weather, "p4.png", ch),
        weather_caption(date_label, weather), "4/6 Ob-havo"))

    # 5-POST: Umumiy kurslar
    results.append(safe_post(
        lambda: render_currency_overview_card(date_label, overview, "p5.png", ch),
        currency_overview_caption(date_label, overview), "5/6 Kurslar"))

    # 6-POST: Dollar batafsil
    results.append(safe_post(
        lambda: render_currency_card(date_label, cbu_text, banks, "p6.png", ch),
        currency_caption(date_label, cbu_text, banks), "6/6 Dollar"))

    ok = sum(results)
    print(f"\nNatija: {ok}/6 post yuborildi.")
    if ok < len(results):
        import sys
        sys.exit(1)


if __name__ == "__main__":
    main()
