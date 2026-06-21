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
import datetime
import requests
import feedparser
from bs4 import BeautifulSoup

from render_card import render_weather_card, render_currency_card

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
# Qo'shimcha valyutalar (rasmiy kurs). USD alohida, yuqorida ko'rsatiladi.
EXTRA_CCY = ["EUR", "RUB", "GBP", "KZT", "CNY"]
CCY_NAMES = {"EUR": "Yevro", "RUB": "Rubl", "GBP": "Funt sterling",
             "KZT": "Tenge", "CNY": "Yuan"}


def _fmt_sum(rate: float) -> str:
    return f"{rate:,.2f}".replace(",", " ").replace(".", ",")


def get_cbu_rates() -> tuple[str, list[dict]]:
    """CBU'dan barcha valyutalarni bitta so'rovda oladi.

    Qaytaradi: (USD matni, [boshqa valyutalar ro'yxati]).
    Har bir element: {"code", "name", "unit", "rate"}.
    """
    url = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"
    data = requests.get(url, headers=UA, timeout=15).json()
    by = {item.get("Ccy"): item for item in data}

    usd_rate = float(by["USD"]["Rate"]) if "USD" in by else 0.0
    usd_text = f"{_fmt_sum(usd_rate)} so'm"

    extras: list[dict] = []
    for code in EXTRA_CCY:
        it = by.get(code)
        if not it:
            continue
        rate = float(it["Rate"])
        nominal = str(it.get("Nominal", "1")).strip() or "1"
        unit = f"{nominal} {code}" if nominal != "1" else f"1 {code}"
        extras.append({
            "code": code,
            "name": CCY_NAMES.get(code, code),
            "unit": unit,
            "rate": _fmt_sum(rate),
        })
    return usd_text, extras


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


def weather_caption(date_label, weather, news) -> str:
    """Ob-havo posti uchun elegant, emoji bilan caption (barcha viloyatlar)."""
    parts = [f"\U0001F326\ufe0f <b>Ob-havo</b> \u2014 {date_label}", ""]
    for region, (temp, desc) in weather.items():
        parts.append(f"{_wx_emoji(desc)} {region} \u2014 <b>{round(temp)}\u00b0</b>  <i>{desc}</i>")
    if news:
        parts.append("")
        parts.append("\U0001F4F0 <b>Kunning yangiliklari</b>")
        parts += [f"\u2022 {h}" for h in news[:4]]
    parts.append("")
    parts.append("Hammaga xayrli kun! \u2600\ufe0f")
    text = "\n".join(parts)
    return text[:1024]


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
    with open(image_path, "rb") as f:
        resp = requests.post(
            url,
            data={"chat_id": TELEGRAM_CHANNEL, "caption": caption, "parse_mode": "HTML"},
            files={"photo": f},
            timeout=30,
        )
    resp.raise_for_status()


# ------------------------------------------------------------------ MAIN
UZ_DAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
UZ_MONTHS = ["", "yanvar", "fevral", "mart", "aprel", "may", "iyun",
             "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]


def main() -> None:
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5)))
    date_label = f"{now.day}-{UZ_MONTHS[now.month]}, {now.year} \u00b7 {UZ_DAYS[now.weekday()]}"

    weather = get_all_weather()
    cbu_text, extra_rates = get_cbu_rates()
    banks = get_bank_rates()
    news = get_top_news()

    print(f"Ob-havo: {len(weather)} viloyat | Banklar: {len(banks)} | "
          f"Qo'shimcha valyuta: {len(extra_rates)} | Yangilik: {len(news)}")

    ch = str(TELEGRAM_CHANNEL)

    # 1-POST: ob-havo
    w_img = render_weather_card(date_label, weather, "weather.png", ch)
    post_photo(w_img, weather_caption(date_label, weather, news))
    print("Ob-havo posti yuborildi.")

    # 2-POST: dollar + boshqa valyutalar
    c_img = render_currency_card(date_label, cbu_text, banks, "currency.png", ch,
                                 extra_rates=extra_rates)
    post_photo(c_img, currency_caption(date_label, cbu_text, banks, extra_rates))
    print("Dollar kursi posti yuborildi.")


if __name__ == "__main__":
    main()
