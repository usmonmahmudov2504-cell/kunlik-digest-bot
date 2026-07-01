# -*- coding: utf-8 -*-
"""Arab tili kanali — 365-kunlik, hafta kuniga qat'iy bog'langan tahririyat kalendari.

editorial_calendar.py'dan farqi: u til-agnostik va "eng kam ishlatilgan kategoriya"
mantig'i bilan istalgan kunga istalgan kategoriyani qo'yadi. Arab tili kanali esa
tasdiqlangan haftalik reja bo'yicha HAR HAFTA KUNI + SLOT (ertalab/kechqurun) uchun
qat'iy belgilangan ruknga ega bo'lishi kerak -> shu yerda alohida, oddiy round-robin
mantiq bilan hal qilinadi (har rukn aynan 2x/haftada takrorlanadi -> 7 rukn x 2 slot
= 14 haftalik post, mukammal muvozanat).

CEFR darajasi har mavzuning o'zida ("Daraja" ustunida) belgilanadi (A1/A2/B1) —
ishga tushirish qamrovi A1-B1 (B2/C1 keyinroq qo'shiladi).

Chiqish: arabic_calendar.csv (730 qator: 365 kun x 2 slot) + konsol xulosasi.
Run: python arabic_calendar.py
"""
import csv
import json
import os
import datetime as dt

START = dt.date(2026, 1, 1)
DAYS = 365
SLOT_TIMES = ["08:00", "19:30"]
HERE = os.path.dirname(os.path.abspath(__file__))

UZ_MONTHS = ["", "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
             "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]
UZ_WEEK = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]


def _load_tarjima_topics(path="arabic_sentences.json"):
    """arabic_sentences.json'dagi manba gaplarni ketma-ket 2 tadan juftlab, (mavzu, CEFR)
    ro'yxatiga aylantiradi. Daraja pozitsiyaga qarab taxminiy belgilanadi (birinchi uchdan
    bir qismi A1, keyingisi A2, oxirgisi B1) -- manbada aniq daraja belgisi yo'q.

    Fayl topilmasa -> bo'sh ro'yxat (chaqiruvchi xato bermaydi, faqat rukn bo'sh qoladi)."""
    fpath = os.path.join(HERE, path)
    try:
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"OGOHLANTIRISH: {path} topilmadi -> Tarjima Mashqi ruknisiz davom etamiz.")
        return [("(manba gap topilmadi)", "A1")]
    sentences = data.get("sentences", [])
    pairs = [sentences[i:i + 2] for i in range(0, len(sentences), 2)]
    n = len(pairs)
    topics = []
    for i, pair in enumerate(pairs):
        level = "A1" if i < n / 3 else ("A2" if i < 2 * n / 3 else "B1")
        numbered = "  ".join(f"{j + 1}) {s}" for j, s in enumerate(pair))
        topics.append((numbered, level))
    return topics


# ---------------------------------------------------------------- RUKN MA'LUMOTLARI
# Har rukn: manba, muqova g'oyasi, "nega muhim", CTA to'plami va (mavzu, CEFR) mavzular banki.
CATS = {
  "Kunlik Ibora": {
    "src": ["Hans Wehr lug'ati", "Klassik/MSA manbalari", "Tabiiy muloqot namunalari"],
    "cover": "So'z/ibora nafis arab kalligrafiyasida + o'zbekcha tarjima, kontekst jumlasi bilan",
    "why": "Yangi so'z eng yaxshi tirik jumla ichida, real vaziyatda esda qoladi.",
    "cta": ["Bugun shu iborani bitta jumlada ishlat va izohda yoz.",
            "Shu iborani bilarmidingiz? Izohda o'z misolingizni qoldiring.",
            "Ovozli xabar tashlab, shu iborani 3 marta talaffuz qiling."],
    "topics": [
      ("على الرحب والسعة — marhamat/arzimaydi (rasmiy javob)", "A2"),
      ("إن شاء الله — Alloh xohlasa (kelajak reja)", "A1"),
      ("ما شاء الله — hayrat/duo ifodasi", "A1"),
      ("بارك الله فيك — Alloh baraka bersin (minnatdorlik)", "A1"),
      ("مع السلامة — xayr, omon boring", "A1"),
      ("بكل سرور — katta xursandchilik bilan (rozilik)", "A2"),
      ("لا بأس — hechqisi yo'q / zarari yo'q", "A1"),
      ("على كل حال — har holda, baribir", "B1"),
      ("من فضلك — iltimos (rasmiy so'rov)", "A1"),
      ("بالتوفيق — omad tilayman", "A1"),
      ("خذ راحتك — o'zingni erkin his qil, shoshilma", "A2"),
      ("كل عام وأنتم بخير — har yili yaxshilikda bo'ling (tabrik)", "A2"),
      ("حياك الله — xush kelibsiz (Alloh senga hayot bersin)", "A1"),
      ("إن شاء الله خير — Alloh xohlasa yaxshilik bo'ladi (tasalli)", "A2"),
      ("بدون تردد — ikkilanmasdan", "B1"),
      ("في أقرب وقت ممكن — imkon qadar tezroq", "B1"),
      ("لك مني كل التقدير — sizga mendan chuqur hurmat", "B1"),
      ("لا مانع عندي — men uchun to'siq yo'q, roziman", "A2"),
      ("خير إن شاء الله — umid qilaman, hammasi yaxshi", "A2"),
      ("على راحتك — xohlaganingcha, shoshilmasdan", "A2"),
      ("يا هلا — xush kelibsiz (samimiy, so'zlashuv)", "A1"),
      ("تحت أمرك — buyrug'ingizga tayyorman (xizmatga tayyorlik)", "B1"),
      ("لا داعي للقلق — xavotirlanishga hojat yo'q", "A2"),
      ("كل شيء تمام — hammasi joyida", "A1"),
    ],
  },
  "Sinonim-Antonim": {
    "src": ["Klassik arab lug'atlari", "Zamonaviy MSA matnlar", "Arab maqollari to'plamlari"],
    "cover": "Ikki so'z yonma-yon (yashil=sinonim yoki qizil=antonim belgisi) + arab maqoli qismi",
    "why": "So'zni juftlikda (o'xshash/qarama-qarshi) o'rganish lug'at boyligini tezroq oshiradi.",
    "cta": ["Shu ikki so'zdan o'zingiz bitta jumla tuzing.",
            "Bu maqolga o'xshash o'zbekcha maqolni izohda yozing.",
            "Qaysi so'zni ko'proq eshitgansiz? Izohda ayting."],
    "topics": [
      ("كبير (katta) — sinonim: ضخم (ulkan) / antonim: صغير (kichik)", "A1"),
      ("سعيد (baxtli) — sinonim: مسرور / antonim: حزين (g'amgin)", "A1"),
      ("سريع (tez) — sinonim: عاجل / antonim: بطيء (sekin)", "A1"),
      ("جميل (chiroyli) — sinonim: رائع (ajoyib) / antonim: قبيح (xunuk)", "A2"),
      ("قوي (kuchli) — sinonim: شديد / antonim: ضعيف (kuchsiz)", "A2"),
      ("الصبر مفتاح الفرج — sabr najot kaliti (maqol)", "B1"),
      ("قريب (yaqin) — sinonim: مجاور / antonim: بعيد (uzoq)", "A1"),
      ("جديد (yangi) — sinonim: حديث / antonim: قديم (eski)", "A1"),
      ("العلم نور والجهل ظلام — ilm nur, jaholat zulmat (maqol)", "B1"),
      ("سهل (oson) — sinonim: بسيط (sodda) / antonim: صعب (qiyin)", "A1"),
      ("غني (boy) — sinonim: ثري / antonim: فقير (kambag'al)", "A2"),
      ("من جد وجد — kim harakat qilsa, topadi (maqol)", "B1"),
      ("مبكر (erta) — sinonim: باكر / antonim: متأخر (kech)", "A2"),
      ("واضح (aniq) — sinonim: بيّن / antonim: غامض (noaniq)", "B1"),
      ("العقل السليم في الجسم السليم — sog'lom tanda sog'lom aql (maqol)", "B1"),
      ("مهم (muhim) — sinonim: ضروري (zarur) / antonim: تافه (ahamiyatsiz)", "A2"),
      ("هادئ (tinch) — sinonim: ساكن / antonim: صاخب (shovqinli)", "B1"),
      ("درهم وقاية خير من قنطار علاج — ehtiyot chorasi davodan afzal (maqol)", "B1"),
      ("ثقيل (og'ir) — sinonim: صعب / antonim: خفيف (yengil)", "A1"),
      ("نظيف (toza) — sinonim: صافٍ / antonim: متسخ (iflos)", "A1"),
      ("لا يعرف قدر النعمة إلا من فقدها — ne'matning qadrini yo'qotgandagina bilasan", "B1"),
      ("مشغول (band) — sinonim: منشغل / antonim: فارغ (bo'sh)", "A2"),
      ("رخيص (arzon) — sinonim: زهيد / antonim: غالٍ (qimmat)", "A1"),
      ("العين لا تعلو على الحاجب — kichik katta bo'lolmaydi (maqol, mavqe haqida)", "B1"),
    ],
  },
  "Tarjima Mashqi": {
    "src": ["Nuriddin — «Arab tiliga tarjima qilish uchun mavzulashtirilgan gaplar» (tahrir: Usmon Mahmudov)"],
    "cover": "Qo'lyozma daftar sahifasi motivi, gap raqami va tarjima strelkasi (UZ -> AR)",
    "why": "Haqiqiy, tayyor manbadagi gapni tizimli, ketma-ket tarjima qilish — kursdek izchil o'sishni ta'minlaydi.",
    "cta": ["Shu gaplarni o'zingiz arabchaga tarjima qilib ko'ring, keyin izohdagi javob bilan solishtiring.",
            "Tarjimangizni izohda yozing — men tekshirib, xato bo'lsa tuzataman.",
            "Shu gapni ovozli xabar qilib arabcha o'qib bering."],
    "topics": _load_tarjima_topics(),
  },
  "Kitaba Shabloni": {
    "src": ["CEFR yozma imtihon namunalari", "Akademik arab tili qo'llanmalari", "Bog'lovchi so'zlar to'plami"],
    "cover": "Qalam+qog'oz motivi, bog'lovchi so'z markazda katta harflarda, misol jumla pastda",
    "why": "Tayyor qolip bilan yozma ishni tezroq va yuqori ballga yozish mumkin.",
    "cta": ["Shu qolipdan foydalanib 2-3 jumla yozing, men tekshirib beraman.",
            "Shu bog'lovchini o'zingizning gapingizda ishlating.",
            "Bugungi mavzuda mini-insho yozing va izohga tashlang."],
    "topics": [
      ("Fikr boshlash: في رأيي / من وجهة نظري (menimcha)", "B1"),
      ("Qarama-qarshi fikr: على العكس / بالرغم من (aksincha)", "B1"),
      ("Xulosa qilish: وختامًا / في النهاية (xulosa qilib aytganda)", "B1"),
      ("Sabab bildirish: بسبب / نظرًا لـ (sababli)", "A2"),
      ("Natija bildirish: لذلك / نتيجة لذلك (shuning uchun)", "A2"),
      ("Qo'shimcha fikr: بالإضافة إلى ذلك (bundan tashqari)", "B1"),
      ("Misol keltirish: على سبيل المثال (masalan)", "A2"),
      ("Solishtirish: مقارنة بـ / بينما (solishtirganda)", "B1"),
      ("Rasmiy xat kirish qismi qolipi", "A2"),
      ("Rasmiy xat yakunlovchi qolipi (تفضلوا بقبول فائق الاحترام)", "B1"),
      ("Shaxsiy tajriba haqida yozish qolipi (لقد مررت بتجربة...)", "A2"),
      ("O'z fikringni asoslash qolipi (أعتقد ذلك لأن...)", "B1"),
      ("Kelajak reja haqida yozish (أخطط لـ / أنوي أن)", "A2"),
      ("Taklif berish qolipi (أقترح أن / من الأفضل أن)", "B1"),
      ("Shart gaplarda yozma qolip (إذا... فإن...)", "B1"),
      ("Insho kirish jumlasi qolipi (umumiy mavzudan xususiyga)", "B1"),
      ("Vaqt ketma-ketligi so'zlari: أولاً، ثانيًا، أخيرًا", "A2"),
      ("His-tuyg'u ifodalash yozma tilda (أشعر بـ)", "A2"),
      ("Taqqoslash darajalari: أكثر من / أقل من (ko'proq/kamroq)", "A2"),
      ("Rasmiy so'rov xati qolipi (أرجو منكم التكرم بـ)", "B1"),
      ("Shikoyat xati qolipi (أكتب إليكم لأشتكي من)", "B1"),
      ("Tavsiyanoma so'rash qolipi", "B1"),
      ("Statistik ma'lumotni tavsiflash (تشير الإحصائيات إلى)", "B1"),
      ("Insho uchun kuchli yakuniy jumla tuzish", "B1"),
    ],
  },
  "Imtihon Strategiyasi": {
    "src": ["CEFR rasmiy namuna testlari", "Til imtihonlari metodikasi", "Tajribali metodistlar tavsiyasi"],
    "cover": "Soat/checklist motivi, bitta aniq layfhak sarlavhada katta harflarda",
    "why": "To'g'ri strategiya bilim darajasidan qat'i nazar ballni sezilarli oshiradi.",
    "cta": ["Sizda qanday imtihon xatolari bo'lgan? Ulashing, birga tahlil qilamiz.",
            "Shu strategiyani keyingi mashqda sinab ko'ring.",
            "Ushbu maslahatni saqlab qo'ying — imtihon oldidan qayta o'qing."],
    "topics": [
      ("Istima': savollarni audiodan OLDIN o'qib chiqish", "A2"),
      ("Istima': kalit so'zlarni (sana, ism, joy) oldindan belgilash", "A2"),
      ("Qiraa (o'qish): skimming va scanning farqi", "B1"),
      ("Qiraa: notanish so'zni kontekstdan taxmin qilish", "B1"),
      ("Kitaba: vaqtni reja/yozish/tekshirish qismlariga bo'lish", "B1"),
      ("Kitaba: so'z sonini nazorat qilish (kam/ko'p emas)", "A2"),
      ("Muhadasa: pauza va to'ldiruvchi iboralar (يعني، بصراحة)", "B1"),
      ("Muhadasa: savolni tushunmasangiz qayta so'rash iborasi", "A2"),
      ("Eng ko'p uchraydigan grammatik xato: fe'l-egalik moslashuvi", "B1"),
      ("Eng ko'p uchraydigan xato: تنوين (tanvin) qo'llash", "B1"),
      ("Vaqt boshqaruvi: qiyin savolni keyinga qoldirish taktikasi", "A2"),
      ("Variantli savollarda 'eliminatsiya' usuli", "A2"),
      ("Imtihondan oldingi kechada nima qilish kerak emas", "A1"),
      ("Stress bilan ishlash: chuqur nafas texnikasi imtihon oldidan", "A1"),
      ("Yozma qismda qayta o'qish (proofreading) checklisti", "B1"),
      ("Og'zaki qismda ko'z bilan aloqa va ishonch tuyg'usi", "A2"),
      ("Grammatik vaqtlarni aralashtirmaslik nazorati", "B1"),
      ("Uzun matnda asosiy g'oyani birinchi/oxirgi abzasdan topish", "B1"),
      ("Lug'at bilmagan so'zga vaqt sarflamaslik qoidasi", "A2"),
      ("Imtihon kuni ertalabki tayyorgarlik ro'yxati", "A1"),
      ("Yozma ishda bog'lovchi so'zlar bilan ball oshirish", "B1"),
      ("Tinglashda birinchi eshitishda umumiy ma'noni, ikkinchisida detalni olish", "A2"),
      ("Nutqda o'zini tuzatish (self-correction) qanday ball beradi", "B1"),
      ("Imtihon formatiga oldindan tanishishning ahamiyati", "A1"),
    ],
  },
  "Fusha-Ammiya": {
    "src": ["Qiyosiy lahja lug'atlari", "Misr/Shom/Xalij tabiiy nutq namunalari", "Tilshunoslik manbalari"],
    "cover": "Bir so'z, 3-4 mamlakat bayrog'i ostida turli yozilishda (qiyosiy jadval uslubida)",
    "why": "Real hayotda (filmlar, suhbat) Fusha yetarli emas — lahjalarni tanish tushunishni osonlashtiradi.",
    "cta": ["Qaysi mamlakat filmini/serialini ko'p tomosha qilasiz? Yozing.",
            "Shu so'zni o'z lahjangizda (bilsangiz) qanday aytilishini ulashing.",
            "Qaysi lahja sizga eng qiziq tuyuladi? Izohda ayting."],
    "topics": [
      ("Xohlayman: أريد (Fusha) / عايز (Misr) / بدّي (Shom) / أبغى (Xalij)", "A2"),
      ("Nima: ماذا (Fusha) / إيه (Misr) / شو (Shom) / وش (Xalij)", "A1"),
      ("Qanday: كيف (Fusha) / إزاي (Misr) / كيف (Shom) / كيف (Xalij)", "A1"),
      ("Bugun: اليوم (Fusha) / النهارده (Misr) / اليوم (Shom) / اليوم (Xalij)", "A1"),
      ("Yaxshi: جيد (Fusha) / كويس (Misr) / منيح (Shom) / زين (Xalij)", "A1"),
      ("Yo'q: لا (Fusha) / لأ (Misr) / لا (Shom) / لا (Xalij) — ohang farqi", "A1"),
      ("Ko'p: كثير (Fusha) / كتير (Misr/Shom) / وايد (Xalij)", "A2"),
      ("Bola: ولد (Fusha) / واد (Misr) / صبي (Shom) / ولد (Xalij)", "A2"),
      ("Uy: بيت (barcha lahjalarda umumiy, talaffuz farqi)", "A1"),
      ("Hozir: الآن (Fusha) / دلوقتي (Misr) / هلق (Shom) / الحين (Xalij)", "A2"),
      ("Ish: عمل (Fusha) / شغل (barcha lahjalarda keng)", "A2"),
      ("Nega: لماذا (Fusha) / ليه (Misr/Shom) / ليش (Xalij)", "A2"),
      ("Qancha turadi: كم السعر (Fusha) / بكام (Misr) / قديش (Shom) / كم (Xalij)", "A2"),
      ("Kel bu yoqqa: تعال هنا (Fusha) / تعالى هنا (Misr) / تعا لهون (Shom)", "B1"),
      ("Misr ammiyasi: filmlarda eng ko'p ishlatiladigan salomlashish iboralari", "B1"),
      ("Shom (Levant) ammiyasi: Suriya/Livan/Iordaniya nutqidagi umumiy jihatlar", "B1"),
      ("Xalij ammiyasi: Saudiya/BAA nutqida ingliz/fors ta'siri", "B1"),
      ("Fusha qachon ishlatiladi: yangiliklar, rasmiy nutq, kitob", "A2"),
      ("Ammiya qachon ishlatiladi: uy, ko'cha, ijtimoiy tarmoq", "A2"),
      ("Lahjalar orasidagi eng katta farq: fe'l tuslanishi", "B1"),
      ("Nega ammiya o'rganish kerak: kundalik tushunish uchun", "A2"),
      ("Bitta so'z, besh talaffuz: mamlakatlar bo'yicha 'salom' qiyosi", "A1"),
      ("Misr ammiyasidagi eng mashhur 5 so'z", "B1"),
      ("Xalij ammiyasidagi eng mashhur 5 so'z", "B1"),
    ],
  },
  "Kino-Qoshiq Tahlili": {
    "src": ["Ommaviy arab multfilmlari/seriallari (umumiy uslub tahlili)", "Mashhur arab qo'shiqlari matni uslubi", "Til o'rganish metodikasi"],
    "cover": "Ekran/parda motivi + subtitr chizig'i, pastda kalit ibora ajratib ko'rsatilgan",
    "why": "Jonli, tabiiy tilni eshitib-ko'rib o'rganish yodlashni his-tuyg'u bilan bog'laydi.",
    "cta": ["Shu janrdagi filmni tomosha qilganmisiz? Ulashing.",
            "Yoqtirgan arabcha qo'shiqni/filmni izohda tavsiya qiling.",
            "Shu iborani eshitgan joyingizni eslaysizmi? Yozing."],
    "topics": [
      ("Multfilmlardagi kundalik salomlashish ohangi va imo-ishoralar", "A1"),
      ("Qo'shiq matnidagi takrorlanuvchi iboralar orqali yodlash usuli", "A2"),
      ("Seriallardagi oddiy kundalik fe'llarni ajratib olish mashqi", "A1"),
      ("Multfilm qahramonlari his-tuyg'usini ifodalovchi so'zlar", "A2"),
      ("Qo'shiqda 'sevgi/sog'inch' mavzusida keng qo'llanadigan so'zlar", "B1"),
      ("Film dialogidagi savol-javob ritmini kuzatish", "A2"),
      ("Ammiya bilan Fusha subtitr farqini solishtirish mashqi", "B1"),
      ("Bolalar multfilmidagi son va rang so'zlarini mustahkamlash", "A1"),
      ("Qo'shiqdagi metafora va majoziy iboralarni tanish", "B1"),
      ("Filmdagi imo-ishora va tana tili orqali ma'noni taxmin qilish", "A2"),
      ("Serial syujetini 3 jumlada qayta hikoya qilish mashqi", "B1"),
      ("Qo'shiq refrenini yodlab, talaffuzni mashq qilish", "A1"),
      ("Multfilmdagi maslahat/nasihat gaplarini ajratib olish", "A2"),
      ("Filmda tez-tez uchraydigan kundalik idiomalar", "B1"),
      ("Qo'shiqdagi vaqt shakllarini (o'tgan/hozirgi) kuzatish mashqi", "B1"),
      ("Bolalar seriali orqali oddiy buyruq gaplarni o'rganish", "A1"),
      ("Film sahnasidagi kayfiyatga qarab ohang o'zgarishini tinglash", "A2"),
      ("Qo'shiq matnida sinonim so'zlarni topish mashqi", "B1"),
      ("Multfilmda tabiat va fasllar haqidagi so'z boyligi", "A1"),
      ("Serialda uchrashuv/xayrlashuv sahnalaridagi iboralar", "A2"),
      ("Qo'shiqchi talaffuzida lahja izlarini payqash mashqi", "B1"),
      ("Filmdagi oilaviy munosabat so'zlari (ota, ona, aka...)", "A1"),
      ("Multfilm qahramonining orzu-maqsad haqidagi gaplari", "A2"),
      ("Qo'shiq matni orqali arab she'riyati ritmiga tanishish", "B1"),
    ],
  },
}

# Hafta kuni (0=Dushanba..6=Yakshanba) x slot (0=ertalab,1=kechqurun) -> rukn.
# Round-robin: 7 rukn x 2 marta/hafta = 14 slot, mukammal muvozanat, bir kunda takror yo'q.
CAT_ORDER = ["Kunlik Ibora", "Sinonim-Antonim", "Tarjima Mashqi", "Kitaba Shabloni",
             "Imtihon Strategiyasi", "Fusha-Ammiya", "Kino-Qoshiq Tahlili"]


def slot_category(weekday: int, slot_idx: int) -> str:
    i = weekday * 2 + slot_idx
    return CAT_ORDER[i % 7]


def build():
    rows = []
    used = {c: 0 for c in CATS}
    for n in range(1, DAYS + 1):
        d = START + dt.timedelta(days=n - 1)
        wd = d.weekday()
        for slot_idx, time in enumerate(SLOT_TIMES):
            cat = slot_category(wd, slot_idx)
            meta = CATS[cat]
            i = used[cat]
            topic, level = meta["topics"][i % len(meta["topics"])]
            used[cat] += 1
            cta = meta["cta"][i % len(meta["cta"])]
            src = meta["src"][i % len(meta["src"])]
            rows.append({
                "Kun": n,
                "Slot": slot_idx,
                "Sana": f"{d.day}-{UZ_MONTHS[d.month]}",
                "Hafta kuni": UZ_WEEK[wd],
                "Kategoriya": cat,
                "Mavzu": topic,
                "Daraja": level,
                "Nega muhim": meta["why"],
                "Ishonchli manba": src,
                "E'lon vaqti": time,
                "Muqova g'oyasi": meta["cover"],
                "CTA taklifi": cta,
            })
    return rows


def integrity(rows):
    from collections import Counter
    cats = Counter(r["Kategoriya"] for r in rows)
    # bir kunda ikkala slot bir xil kategoriya bo'lmasligi kerak
    same_day = sum(1 for n in range(1, DAYS + 1)
                   if rows[(n - 1) * 2]["Kategoriya"] == rows[(n - 1) * 2 + 1]["Kategoriya"])
    levels = Counter(r["Daraja"] for r in rows)
    return cats, same_day, levels


def main():
    rows = build()
    cols = list(rows[0].keys())
    with open("arabic_calendar.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    cats, same_day, levels = integrity(rows)
    print(f"✅ arabic_calendar.csv yozildi — {len(rows)} qator ({DAYS} kun x 2 slot)")
    print(f"   Bir kunda ikkala slot bir xil kategoriya: {same_day} (0 bo'lishi kerak)")
    print("   Rukn balansi (haftada 2x, yiliga):")
    for c, n in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"     {c:<20} {n}")
    print("   CEFR darajasi taqsimoti:", dict(levels))
    print("\n   Namuna (1-hafta, 1-14 slot):")
    for r in rows[:14]:
        vaqt = r["E'lon vaqti"]
        print(f"     Kun{r['Kun']:>3} S{r['Slot']} {r['Hafta kuni']:<11} {vaqt} "
              f"{r['Kategoriya']:<20} [{r['Daraja']}] {r['Mavzu'][:55]}")


if __name__ == "__main__":
    main()
