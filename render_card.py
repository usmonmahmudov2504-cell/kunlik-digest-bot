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
import io
import math
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ---- Ranglar (oq/yorug' tema) ----
BG     = (255, 255, 255)
BG_TOP = (237, 242, 248)      # fon gradienti: tepa (juda och kulrang)
BG_BOT = (252, 253, 255)      # fon gradienti: past (deyarli oq)
CARD   = (255, 255, 255)      # oq panellar (soya bilan ajraladi)
CARD2  = (241, 245, 249)      # ikkilamchi och kulrang
TEXT   = (17, 24, 39)         # deyarli qora
MUTED  = (107, 114, 128)      # kulrang-500
ACCENT = (37, 99, 235)        # ko'k-600
GREEN  = (5, 150, 105)        # emerald-600
GOLD   = (202, 138, 4)        # amber-600 (oqda kontrast uchun quyuqroq)
PURPLE = (124, 58, 237)       # violet-600
TEAL   = (13, 148, 136)       # teal-600
RED    = (220, 38, 38)        # qizil-600 (kurs pasayishi)
DIVIDER = (226, 232, 240)
SHADOW = (15, 23, 42)         # yumshoq soya rangi (oq fonda kulrang ko'rinadi)

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIRS = [os.path.join(HERE, "fonts"), "/usr/share/fonts/truetype/dejavu", r"C:\Windows\Fonts"]
INTER_FILE = "Inter-Variable.ttf"   # zamonaviy variable shrift (matn uchun)
FLAG_DIR = os.path.join(HERE, "assets", "flags")   # valyuta bayroqlari (USD.png, EUR.png ...)
_flag_cache: dict = {}


def _flag(code, h):
    """Valyuta bayrog'ini (PNG) balandlik bo'yicha o'lchab qaytaradi. Yo'q bo'lsa None."""
    key = (code, h)
    if key in _flag_cache:
        return _flag_cache[key]
    img = None
    p = os.path.join(FLAG_DIR, f"{code}.png")
    if os.path.exists(p):
        try:
            f = Image.open(p).convert("RGBA")
            w = max(1, round(f.width * h / f.height))
            img = f.resize((w, h))
        except Exception:
            img = None
    _flag_cache[key] = img
    return img


def _fmt_delta(delta):
    return f"{abs(delta):,.2f}".replace(",", " ").replace(".", ",")


def _ellipsize(d, text, font, max_w):
    """Matn max_w ga sig'masa, oxiriga "…" qo'yib qisqartiradi."""
    if d.textlength(text, font=font) <= max_w:
        return text
    while text and d.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"


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
    a = min(alpha, 45)                       # oq fon -> yumshoq, nozik soya
    m = blur * 3
    rx0, ry0 = max(x0 - m, 0), max(y0 - m, 0)
    rx1, ry1 = min(x1 + m, img.width), min(y1 + m + dy, img.height)
    sh = Image.new("RGBA", (rx1 - rx0, ry1 - ry0), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        (x0 - rx0, y0 - ry0 + dy, x1 - rx0, y1 - ry0 + dy), radius=radius, fill=(*SHADOW, a))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    img.paste(sh, (rx0, ry0), sh)
    d2 = ImageDraw.Draw(img)
    d2.rounded_rectangle(box, radius=radius, fill=fill)
    d2.rounded_rectangle(box, radius=radius, outline=DIVIDER, width=1)   # nozik chek


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
    elif kind == "rates":                                   # tanga ($ belgili) -> pul/valyuta
        r = s * 0.30
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=lw)
        f = B(int(s * 0.46))
        bb = d.textbbox((0, 0), "$", font=f)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        d.text((cx - tw / 2 - bb[0], cy - th / 2 - bb[1]), "$", font=f, fill=color)
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
    elif kind == "ball":                                    # futbol to'pi
        r = s * 0.30
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=lw)
        d.ellipse((cx - r * 0.16, cy - r * 0.16, cx + r * 0.16, cy + r * 0.16), fill=color)
        for a in range(0, 360, 72):
            rad = math.radians(a - 90)
            d.line((cx, cy, cx + math.cos(rad) * r * 0.62, cy + math.sin(rad) * r * 0.62),
                   fill=color, width=max(1, lw // 2))


def _header(img, W, pad, title, date_label, accent=ACCENT, icon=None):
    _panel(img, (pad, pad, W - pad, pad + 96), 18, CARD)
    d = ImageDraw.Draw(img)
    tx = pad + 30
    if icon:                                                # accent rangli ikonka-chip
        ch = 60
        ix0, iy0 = pad + 22, pad + 18
        _draw_icon(d, icon, (ix0, iy0, ix0 + ch, iy0 + ch), accent)
        tx = ix0 + ch + 20
    # sana (o'ng) -- kichikroq shrift, sarlavhaga yopishmasligi uchun
    f = R(24)
    dw = d.textlength(date_label, font=f) if date_label else 0
    date_x = W - pad - 26 - dw
    if date_label:
        d.text((date_x, pad + 38), date_label, font=f, fill=accent)
    # sarlavha -- sana bilan to'qnashmasligi uchun avtomatik kichrayadi
    avail = date_x - tx - 16 if date_label else (W - pad - 30 - tx)
    tf = B(48)
    for size in (48, 42, 36, 32):
        tf = B(size)
        if d.textlength(title, font=tf) <= avail:
            break
    th = tf.getbbox(title)[3] if hasattr(tf, "getbbox") else 48
    d.text((tx, pad + (96 - th) // 2 - 6), title, font=tf, fill=TEXT)


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
        return ("\u2744", (37, 99, 235))
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
        return (220, 38, 38)       # jazirama -> qizil
    if t >= 30:
        return (234, 88, 12)       # issiq -> to'q sariq
    if t >= 22:
        return (202, 138, 4)       # iliq -> amber
    if t >= 12:
        return TEXT                # mo'tadil -> quyuq
    if t >= 2:
        return (2, 132, 199)       # salqin -> sky-600
    return (37, 99, 235)           # sovuq -> ko'k


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
        _rrect(d, (pad, y, W - pad, y + 44), 12, CARD2)
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
def render_currency_overview_card(date_label, rows, out_path="rates.png", channel_label="", prev=None):
    """rows: [{"code","name","unit","rate","value"}, ...] (USD birinchi).

    prev: {code: oldingi_qiymat} -> kunlik o'zgarish (▲ yashil / ▼ qizil) ko'rsatiladi.
    """
    prev = prev or {}
    W, pad, row_h = 900, 40, 74
    H = pad + 96 + 40 + 44 + len(rows) * row_h + 60
    img, d = _new(W, H)
    _header(img, W, pad, "Valyuta kurslari", date_label, GREEN, "rates")
    y = pad + 96 + 40
    d.text((pad + 4, y), "Markaziy bank rasmiy kursi · so'mda", font=R(22), fill=MUTED)
    y += 44
    f_code, f_val, f_chg = B(34), B(32), B(23)
    chg_right = W - pad - 24
    for r in rows:
        _panel(img, (pad, y, W - pad, y + row_h - 8), 14, CARD, blur=10, dy=4, alpha=85)
        cy = y + (row_h - 8) // 2
        x = pad + 26
        fl = _flag(r["code"], 32)               # bayroq
        if fl:
            img.paste(fl, (x, cy - fl.height // 2), fl)
            x += fl.width + 20
        d.text((x, cy - 21), r["code"], font=f_code, fill=ACCENT)   # KOD (ko'k)
        x += d.textlength(r["code"], font=f_code) + 14
        d.text((x, cy - 20), f"= {r['rate']}", font=f_val, fill=TEXT)  # = qiymat
        # kunlik o'zgarish: rangli farq + yo'nalish uchburchagi (o'ng tomonda)
        val = r.get("value")
        delta = (val - prev[r["code"]]) if (val is not None and r["code"] in prev) else None
        if delta is not None and abs(delta) >= 0.005:
            up = delta > 0
            col = GREEN if up else RED
            txt = _fmt_delta(delta)
            tw = d.textlength(txt, font=f_chg)
            tri = 14
            xs = chg_right - tw - tri - 10
            t = cy - 2
            if up:
                d.polygon([(xs, t + 6), (xs + tri, t + 6), (xs + tri / 2, t - 7)], fill=col)
            else:
                d.polygon([(xs, t - 6), (xs + tri, t - 6), (xs + tri / 2, t + 7)], fill=col)
            d.text((chg_right - tw, cy - 14), txt, font=f_chg, fill=col)
        y += row_h
    _footer(d, W, H, pad, channel_label, "Manba: cbu.uz")
    img.save(out_path)
    return out_path


# ============================================================ 5) DOLLAR (BANKLAR)
def render_currency_card(date_label, cbu_rate, banks, out_path="currency.png",
                         channel_label="", extra_rates=None, usd_value=None, prev_usd=None):
    W, pad, row_h = 900, 40, 50
    nrows = (len(banks) + 1) // 2          # banklar 2 ustunga bo'linadi -> rasm ixcham
    H = pad + 96 + 26 + 42 + 40 + 42 + nrows * row_h + 20 + 70
    img, d = _new(W, H)
    _header(img, W, pad, "Markaziy bank", date_label, ACCENT, "currency")
    y = pad + 96 + 26

    # Rasmiy kurs \u2014 ixcham bitta qator (katta panel emas; batafsili caption'da)
    fl = _flag("USD", 26)
    x = pad + 4
    if fl:
        img.paste(fl, (x, y), fl)
        x += fl.width + 14
    d.text((x, y + 2), "Rasmiy kurs (1 USD):", font=R(23), fill=MUTED)
    x += d.textlength("Rasmiy kurs (1 USD):", font=R(23)) + 12
    d.text((x, y - 2), cbu_rate, font=B(30), fill=TEXT)
    x += d.textlength(cbu_rate, font=B(30)) + 14
    if usd_value is not None and prev_usd is not None and abs(usd_value - prev_usd) >= 0.005:
        delta = usd_value - prev_usd
        col = GREEN if delta > 0 else RED
        d.text((x, y + 1), _fmt_delta(delta), font=B(24), fill=col)
    y += 42

    valid = [b for b in banks if b.get("sell") and b.get("buy")]
    max_buy = max((b["buy"] for b in valid), default=None)
    min_sell = min((b["sell"] for b in valid), default=None)

    d.text((pad + 4, y), "Tijorat banklarida \u2014 olish / sotish", font=R(23), fill=MUTED)
    y += 40

    # Banklar jadvali \u2014 2 ustun (ixcham). Yashil = max olish, ko'k = min sotish.
    # (Izoh post matnida -> rasm qisqaroq.)
    colw = (W - 2 * pad - 24) // 2
    cols_x = [pad, pad + colw + 24]
    f_hs = R(22)
    f_n, f_nb = R(26), B(26)
    for cx in cols_x:
        sell_rx = cx + colw - 12
        buy_rx = sell_rx - 110
        d.text((cx + 12, y), "Bank", font=f_hs, fill=MUTED)
        d.text((buy_rx - d.textlength("Olish", font=f_hs), y), "Olish", font=f_hs, fill=GREEN)
        d.text((sell_rx - d.textlength("Sotish", font=f_hs), y), "Sotish", font=f_hs, fill=ACCENT)
    y += 34
    d.line((pad, y, W - pad, y), fill=DIVIDER, width=2)
    y += 8
    table_top = y
    for i, b in enumerate(banks):
        cx = cols_x[i // nrows]
        ry = table_top + (i % nrows) * row_h
        sell_rx = cx + colw - 12
        buy_rx = sell_rx - 110
        name_w = (buy_rx - 92) - (cx + 12)
        is_bb = b.get("buy") == max_buy
        is_bs = b.get("sell") == min_sell
        if is_bb or is_bs:
            _rrect(d, (cx, ry - 2, cx + colw, ry + row_h - 8), 9, CARD2)
        d.text((cx + 12, ry + 8), _ellipsize(d, b["bank"], f_n, name_w), font=f_n, fill=TEXT)
        buy_s, sell_s = fmt(b.get("buy")), fmt(b.get("sell"))
        fb = f_nb if is_bb else f_n
        fs = f_nb if is_bs else f_n
        d.text((buy_rx - d.textlength(buy_s, font=fb), ry + 8), buy_s,
               font=fb, fill=(GREEN if is_bb else TEXT))
        d.text((sell_rx - d.textlength(sell_s, font=fs), ry + 8), sell_s,
               font=fs, fill=(ACCENT if is_bs else TEXT))
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
    _header(img, W, pad, "Kun maslahati", "", TEAL, "advice")   # sana yo'q
    y = pad + 96 + 40

    klbl = kind.upper()
    kw = d.textlength(klbl, font=B(22))
    _rrect(d, (pad, y, pad + kw + 40, y + 42), 21, CARD2)
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


# ============================================================ 7) BOZOR (oltin + kripto)
_MK_COLOR = {"gold": GOLD, "btc": (234, 88, 12), "eth": (79, 70, 229),
             "ton": (0, 136, 204), "bnb": (216, 160, 8),
             "sol": PURPLE, "xrp": (51, 65, 85)}


def render_market_card(date_label, rows, out_path="market.png", channel_label=""):
    """rows: [{"name","sub","value","chg"(% yoki None),"kind"}]."""
    W, pad, row_h, gap = 900, 40, 96, 16
    H = pad + 96 + 40 + len(rows) * (row_h + gap) + 50
    img, d = _new(W, H)
    _header(img, W, pad, "Bozor", date_label, GOLD, "rates")
    y = pad + 96 + 40
    for r in rows:
        _panel(img, (pad, y, W - pad, y + row_h), 16, CARD, blur=12, dy=5, alpha=90)
        col = _MK_COLOR.get(r.get("kind"), ACCENT)
        cyc = y + row_h // 2
        d.ellipse((pad + 24, cyc - 9, pad + 42, cyc + 9), fill=col)
        d.text((pad + 64, y + 18), r["name"], font=B(34), fill=ACCENT)
        d.text((pad + 64, y + 60), r.get("sub", ""), font=R(22), fill=MUTED)
        pf = B(40)
        pw = d.textlength(r["value"], font=pf)
        d.text((W - pad - 30 - pw, y + 16), r["value"], font=pf, fill=TEXT)
        chg = r.get("chg")
        if chg is not None:
            up = chg >= 0
            ccol = GREEN if up else RED
            txt = f"{abs(chg):.2f}%".replace(".", ",")
            cf = B(24)
            cw = d.textlength(txt, font=cf)
            tx = W - pad - 30 - cw
            ty = y + 62
            tri = 13
            bx = tx - tri - 10
            if up:
                d.polygon([(bx, ty + 16), (bx + tri, ty + 16), (bx + tri / 2, ty + 3)], fill=ccol)
            else:
                d.polygon([(bx, ty + 5), (bx + tri, ty + 5), (bx + tri / 2, ty + 18)], fill=ccol)
            d.text((tx, ty), txt, font=cf, fill=ccol)
        y += row_h + gap
    _footer(d, W, H, pad, channel_label, "Manba: gold-api, CoinGecko")
    img.save(out_path)
    return out_path


# ============================================================ 8) FUTBOL (JCH-2026)
_badge_cache: dict = {}


def _badge(url, h):
    """Jamoa logosini (URL) yuklab, balandlik bo'yicha o'lchaydi (keshlanadi)."""
    if not url:
        return None
    key = (url, h)
    if key in _badge_cache:
        return _badge_cache[key]
    img = None
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            f = Image.open(io.BytesIO(r.content)).convert("RGBA")
            w = max(1, round(f.width * h / f.height))
            img = f.resize((w, h))
    except Exception:
        img = None
    _badge_cache[key] = img
    return img


_TEAM_SHORT = {
    "Cape Verde Islands": "Cape Verde", "Bosnia and Herzegovina": "Bosnia",
    "Trinidad and Tobago": "Trinidad", "Dominican Republic": "Dominican R.",
    "United Arab Emirates": "UAE", "Central African Republic": "CAR",
    "Republic of Ireland": "Ireland", "Korea Republic": "South Korea",
}


def _tname(n, maxlen=15):
    n = _TEAM_SHORT.get(n, n or "")
    return n if len(n) <= maxlen else n[:maxlen - 1] + "…"


def _pitch_header(img, W, pad, title, date_label):
    """Futbol kartalari uchun stadion-maydon uslubidagi sarlavha banneri."""
    h = 96
    bw = W - 2 * pad
    banner = Image.new("RGB", (bw, h))
    bd = ImageDraw.Draw(banner)
    for yy in range(h):                       # maydon yashil gradienti
        t = yy / (h - 1)
        bd.line((0, yy, bw, yy), fill=(int(16 + 8 * t), int(82 - 36 * t), int(46 - 22 * t)))
    line_col = (90, 140, 108)                 # nozik maydon chiziqlari (grassga yaqin)
    bd.line((bw // 2, 6, bw // 2, h - 6), fill=line_col, width=2)
    bd.ellipse((bw // 2 - 28, h // 2 - 28, bw // 2 + 28, h // 2 + 28), outline=line_col, width=2)
    bd.line((6, h // 2, bw - 6, h // 2), fill=line_col, width=1)
    glow = Image.new("RGBA", (bw, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for gx in (70, bw - 70):
        gd.ellipse((gx - 85, -65, gx + 85, 48), fill=(255, 255, 235, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(26))
    banner = Image.alpha_composite(banner.convert("RGBA"), glow).convert("RGB")
    mask = Image.new("L", (bw, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, bw - 1, h - 1), 18, fill=255)
    img.paste(banner, (pad, pad), mask)
    d = ImageDraw.Draw(img)
    _draw_icon(d, "ball", (pad + 22, pad + 18, pad + 82, pad + 78), (255, 255, 255))
    d.text((pad + 96, pad + 22), title, font=B(46), fill=(255, 255, 255))
    f = R(24)
    dw = d.textlength(date_label, font=f)
    d.text((W - pad - 26 - dw, pad + 38), date_label, font=f, fill=(190, 235, 205))


def _match_row(img, d, y, row_h, m, center):
    """Bitta o'yin qatori: vaqt | [logo] Uy — Mehmon [logo]. center = '—' yoki hisob."""
    W, pad = 900, 40
    mid = W // 2
    cy = y + (row_h - 8) // 2
    nf, cf = R(26), B(28)
    if m.get("time"):
        d.text((pad + 16, cy - 15), m["time"], font=B(25), fill=ACCENT)
    hx = pad + 108
    hb = _badge(m.get("hb"), 34)
    if hb:
        img.paste(hb, (pad + 108, cy - hb.height // 2), hb)
        hx = pad + 108 + hb.width + 10
    d.text((hx, cy - 15), _tname(m.get("home")), font=nf, fill=TEXT)
    cw = d.textlength(center, font=cf)
    d.text((mid - cw / 2, cy - 16), center, font=cf, fill=TEXT)
    an = _tname(m.get("away"))
    x_end = W - pad - 16
    ab = _badge(m.get("ab"), 34)
    if ab:
        img.paste(ab, (x_end - ab.width, cy - ab.height // 2), ab)
        x_end -= ab.width + 10
    d.text((x_end - d.textlength(an, font=nf), cy - 15), an, font=nf, fill=TEXT)


def render_fixtures_card(date_label, matches, out_path="fixtures.png", channel_label="", comp="JCH-2026"):
    matches = [m for m in (matches or []) if m.get("home") and m.get("away")]   # bo'sh jamoa -> chizmaymiz
    W, pad, row_h = 900, 40, 70
    H = pad + 96 + 40 + 40 + (len(matches) or 1) * row_h + 50
    img, d = _new(W, H)
    _pitch_header(img, W, pad, "Bugungi o'yinlar", date_label)
    y = pad + 96 + 40
    d.text((pad + 4, y), f"{comp} · vaqtlar Toshkent bo'yicha", font=R(22), fill=MUTED)
    y += 40
    if not matches:
        d.text((pad + 6, y), "Yaqin kunlarda o'yin yo'q.", font=R(26), fill=MUTED)
    for m in matches:
        _panel(img, (pad, y, W - pad, y + row_h - 8), 12, CARD, blur=10, dy=4, alpha=80)
        _match_row(img, d, y, row_h, m, "—")
        y += row_h
    _footer(d, W, H, pad, channel_label, "Manba: football-data.org")
    img.save(out_path)
    return out_path


def render_results_card(date_label, matches, out_path="results.png", channel_label="", comp="JCH-2026"):
    matches = [m for m in (matches or []) if m.get("home") and m.get("away")]   # bo'sh jamoa -> chizmaymiz
    W, pad, row_h = 900, 40, 70
    H = pad + 96 + 40 + 40 + (len(matches) or 1) * row_h + 50
    img, d = _new(W, H)
    _pitch_header(img, W, pad, "Natijalar", date_label)
    y = pad + 96 + 40
    d.text((pad + 4, y), f"{comp} · so'nggi o'yinlar hisobi", font=R(22), fill=MUTED)
    y += 40
    if not matches:
        d.text((pad + 6, y), "So'nggi natijalar topilmadi.", font=R(26), fill=MUTED)
    for m in matches:
        _panel(img, (pad, y, W - pad, y + row_h - 8), 12, CARD, blur=10, dy=4, alpha=80)
        score = f"{m.get('hs', '')} : {m.get('as', '')}"
        _match_row(img, d, y, row_h, m, score)
        y += row_h
    _footer(d, W, H, pad, channel_label, "Manba: football-data.org")
    img.save(out_path)
    return out_path


def render_standings_card(date_label, groups, out_path="standings.png", channel_label="", comp="JCH-2026"):
    W, pad = 900, 32
    GAP = 14                    # ustunlar orasidagi bo'shliq
    GRP_HDR = 44                # guruh sarlavhasi balandligi
    COL_HDR = 28                # ustun nomlari qatori
    DARK_GRN = (15, 79, 43)    # guruh sarlavhasi rangi
    PROMO_GRN = (240, 253, 244) # o'tuvchi qatorlar foni (yashil och)
    PROMO_BAR = (16, 185, 129)  # chap aksent chiziq rangi
    ALT = (248, 250, 252)       # juft qator foni (alternatsiya)
    is_single = len(groups) == 1

    # ---- yagona guruh (CL, PL va h.k.) — to'liq kenglik ----
    if is_single:
        name, rows = next(iter(groups.items()))
        ROW_H = 46
        H = pad + 96 + 18 + 28 + GRP_HDR + COL_HDR + len(rows) * ROW_H + 14 + 48
        img, d = _new(W, H)
        _pitch_header(img, W, pad, "Turnir jadvali", date_label)

        y = pad + 96 + 10
        d.text((pad + 4, y), f"{comp} · ochko jadvali", font=R(22), fill=MUTED)
        y += 28

        # Guruh sarlavhasi — to'q yashil band
        d.rounded_rectangle((pad, y, W - pad, y + GRP_HDR), radius=10, fill=DARK_GRN)
        gname = name.replace("GROUP_", "Guruh ").replace("Group", "Guruh").replace("League phase", "Guruh bosqichi")
        d.text((pad + 18, y + 9), gname, font=B(28), fill=(255, 255, 255))
        y += GRP_HDR

        # Ustun nomlari
        cx_o   = W - pad - 132
        cx_gd  = W - pad - 76
        cx_pts = W - pad - 18
        d.text((pad + 66, y + 5),  "Jamoa",  font=R(17), fill=MUTED)
        d.text((cx_o  - d.textlength("O",   font=R(17)) / 2, y + 5), "O",   font=R(17), fill=MUTED)
        d.text((cx_gd - d.textlength("+/-", font=R(17)) / 2, y + 5), "+/-", font=R(17), fill=MUTED)
        d.text((cx_pts - d.textlength("B",  font=R(17)) / 2, y + 5), "B",   font=R(17), fill=MUTED)
        y += COL_HDR

        for i, r in enumerate(rows):
            rank = int(r.get("rank") or 99)
            # Tur bosqichlari: >=1-8 to'g'ridan-to'g'ri, 9-24 pley-off, 25+ tushadi
            promo = rank <= 8
            playoff = 9 <= rank <= 24
            row_fill = PROMO_GRN if promo else (245, 247, 255) if playoff else (CARD if i % 2 == 0 else ALT)
            d.rounded_rectangle((pad, y, W - pad, y + ROW_H - 2), radius=8, fill=row_fill)
            bar_col = PROMO_BAR if promo else ACCENT if playoff else None
            if bar_col:
                d.rounded_rectangle((pad, y, pad + 5, y + ROW_H - 2), radius=4, fill=bar_col)

            cy = y + ROW_H // 2
            # Raqam (o'rin)
            rk_str = str(rank)
            rk_col = (202, 138, 4) if rank == 1 else (148, 163, 184) if rank == 2 else (205, 92, 92) if rank == 3 else MUTED
            rk_w = d.textlength(rk_str, font=B(22))
            d.text((pad + 8 + (26 - rk_w) / 2, cy - 12), rk_str, font=B(22), fill=rk_col)
            # Bayroq
            tx = pad + 42
            bb = _badge(r.get("badge"), 30)
            if bb:
                img.paste(bb, (pad + 40, cy - bb.height // 2), bb)
                tx = pad + 40 + bb.width + 8
            # Jamoa nomi
            max_nw = cx_o - tx - 16
            d.text((tx, cy - 13), _ellipsize(d, _tname(r.get("team"), 20), R(24), max_nw), font=R(24), fill=TEXT)
            # Statistikalar (markazlashgan)
            p_str = str(r.get("p", ""))
            d.text((cx_o  - d.textlength(p_str,  font=R(22)) / 2, cy - 12), p_str,  font=R(22), fill=MUTED)
            gd_val = r.get("gd") or 0
            gd_str = ("+" if gd_val > 0 else "") + str(gd_val)
            gd_col = GREEN if gd_val > 0 else RED if gd_val < 0 else MUTED
            d.text((cx_gd - d.textlength(gd_str, font=R(22)) / 2, cy - 12), gd_str, font=R(22), fill=gd_col)
            pts_str = str(r.get("pts", ""))
            d.text((cx_pts - d.textlength(pts_str, font=B(26)) / 2, cy - 13), pts_str, font=B(26), fill=TEXT)
            y += ROW_H

        _footer(d, W, H, pad, channel_label, "Manba: football-data.org")
        img.save(out_path)
        return out_path

    # ---- ko'p guruh (JCH va h.k.) — 2 ustunli grid ----
    colw = (W - 2 * pad - GAP) // 2
    ROW_H = 38
    SUBPAD = 4

    def gh(n):
        return GRP_HDR + COL_HDR + n * ROW_H + 18

    colh, colgroups = [0, 0], [[], []]
    for name, rows in groups.items():
        c = 0 if colh[0] <= colh[1] else 1
        colgroups[c].append((name, rows))
        colh[c] += gh(len(rows))
    H = pad + 96 + 18 + 28 + (max(colh) if any(colh) else 60) + 50
    img, d = _new(W, H)
    _pitch_header(img, W, pad, "Turnir jadvali", date_label)

    y0 = pad + 96 + 10
    d.text((pad + 4, y0), f"{comp} · ochko jadvali", font=R(22), fill=MUTED)
    y0 += 28

    cx_pts_off = colw - 16          # o'ng chekkadan oʻrin (ochko)
    cx_gd_off  = colw - 62
    cx_o_off   = colw - 112

    for cx, gc in [(pad, colgroups[0]), (pad + colw + GAP, colgroups[1])]:
        y = y0
        for gname_raw, rows in gc:
            gname = (gname_raw.replace("GROUP_", "Guruh ")
                               .replace("Group", "Guruh")
                               .replace("League phase", "Guruh bosqichi"))

            # Guruh sarlavhasi
            d.rounded_rectangle((cx, y, cx + colw, y + GRP_HDR), radius=10, fill=DARK_GRN)
            d.text((cx + 14, y + 9), gname, font=B(26), fill=(255, 255, 255))
            # Ustun nomlari
            y += GRP_HDR
            d.text((cx + cx_o_off  - d.textlength("O",   font=R(17)) / 2, y + 5), "O",   font=R(17), fill=MUTED)
            d.text((cx + cx_gd_off - d.textlength("+/-", font=R(17)) / 2, y + 5), "+/-", font=R(17), fill=MUTED)
            d.text((cx + cx_pts_off - d.textlength("B",  font=R(17)) / 2, y + 5), "B",  font=R(17), fill=MUTED)
            y += COL_HDR

            for i, r in enumerate(rows):
                rank = int(r.get("rank") or 99)
                top = rank <= 2
                row_fill = PROMO_GRN if top else (CARD if i % 2 == 0 else ALT)
                d.rounded_rectangle((cx + SUBPAD, y, cx + colw - SUBPAD, y + ROW_H - 2), radius=7, fill=row_fill)
                if top:
                    d.rounded_rectangle((cx + SUBPAD, y, cx + SUBPAD + 4, y + ROW_H - 2), radius=4, fill=PROMO_BAR)

                cy = y + ROW_H // 2
                rk_str = str(rank)
                rk_col = (202, 138, 4) if rank == 1 else (148, 163, 184) if rank == 2 else MUTED
                rk_w = d.textlength(rk_str, font=B(20))
                d.text((cx + SUBPAD + 6 + (20 - rk_w) / 2, cy - 11), rk_str, font=B(20), fill=rk_col)
                tx = cx + SUBPAD + 32
                bb = _badge(r.get("badge"), 26)
                if bb:
                    img.paste(bb, (cx + SUBPAD + 30, cy - bb.height // 2), bb)
                    tx = cx + SUBPAD + 30 + bb.width + 6
                max_nw = cx + cx_o_off - 18 - tx
                d.text((tx, cy - 11), _ellipsize(d, _tname(r.get("team"), 14), R(21), max_nw), font=R(21), fill=TEXT)

                p_str = str(r.get("p", ""))
                d.text((cx + cx_o_off  - d.textlength(p_str,  font=R(19)) / 2, cy - 11), p_str,  font=R(19), fill=MUTED)
                gd_val = r.get("gd") or 0
                gd_str = ("+" if gd_val > 0 else "") + str(gd_val)
                gd_col = GREEN if gd_val > 0 else RED if gd_val < 0 else MUTED
                d.text((cx + cx_gd_off - d.textlength(gd_str, font=R(19)) / 2, cy - 11), gd_str, font=R(19), fill=gd_col)
                pts_str = str(r.get("pts", ""))
                d.text((cx + cx_pts_off - d.textlength(pts_str, font=B(22)) / 2, cy - 12), pts_str, font=B(22), fill=TEXT)
                y += ROW_H
            y += 18

    _footer(d, W, H, pad, channel_label, "Manba: football-data.org")
    img.save(out_path)
    return out_path


# ============================================================ 9) GOOOL (real-vaqt)
def render_goal_card(m, out_path="goal.png", channel_label=""):
    """Gol grafikasi: ko'k fon, stadion nuri, to'p, katta GOOOL + hisob."""
    W, H, pad = 900, 600, 40
    top, bot = (33, 96, 240), (16, 36, 108)
    col = Image.new("RGB", (1, H))
    px = col.load()
    for y in range(H):
        t = y / (H - 1)
        px[0, y] = (round(top[0] + (bot[0] - top[0]) * t), round(top[1] + (bot[1] - top[1]) * t),
                    round(top[2] + (bot[2] - top[2]) * t))
    img = col.resize((W, H))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for gx in (155, W - 155):
        gd.ellipse((gx - 140, -130, gx + 140, 120), fill=(255, 255, 255, 85))
    glow = glow.filter(ImageFilter.GaussianBlur(55))
    img.paste(glow, (0, 0), glow)
    d = ImageDraw.Draw(img)
    # katta to'p
    bs = 130
    _draw_icon(d, "ball", (W // 2 - bs // 2, 56, W // 2 + bs // 2, 56 + bs), (255, 255, 255))
    # GOOOL
    gf = B(120)
    txt = "GOOOL"
    tw = d.textlength(txt, font=gf)
    d.text((W // 2 - tw / 2, 222), txt, font=gf, fill=(255, 255, 255),
           stroke_width=5, stroke_fill=(14, 30, 86))
    # hisob qatori (markazlashgan): [bayroq] Uy  H : M  Mehmon [bayroq]
    nf, sf = B(36), B(58)
    hn, an = _tname(m.get("home"), 15), _tname(m.get("away"), 15)
    score = f"{m.get('hs', 0)}  :  {m.get('as', 0)}"
    hb, ab = _badge(m.get("hb"), 46), _badge(m.get("ab"), 46)
    GAP = 18
    hw, aw, sw = d.textlength(hn, font=nf), d.textlength(an, font=nf), d.textlength(score, font=sf)
    total = (hb.width + GAP if hb else 0) + hw + GAP + sw + GAP + aw + (GAP + ab.width if ab else 0)
    x = (W - total) / 2
    yr = 410
    cyr = yr + 26
    if hb:
        img.paste(hb, (int(x), cyr - hb.height // 2), hb)
        x += hb.width + GAP
    d.text((x, yr + 12), hn, font=nf, fill=(236, 242, 255))
    x += hw + GAP
    d.text((x, yr), score, font=sf, fill=(255, 255, 255))
    x += sw + GAP
    d.text((x, yr + 12), an, font=nf, fill=(236, 242, 255))
    x += aw + GAP
    if ab:
        img.paste(ab, (int(x), cyr - ab.height // 2), ab)
    if m.get("minute"):
        mt = f"{m['minute']}-daqiqa"
        mf = B(30)
        d.text((W // 2 - d.textlength(mt, font=mf) / 2, 500), mt, font=mf, fill=(195, 214, 255))
    if channel_label:
        d.text((pad, H - 48), channel_label, font=R(22), fill=(205, 218, 255))
    img.save(out_path)
    return out_path


# ============================================================ 10) BLOG / IQTIBOS kartasi
def render_blog_card(text, channel_label="", out_path="blog.png", accent=PURPLE):
    """Blog/iqtibos matnidan chiroyli, o'qiladigan karta (PNG).

    Matn uzunligiga qarab shrift va balandlik avtomatik moslashadi. Faqat Pillow ->
    o'zbekcha matn 100% aniq (AI rasm matnni buzadi), bepul va brendga mos.
    """
    text = (text or "").strip()
    W, pad = 1000, 60
    left = pad + 48                       # matn chap cheki (accent chiziq uchun joy)
    right = W - pad - 36
    max_w = right - left
    n = len(text)                         # uzunlik -> shrift (uzun bo'lsa kichikroq)
    fsize = 44 if n < 180 else 38 if n < 320 else 33 if n < 520 else 29
    font = R(fsize)
    line_h = round(fsize * 1.46)
    lines = []                            # abzaslarni saqlab, har birini alohida o'raymiz
    for para in text.split("\n"):
        if para.strip():
            lines += _wrap(para, font, max_w)
        else:
            lines.append("")
    quote_top = pad + 4
    text_top = quote_top + 96
    text_h = len(lines) * line_h
    H = text_top + text_h + 78 + pad
    img, d = _new(W, H)
    _panel(img, (pad - 16, pad - 16, W - pad + 16, H - pad + 16), 30, CARD)
    d.text((left - 8, quote_top - 26), "“", font=B(130), fill=accent)   # dekor tirnoq
    y = text_top
    for ln in lines:
        if ln:
            d.text((left, y), ln, font=font, fill=TEXT)
        y += line_h
    d.rounded_rectangle((pad + 10, text_top + 2, pad + 16, y - (line_h - fsize)),
                        radius=3, fill=accent)                                # chap accent chiziq
    fy = y + 18
    d.line((left, fy, right, fy), fill=DIVIDER, width=2)
    if channel_label:
        d.text((left, fy + 18), channel_label, font=B(28), fill=MUTED)
    img.save(out_path)
    return out_path


if __name__ == "__main__":
    import sys
    out = os.path.join(HERE, "test_out")
    os.makedirs(out, exist_ok=True)
    dl = "30-iyun, 2026"

    # --- Standings test (JCH ko'p guruh) ---
    if "standings" in sys.argv or "all" in sys.argv or len(sys.argv) == 1:
        jch_groups = {
            "Group A": [
                {"rank": 1, "team": "Meksika",      "badge": None, "p": 3, "gd":  6, "pts": 9},
                {"rank": 2, "team": "JAR",           "badge": None, "p": 3, "gd": -1, "pts": 4},
                {"rank": 3, "team": "Janubiy Koreya","badge": None, "p": 3, "gd": -1, "pts": 3},
                {"rank": 4, "team": "Chexiya",       "badge": None, "p": 3, "gd": -4, "pts": 1},
            ],
            "Group B": [
                {"rank": 1, "team": "Shveytsariya", "badge": None, "p": 3, "gd":  4, "pts": 7},
                {"rank": 2, "team": "Kanada",        "badge": None, "p": 3, "gd":  5, "pts": 4},
                {"rank": 3, "team": "Bosniya",       "badge": None, "p": 3, "gd": -1, "pts": 4},
                {"rank": 4, "team": "Qatar",         "badge": None, "p": 3, "gd": -8, "pts": 1},
            ],
            "Group C": [
                {"rank": 1, "team": "Braziliya",  "badge": None, "p": 3, "gd":  6, "pts": 7},
                {"rank": 2, "team": "Marokash",   "badge": None, "p": 3, "gd":  3, "pts": 7},
                {"rank": 3, "team": "Shotlandiya","badge": None, "p": 3, "gd": -3, "pts": 3},
                {"rank": 4, "team": "Gaiti",      "badge": None, "p": 3, "gd": -6, "pts": 0},
            ],
            "Group D": [
                {"rank": 1, "team": "AQSH",      "badge": None, "p": 3, "gd":  4, "pts": 6},
                {"rank": 2, "team": "Avstraliya","badge": None, "p": 3, "gd":  0, "pts": 4},
                {"rank": 3, "team": "Paragvay",  "badge": None, "p": 3, "gd": -2, "pts": 4},
                {"rank": 4, "team": "Turkiya",   "badge": None, "p": 3, "gd": -2, "pts": 3},
            ],
        }
        p = render_standings_card(dl, jch_groups, f"{out}/standings_jch.png", "@FutbolUz25", "JCH-2026")
        print(f"JCH jadval:  {p}")

    # --- Standings test (CL yagona guruh) ---
    if "cl" in sys.argv or "all" in sys.argv or len(sys.argv) == 1:
        cl_rows = [
            {"rank":  1, "team": "Arsenal FC",       "badge": None, "p": 8, "gd": 19, "pts": 24},
            {"rank":  2, "team": "FC Bayern M.",      "badge": None, "p": 8, "gd": 14, "pts": 21},
            {"rank":  3, "team": "Liverpool FC",      "badge": None, "p": 8, "gd": 12, "pts": 18},
            {"rank":  4, "team": "Tottenham H.",      "badge": None, "p": 8, "gd": 10, "pts": 17},
            {"rank":  5, "team": "FC Barcelona",      "badge": None, "p": 8, "gd":  8, "pts": 16},
            {"rank":  6, "team": "Chelsea FC",        "badge": None, "p": 8, "gd":  7, "pts": 16},
            {"rank":  7, "team": "Sporting CL.",      "badge": None, "p": 8, "gd":  6, "pts": 16},
            {"rank":  8, "team": "Manchester C.",     "badge": None, "p": 8, "gd":  6, "pts": 16},
            {"rank":  9, "team": "Real Madrid",       "badge": None, "p": 8, "gd":  9, "pts": 15},
            {"rank": 10, "team": "FC Internazionale", "badge": None, "p": 8, "gd":  8, "pts": 15},
            {"rank": 11, "team": "Paris Saint-G.",    "badge": None, "p": 8, "gd": 10, "pts": 14},
            {"rank": 12, "team": "Newcastle Utd",     "badge": None, "p": 8, "gd": 10, "pts": 14},
            {"rank": 13, "team": "Juventus FC",       "badge": None, "p": 8, "gd":  4, "pts": 13},
            {"rank": 14, "team": "Club Atletico",     "badge": None, "p": 8, "gd":  2, "pts": 13},
            {"rank": 15, "team": "Atalanta BC",       "badge": None, "p": 8, "gd":  0, "pts": 13},
            {"rank": 16, "team": "Bayer 04 Lev.",     "badge": None, "p": 8, "gd": -1, "pts": 12},
            {"rank": 25, "team": "Olympique M.",      "badge": None, "p": 8, "gd": -3, "pts":  9},
            {"rank": 26, "team": "Paphos FC",         "badge": None, "p": 8, "gd": -3, "pts":  9},
            {"rank": 35, "team": "Villarreal CF",     "badge": None, "p": 8, "gd":-13, "pts":  1},
            {"rank": 36, "team": "FK Kairat",         "badge": None, "p": 8, "gd":-15, "pts":  1},
        ]
        p = render_standings_card(dl, {"League phase": cl_rows},
                                  f"{out}/standings_cl.png", "@FutbolUz25", "Chempionlar ligasi")
        print(f"CL jadval:   {p}")
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
