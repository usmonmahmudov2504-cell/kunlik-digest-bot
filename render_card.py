"""
Kunlik digest uchun rangli info-card (PNG) yasovchi modul.

Ikkita alohida karta:
  - render_weather_card()  -> ob-havo (14 viloyat)
  - render_currency_card() -> dollar kursi (banklar olish/sotish)

Har biri alohida post sifatida yuboriladi, shuning uchun rasmlar kaltaroq
va matn kattaroq -> Telegram'da o'qish oson.

Faqat Pillow kerak. Shriftlar loyiha ichidagi fonts/ papkasidan olinadi.
"""

from __future__ import annotations
import os
from PIL import Image, ImageDraw, ImageFont

# ---- Ranglar (dark, premium ko'rinish) ----
BG        = (15, 23, 42)      # slate-900
CARD      = (30, 41, 59)      # slate-800
CARD2     = (51, 65, 85)      # slate-700
TEXT      = (241, 245, 249)   # slate-100
MUTED     = (148, 163, 184)   # slate-400
ACCENT    = (56, 189, 248)    # sky-400
GREEN     = (52, 211, 153)    # emerald-400
GOLD      = (251, 191, 36)    # amber-400
DIVIDER   = (51, 65, 85)

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIRS = [
    os.path.join(HERE, "fonts"),
    "/usr/share/fonts/truetype/dejavu",
    r"C:\Windows\Fonts",
]


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.truetype(name, size)


# Ob-havo holati -> (belgi, rang)
def _glyph_for(desc: str):
    d = desc.lower()
    if "qor" in d:
        return ("\u2744", (191, 219, 254))   # ❄
    if "yomg'ir" in d or "jala" in d:
        return ("\u2602", ACCENT)            # ☂
    if "momaqaldiroq" in d:
        return ("\u26A1", GOLD)              # ⚡
    if "tuman" in d:
        return ("\u2248", MUTED)             # ≈
    if "bulut" in d:
        return ("\u2601", MUTED)             # ☁
    return ("\u2600", GOLD)                  # ☀


def _new(W, H):
    img = Image.new("RGB", (W, H), BG)
    return img, ImageDraw.Draw(img)


def _rrect(d, box, radius, fill):
    d.rounded_rectangle(box, radius=radius, fill=fill)


def _header(d, W, pad, title, date_label):
    f_title = _font("DejaVuSans-Bold.ttf", 50)
    f_date = _font("DejaVuSans.ttf", 26)
    _rrect(d, (pad, pad, W - pad, pad + 96), 18, CARD)
    d.text((pad + 30, pad + 20), title, font=f_title, fill=TEXT)
    tw = d.textlength(date_label, font=f_date)
    d.text((W - pad - 30 - tw, pad + 36), date_label, font=f_date, fill=ACCENT)


def _footer(d, W, H, pad, channel_label, source):
    f_small = _font("DejaVuSans.ttf", 21)
    foot = source
    if channel_label:
        foot = f"{channel_label}   |   {source}"
    d.text((pad, H - 46), foot, font=f_small, fill=MUTED)


def fmt(n):
    return f"{n:,}".replace(",", " ") if n else "\u2014"


# ============================================================ OB-HAVO KARTASI
def render_weather_card(date_label, weather, out_path="weather.png", channel_label=""):
    W = 900
    pad = 40
    cols = 2
    gap = 20
    cell_h = 104
    n = len(weather)
    rows = (n + cols - 1) // cols

    H = pad + 96 + 40 + rows * (cell_h + gap) + 50
    img, d = _new(W, H)

    _header(d, W, pad, "Ob-havo", date_label)

    f_region = _font("DejaVuSans.ttf", 27)
    f_temp = _font("DejaVuSans-Bold.ttf", 50)
    f_desc = _font("DejaVuSans.ttf", 22)
    f_glyph = _font("DejaVuSans.ttf", 46)

    y0 = pad + 96 + 40
    col_w = (W - 2 * pad - (cols - 1) * gap) // cols
    for i, (region, (temp, desc)) in enumerate(weather.items()):
        c = i % cols
        r = i // cols
        x = pad + c * (col_w + gap)
        y = y0 + r * (cell_h + gap)
        _rrect(d, (x, y, x + col_w, y + cell_h), 16, CARD)
        d.text((x + 22, y + 14), region, font=f_region, fill=MUTED)
        d.text((x + 22, y + 44), f"{round(temp)}\u00b0", font=f_temp, fill=TEXT)
        glyph, gcol = _glyph_for(desc)
        gw = d.textlength(glyph, font=f_glyph)
        d.text((x + col_w - 24 - gw, y + 30), glyph, font=f_glyph, fill=gcol)
        d.text((x + col_w - 24 - d.textlength(desc, font=f_desc), y + cell_h - 32),
               desc, font=f_desc, fill=MUTED)

    _footer(d, W, H, pad, channel_label, "Manba: Open-Meteo")
    img.save(out_path)
    return out_path


# ============================================================ VALYUTA KARTASI
def render_currency_card(date_label, cbu_rate, banks, out_path="currency.png",
                         channel_label="", extra_rates=None):
    extra_rates = extra_rates or []
    W = 900
    pad = 40
    row_h = 54
    callout_h = 150

    extra_h = 0
    if extra_rates:
        extra_h = 30 + 44 + len(extra_rates) * 48 + 10

    H = (pad + 96 + 40 + 50 + callout_h + 24 + 56 + len(banks) * row_h
         + 120 + extra_h + 50)
    img, d = _new(W, H)

    _header(d, W, pad, "Dollar kursi", date_label)

    f_h_small = _font("DejaVuSans.ttf", 22)
    f_row = _font("DejaVuSans.ttf", 27)
    f_row_b = _font("DejaVuSans-Bold.ttf", 27)
    f_co_lbl = _font("DejaVuSans.ttf", 23)
    f_co_big = _font("DejaVuSans-Bold.ttf", 44)
    f_co_sub = _font("DejaVuSans.ttf", 21)
    f_tiny = _font("DejaVuSans.ttf", 17)

    y = pad + 96 + 40

    # CBU rasmiy
    _rrect(d, (pad, y, W - pad, y + 48), 12, CARD2)
    d.text((pad + 20, y + 11), "Markaziy bank (rasmiy)", font=f_h_small, fill=MUTED)
    tw = d.textlength(cbu_rate, font=f_row_b)
    d.text((W - pad - 20 - tw, y + 9), cbu_rate, font=f_row_b, fill=TEXT)
    y += 50 + 14

    # Eng qimmat oladigan / eng arzon sotadigan
    valid = [b for b in banks if b.get("sell") and b.get("buy")]
    max_buy = max((b["buy"] for b in valid), default=None)
    min_sell = min((b["sell"] for b in valid), default=None)
    best_buy_bank = next((b["bank"] for b in valid if b["buy"] == max_buy), "")
    best_sell_bank = next((b["bank"] for b in valid if b["sell"] == min_sell), "")

    gap = 20
    cw = (W - 2 * pad - gap) // 2
    cy = y
    # CHAP: dollar sotmoqchilar (eng qimmat oladigan) -> yashil
    _rrect(d, (pad, cy, pad + cw, cy + callout_h), 16, CARD)
    d.rounded_rectangle((pad, cy, pad + 9, cy + callout_h), radius=4, fill=GREEN)
    d.text((pad + 28, cy + 20), "Dollar SOTMOQCHIMISIZ?", font=f_co_lbl, fill=TEXT)
    d.text((pad + 28, cy + 54), fmt(max_buy) + " so'm", font=f_co_big, fill=GREEN)
    d.text((pad + 28, cy + 110), f"{best_buy_bank} \u2014 eng qimmat oladi", font=f_co_sub, fill=MUTED)
    # O'NG: dollar olmoqchilar (eng arzon sotadigan) -> ko'k
    x2 = pad + cw + gap
    _rrect(d, (x2, cy, x2 + cw, cy + callout_h), 16, CARD)
    d.rounded_rectangle((x2, cy, x2 + 9, cy + callout_h), radius=4, fill=ACCENT)
    d.text((x2 + 28, cy + 20), "Dollar OLMOQCHIMISIZ?", font=f_co_lbl, fill=TEXT)
    d.text((x2 + 28, cy + 54), fmt(min_sell) + " so'm", font=f_co_big, fill=ACCENT)
    d.text((x2 + 28, cy + 110), f"{best_sell_bank} \u2014 eng arzon sotadi", font=f_co_sub, fill=MUTED)
    y = cy + callout_h + 24

    # Jadval sarlavhasi
    c_bank = pad + 20
    c_buy = pad + 430
    c_sell = pad + 650
    d.text((c_bank, y), "Bank", font=f_h_small, fill=MUTED)
    d.text((c_buy, y), "Olish", font=f_h_small, fill=GREEN)
    d.text((c_sell, y), "Sotish", font=f_h_small, fill=ACCENT)
    y += 28
    d.text((c_buy, y), "(siz sotasiz)", font=f_tiny, fill=MUTED)
    d.text((c_sell, y), "(siz olasiz)", font=f_tiny, fill=MUTED)
    y += 26
    d.line((pad, y, W - pad, y), fill=DIVIDER, width=2)
    y += 8

    for b in banks:
        is_best_buy = b.get("buy") == max_buy
        is_best_sell = b.get("sell") == min_sell
        if is_best_buy or is_best_sell:
            _rrect(d, (pad, y, W - pad, y + row_h - 8), 10, CARD)
        d.text((c_bank, y + 10), b["bank"], font=f_row, fill=TEXT)
        d.text((c_buy, y + 10), fmt(b.get("buy")), font=(f_row_b if is_best_buy else f_row),
               fill=(GREEN if is_best_buy else TEXT))
        d.text((c_sell, y + 10), fmt(b.get("sell")), font=(f_row_b if is_best_sell else f_row),
               fill=(ACCENT if is_best_sell else TEXT))
        y += row_h

    y += 14
    d.ellipse((pad + 2, y + 6, pad + 18, y + 22), fill=GREEN)
    d.text((pad + 28, y), "eng qimmat oladi \u2014 dollaringizni shu yerda soting", font=f_h_small, fill=MUTED)
    y += 34
    d.ellipse((pad + 2, y + 6, pad + 18, y + 22), fill=ACCENT)
    d.text((pad + 28, y), "eng arzon sotadi \u2014 dollarni shu yerdan oling", font=f_h_small, fill=MUTED)
    y += 44

    # ---- Boshqa valyutalar (rasmiy CBU) ----
    if extra_rates:
        d.line((pad, y, W - pad, y), fill=DIVIDER, width=2)
        y += 16
        d.text((pad + 4, y), "Boshqa valyutalar (rasmiy, CBU)",
               font=_font("DejaVuSans-Bold.ttf", 24), fill=TEXT)
        y += 44
        f_code = _font("DejaVuSans-Bold.ttf", 26)
        f_name = _font("DejaVuSans.ttf", 23)
        for e in extra_rates:
            d.text((pad + 20, y + 6), e["code"], font=f_code, fill=ACCENT)
            label = f"{e['name']}  ({e['unit']})"
            d.text((pad + 110, y + 9), label, font=f_name, fill=MUTED)
            rate_s = f"{e['rate']} so'm"
            tw = d.textlength(rate_s, font=f_row_b)
            d.text((W - pad - 20 - tw, y + 7), rate_s, font=f_row_b, fill=TEXT)
            y += 48
        y += 6

    _footer(d, W, H, pad, channel_label, "Manba: cbu.uz, goldenpages.uz")
    img.save(out_path)
    return out_path


if __name__ == "__main__":
    weather = {
        "Toshkent sh.": (28, "asosan ochiq"), "Toshkent vil.": (27, "qisman bulutli"),
        "Andijon": (26, "bulutli"), "Buxoro": (32, "ochiq"),
        "Farg'ona": (25, "yomg'ir"), "Jizzax": (30, "ochiq"),
        "Namangan": (26, "qisman bulutli"), "Navoiy": (33, "ochiq"),
        "Qashqadaryo": (31, "ochiq"), "Qoraqalpog'iston": (29, "momaqaldiroq"),
        "Samarqand": (27, "bulutli"), "Sirdaryo": (30, "ochiq"),
        "Surxondaryo": (34, "ochiq"), "Xorazm": (29, "tuman"),
    }
    banks = [
        {"bank": "Asia Alliance", "buy": 12035, "sell": 12110},
        {"bank": "Hamkorbank", "buy": 12050, "sell": 12145},
        {"bank": "Trastbank", "buy": 12050, "sell": 12110},
        {"bank": "NBU", "buy": 12070, "sell": 12145},
        {"bank": "Xalqbanki", "buy": 12045, "sell": 12100},
        {"bank": "Ipoteka Bank", "buy": 12035, "sell": 12125},
        {"bank": "Aloqabank", "buy": 12060, "sell": 12100},
        {"bank": "Anorbank", "buy": 12010, "sell": 12120},
        {"bank": "Orient Finans", "buy": 12080, "sell": 12140},
        {"bank": "Apex Bank", "buy": 12010, "sell": 12090},
    ]
    extra = [
        {"code": "EUR", "name": "Yevro", "unit": "1 EUR", "rate": "13 901,44"},
        {"code": "RUB", "name": "Rubl", "unit": "1 RUB", "rate": "153,28"},
        {"code": "GBP", "name": "Funt sterling", "unit": "1 GBP", "rate": "16 240,10"},
        {"code": "KZT", "name": "Tenge", "unit": "100 KZT", "rate": "2 410,55"},
        {"code": "CNY", "name": "Yuan", "unit": "1 CNY", "rate": "1 681,90"},
    ]
    render_weather_card("21-iyun, 2026 \u00b7 Yakshanba", weather,
                        "/home/claude/dist/post-ob-havo.png", "@oq_xabar")
    render_currency_card("21-iyun, 2026 \u00b7 Yakshanba", "12 085,56 so'm", banks,
                         "/home/claude/dist/post-dollar.png", "@oq_xabar",
                         extra_rates=extra)
    print("ikkala karta render qilindi")
