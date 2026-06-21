"""
Kunlik digest uchun rangli info-card (PNG) yasovchi modul.

Telegram matnli postda rang yo'q, shuning uchun ob-havo va valyuta jadvalini
chiroyli rasmga aylantiramiz: eng arzon SOTADIGAN va eng qimmat OLADIGAN banklar
ranglar bilan ajratiladi. Rasm sendPhoto orqali kanalga yuboriladi.

Faqat Pillow kerak (pip install Pillow). Brauzer/headless kerak emas — GitHub
Actions ubuntu-latest'da to'g'ridan-to'g'ri ishlaydi.
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
GREEN     = (52, 211, 153)    # emerald-400  -> eng arzon sotadigan
GOLD      = (251, 191, 36)    # amber-400    -> eng qimmat oladigan
DIVIDER   = (51, 65, 85)

# Shriftlar loyiha ichidagi fonts/ papkasidan yuklanadi (Windows/Mac/Linux'da bir xil).
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIRS = [
    os.path.join(HERE, "fonts"),                 # loyiha ichidagi (asosiy)
    "/usr/share/fonts/truetype/dejavu",          # Linux / GitHub Actions
    r"C:\Windows\Fonts",                          # Windows zaxira
]


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    # oxirgi chora: tizimdan nomi bo'yicha qidirish
    return ImageFont.truetype(name, size)


# Ob-havo kodi -> (belgi, rang)
WEATHER_GLYPH = {
    "ochiq":      ("\u2600", GOLD),       # ☀
    "bulut":      ("\u2601", MUTED),      # ☁
    "yomg'ir":    ("\u2602", ACCENT),     # ☂ (yomg'ir o'rnida soyabon belgisi)
    "qor":        ("\u2744", (191, 219, 254)),  # ❄
    "tuman":      ("\u2248", MUTED),      # ≈
    "momaqaldiroq": ("\u26A1", GOLD),     # ⚡
}


def _glyph_for(desc: str):
    d = desc.lower()
    if "qor" in d:
        return WEATHER_GLYPH["qor"]
    if "yomg'ir" in d or "jala" in d:
        return WEATHER_GLYPH["yomg'ir"]
    if "momaqaldiroq" in d:
        return WEATHER_GLYPH["momaqaldiroq"]
    if "tuman" in d:
        return WEATHER_GLYPH["tuman"]
    if "bulut" in d:
        return WEATHER_GLYPH["bulut"]
    return WEATHER_GLYPH["ochiq"]


def render_card(
    date_label: str,
    weather: dict[str, tuple],   # region -> (temp:float, desc:str)
    cbu_rate: str,
    banks: list[dict],           # [{"bank":..., "buy":int, "sell":int}, ...]
    out_path: str = "digest.png",
    channel_label: str = "",
) -> str:
    W = 1000
    pad = 40

    # Shriftlar
    f_title  = _font("DejaVuSans-Bold.ttf", 46)
    f_date   = _font("DejaVuSans.ttf", 24)
    f_h2     = _font("DejaVuSans-Bold.ttf", 30)
    f_region = _font("DejaVuSans.ttf", 22)
    f_temp   = _font("DejaVuSans-Bold.ttf", 30)
    f_glyph  = _font("DejaVuSans.ttf", 30)
    f_row    = _font("DejaVuSans.ttf", 24)
    f_row_b  = _font("DejaVuSans-Bold.ttf", 24)
    f_small  = _font("DejaVuSans.ttf", 20)

    # --- Balandlikni hisoblash ---
    n_w_rows = (len(weather) + 2) // 3          # 3 ustun
    weather_h = 70 + n_w_rows * 92
    bank_h = 70 + 56 + len(banks) * 46 + 70      # sarlavha + cbu + qatorlar + legend
    H = 150 + weather_h + 40 + bank_h + 60

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    def rrect(box, radius, fill):
        d.rounded_rectangle(box, radius=radius, fill=fill)

    # ---- Header ----
    rrect((pad, pad, W - pad, pad + 90), 18, CARD)
    d.text((pad + 28, pad + 16), "Bugungi digest", font=f_title, fill=TEXT)
    tw = d.textlength(date_label, font=f_date)
    d.text((W - pad - 28 - tw, pad + 34), date_label, font=f_date, fill=ACCENT)

    y = pad + 90 + 34

    # ---- OB-HAVO ----
    d.text((pad + 4, y), "Ob-havo \u2014 viloyatlar bo'yicha", font=f_h2, fill=TEXT)
    y += 50
    col_w = (W - 2 * pad - 2 * 16) // 3
    items = list(weather.items())
    for i, (region, (temp, desc)) in enumerate(items):
        col = i % 3
        row = i // 3
        x0 = pad + col * (col_w + 16)
        y0 = y + row * 92
        rrect((x0, y0, x0 + col_w, y0 + 78), 14, CARD)
        d.text((x0 + 16, y0 + 12), region, font=f_region, fill=MUTED)
        glyph, gcol = _glyph_for(desc)
        d.text((x0 + 16, y0 + 40), f"{round(temp)}\u00b0", font=f_temp, fill=TEXT)
        tw = d.textlength(glyph, font=f_glyph)
        d.text((x0 + col_w - 16 - tw, y0 + 36), glyph, font=f_glyph, fill=gcol)

    y = y + n_w_rows * 92 + 26

    # ---- VALYUTA ----
    d.text((pad + 4, y), "Dollar kursi \u2014 banklar", font=f_h2, fill=TEXT)
    y += 50

    # CBU rasmiy kursi
    rrect((pad, y, W - pad, y + 44), 12, CARD2)
    d.text((pad + 18, y + 9), "Markaziy bank (rasmiy)", font=f_small, fill=MUTED)
    tw = d.textlength(cbu_rate, font=f_row_b)
    d.text((W - pad - 18 - tw, y + 8), cbu_rate, font=f_row_b, fill=TEXT)
    y += 58

    # Eng arzon sotadigan (min sell) va eng qimmat oladigan (max buy)
    valid = [b for b in banks if b.get("sell") and b.get("buy")]
    min_sell = min(b["sell"] for b in valid) if valid else None
    max_buy = max(b["buy"] for b in valid) if valid else None

    # Jadval sarlavhasi
    c_bank = pad + 18
    c_buy  = pad + 430
    c_sell = pad + 660
    d.text((c_bank, y), "Bank", font=f_small, fill=MUTED)
    d.text((c_buy, y), "Olish", font=f_small, fill=MUTED)
    d.text((c_sell, y), "Sotish", font=f_small, fill=MUTED)
    y += 32
    d.line((pad, y, W - pad, y), fill=DIVIDER, width=2)
    y += 6

    for b in banks:
        rh = 46
        is_best_buy = b.get("buy") == max_buy
        is_best_sell = b.get("sell") == min_sell
        # qator foni
        if is_best_buy or is_best_sell:
            rrect((pad, y, W - pad, y + rh - 6), 10, CARD)
        d.text((c_bank, y + 8), b["bank"], font=f_row, fill=TEXT)

        buy_s = f"{b['buy']:,}".replace(",", " ") if b.get("buy") else "\u2014"
        sell_s = f"{b['sell']:,}".replace(",", " ") if b.get("sell") else "\u2014"

        buy_col = GOLD if is_best_buy else TEXT
        sell_col = GREEN if is_best_sell else TEXT
        d.text((c_buy, y + 8), buy_s, font=(f_row_b if is_best_buy else f_row), fill=buy_col)
        d.text((c_sell, y + 8), sell_s, font=(f_row_b if is_best_sell else f_row), fill=sell_col)
        y += rh

    y += 10
    # Legend
    d.ellipse((pad + 2, y + 6, pad + 16, y + 20), fill=GREEN)
    d.text((pad + 24, y), "eng arzon sotadigan (dollar olishga)", font=f_small, fill=MUTED)
    y += 30
    d.ellipse((pad + 2, y + 6, pad + 16, y + 20), fill=GOLD)
    d.text((pad + 24, y), "eng qimmat oladigan (dollar sotishga)", font=f_small, fill=MUTED)

    # Footer
    foot = "Manba: cbu.uz, bankrate.uz, Open-Meteo"
    if channel_label:
        foot = channel_label + "   |   " + foot
    d.text((pad, H - 44), foot, font=f_small, fill=MUTED)

    img.save(out_path)
    return out_path


if __name__ == "__main__":
    # MOCK ma'lumot bilan dizaynni sinash
    weather = {
        "Toshkent sh.": (34, "ochiq, quyoshli"),
        "Toshkent vil.": (33, "qisman bulutli"),
        "Andijon": (30, "bulutli"),
        "Buxoro": (37, "ochiq"),
        "Farg'ona": (31, "yomg'ir"),
        "Jizzax": (35, "ochiq"),
        "Namangan": (30, "qisman bulutli"),
        "Navoiy": (38, "ochiq"),
        "Qashqadaryo": (36, "ochiq"),
        "Qoraqalpog'iston": (33, "momaqaldiroq"),
        "Samarqand": (32, "bulutli"),
        "Sirdaryo": (35, "ochiq"),
        "Surxondaryo": (39, "ochiq"),
        "Xorazm": (34, "tuman"),
    }
    banks = [
        {"bank": "Hamkorbank", "buy": 12580, "sell": 12660},
        {"bank": "NBU", "buy": 12590, "sell": 12650},
        {"bank": "SQB", "buy": 12580, "sell": 12660},
        {"bank": "Infinbank", "buy": 12540, "sell": 12660},
        {"bank": "Asakabank", "buy": 12620, "sell": 12690},
        {"bank": "Agrobank", "buy": 12600, "sell": 12695},
        {"bank": "Xalqbanki", "buy": 12630, "sell": 12690},
        {"bank": "Ipotekabank", "buy": 12610, "sell": 12685},
        {"bank": "Aloqabank", "buy": 12630, "sell": 12640},
        {"bank": "Anorbank", "buy": 12575, "sell": 12645},
    ]
    path = render_card(
        date_label="21-iyun, 2026 \u00b7 Shanba",
        weather=weather,
        cbu_rate="12 642,17 so'm",
        banks=banks,
        out_path="/home/claude/project/sample_digest.png",
        channel_label="@mening_kanalim",
    )
    print("saved:", path)
