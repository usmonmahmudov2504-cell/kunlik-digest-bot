"""
Kunlik digest uchun rangli info-card (PNG) yasovchi modul (5 post uchun).

Kartalar:
  1) render_day_card()              -> Bugun qanaqa kun (sana, fasl, bayramlar)
  2) render_news_card()             -> Yangiliklar/biznes (sarlavhalar)
  3) render_weather_card()          -> Ob-havo (14 viloyat)
  4) render_currency_overview_card()-> Umumiy valyuta kurslari (rasmiy)
  5) render_currency_card()         -> Dollar batafsil (banklar olish/sotish)

Faqat Pillow kerak. Shriftlar loyiha ichidagi fonts/ papkasidan olinadi.
"""

from __future__ import annotations
import os
from PIL import Image, ImageDraw, ImageFont

# ---- Ranglar ----
BG     = (15, 23, 42)
CARD   = (30, 41, 59)
CARD2  = (51, 65, 85)
TEXT   = (241, 245, 249)
MUTED  = (148, 163, 184)
ACCENT = (56, 189, 248)
GREEN  = (52, 211, 153)
GOLD   = (251, 191, 36)
PURPLE = (167, 139, 250)
TEAL   = (45, 212, 191)
DIVIDER = (51, 65, 85)

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIRS = [os.path.join(HERE, "fonts"), "/usr/share/fonts/truetype/dejavu", r"C:\Windows\Fonts"]


def _font(name, size):
    for dpath in FONT_DIRS:
        p = os.path.join(dpath, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.truetype(name, size)


def B(size):  # bold
    return _font("DejaVuSans-Bold.ttf", size)


def R(size):  # regular
    return _font("DejaVuSans.ttf", size)


def _new(W, H):
    img = Image.new("RGB", (W, H), BG)
    return img, ImageDraw.Draw(img)


def _rrect(d, box, radius, fill):
    d.rounded_rectangle(box, radius=radius, fill=fill)


def _header(d, W, pad, title, date_label, accent=ACCENT):
    _rrect(d, (pad, pad, W - pad, pad + 96), 18, CARD)
    d.text((pad + 30, pad + 20), title, font=B(50), fill=TEXT)
    f = R(26)
    tw = d.textlength(date_label, font=f)
    d.text((W - pad - 30 - tw, pad + 36), date_label, font=f, fill=accent)


def _footer(d, W, H, pad, channel_label, source):
    foot = f"{channel_label}   |   {source}" if channel_label else source
    d.text((pad, H - 46), foot, font=R(21), fill=MUTED)


def _wrap(text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if font.getlength(t) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def fmt(n):
    return f"{n:,}".replace(",", " ") if n else "\u2014"


# Ob-havo holati -> (belgi, rang)
def _glyph_for(desc):
    dd = desc.lower()
    if "qor" in dd:
        return ("\u2744", (191, 219, 254))
    if "yomg'ir" in dd or "jala" in dd:
        return ("\u2602", ACCENT)
    if "momaqaldiroq" in dd:
        return ("\u26A1", GOLD)
    if "tuman" in dd:
        return ("\u2248", MUTED)
    if "qisman bulut" in dd:
        return ("\u2601", MUTED)
    if "bulut" in dd:
        return ("\u2601", MUTED)
    return ("\u2600", GOLD)


# ============================================================ 1) BUGUN
def render_day_card(date_label, weekday, season, day_of_year, days_left,
                    week_no, holidays, out_path="day.png", channel_label=""):
    W, pad = 900, 40
    hol = holidays or []
    hol_lines = hol if hol else ["Bugun maxsus bayram/sana yo'q"]
    H = pad + 96 + 40 + 96 + 56 + 110 + 30 + 50 + len(hol_lines) * 50 + 60
    img, d = _new(W, H)
    _header(d, W, pad, "Bugun", date_label, PURPLE)
    y = pad + 96 + 40

    d.text((pad + 6, y), weekday, font=B(64), fill=TEXT)
    y += 90
    d.text((pad + 6, y), f"{season} fasli", font=R(30), fill=PURPLE)
    y += 60

    chips = [("Yil kuni", str(day_of_year)), ("Yil oxiriga", f"{days_left} kun"),
             ("Hafta", f"{week_no}-hafta")]
    cw = (W - 2 * pad - 2 * 16) // 3
    for i, (lbl, val) in enumerate(chips):
        x = pad + i * (cw + 16)
        _rrect(d, (x, y, x + cw, y + 92), 14, CARD)
        d.text((x + 20, y + 16), lbl, font=R(21), fill=MUTED)
        d.text((x + 20, y + 44), val, font=B(34), fill=TEXT)
    y += 92 + 30

    d.text((pad + 6, y), "Bugungi sana / bayram", font=B(28), fill=TEXT)
    y += 50
    for line in hol_lines:
        _rrect(d, (pad, y, W - pad, y + 44), 12, CARD)
        d.text((pad + 18, y + 9), line, font=R(25), fill=TEXT if hol else MUTED)
        y += 50

    _footer(d, W, H, pad, channel_label, "Manba: taqvim")
    img.save(out_path)
    return out_path


# ============================================================ 2) YANGILIKLAR
def render_news_card(title, date_label, headlines, out_path="news.png",
                     channel_label="", source="Manba: gazeta.uz, daryo.uz"):
    W, pad = 900, 40
    f_item, f_num = R(27), B(27)
    max_w = W - 2 * pad - 70
    items = [_wrap(h, f_item, max_w) for h in headlines[:6]]
    body_h = sum(len(w) * 38 + 22 for w in items) or 60
    H = pad + 96 + 40 + body_h + 70
    img, d = _new(W, H)
    _header(d, W, pad, title, date_label, GOLD)
    y = pad + 96 + 40
    for i, lines in enumerate(items, 1):
        d.text((pad + 6, y), f"{i}.", font=f_num, fill=GOLD)
        for ln in lines:
            d.text((pad + 54, y), ln, font=f_item, fill=TEXT)
            y += 38
        y += 22
    if not items:
        d.text((pad + 6, y), "Bugun yangilik topilmadi.", font=f_item, fill=MUTED)
    _footer(d, W, H, pad, channel_label, source)
    img.save(out_path)
    return out_path


# ============================================================ 3) OB-HAVO
def render_weather_card(date_label, weather, out_path="weather.png", channel_label=""):
    W, pad, cols, gap, cell_h = 900, 40, 2, 20, 104
    n = len(weather)
    rows = (n + cols - 1) // cols
    H = pad + 96 + 40 + rows * (cell_h + gap) + 50
    img, d = _new(W, H)
    _header(d, W, pad, "Ob-havo", date_label)
    f_region, f_temp, f_desc, f_glyph = R(27), B(50), R(22), R(46)
    y0 = pad + 96 + 40
    col_w = (W - 2 * pad - (cols - 1) * gap) // cols
    for i, (region, (temp, desc)) in enumerate(weather.items()):
        c, r = i % cols, i // cols
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


# ============================================================ 4) UMUMIY KURSLAR
def render_currency_overview_card(date_label, rows, out_path="rates.png", channel_label=""):
    """rows: [{"code","name","unit","rate"}, ...] (USD birinchi)."""
    W, pad, row_h = 900, 40, 60
    H = pad + 96 + 40 + 44 + len(rows) * row_h + 60
    img, d = _new(W, H)
    _header(d, W, pad, "Kurslar", date_label, GREEN)
    y = pad + 96 + 40
    d.text((pad + 4, y), "Markaziy bank rasmiy kursi (1 birlik uchun)", font=R(22), fill=MUTED)
    y += 44
    f_code, f_name, f_rate = B(30), R(24), B(30)
    for r in rows:
        _rrect(d, (pad, y, W - pad, y + row_h - 8), 12, CARD)
        d.text((pad + 20, y + 12), r["code"], font=f_code, fill=ACCENT)
        d.text((pad + 130, y + 15), f"{r['name']}  ({r['unit']})", font=f_name, fill=MUTED)
        rate_s = f"{r['rate']} so'm"
        tw = d.textlength(rate_s, font=f_rate)
        d.text((W - pad - 20 - tw, y + 12), rate_s, font=f_rate, fill=TEXT)
        y += row_h
    _footer(d, W, H, pad, channel_label, "Manba: cbu.uz")
    img.save(out_path)
    return out_path


# ============================================================ 5) DOLLAR (BANKLAR)
def render_currency_card(date_label, cbu_rate, banks, out_path="currency.png",
                         channel_label="", extra_rates=None):
    W, pad, row_h, callout_h = 900, 40, 54, 150
    H = pad + 96 + 40 + 50 + callout_h + 24 + 56 + len(banks) * row_h + 120 + 50
    img, d = _new(W, H)
    _header(d, W, pad, "Dollar kursi", date_label)
    f_hs, f_row, f_rowb = R(22), R(27), B(27)
    f_lbl, f_big, f_sub, f_tiny = R(23), B(44), R(21), R(17)
    y = pad + 96 + 40

    _rrect(d, (pad, y, W - pad, y + 48), 12, CARD2)
    d.text((pad + 20, y + 11), "Markaziy bank (rasmiy)", font=f_hs, fill=MUTED)
    tw = d.textlength(cbu_rate, font=f_rowb)
    d.text((W - pad - 20 - tw, y + 9), cbu_rate, font=f_rowb, fill=TEXT)
    y += 50 + 14

    valid = [b for b in banks if b.get("sell") and b.get("buy")]
    max_buy = max((b["buy"] for b in valid), default=None)
    min_sell = min((b["sell"] for b in valid), default=None)
    best_buy_bank = next((b["bank"] for b in valid if b["buy"] == max_buy), "")
    best_sell_bank = next((b["bank"] for b in valid if b["sell"] == min_sell), "")

    gap = 20
    cw = (W - 2 * pad - gap) // 2
    cy = y
    _rrect(d, (pad, cy, pad + cw, cy + callout_h), 16, CARD)
    d.rounded_rectangle((pad, cy, pad + 9, cy + callout_h), radius=4, fill=GREEN)
    d.text((pad + 28, cy + 20), "Dollar SOTMOQCHIMISIZ?", font=f_lbl, fill=TEXT)
    d.text((pad + 28, cy + 54), fmt(max_buy) + " so'm", font=f_big, fill=GREEN)
    d.text((pad + 28, cy + 110), f"{best_buy_bank} \u2014 eng qimmat oladi", font=f_sub, fill=MUTED)
    x2 = pad + cw + gap
    _rrect(d, (x2, cy, x2 + cw, cy + callout_h), 16, CARD)
    d.rounded_rectangle((x2, cy, x2 + 9, cy + callout_h), radius=4, fill=ACCENT)
    d.text((x2 + 28, cy + 20), "Dollar OLMOQCHIMISIZ?", font=f_lbl, fill=TEXT)
    d.text((x2 + 28, cy + 54), fmt(min_sell) + " so'm", font=f_big, fill=ACCENT)
    d.text((x2 + 28, cy + 110), f"{best_sell_bank} \u2014 eng arzon sotadi", font=f_sub, fill=MUTED)
    y = cy + callout_h + 24

    c_bank, c_buy, c_sell = pad + 20, pad + 430, pad + 650
    d.text((c_bank, y), "Bank", font=f_hs, fill=MUTED)
    d.text((c_buy, y), "Olish", font=f_hs, fill=GREEN)
    d.text((c_sell, y), "Sotish", font=f_hs, fill=ACCENT)
    y += 28
    d.text((c_buy, y), "(siz sotasiz)", font=f_tiny, fill=MUTED)
    d.text((c_sell, y), "(siz olasiz)", font=f_tiny, fill=MUTED)
    y += 26
    d.line((pad, y, W - pad, y), fill=DIVIDER, width=2)
    y += 8

    for b in banks:
        is_bb = b.get("buy") == max_buy
        is_bs = b.get("sell") == min_sell
        if is_bb or is_bs:
            _rrect(d, (pad, y, W - pad, y + row_h - 8), 10, CARD)
        d.text((c_bank, y + 10), b["bank"], font=f_row, fill=TEXT)
        d.text((c_buy, y + 10), fmt(b.get("buy")), font=(f_rowb if is_bb else f_row),
               fill=(GREEN if is_bb else TEXT))
        d.text((c_sell, y + 10), fmt(b.get("sell")), font=(f_rowb if is_bs else f_row),
               fill=(ACCENT if is_bs else TEXT))
        y += row_h

    y += 14
    d.ellipse((pad + 2, y + 6, pad + 18, y + 22), fill=GREEN)
    d.text((pad + 28, y), "eng qimmat oladi \u2014 dollaringizni shu yerda soting", font=f_hs, fill=MUTED)
    y += 34
    d.ellipse((pad + 2, y + 6, pad + 18, y + 22), fill=ACCENT)
    d.text((pad + 28, y), "eng arzon sotadi \u2014 dollarni shu yerdan oling", font=f_hs, fill=MUTED)

    _footer(d, W, H, pad, channel_label, "Manba: cbu.uz, goldenpages.uz")
    img.save(out_path)
    return out_path



# ============================================================ 6) KUN MASLAHATI
def render_advice_card(date_label, kind, text, out_path="advice.png", channel_label=""):
    W, pad = 900, 40
    f_text = R(36)
    max_w = W - 2 * pad - 80
    lines = _wrap(text, f_text, max_w)
    body_h = len(lines) * 50
    H = pad + 96 + 40 + 70 + 40 + body_h + 70
    img, d = _new(W, H)
    _header(d, W, pad, "Kun maslahati", date_label, TEAL)
    y = pad + 96 + 40

    klbl = kind.upper()
    kw = d.textlength(klbl, font=B(22))
    _rrect(d, (pad, y, pad + kw + 40, y + 42), 21, CARD)
    d.text((pad + 20, y + 8), klbl, font=B(22), fill=TEAL)
    y += 60

    d.text((pad - 4, y - 24), "\u201C", font=B(110), fill=CARD2)
    y += 40
    for ln in lines:
        d.text((pad + 20, y), ln, font=f_text, fill=TEXT)
        y += 50

    _footer(d, W, H, pad, channel_label, "Kunlik biznes maslahati")
    img.save(out_path)
    return out_path


if __name__ == "__main__":
    out = "/home/claude/dist"
    dl = "21-iyun, 2026 \u00b7 Yakshanba"
    render_day_card(dl, "Yakshanba", "Yoz", 172, 193, 25,
                    ["Xalqaro yoga kuni", "Yozgi quyosh turishi (eng uzun kun)"],
                    f"{out}/p1-bugun.png", "@oq_xabar")
    render_news_card("Biznes", dl, [
        "Markaziy bank asosiy stavkani 13,5% da saqlab qoldi",
        "Toshkentda yangi savdo markazi ochildi, 2000 ish o'rni yaratiladi",
        "Eksport hajmi yil boshidan 12% ga oshdi",
        "Yangi soliq imtiyozlari IT kompaniyalar uchun joriy etildi",
    ], f"{out}/p2-biznes.png", "@oq_xabar", "Manba: spot.uz, kun.uz")
    weather = {"Toshkent sh.": (28, "asosan ochiq"), "Toshkent vil.": (27, "qisman bulutli"),
               "Andijon": (26, "bulutli"), "Buxoro": (32, "ochiq"), "Farg'ona": (25, "yomg'ir"),
               "Jizzax": (30, "ochiq"), "Namangan": (26, "qisman bulutli"), "Navoiy": (33, "ochiq"),
               "Qashqadaryo": (31, "ochiq"), "Qoraqalpog'iston": (29, "momaqaldiroq"),
               "Samarqand": (27, "bulutli"), "Sirdaryo": (30, "ochiq"),
               "Surxondaryo": (34, "ochiq"), "Xorazm": (29, "tuman")}
    render_weather_card(dl, weather, f"{out}/p3-obhavo.png", "@oq_xabar")
    rates = [
        {"code": "USD", "name": "AQSH dollari", "unit": "1 USD", "rate": "12 085,56"},
        {"code": "EUR", "name": "Yevro", "unit": "1 EUR", "rate": "13 870,60"},
        {"code": "GBP", "name": "Funt sterling", "unit": "1 GBP", "rate": "16 002,49"},
        {"code": "RUB", "name": "Rubl", "unit": "1 RUB", "rate": "164,52"},
        {"code": "KZT", "name": "Tenge", "unit": "100 KZT", "rate": "2 476,00"},
        {"code": "CNY", "name": "Yuan", "unit": "1 CNY", "rate": "1 785,74"},
        {"code": "JPY", "name": "Yaponiya iyenasi", "unit": "100 JPY", "rate": "7 980,00"},
        {"code": "TRY", "name": "Turk lirasi", "unit": "1 TRY", "rate": "350,20"},
    ]
    render_currency_overview_card(dl, rates, f"{out}/p4-kurslar.png", "@oq_xabar")
    banks = [{"bank": "Asia Alliance", "buy": 12035, "sell": 12110},
             {"bank": "Hamkorbank", "buy": 12010, "sell": 12140},
             {"bank": "NBU", "buy": 12070, "sell": 12140},
             {"bank": "Kapitalbank", "buy": 12035, "sell": 12115},
             {"bank": "Ipoteka Bank", "buy": 12005, "sell": 12125},
             {"bank": "Aloqabank", "buy": 12060, "sell": 12120},
             {"bank": "Orient Finans", "buy": 12080, "sell": 12140},
             {"bank": "Apex Bank", "buy": 12010, "sell": 12090}]
    render_currency_card(dl, "12 085,56 so'm", banks, f"{out}/p5-dollar.png", "@oq_xabar")
    render_advice_card(dl, "Hikmat",
                       "Daraxt ekishning eng yaxshi vaqti 20 yil oldin edi. Ikkinchisi \u2014 hozir.",
                       f"{out}/p6-maslahat.png", "@oq_xabar")
    print("6 karta render qilindi")
