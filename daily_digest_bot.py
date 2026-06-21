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
def get_cbu_usd() -> tuple[str, float]:
    """Markaziy bankning rasmiy USD/UZS kursini qaytaradi (matn, son)."""
    url = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/"
    data = requests.get(url, headers=UA, timeout=15).json()
    rate = float(data[0]["Rate"])
    pretty = f"{rate:,.2f}".replace(",", " ").replace(".", ",")
    return f"{pretty} so'm", rate


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
def weather_caption(date_label, weather, news) -> str:
    """Ob-havo posti uchun caption (yangiliklar shu yerda)."""
    tashkent = weather.get("Toshkent sh.")
    parts = [f"\U0001F324 <b>Ob-havo</b> \u2014 {date_label}", ""]
    if tashkent:
        parts.append(f"Toshkent: <b>{round(tashkent[0])}\u00b0C</b>, {tashkent[1]}")
        parts.append("")
    if news:
        parts.append("<b>Kunning yangiliklari</b>")
        parts += [f"\u2022 {h}" for h in news]
        parts.append("")
    parts.append("Hammaga xayrli kun! \u2600")

    text = "\n".join(parts)
    # Kalit bo'lsa, Claude jonliroq qilib yozadi
    if client is not None:
        try:
            news_list = "\n".join(f"- {h}" for h in news) or "- (yo'q)"
            prompt = (
                f"Bugun {date_label}. Telegram ob-havo posti uchun QISQA caption yoz. "
                f"Toshkent: {round(tashkent[0])}\u00b0C, {tashkent[1]}.\n"
                f"Yangiliklar:\n{news_list}\n\n"
                "O'zbek tilida, Telegram HTML (faqat <b>), 600 belgidan kam. Tuzilishi: "
                "emoji bilan sarlavha; 1 jumla ob-havo haqida; <b>Yangiliklar</b> ostida "
                "ro'yxat; oxirida xayrli kun tilagi. Faqat matnni qaytar."
            )
            resp = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text").strip() or text
        except Exception as e:
            print("Claude caption xato (ob-havo):", e)
    return text[:1024]


def currency_caption(date_label, cbu_rate, banks) -> str:
    """Dollar kursi posti uchun caption."""
    best_sell = min((b for b in banks if b.get("sell")), key=lambda b: b["sell"], default=None)
    best_buy = max((b for b in banks if b.get("buy")), key=lambda b: b["buy"], default=None)
    parts = [f"\U0001F4B5 <b>Dollar kursi</b> \u2014 {date_label}", ""]
    parts.append(f"Markaziy bank (rasmiy): <b>{cbu_rate}</b>")
    parts.append("")
    if best_buy and best_sell:
        parts.append(
            f"\U0001F7E2 Dollar SOTMOQCHIMISIZ? Eng qimmat oladi: "
            f"<b>{best_buy['bank']}</b> \u2014 {best_buy['buy']:,} so'm".replace(",", " ")
        )
        parts.append(
            f"\U0001F535 Dollar OLMOQCHIMISIZ? Eng arzon sotadi: "
            f"<b>{best_sell['bank']}</b> \u2014 {best_sell['sell']:,} so'm".replace(",", " ")
        )
    else:
        parts.append("<i>Banklar kursi hozircha mavjud emas.</i>")
    parts.append("")
    parts.append("To'liq jadval rasmda \u2191")
    return "\n".join(parts)[:1024]


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
    cbu_text, _ = get_cbu_usd()
    banks = get_bank_rates()
    news = get_top_news()

    print(f"Ob-havo: {len(weather)} viloyat | Banklar: {len(banks)} | Yangilik: {len(news)}")

    ch = str(TELEGRAM_CHANNEL)

    # 1-POST: ob-havo
    w_img = render_weather_card(date_label, weather, "weather.png", ch)
    post_photo(w_img, weather_caption(date_label, weather, news))
    print("Ob-havo posti yuborildi.")

    # 2-POST: dollar kursi
    c_img = render_currency_card(date_label, cbu_text, banks, "currency.png", ch)
    post_photo(c_img, currency_caption(date_label, cbu_text, banks))
    print("Dollar kursi posti yuborildi.")


if __name__ == "__main__":
    main()
