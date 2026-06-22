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
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ---- Ranglar ----
BG     = (15, 23, 42)
BG_TOP = (16, 24, 43)        # fon gradienti: tepa (biroz quyuq)
BG_BOT = (24, 34, 58)        # fon gradienti: past (biroz ochiq)
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
INTER_FILE = "Inter-Variable.ttf"   # zamonaviy variable shrift (matn uchun)


def _font(name, size):
    for dpath in FONT_DIRS:
        p = os.path.join(dpath, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.truetype(name, size)


def _inter(size, variation, fallback):
    """Inter (variable) ni kerakli qalinlikda yuklaydi. Bo'lmasa DejaVu'ga tushadi."""
    for dpath in FONT_DIRS:
        p = os.path.join(dpath, INTER_FILE)
        if os.path.exists(p):
            f = ImageFont.truetype(p, size)
            try:
                f.set_variation_by_name(variation)
            except Exception:
                pass
            return f
    return _font(fallback, size)


def B(size):  # bold (matn)
    return _inter(size, "Bold", "DejaVuSans-Bold.ttf")


def R(size):  # regular (matn)
    return _inter(size, "Regular", "DejaVuSans.ttf")


def G(size):  # ob-havo/simvol glyphlari (Inter qoplamaydi) -> DejaVu
    return _font("DejaVuSans.ttf", size)


def _new(W, H):
    """Nozik vertikal gradient fon (tekis rang o'rniga -> chuqurlik hissi)."""
    col = Image.new("RGB", (1, H))
    px = col.load()
    for y in range(H):
        t = y / max(H - 1, 1)
        px[0, y] = (round(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t),
                    round(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t),
                    round(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t))
    img = col.resize((W, H))
    return img, ImageDraw.Draw(img)


def _rrect(d, box, radius, fill):
    d.rounded_rectangle(box, radius=radius, fill=fill)


def _panel(img, box, radius=16, fill=CARD, blur=16, dy=7, alpha=120):
    """Yumshoq soya bilan yumaloq karta chizadi (chuqurlik/floating effekti).

    Soya faqat karta atrofidagi kichik hududda hisoblanadi (tez)."""
    x0, y0, x1, y1 = [int(v) for v in box]
    m = blur * 3
    rx0, ry0 = max(x0 - m, 0), max(y0 - m, 0)
    rx1, ry1 = min(x1 + m, img.width), min(y1 + m + dy, img.height)
    sh = Image.new("RGBA", (rx1 - rx0, ry1 - ry0), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        (x0 - rx0, y0 - ry0 + dy, x1 - rx0, y1 - ry0 + dy), radius=radius, fill=(0, 0, 0, alpha))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    img.paste(sh, (rx0, ry0), sh)
    ImageDraw.Draw(img).rounded_rectangle(box, radius=radius, fill=fill)


# Karta turi -> sarlavhadagi ikonka (vektor, accent rangda chiziladi)
def _draw_icon(d, kind, box, color):
    x0, y0, x1, y1 = box
    s = x1 - x0
    cx, cy = x0 + s / 2, y0 + s / 2
    lw = max(2, round(s * 0.07))
    if kind == "weather":                                   # quyosh
        r = s * 0.20
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
        for a in range(0, 360, 45):
            rad = math.radians(a)
            x_in, y_in = cx + math.cos(rad) * r * 1.5, cy + math.sin(rad) * r * 1.5
            x_out, y_out = cx + math.cos(rad) * r * 2.1, cy + math.sin(rad) * r * 2.1
            d.line((x_in, y_in, x_out, y_out), fill=color, width=lw)
    elif kind == "day":                                     # taqvim
        bx0, by0, bx1, by1 = cx - s * 0.28, cy - s * 0.22, cx + s * 0.28, cy + s * 0.30
        d.rounded_rectangle((bx0, by0, bx1, by1), radius=s * 0.06, outline=color, width=lw)
        d.line((bx0, by0 + s * 0.16, bx1, by0 + s * 0.16), fill=color, width=lw)
        d.line((cx - s * 0.14, by0 - s * 0.06, cx - s * 0.14, by0 + s * 0.06), fill=color, width=lw)
        d.line((cx + s * 0.14, by0 - s * 0.06, cx + s * 0.14, by0 + s * 0.06), fill=color, width=lw)
    elif kind == "news":                                    # hujjat/qatorlar
        for i, frac in enumerate((0.0, 0.33, 0.66)):
            yy = cy - s * 0.22 + frac * s * 0.66
            x_end = x1 - s * 0.22 if i < 2 else cx + s * 0.05
            d.line((x0 + s * 0.22, yy, x_end, yy), fill=color, width=lw)
    elif kind == "rates":                                   # tangalar (ustma-ust ellips)
        for i, oy in enumerate((0.22, 0.0, -0.22)):
            ey = cy + s * oy
            d.ellipse((cx - s * 0.26, ey - s * 0.10, cx + s * 0.26, ey + s * 0.10),
                      outline=color, width=lw)
    elif kind == "currency":                                # banknot
        d.rounded_rectangle((cx - s * 0.30, cy - s * 0.18, cx + s * 0.30, cy + s * 0.18),
                            radius=s * 0.05, outline=color, width=lw)
        r = s * 0.07
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=lw)
    elif kind == "advice":                                  # lampochka
        r = s * 0.20
        d.ellipse((cx - r, cy - r * 1.1, cx + r, cy + r * 0.9), outline=color, width=lw)
        d.line((cx - r * 0.5, cy + r, cx + r * 0.5, cy + r), fill=color, width=lw)
        d.line((cx - r * 0.5, cy + r * 1.4, cx + r * 0.5, cy + r * 1.4), fill=color, width=lw)


def _header(img, W, pad, title, date_label, accent=ACCENT, icon=None):
    d = ImageDraw.Draw(img)
    _panel(img, (pad, pad, W - pad, pad + 96), 18, CARD)
    d = ImageDraw.Draw(img)
    tx = pad + 30
    if icon:                                                # accent rangli ikonka-chip
        ch = 60
        ix0, iy0 = pad + 22, pad + 18
        _draw_icon(d, icon, (ix0, iy0, ix0 + ch, iy0 + ch), accent)
        tx = ix0 + ch + 20
    d.text((tx, pad + 22), title, font=B(48), fill=TEXT)
    f = R(26)
    tw = d.textlength(date_label, font=f)
    d.text((W - pad - 30 - tw, pad + 36), date_label, font=f, fill=accent)


def _paste_banner(img, d, banner_path, box, radius=16):
    """Tashqi rasmni (banner) yumaloq burchakli qilib kartaga joylashtiradi.

    Rasm box o'lchamiga 'cover' rejimida kesiladi (nisbat buzilmaydi). Xato bo'lsa
    o'rniga oddiy karta foni chiziladi (post baribir chiqaveradi)."""
    x0, y0, x1, y1 = box
    tw, th = x1 - x0, y1 - y0
    try:
        src = Image.open(banner_path).convert("RGB")
        scale = max(tw / src.width, th / src.height)
        src = src.resize((max(tw, round(src.width * scale)),
                          max(th, round(src.height * scale))))
        left = (src.width - tw) // 2
        top = (src.height - th) // 2
        crop = src.crop((left, top, left + tw, top + th))
        mask = Image.new("L", (tw, th), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, tw - 1, th - 1), radius=radius, fill=255)
        img.paste(crop, (x0, y0), mask)
    except Exception as e:
        print("banner joylashda xato:", e)
        _rrect(d, box, radius, CARD2)


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


# Harorat -> rang (issiq qizg'ish, sovuq ko'k). O'rtacha haroratlar neytral (TEXT).
def _temp_color(t):
    if t >= 38:
        return (248, 113, 113)     # jazirama -> qizil
    if t >= 30:
        return (251, 146, 60)      # issiq -> to'q sariq
    if t >= 22:
        return (250, 204, 21)      # iliq -> sariq
    if t >= 12:
        return TEXT                # mo'tadil -> oq
    if t >= 2:
        return (125, 211, 252)     # salqin -> och ko'k
    return (96, 165, 250)          # sovuq -> ko'k


# ============================================================ 1) BUGUN
def render_day_card(date_label, weekday, season, day_of_year, days_left,
                    week_no, holidays, out_path="day.png", channel_label=""):
    W, pad = 900, 40
    hol = holidays or []
    hol_lines = hol if hol else ["Bugun maxsus bayram/sana yo'q"]
    H = pad + 96 + 40 + 96 + 56 + 110 + 30 + 84 + 50 + len(hol_lines) * 50 + 60
    img, d = _new(W, H)
    _header(img, W, pad, "Bugun", date_label, PURPLE, "day")
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
        _panel(img, (x, y, x + cw, y + 92), 14, CARD, blur=12, dy=5, alpha=90)
        d.text((x + 20, y + 16), lbl, font=R(21), fill=MUTED)
        d.text((x + 20, y + 44), val, font=B(34), fill=TEXT)
    y += 92 + 30

    # Yil progressi: yilning necha foizi o'tdi (vizual progress chizig'i)
    total = day_of_year + days_left
    frac = (day_of_year / total) if total else 0
    d.text((pad + 6, y), "Yil progressi", font=R(22), fill=MUTED)
    pct = f"{round(frac * 100)}%"
    fp = B(24)
    pw = d.textlength(pct, font=fp)
    d.text((W - pad - 6 - pw, y - 2), pct, font=fp, fill=PURPLE)
    y += 36
    _rrect(d, (pad, y, W - pad, y + 22), 11, CARD2)
    fill_w = pad + max(22, round((W - 2 * pad) * frac))
    d.rounded_rectangle((pad, y, fill_w, y + 22), radius=11, fill=PURPLE)
    y += 22 + 26

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
                     channel_label="", source="Manba: gazeta.uz, daryo.uz",
                     banner_path=None):
    W, pad = 900, 40
    f_item, f_num = R(27), B(27)
    max_w = W - 2 * pad - 70

    def _title(h):
        return h["title"] if isinstance(h, dict) else h

    items = [_wrap(_title(h), f_item, max_w) for h in headlines[:6]]
    body_h = sum(len(w) * 38 + 22 for w in items) or 60
    has_banner = bool(banner_path and os.path.exists(banner_path))
    banner_h = 300 if has_banner else 0
    banner_gap = 24 if has_banner else 0
    H = pad + 96 + 40 + banner_h + banner_gap + body_h + 70
    img, d = _new(W, H)
    _header(img, W, pad, title, date_label, GOLD, "news")
    y = pad + 96 + 40
    if has_banner:
        _paste_banner(img, d, banner_path, (pad, y, W - pad, y + banner_h))
        y += banner_h + banner_gap
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
    _header(img, W, pad, "Ob-havo", date_label, ACCENT, "weather")
    f_region, f_temp, f_desc, f_glyph = R(27), B(50), R(22), G(46)
    y0 = pad + 96 + 40
    col_w = (W - 2 * pad - (cols - 1) * gap) // cols
    for i, (region, (temp, desc)) in enumerate(weather.items()):
        c, r = i % cols, i // cols
        x = pad + c * (col_w + gap)
        y = y0 + r * (cell_h + gap)
        _panel(img, (x, y, x + col_w, y + cell_h), 16, CARD, blur=12, dy=5, alpha=90)
        d.text((x + 22, y + 14), region, font=f_region, fill=MUTED)
        d.text((x + 22, y + 44), f"{round(temp)}\u00b0", font=f_temp, fill=_temp_color(temp))
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
    _header(img, W, pad, "Kurslar", date_label, GREEN, "rates")
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
    _header(img, W, pad, "Dollar kursi", date_label, ACCENT, "currency")
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
    _panel(img, (pad, cy, pad + cw, cy + callout_h), 16, CARD, blur=14, dy=6, alpha=100)
    d.rounded_rectangle((pad, cy, pad + 9, cy + callout_h), radius=4, fill=GREEN)
    d.text((pad + 28, cy + 20), "Dollar SOTMOQCHIMISIZ?", font=f_lbl, fill=TEXT)
    d.text((pad + 28, cy + 54), fmt(max_buy) + " so'm", font=f_big, fill=GREEN)
    d.text((pad + 28, cy + 110), f"{best_buy_bank} \u2014 eng qimmat oladi", font=f_sub, fill=MUTED)
    x2 = pad + cw + gap
    _panel(img, (x2, cy, x2 + cw, cy + callout_h), 16, CARD, blur=14, dy=6, alpha=100)
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
    _header(img, W, pad, "Kun maslahati", date_label, TEAL, "advice")
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
