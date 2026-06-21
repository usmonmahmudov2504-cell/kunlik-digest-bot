# Kunlik digest bot v2 — ob-havo (barcha viloyatlar) + banklar dollar kursi + yangiliklar

Har kuni avtomatik ravishda Telegram kanalingizga **rangli rasm (info-card)** yuboradi:

- **Ob-havo** — O'zbekistonning 14 viloyati bo'yicha harorat (Open-Meteo, bepul, kalitsiz).
- **Dollar kursi** — barcha banklarning **olish/sotish** kursi (bankrate.uz) + Markaziy bank rasmiy kursi (cbu.uz).
  - 🟢 yashil — **eng arzon sotadigan** bank (dollar olmoqchilar uchun, eng past sotish kursi).
  - 🟡 oltin — **eng qimmat oladigan** bank (dollar sotmoqchilar uchun, eng baland olish kursi).
- **Caption** — Claude qisqa sarlavha va kunning yangiliklarini yozadi (gazeta.uz, daryo.uz).

> Nega rasm? Telegram matnli postda rang yo'q. Banklarni ranglar bilan ajratish va
> postni vizual qilish uchun ma'lumotdan PNG karta yasaladi va `sendPhoto` orqali yuboriladi.
> Bu internetdan rasm qidirish yoki AI bilan generatsiyadan ko'ra ishonchli: har doim
> mavzuga 100% mos, bepul, copyright muammosi yo'q.

## Fayllar

| Fayl | Vazifasi |
|------|----------|
| `daily_digest_bot.py` | Asosiy bot: ma'lumot yig'ish, rasm yasash, Telegramga yuborish |
| `render_card.py` | Rangli info-card (PNG) yasovchi modul (Pillow) |
| `requirements.txt` | Kutubxonalar |
| `.github/workflows/daily-post.yml` | Har kuni 07:00 (Toshkent) avtomatik ishga tushirish |

## 1. Telegram tomondan tayyorlik

1. [@BotFather](https://t.me/BotFather)'da bot yarating, tokenni saqlang.
2. Kanal yarating (yoki mavjudini ishlating).
3. Botni kanalga **administrator** qiling (kamida "Post messages" huquqi).
4. Kanal username'ini eslang, masalan `@mening_kanalim`
   (username bo'lmasa raqamli chat ID kerak — [@username_to_id_bot](https://t.me/username_to_id_bot)).

## 2. Mahalliy sinov

```bash
pip install -r requirements.txt --break-system-packages

# Faqat ikkita kalit MAJBURIY:
export TELEGRAM_BOT_TOKEN="123456:ABC-..."
export TELEGRAM_CHANNEL="@mening_kanalim"

# ANTHROPIC_API_KEY IXTIYORIY:
#  - qo'ymasangiz -> caption oddiy (bepul) shablon bilan chiqadi
#  - qo'ysangiz   -> Claude jonli caption yozadi
# export ANTHROPIC_API_KEY="sk-ant-..."

python daily_digest_bot.py
```

Konsolda `Ob-havo: 14 viloyat | Banklar: 17 | ...` va `Post yuborildi` chiqsa — tayyor.
Faqat rasm dizaynini sinash uchun: `python render_card.py` (mock ma'lumot bilan `sample_digest.png` yasaydi).

## 3. Avtomatik kuniga ishga tushirish (GitHub Actions)

1. Shu papkani GitHub repo'siga yuklang (`.github/workflows/daily-post.yml` ham birga).
2. **Settings → Secrets and variables → Actions** → 3 ta secret qo'shing:
   `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL`.
3. Workflow har kuni 07:00 (Toshkent) ishlaydi. Vaqtni o'zgartirish: `cron: "0 2 * * *"` (UTC, Toshkent = UTC+5).
4. Darhol sinash: **Actions → workflow → Run workflow**.

## Moslashtirish

- **Viloyat qo'shish/olib tashlash**: `daily_digest_bot.py` ichidagi `REGIONS` lug'atini tahrirlang.
- **Bank qo'shish**: `BANK_NAMES` ro'yxatiga bank nomini bankrate.uz'dagi yozilishi bilan qo'shing.
- **Rang/dizayn**: `render_card.py` boshidagi rang konstantalari (`GREEN`, `GOLD`, `BG` ...).
- **Bir kunda 2 post**: `daily-post.yml`'ga yana bitta `cron` qo'shing (masalan `"0 14 * * *"` = 19:00).

## Diqqat (mo'rt joylar)

- **bankrate.uz** — sayt strukturasi o'zgarsa, banklar bo'sh chiqishi mumkin. Bot bunday holatda
  ishlashda davom etadi (faqat rasmiy kurs ko'rsatiladi). Agar `Banklar: 0` chiqsa, avval
  `python -c "import requests,bs4; print(bs4.BeautifulSoup(requests.get('https://bankrate.uz/uz',headers={'User-Agent':'Mozilla/5.0'}).text,'html.parser').get_text(' ')[:1500])"`
  bilan tekshiring va `BANK_NAMES` nomlarini moslang.
- **Shrift** — DejaVuSans ishlatiladi (Ubuntu/GitHub Actions'da bor, o'zbekcha harflarni qoplaydi).
