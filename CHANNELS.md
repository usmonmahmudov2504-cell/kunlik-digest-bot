# Ko'p kanal — qo'shish qo'llanmasi

Bot endi **config-driven**: kanallar `channels.json`da. Bitta workflow har 15 daqiqa
ishga tushib, **ro'yxatdagi HAMMA kanal**ga post qiladi. Yangi kanal = config'ga
bitta blok (kodga tegmaysiz).

## channels.json tuzilishi

```json
[
  {
    "name": "Ajoyib Kun | Bugun",
    "channel": "@ajoyib_kun_uz",
    "token_env": "TELEGRAM_BOT_TOKEN",
    "groups": ["A", "B", "C", "D", "M"],
    "footer_services": "🌤 Ob-havo · 💵 Kurslar · ⚡ Yangiliklar"
  }
]
```

| Maydon | Ma'nosi |
|---|---|
| `channel` | Kanal username (@...). Bot shu kanalga **admin** bo'lishi shart |
| `token_env` | Bot token saqlanadigan **secret/env NOMI** (token o'zi emas!). Bitta bot ishlatsangiz — hamma kanalda `TELEGRAM_BOT_TOKEN` |
| `groups` | Shu kanal qaysi postlarni oladi: `A`=Bugun+Maslahat, `B`=Ob-havo, `C`=Tezkor xabar, `D`=Kurslar+Dollar, `M`=Bozor |
| `footer_services` | Footer'dagi xizmatlar qatori (brend) |

## Yangi kanal qo'shish (3 qadam)

1. **Botni admin qiling** — yangi kanalga o'sha botni (yoki yangi botni) admin qo'shing
   (post yuborish huquqi bilan).
2. **channels.json'ga blok qo'shing**, masalan faqat kurs/bozor kanali:
   ```json
   {
     "name": "Valyuta Kurslari",
     "channel": "@valyuta_kanal",
     "token_env": "TELEGRAM_BOT_TOKEN",
     "groups": ["D", "M"],
     "footer_services": "💵 Kurslar · 🥇 Oltin · ₿ Kripto"
   }
   ```
3. **Agar ALOHIDA bot** ishlatsangiz — GitHub Secrets'ga yangi token qo'shing
   (masalan `TELEGRAM_BOT_TOKEN_2`) va `token_env`'da shu nomni yozing. Bitta bot
   bo'lsa — bu qadam shart emas.

Tamom. cron-job.org trigger'i o'zgarmaydi — bitta trigger hamma kanalni boshqaradi.

## Holat (state)
Har kanalning holati alohida: `state/<kanal>/...` (takror, kunlik belgi, kurslar).
GitHub Actions buni avtomatik commit qiladi.

## Hozircha cheklov (keyingi bosqich)
Hamma kanal hozir **bir xil kontent** oladi (bir xil ob-havo/kurs/yangilik).
Har kanalga **boshqa yangilik manbalari / til / viloyatlar** kerak bo'lsa — bu
keyingi bosqich (config'ga `manbalar`, `til`, `viloyatlar` qo'shiladi). Hozircha
`groups` bilan qaysi BO'LIMLAR chiqishini kanal-kanal sozlay olasiz.
