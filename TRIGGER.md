# Tashqi trigger (cron-job.org) — aniq vaqtli, ishonchli ishga tushirish

GitHub Actions'ning ichki cron'i ishonchsiz (kechikadi/ishlamaydi). Bu qo'llanma
**cron-job.org** (bepul) orqali GitHub API'sini aniq vaqtda chaqirib, workflow'ni
ishga tushirishni sozlaydi. Bu GitHub'ning ichki jadvaliga umuman bog'liq emas.

Bot AUTO rejimida o'zi qaror qiladi (vaqti kelgan kunlik post + tezkor xabar),
shuning uchun trigger faqat har 15 daqiqada "turt" yuborsa kifoya. Takror chiqmaydi
(dedup: `state/posted_daily.json`, `state/posted_news.json`).

---

## 1-qadam: GitHub token (fine-grained PAT) yaratish

1. GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**
   (havola: https://github.com/settings/tokens?type=beta)
2. **Token name:** `cron-trigger` (ixtiyoriy)
3. **Expiration:** uzoq muddat (masalan 1 yil yoki "No expiration"). _Eslatma: muddati
   tugasa trigger to'xtaydi — kalendarga eslatma qo'ying._
4. **Resource owner:** o'z akkauntingiz
5. **Repository access:** _Only select repositories_ → **kunlik-digest-bot**
6. **Permissions → Repository permissions → Actions:** **Read and write**
   (Metadata: Read-only avtomatik qo'shiladi — shu yetarli)
7. **Generate token** → tokenni **NUSXALANG** (faqat bir marta ko'rsatiladi).
   ⚠️ Bu tokenni hech kimga bermang, repoga commit qilmang — faqat cron-job.org'ga kiriting.

---

## 2-qadam: cron-job.org'da job yaratish

1. https://cron-job.org → ro'yxatdan o'ting / kiring.
2. **Create cronjob** tugmasi.
3. **Title:** `Ajoyib Kun digest trigger`
4. **URL:**
   ```
   https://api.github.com/repos/usmonmahmudov2504-cell/kunlik-digest-bot/actions/workflows/daily-post.yml/dispatches
   ```
5. **Schedule (jadval):**
   - **Timezone:** `Asia/Tashkent`
   - Har **15 daqiqada**, soat **07:00–22:00** orasida, har kuni.
   - (Custom: minutes = `0,15,30,45`, hours = `7-22`, har kun)
6. **Advanced / Request** bo'limida:
   - **Request method:** `POST`
   - **Request headers** (har birini qo'shing):
     | Key | Value |
     |-----|-------|
     | `Accept` | `application/vnd.github+json` |
     | `Authorization` | `Bearer SIZNING_TOKENINGIZ` |
     | `X-GitHub-Api-Version` | `2022-11-28` |
     | `Content-Type` | `application/json` |
   - **Request body:**
     ```json
     {"ref":"main","inputs":{"group":"AUTO"}}
     ```
7. **Save / Create**.

Muvaffaqiyatli javob = **HTTP 204** (bo'sh javob). cron-job.org buni yashil/OK deb ko'rsatadi.

---

## 3-qadam: Sinash (ixtiyoriy, lokal)

PowerShell'da (tokeningizni qo'ying):

```powershell
$token = "github_pat_..."   # o'z tokeningiz
$headers = @{
  Authorization          = "Bearer $token"
  Accept                 = "application/vnd.github+json"
  "X-GitHub-Api-Version" = "2022-11-28"
}
$body = '{"ref":"main","inputs":{"group":"AUTO"}}'
Invoke-RestMethod -Method Post -ContentType "application/json" -Headers $headers -Body $body `
  -Uri "https://api.github.com/repos/usmonmahmudov2504-cell/kunlik-digest-bot/actions/workflows/daily-post.yml/dispatches"
```

Xatosiz o'tsa (204), GitHub **Actions** bo'limida yangi run paydo bo'ladi.

---

## Eslatmalar

- **Ikkala trigger ham qoladi:** GitHub ichki cron (`*/15`) + cron-job.org. Dedup
  tufayli ikkalasi ishlasa ham post takrorlanmaydi (xavfsiz ortiqchalik).
- Agar repo **private** bo'lsa, ishlar sonini kamaytirish uchun tashqi trigger
  ishonchli ishlayotganiga ishonch hosil qilgach, `daily-post.yml`'dagi `schedule:`
  blokini olib tashlasangiz bo'ladi (faqat cron-job.org qoladi).
- Token muddati tugasa trigger to'xtaydi — yangi token yaratib, cron-job.org'da yangilang.
