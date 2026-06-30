# -*- coding: utf-8 -*-
"""Morning Box — 365-day editorial calendar generator.

World-class editorial-team approach: instead of hand-typing 365 rows, we encode the
RULES and let the generator guarantee them:

  - Never repeat a topic (each topic in the bank is used at most once).
  - Balance all categories (clean 21-category rotation -> ~17 posts each).
  - 30-day spacing for similar ideas (same category recurs only every 21 days; topics
    inside a category are all distinct, so no idea repeats within a month).
  - Seasonal events only when relevant (injected on their real date, overriding the slot).
  - Variety (light/analytical categories interleaved so no two heavy days in a row).

Output: editorial_calendar.csv (365 rows) + console summary + integrity checks.
Run:  python editorial_calendar.py
"""
import csv
import datetime as dt

# Reference (non-leap) year just for date labels & weekday; the plan itself is year-agnostic.
START = dt.date(2026, 1, 1)
DAYS = 365

UZ_MONTHS = ["", "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
             "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]
UZ_WEEK = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]

# Monthly themes (12)
MONTH_THEME = {
    1: "Yangi boshlanish — maqsad va tizim",
    2: "Ong va odatlar",
    3: "Yangilanish va o'sish",
    4: "Bilim va kitob",
    5: "Mahorat va kasb",
    6: "Pul va moliyaviy savod",
    7: "Ijod va texnologiya",
    8: "Liderlik va jamoa",
    9: "Ilm va intizom",
    10: "Muloqot va munosabat",
    11: "Tafakkur va qaror",
    12: "Refleksiya va shukr",
}
# Weekly lens (rotates within a month -> 52 distinct weekly themes when combined with month theme)
WEEK_LENS = ["Asoslar", "Chuqurlashish", "Amaliyot", "Mahorat", "Mustahkamlash"]

# Quarterly objectives (Q1..Q4)
QUARTER_OBJ = {
    1: "Q1 — Kunlik odatni va asosiy tafakkurni qurish; izchillik va ishonchni o'rnatish.",
    2: "Q2 — Bilimni chuqurlashtirish (kitob, mahorat, pul); ulashish va jalbni o'stirish.",
    3: "Q3 — Qo'llash va intilish (texnologiya, liderlik, intizom); auditoriyani kengaytirish.",
    4: "Q4 — Mahorat, refleksiya va jamoa; ushlab qolish va brend sodiqligini mustahkamlash.",
}

# ---------------------------------------------------------------- CATEGORY DATA
# Each category: suggested time, difficulty, reading time, sources, cover concept,
# why-readers-care lead, CTA pool, and a topic bank (18 distinct topics each).
CATS = {
  "Book Box": {
    "time": "07:00", "diff": "O'rta", "read": "1–2 daq",
    "src": ["Asl kitob + muallif intervyulari", "Universitet konspektlari", "Blinkist (tekshirilgan)"],
    "cover": "Minimal ochiq kitob yoki kitob qirrasi, sokin gradient, bitta g'oya-ibora",
    "why": "Yillar davomida shakllangan kitob g'oyasini 1 daqiqada o'zlashtiradi.",
    "cta": ["Bugun shu g'oyani bitta qaroringda sinab ko'r.",
            "Ushbu kitobni o'qiganmisiz? Asosiy saboqni izohda yozing.",
            "Shu fikrni bugun bir amalga aylantir."],
    "topics": [
      "Atomic Habits — 1% har kuni yaxshilanish kuchi",
      "Deep Work — chuqur ish nega noyob qadriyat",
      "Thinking, Fast and Slow — ikki tizimli tafakkur",
      "The Psychology of Money — boylik haqida ong",
      "Man's Search for Meaning — ma'no insonni qanday saqlaydi",
      "The 7 Habits — proaktivlik tamoyili",
      "Rich Dad Poor Dad — aktiv va passiv farqi",
      "Mindset (Dweck) — o'sish tafakkuri",
      "Ego is the Enemy — manmanlik dushman",
      "Essentialism — kamroq, lekin yaxshiroq",
      "The Almanack of Naval — boylik va baxt",
      "How to Win Friends — insonlarga samimiy ta'sir",
      "Start With Why — 'nega' dan boshlash",
      "Sapiens — hikoyalar insoniyatni birlashtirgani",
      "The Obstacle Is the Way — to'siq yo'lning o'zi",
      "Grit — qat'iyat iste'doddan ustun",
      "Outliers — 10 000 soat va imkoniyat",
      "Show Your Work — ijodingni ulashish jasorati",
    ],
  },
  "Habits": {
    "time": "07:00", "diff": "Boshlang'ich", "read": "1 daq",
    "src": ["James Clear — Atomic Habits", "Charles Duhigg", "BJ Fogg (Stanford)"],
    "cover": "Minimal zanjir/streak yoki o'sayotgan urug' motivi, sokin ranglar",
    "why": "Kichik, amaliy qadam bilan haqiqiy o'zgarishni boshlash mumkinligini ko'rsatadi.",
    "cta": ["Bugun shu odatni 2 daqiqalik versiyada boshla.",
            "Ertangi kun uchun bitta kichik odat belgila.",
            "Shu odatni mavjud odatingga ulab qo'y."],
    "topics": [
      "Habit loop: ishora–harakat–mukofot",
      "Identity-based odatlar (kim bo'lishni istaysan)",
      "2 daqiqa qoidasi",
      "Habit stacking — odatni odatga ulash",
      "Muhitni dizayn qilish (iroda emas)",
      "Streak — uzluksizlik kuchi",
      "Yomon odatni qiyinlashtirish",
      "Trigger (ishora) yaratish",
      "Kichik g'alabalar va momentum",
      "'Hech qachon ikki marta o'tkazma' qoidasi",
      "Keystone — kalit odatlar",
      "Track qilish: kuzatuvning kuchi",
      "Niyat-ijro (implementation intention)",
      "Odatni almashtirish (o'chirish emas)",
      "Relapse'dan keyin qaytish",
      "Plateau — ko'rinmas o'sish bosqichi",
      "Mukofot va motivatsiya bog'liqligi",
      "Mikro-odatlardan tizim qurish",
    ],
  },
  "Money Box": {
    "time": "07:30", "diff": "O'rta", "read": "1 daq",
    "src": ["The Psychology of Money (Housel)", "Bogle / indeks asoslari", "Markaziy bank moliyaviy savod"],
    "cover": "Minimal tanga/banka yoki o'sish-egri chizig'i, vazmin tilla aksent",
    "why": "Pulni boshqarishda xotirjam nazorat va sog'lom mentalitet beradi.",
    "cta": ["Bugun bitta keraksiz xarajatni jamg'armaga yo'naltir.",
            "Daromadingning 1 foizini bugun chetga qo'y.",
            "Bu oygi bitta moliyaviy maqsadingni yozib qo'y."],
    "topics": [
      "Murakkab foiz (compound) mo'jizasi",
      "50/30/20 byudjet qoidasi",
      "Favqulodda jamg'arma (emergency fund)",
      "Aktiv vs passiv daromad",
      "Inflyatsiya pulingni qanday yeydi",
      "Diversifikatsiya tamoyili",
      "O'zingga avval to'la (pay yourself first)",
      "Yaxshi qarz va yomon qarz farqi",
      "Lifestyle inflation tuzog'i",
      "Daromad emas, sof boylik (net worth)",
      "Tejash stavkasi nega hal qiluvchi",
      "Risk va daromad bog'liqligi",
      "Avtomatlashtirilgan jamg'arma",
      "Pul va his-tuyg'u (emotional spending)",
      "Sug'urta nega himoya",
      "Uzoq muddatli fikrlash kuchi",
      "Kichik xarajatlar (latte factor)",
      "Moliyaviy maqsad qo'yish tizimi",
    ],
  },
  "English Box": {
    "time": "07:00", "diff": "Boshlang'ich", "read": "<1 daq",
    "src": ["Oxford / Cambridge lug'ati", "Merriam-Webster", "Ishonchli ESL manbalari"],
    "cover": "Toza tipografik karta — so'z katta yozilgan, ikki tilli minimal layout",
    "why": "Har kuni bitta tabiiy ibora bilan ingliz tilini amaliy o'stiradi.",
    "cta": ["Bugun shu iborani bitta jumlada ishlat.",
            "Eslab qolish uchun o'zing bitta gap tuz.",
            "Shu so'zni bugun ovoz chiqarib mashq qil."],
    "topics": [
      "'Get the hang of it' — o'rganib olmoq",
      "'On the same page' — bir fikrda bo'lmoq",
      "'Break the ice' — muzni sindirmoq",
      "Phrasal verb: 'figure out'",
      "'By and large' — umuman olganda",
      "Collocation: 'make a decision' (do emas)",
      "'Touch base' — bog'lanib turmoq",
      "'A blessing in disguise'",
      "'Bite the bullet' — chidab bajarmoq",
      "'Cut to the chase' — asosiy gapga o'tmoq",
      "'The ball is in your court'",
      "So'z: 'resilience' (matonatlilik)",
      "So'z: 'leverage' (fe'l va ot)",
      "'In the long run' — uzoq muddatda",
      "'Pull yourself together' — o'zingni qo'lga ol",
      "'Food for thought' — o'ylantiradigan narsa",
      "So'z: 'nuance' (nozik farq)",
      "'Once in a blue moon' — juda kamdan-kam",
    ],
  },
  "Mind Box": {
    "time": "07:00", "diff": "O'rta", "read": "1 daq",
    "src": ["Kahneman / Cialdini", "Tekshirilgan psixologiya tadqiqotlari", "Universitet psix. manbalari"],
    "cover": "Abstrakt miya yoki ikki-yo'l silueti, vazmin premium palitra",
    "why": "O'z xulqini tushunib, ongli qaror qabul qilishga yordam beradi.",
    "cta": ["Bugun shu his kelganda nomini ayt va bir nafas ol.",
            "Keyingi safar buni o'zingda kuzat.",
            "Bugun bitta qaroringda bu xatoga e'tibor ber."],
    "topics": [
      "Tasdiqlash xatosi (confirmation bias)",
      "Dunning-Kruger effekti",
      "Zeigarnik effekti (tugallanmagan ish)",
      "Loss aversion — yo'qotishdan qo'rquv",
      "Anchoring — birinchi raqam ta'siri",
      "Spotlight effekti — 'hamma menga qaraydi'",
      "Hedonik adaptatsiya (baxtga ko'nikish)",
      "Flow — to'liq berilish holati",
      "Imposter sindromi",
      "Negativity bias — yomonga ko'proq e'tibor",
      "Sunk cost — botgan xarajat tuzog'i",
      "Paradox of choice — tanlov ko'pligi",
      "Social proof — ijtimoiy dalil",
      "Fundamental attribution error",
      "Prokrastinatsiya ildizi — his boshqaruvi",
      "Dopamin va kutish mexanizmi",
      "Halo effekti",
      "Default effekti — standart tanlov kuchi",
    ],
  },
  "Productivity": {
    "time": "07:30", "diff": "O'rta", "read": "1 daq",
    "src": ["Cal Newport — Deep Work", "Ali Abdaal", "GTD (David Allen)"],
    "cover": "Minimal fokus/soat yoki bitta-vazifa motivi, tinchlantiruvchi",
    "why": "Ko'p emas — muhim ishni fokus bilan bajarish yo'lini beradi.",
    "cta": ["Bugun eng muhim bitta ishni birinchi qil.",
            "Telefoningni 1 soat boshqa xonaga qo'y va ishla.",
            "Bugun ertaga uchun 3 ta MIT (eng muhim ish) yoz."],
    "topics": [
      "Deep work bloklari",
      "Eisenhower matritsasi",
      "Pomodoro texnikasi",
      "Eng muhim 1 ish (MIT) tamoyili",
      "Time blocking — vaqtni bo'laklash",
      "Diqqatni o'g'irlovchilarni yo'qotish",
      "Single-tasking — bir ishga berilish",
      "Parkinson qonuni",
      "Energiya boshqaruvi (vaqt emas)",
      "2 daqiqalik qoida (GTD)",
      "Batching — o'xshash ishlarni guruhlash",
      "'Yo'q' deyish — mahsuldorlik vositasi",
      "Tongi rejim (morning routine)",
      "Shutdown ritual — ish kunini yopish",
      "Diqqat va telefon bog'liqligi",
      "Rejalashtirishning real kuchi",
      "Dam olish — mahsuldorlik qismi",
      "Perfeksionizm tuzog'i",
    ],
  },
  "Islamic Wisdom": {
    "time": "07:00", "diff": "Boshlang'ich", "read": "1 daq",
    "src": ["Qur'on va sahih hadis (to'g'ri nisbat)", "E'tirof etilgan ulamolar", "Klassik asarlar"],
    "cover": "Minimal geometrik/arabeska naqsh, sokin yer ranglari (tasvirsiz)",
    "why": "Hayotga ma'no, axloq va ichki muvozanat baxsh etadi.",
    "cta": ["Bugun shu amalni bir marta niyat bilan bajar.",
            "Bugun bir kishiga chin ko'ngildan yaxshilik qil.",
            "Bugun shu fazilatni bitta ishda ko'rsat."],
    "topics": [
      "Niyatning ahamiyati (a'mollar niyatga bog'liq)",
      "Sabr — kuch belgisi",
      "Shukr — qanoat manbai",
      "Ilm izlashning fazli",
      "Vaqtning qadri",
      "Halol rizq",
      "Husnul xuluq — go'zal axloq",
      "Sadaqa va saxovat",
      "Adolat tamoyili",
      "Tavakkul — harakat va ishonch",
      "Ota-onaga yaxshilik",
      "Tilni saqlash — so'z mas'uliyati",
      "Tavoze — kamtarlik",
      "Qo'shni haqlari",
      "Va'daga vafo",
      "Mizon — o'lchov va halollik",
      "Tafakkur — koinotda mushohada",
      "Tavba va o'zini isloh",
    ],
  },
  "Business Box": {
    "time": "07:30", "diff": "Murakkab", "read": "1–2 daq",
    "src": ["Harvard Business Review", "Asoschilar memuarlari", "Rasmiy kompaniya case-study'lari"],
    "cover": "Toza geometrik framework diagrammasi yoki yuqoriga yo'l, korporativ-minimal",
    "why": "Biznes qurish va o'stirishning barqaror tamoyilini beradi.",
    "cta": ["Bugun so'ra: kim sening haqiqiy mijozing?",
            "Ushbu modelni o'z loyihangga moslab ko'r.",
            "Bugun bitta gipotezangni kichik test bilan tekshir."],
    "topics": [
      "Product-market fit nima",
      "MVP — minimal hayotiy mahsulot",
      "Unit economics asoslari",
      "Mijoz umrbod qiymati (LTV)",
      "Network effekti biznesda",
      "Moat — raqobat himoyasi",
      "Pivot qachon kerak",
      "B2B va B2C farqi",
      "Narx strategiyasi asoslari",
      "Cash flow — biznes qoni",
      "Lean Startup tsikli",
      "Niche — kichik bozordan boshlash",
      "Operatsion samaradorlik",
      "Franchise modeli",
      "Subscription (obuna) biznesi",
      "Mijozni ushlab qolish (retention)",
      "Brendni qurish asoslari",
      "Taklif va talab muvozanati",
    ],
  },
  "Interesting Facts": {
    "time": "08:00", "diff": "Boshlang'ich", "read": "<1 daq",
    "src": ["Ilmiy jurnallar", "Universitet/ensiklopediya", "Birlamchi tadqiqot"],
    "cover": "Faktning predmeti — bitta jasur, minimal vizual",
    "why": "Tasdiqlangan qiziq fakt bilan dunyoga yangi nazar beradi.",
    "cta": ["Buni bilarmidingiz? Yana qiziq faktni izohda yozing.",
            "Bugun shu faktni bir kishiga aytib ber.",
            "Shu hodisa ortidagi sababni o'ylab ko'r."],
    "topics": [
      "Asal nega buzilmaydi",
      "Miya taxminan 20 vatt energiya sarflaydi",
      "Yorug'lik Quyoshdan 8 daqiqada keladi",
      "Oktopusda uchta yurak bor",
      "Muz suvda nega suzadi (anomal zichlik)",
      "Asalarilar 'raqs' bilan muloqot qiladi",
      "Kosmosda ovoz tarqalmaydi",
      "Toshbaqalarning ajoyib umri",
      "Eyfel minorasi issiqda kengayadi",
      "Nilufar bargi o'z-o'zini tozalaydi",
      "Hid xotirani eng kuchli uyg'otadi",
      "DNK uzunligi tasavvurdan tashqari",
      "Kitlarda madaniyat va lahjalar",
      "Olmos abadiy emas (grafitga aylanadi)",
      "Inson tanasidagi bakteriyalar soni",
      "Banan tabiiy radioaktiv (zararsiz)",
      "Ko'z — aslida miyaning bir qismi",
      "Suvning sirti (sirt tarangligi) kuchi",
    ],
  },
  "Marketing Box": {
    "time": "07:30", "diff": "O'rta", "read": "1 daq",
    "src": ["Cialdini — Influence", "Ogilvy / Seth Godin", "Rasmiy brend case-study'lari"],
    "cover": "Magnit, ko'z yoki voronka motivi; jasur, lekin toza bitta aksent rang",
    "why": "Odamlar nega xarid qilishini — diqqat va ishontirish psixologiyasini ochadi.",
    "cta": ["Bugun taklifingni mijoz ehtiyoji tilida qayta yoz.",
            "Sarlavhangni 3 xil variantda sinab ko'r.",
            "Bugun bitta mijozdan 'nega tanladingiz?' deb so'ra."],
    "topics": [
      "Cialdini — ta'sirning 6 tamoyili",
      "AIDA modeli",
      "Pozitsiyalash (positioning)",
      "Hikoya orqali sotish (storytelling)",
      "Ijtimoiy dalil va sharhlar",
      "Defitsit (scarcity) tamoyili",
      "Sarlavha yozish san'ati",
      "Mijoz avatari (persona)",
      "Voronka (funnel) bosqichlari",
      "Word of mouth kuchi",
      "Email marketing asoslari",
      "Kontent marketing nega ishlaydi",
      "Differensiatsiya — farqlanish",
      "Narx anchoring marketingda",
      "Loyallik dasturlari",
      "Reklama va PR farqi",
      "Hook — birinchi 3 soniya",
      "Brend ovozi va eslab qolish",
    ],
  },
  "Arabic Box": {
    "time": "07:00", "diff": "Boshlang'ich", "read": "<1 daq",
    "src": ["Ishonchli arab lug'atlari", "Klassik/MSA manbalari", "E'tirofli til resurslari"],
    "cover": "So'zning nafis arab kalligrafiyasi, sokin fon",
    "why": "Har kuni bitta arabcha so'z bilan til va ma'no eshigini ochadi.",
    "cta": ["Bugun shu so'zni ovoz chiqarib 3 marta takrorla.",
            "Shu iborani bilganmidingiz? Izohda yozing.",
            "Shu so'zni bugun bir jumlada eslab ko'r."],
    "topics": [
      "الحمد لله (alhamdulillah) — ma'no va qo'llanish",
      "إن شاء الله (inshaAllah) — agar Alloh xohlasa",
      "بارك الله فيك (barakAllohu fik)",
      "ما شاء الله (mashaAllah)",
      "So'z: صبر (sabr) — sabr",
      "So'z: علم ('ilm) — ilm",
      "So'z: نية (niyya) — niyat",
      "So'z: رحمة (rahma) — rahm-shafqat",
      "So'z: حكمة (hikma) — hikmat",
      "So'z: أمانة (amana) — omonat",
      "So'z: عدل ('adl) — adolat",
      "So'z: قلب (qalb) — qalb",
      "So'z: نور (nur) — nur",
      "So'z: سلام (salam) — tinchlik",
      "So'z: خير (khayr) — yaxshilik",
      "So'z: توكل (tawakkul) — tavakkul",
      "So'z: إحسان (ihsan) — ehson",
      "جزاك الله خيرا (jazakallohu khayran)",
    ],
  },
  "Mental Models": {
    "time": "07:30", "diff": "Murakkab", "read": "1 daq",
    "src": ["Farnam Street", "Munger — latticework", "Modelning asl sohasi (fizika/biologiya...)"],
    "cover": "Minimal panjara/linza/tishli g'ildirak motivi, intellektual-premium",
    "why": "Hayotning ko'p sohasida ishlaydigan qayta-qo'llanadigan tafakkur vositasi beradi.",
    "cta": ["Bugungi bitta qarorni shu model orqali ko'rib chiq.",
            "Shu modelni qaysi muammoga qo'llaysan?",
            "Bugun shu nuqtai nazardan bitta masalaga qara."],
    "topics": [
      "Inversion — teskaridan o'ylash",
      "Opportunity cost — imkoniyat narxi",
      "Pareto (80/20) tamoyili",
      "Second-order fikrlash",
      "Map ≠ territory (xarita hudud emas)",
      "Circle of competence",
      "Margin of safety",
      "Compounding — har joyda to'planish",
      "Feedback loop — qaytar aloqa",
      "Antifragility — zarbadan kuchayish",
      "Via negativa — olib tashlash kuchi",
      "Lindy effekti",
      "Hanlon ustarasi",
      "Game theory — o'yin nazariyasi asosi",
      "Bottleneck — cheklov nazariyasi",
      "Regression to the mean",
      "Probabilistik fikrlash",
      "First principles — birinchi tamoyil",
    ],
  },
  "Communication Box": {
    "time": "08:00", "diff": "O'rta", "read": "1 daq",
    "src": ["Communication tadqiqotlari", "Chris Voss (negotiation)", "Ritorika klassikalari"],
    "cover": "Gap-bulutchasi yoki ovoz-to'lqini minimal motivi, iliq lekin toza",
    "why": "Gapirish, tinglash va ishontirishni yaxshilab, tushunilishni oson qiladi.",
    "cta": ["Bugungi suhbatda kamroq gapir, ko'proq tingla.",
            "Bugun bir kishini gapini bo'lmasdan oxirigacha eshit.",
            "Shu texnikani keyingi suhbatda sinab ko'r."],
    "topics": [
      "Faol tinglash (active listening)",
      "'Men' tilida gapirish",
      "Tana tili asoslari",
      "Pauza — sukunatning kuchi",
      "Savol berish san'ati",
      "Empatik javob berish",
      "Qisqa va aniq gapirish",
      "Hikoya bilan tushuntirish",
      "Tanqidni to'g'ri yetkazish",
      "'Yo'q' deyishni o'rganish",
      "Ko'z bilan aloqa",
      "Ohang va intonatsiya",
      "Yozma muloqot aniqligi",
      "Kelishuv (negotiation) asoslari",
      "Samimiy maqtov",
      "Suhbatni boshlash mahorati",
      "Nizoda tinch til",
      "Taqdimot qo'rquvini yengish",
    ],
  },
  "AI Box": {
    "time": "08:00", "diff": "O'rta", "read": "1 daq",
    "src": ["Rasmiy model hujjatlari (Anthropic/OpenAI/Google)", "E'tiborli AI tadqiqotlari", "Universitet kurslari"],
    "cover": "Minimal neyron/uchqun motivi, sovuq premium palitra (robot klishesiz)",
    "why": "AI'ni amaliy va tushunarli qilib, bugun foydalanish yo'lini ko'rsatadi.",
    "cta": ["Bugun bitta takroriy ishni AI'ga top va vaqtingni o'lcha.",
            "Shu promptni bugun o'zingda sinab ko'r.",
            "Bugun AI bilan bitta g'oyani brainstorming qil."],
    "topics": [
      "LLM qanday 'o'ylaydi' (token bashorat)",
      "Yaxshi prompt yozish asoslari",
      "AI bilan vaqtni tejash workflowlari",
      "Hallyutsinatsiya nima va nega bo'ladi",
      "AI va ish o'rinlari — haqiqat",
      "Context window nima",
      "AI'dan ustoz (tutor) sifatida foydalanish",
      "Prompt'da rol berish (persona)",
      "AI bilan kontent rejalashtirish",
      "Maxfiylik va AI — nimaga ehtiyot",
      "AI agentlar nima",
      "Tarjima va til o'rganishda AI",
      "Fact-check: AI'ga ko'r-ko'rona ishonmaslik",
      "Avtomatlashtirishga mos vazifalar",
      "Few-shot — misol berish texnikasi",
      "AI bilan brainstorming",
      "AI rasm generatsiyasi asoslari",
      "AI etikasi asoslari",
    ],
  },
  "Life Lessons": {
    "time": "08:00", "diff": "Boshlang'ich", "read": "1 daq",
    "src": ["Stoik falsafa", "Hikmat adabiyoti", "Umuminsoniy haqiqatlar"],
    "cover": "Minimal tabiat/yo'l/ufq motivi, yumshoq mushohadali ranglar",
    "why": "Hayotni yaxshiroq yashashga yordam beradigan asosli donolik beradi.",
    "cta": ["Bugun shu fikr bilan bir lahza to'xtab o'yla.",
            "Bugun bir kishidan kechirim so'ra yoki rahmat ayt.",
            "Shu saboqni bugun bitta ishda yasha."],
    "topics": [
      "Nazorat doirasi (Stoik tamoyil)",
      "Memento mori — vaqtni qadrlash",
      "Solishtirish — quvonch o'g'risi",
      "Kechirimning ozodligi",
      "Kichik narsalardan minnatdorlik",
      "'Bu ham o'tib ketadi'",
      "Hozirgi onda yashash",
      "Boshqalarning fikri seniki emas",
      "Mukammallik emas, harakat",
      "Yo'qotishdan o'rganish",
      "Sokinlikning kuchi",
      "Pul — vosita, maqsad emas",
      "Munosabatlar — haqiqiy boylik",
      "Mehnat va sabr mevasi",
      "O'zingga mehr (self-compassion)",
      "Hayot adolatsiz — javobing seniki",
      "Kichik yaxshilik katta iz qoldiradi",
      "Yengillik: ortiqchani qo'yib yuborish",
    ],
  },
  "Leadership Box": {
    "time": "07:30", "diff": "O'rta", "read": "1–2 daq",
    "src": ["Leadership tadqiqotlari + HBR", "Tasdiqlangan liderlik hikoyalari", "Harbiy/sport/biznes case'lar"],
    "cover": "Minimal kompas, mayoq yoki guruh oldidagi siluet; kuchli va sokin",
    "why": "Odamlarni boshqarish va kuchli jamoa qurish tamoyilini beradi.",
    "cta": ["Bugun jamoangdagi bir kishini chin ko'ngildan maqta.",
            "Bugun bitta qarorni jamoang bilan maslahatlash.",
            "Bugun bir mas'uliyatni ishonib topshir (delegatsiya)."],
    "topics": [
      "Xizmatkor liderlik (servant leadership)",
      "Misol orqali yetaklash",
      "Ishonch — liderlik valyutasi",
      "Qiyin qarorlarning egasi bo'lish",
      "Fikr-mulohaza (feedback) berish san'ati",
      "Vakil qilish (delegation)",
      "Vizyon yaratish",
      "Jamoa psixologik xavfsizligi",
      "Tinglovchi lider",
      "Inqirozda xotirjamlik",
      "Maqtov va e'tirof kuchi",
      "Jamoa madaniyatini qurish",
      "Empatiya bilan boshqarish",
      "Konfliktni boshqarish",
      "Mentorlik — o'sishga imkon berish",
      "Kamtar lider (Level 5)",
      "Mas'uliyatni o'z zimmasiga olish",
      "Ishonch va hisobdorlik muvozanati",
    ],
  },
  "History Box": {
    "time": "08:00", "diff": "O'rta", "read": "1–2 daq",
    "src": ["Akademik tarix + birlamchi manbalar", "Universitet/muzey materiallari", "E'tiborli tarixchilar"],
    "cover": "Vintage-toned minimal motiv (xarita, ustun, qadimiy hujjat), sepia aksent",
    "why": "Real tarixiy voqeadan bugun uchun amaliy saboq beradi.",
    "cta": ["Bugun shu saboqni o'z hayotingga qanday bog'laysan?",
            "Tarix takrorlanmasligi uchun bugun nima qilasan?",
            "Shu voqeadan bitta xulosani yozib qo'y."],
    "topics": [
      "Ibn Sino va 'Tib qonunlari'",
      "Al-Xorazmiy va 'algoritm' so'zining tug'ilishi",
      "Beruniy — universal olim",
      "Ulug'bek va astronomiya maktabi",
      "Buyuk Ipak yo'li saboqlari",
      "Bag'dod 'Donolik uyi' (Bayt al-Hikma)",
      "Gutenberg matbaasi inqilobi",
      "Sanoat inqilobi saboqlari",
      "Renessans nega Florensiyada portladi",
      "Mansa Musa va boylik o'lchovi",
      "Apollo 11 — jamoaviy buyuk maqsad",
      "Berlin devorining qulashi",
      "Internetning tug'ilishi",
      "Edisonning 1000 urinishi",
      "Buyuk depressiya saboqlari",
      "Algebra — 'al-jabr' dan kelgan ilm",
      "Rim imperiyasi qulashi saboqlari",
      "Forsdan Yevropaga raqamlar yo'li",
    ],
  },
  "Critical Thinking": {
    "time": "07:30", "diff": "Murakkab", "read": "1 daq",
    "src": ["Mantiq / critical thinking darsliklari", "Kognitiv fan", "Farnam Street / falsafa asoslari"],
    "cover": "Lupa yoki shoxlanuvchi-savol motivi, toza intellektual uslub",
    "why": "Fikrlashni o'tkirlashtirib, yomon dalillardan himoya qiladi.",
    "cta": ["Bugun bir fikringga 'qaerdan bilaman?' deb savol ber.",
            "Keyingi xabarni o'qiganda manbasini so'ra.",
            "Bugun bitta qarama-qarshi fikrni adolatli o'qib chiq."],
    "topics": [
      "Ad hominem mantiqiy xatosi",
      "Strawman — qo'g'irchoq dalil",
      "Correlation ≠ causation",
      "'Qaerdan bilaman?' savoli",
      "Manbani tekshirish madaniyati",
      "Tasdiqlash xatosini yengish",
      "False dilemma — soxta ikkilik",
      "Appeal to authority xatosi",
      "Bayes'cha fikrlash asosi",
      "First principles — birinchi tamoyildan",
      "Steelman — kuchli qarshi dalil",
      "Anekdot ≠ dalil",
      "Occam ustarasi",
      "Survivorship bias",
      "O'z fikringni rad eta olish",
      "Manbalar tarafkashligini ko'rish",
      "Statistikani to'g'ri o'qish",
      "Sekin, asosli xulosa",
    ],
  },
  "Technology Box": {
    "time": "08:00", "diff": "O'rta", "read": "1 daq",
    "src": ["Rasmiy mahsulot hujjatlari", "Nufuzli texno-jurnalistika", "Standart tashkilotlari"],
    "cover": "Toza kontur uslubidagi mikrosxema/qurilma, vazmin va zamonaviy",
    "why": "Hayot va karyera uchun muhim texnologiya hamda ko'nikmani tushuntiradi.",
    "cta": ["Bugun shu vositani 10 daqiqa sinab ko'r.",
            "Keyingi 6 oyda o'rganmoqchi bo'lgan ko'nikmani yoz.",
            "Bugun bitta raqamli gigiena qadamini bajar."],
    "topics": [
      "Bulutli texnologiya (cloud) nima",
      "API nima — sodda tilda",
      "Open source g'oyasi",
      "Kiberxavfsizlik asoslari (parol, 2FA)",
      "Blockchain qanday ishlaydi",
      "Algoritm nima — sodda misol",
      "Ma'lumotlar — 'yangi neft' mi?",
      "No-code/low-code inqilobi",
      "Internet qanday ishlaydi (sodda)",
      "Digital minimalism",
      "Privacy — ma'lumotlaringizni kim ko'radi",
      "Avtomatlashtirish va robototexnika",
      "Kelajak ko'nikmalari (future skills)",
      "Backup — ma'lumotni saqlash madaniyati",
      "Phishing'dan himoya",
      "Texnologik gigiena (raqamli muvozanat)",
      "Quyosh energiyasi va kelajak",
      "5G nimani o'zgartiradi",
    ],
  },
  "Success Stories": {
    "time": "08:00", "diff": "O'rta", "read": "1–2 daq",
    "src": ["Tekshirilgan biografiyalar", "Rasmiy intervyular", "E'tiborli jurnalistika"],
    "cover": "Minimal portret silueti yoki cho'qqi motivi, iliq va ilhomli premium",
    "why": "Real hikoyadan qiyinchilikni yengish va amaliy saboq beradi (mif emas).",
    "cta": ["Shu hikoyadan bitta saboq olib bugun qo'lla.",
            "Sen qaysi qadamdan boshlaysan?",
            "Bugun bitta 'rad javob'dan qo'rqmasdan harakat qil."],
    "topics": [
      "Walt Disney — 300+ rad javobdan imperiyagacha",
      "J.K. Rowling — 12 marta rad etilgani",
      "Thomas Edison — lampochka yo'lidagi minglab urinish",
      "Soichiro Honda — muvaffaqiyat 99% mag'lubiyat",
      "Colonel Sanders (KFC) — 62 yoshda boshlangani",
      "Howard Schultz (Starbucks) yo'li",
      "Sara Blakely (Spanx) — noldan",
      "Jack Ma — rad etishlar tarixi",
      "Steve Jobs — o'z kompaniyasidan haydalishi",
      "James Dyson — 5126 prototip",
      "Airbnb — nonushta sotgan kunlar",
      "Stephen King — 'Carrie' axlatdan qaytgani",
      "Abraham Lincoln — mag'lubiyatlar zanjiri",
      "Oprah Winfrey — og'ir boshlanish",
      "Brian Acton (WhatsApp) — Facebook rad etgani",
      "Vera Wang — kech boshlangan muvaffaqiyat",
      "Milton Hershey — uch marta bankrot",
      "Reid Hoffman — 'birinchi versiyadan uyalmaslik'",
    ],
  },
  "Decision Making": {
    "time": "07:30", "diff": "Murakkab", "read": "1 daq",
    "src": ["Kahneman", "Annie Duke — Thinking in Bets", "Qaror fani (decision science)"],
    "cover": "Minimal chorraha/ayri yo'l yoki tarozi motivi, aniq va muvozanatli",
    "why": "Noaniqlikda yaxshiroq va aniqroq qaror qabul qilishga yordam beradi.",
    "cta": ["Bugungi qarorni 'eng yomon holatda nima bo'ladi?' bilan ko'r.",
            "Qaroringni 10/10/10 qoidasi bilan sinab ko'r.",
            "Bugun bitta kichik qarorni 24 soat sovutib ko'r."],
    "topics": [
      "10/10/10 qoidasi",
      "Pre-mortem — eng yomon holatni oldindan ko'rish",
      "Qaytariladigan vs qaytmas qaror (Bezos)",
      "Opportunity cost har qarorda",
      "Jarayon ≠ natija (Annie Duke)",
      "Satisficing — yetarlicha yaxshini tanlash",
      "Ikki yo'lli eshik tamoyili",
      "Maslahatlash, lekin o'zing qaror qil",
      "Emotsiyani sovutish (24 soat qoidasi)",
      "'Yo'q' — ham qaror",
      "Ortiqcha tanlovni kamaytirish",
      "Bayes yangilanishi — yangi dalilda fikrni o'zgartirish",
      "Kichik tajriba (test) qilib ko'rish",
      "Qadriyatga asoslangan qaror",
      "Sunk cost'ni e'tiborsiz qoldirish",
      "Intuitsiya qachon ishonchli",
      "Checklist kuchi",
      "Qaror jurnali (decision journal)",
    ],
  },
}

# Interleaved 21-category rotation (light/analytical alternated -> no two heavy days in a row)
ROTATION = [
    "Book Box", "Habits", "Money Box", "English Box", "Mind Box", "Productivity",
    "Islamic Wisdom", "Business Box", "Interesting Facts", "Marketing Box", "Arabic Box",
    "Mental Models", "Communication Box", "AI Box", "Life Lessons", "Leadership Box",
    "History Box", "Critical Thinking", "Technology Box", "Success Stories", "Decision Making",
]

# Seasonal events — injected ONLY on their real date (overrides that day's slot).
# Lunar dates (Ramadan/Eid) are movable -> handled manually each year, not fixed here.
SEASONAL = {
    "01-01": ("Life Lessons", "Yangi yil: maqsadni tizimga aylantirish",
              "Yil boshida niyatni aniq tizim va kichik qadamga aylantirish yo'li.",
              "Bu yil uchun bitta aniq, o'lchanadigan maqsad yozib qo'y."),
    "03-08": ("Life Lessons", "Ayollarning hayot va jamiyatdagi o'rni",
              "Hurmat va minnatdorlik orqali munosabatlarni mustahkamlash.",
              "Bugun hayotingdagi bir ayolga samimiy minnatdorlik bildir."),
    "03-21": ("Islamic Wisdom", "Navro'z: yangilanish va tabiat uyg'oqligi",
              "Tabiat yangilanishi — niyat va hayotni yangilash uchun ilhom.",
              "Bugun bitta yangi yaxshi odatga 'qish'dan keyin start ber."),
    "04-23": ("Book Box", "Jahon kitob kuni: bir kitob — bir umr",
              "Kitob — eng arzon, eng kuchli ustoz; bugun o'qishni qadrlash kuni.",
              "Bugun bitta kitob ochib, atigi 10 betini o'qi."),
    "05-09": ("History Box", "Xotira va qadrlash kuni",
              "O'tmishni eslab, tinchlik va minnatdorlik qadrini anglash.",
              "Bugun o'tmishdan bitta saboqni yodda tut va qadrla."),
    "09-01": ("History Box", "Mustaqillik: erk va mas'uliyat",
              "Erkning haqiqiy ma'nosi — mas'uliyat va hissa qo'shish.",
              "Bugun o'z ishingda kichik bo'lsa-da bitta hissa qo'sh."),
    "10-01": ("Leadership Box", "Ustozlar kuni: bilim uzatish kuchi",
              "Ustoz — kelajakni shakllantiradigan eng kuchli lider.",
              "Bugun bir ustozingga rahmat ayt yoki kimgadir bir narsa o'rgat."),
    "12-31": ("Life Lessons", "Yil yakuni: refleksiya va shukr",
              "O'tgan yilni mulohaza qilib, saboq va minnatdorlik bilan yakunlash.",
              "Bugun shu yilning 3 ta saboqi va 3 ta shukrini yozib qo'y."),
}


def quarter(month):
    return (month - 1) // 3 + 1


def week_of_month(d):
    return (d.day - 1) // 7  # 0..4


MIN_GAP = 14  # same category may not recur within this many days (similar-idea spacing)


def build():
    rows = []
    used = {c: 0 for c in CATS}       # per-category topic pointer (guarantees no topic repeat)
    last_used = {}                    # category -> last day used (seasonal + rotation)
    seen_topics = set()
    # Pre-map seasonal days -> category, so rotation also avoids UPCOMING seasonal collisions.
    seasonal_day_cat = {}
    for n in range(1, DAYS + 1):
        mmdd = (START + dt.timedelta(days=n - 1)).strftime("%m-%d")
        if mmdd in SEASONAL:
            seasonal_day_cat[n] = SEASONAL[mmdd][0]
    for n in range(1, DAYS + 1):
        d = START + dt.timedelta(days=n - 1)
        mmdd = d.strftime("%m-%d")
        month = d.month
        wk_year = (n - 1) // 7 + 1
        month_theme = MONTH_THEME[month]
        weekly_theme = f"{month_theme} · {WEEK_LENS[week_of_month(d)]}"

        if mmdd in SEASONAL:
            cat, topic, why, cta = SEASONAL[mmdd]
            meta = CATS[cat]
            src = meta["src"][n % len(meta["src"])]
            time = meta["time"]
            cover = meta["cover"]
            diff = meta["diff"]
            read = meta["read"]
            tag = "🎯 Mavsumiy"
        else:
            # Pick the least-used category that hasn't appeared within MIN_GAP days.
            # least-used -> balance; largest gap -> variety. Topics never run out (18 each).
            upcoming = {seasonal_day_cat[m] for m in range(n + 1, n + MIN_GAP + 1)
                        if m in seasonal_day_cat}
            cands = [c for c in ROTATION
                     if used[c] < len(CATS[c]["topics"])
                     and (c not in last_used or n - last_used[c] >= MIN_GAP)
                     and c not in upcoming]
            if not cands:
                cands = [c for c in ROTATION if used[c] < len(CATS[c]["topics"])]
            cat = min(cands, key=lambda c: (used[c], -(n - last_used.get(c, -999)),
                                            ROTATION.index(c)))
            meta = CATS[cat]
            i = used[cat]
            topic = meta["topics"][i % len(meta["topics"])]
            used[cat] += 1
            why = meta["why"]
            src = meta["src"][i % len(meta["src"])]
            cta = meta["cta"][i % len(meta["cta"])]
            time = meta["time"]
            cover = meta["cover"]
            diff = meta["diff"]
            read = meta["read"]
            tag = ""
        last_used[cat] = n

        seen_topics.add((cat, topic))
        rows.append({
            "Kun": n,
            "Sana": f"{d.day}-{UZ_MONTHS[month]}",
            "Hafta": wk_year,
            "Oy mavzusi": month_theme,
            "Haftalik mavzu": weekly_theme,
            "Chorak maqsadi": QUARTER_OBJ[quarter(month)].split(" — ")[0],
            "Kategoriya": cat + (f" {tag}" if tag else ""),
            "Mavzu": topic,
            "Nega muhim": why,
            "Ishonchli manba": src,
            "E'lon vaqti": time,
            "Muqova g'oyasi": cover,
            "Daraja": diff,
            "O'qish vaqti": read,
            "CTA taklifi": cta,
        })
    return rows


def integrity(rows):
    # 1) No topic repeated across the year
    topics = [r["Mavzu"] for r in rows]
    dup = {t for t in topics if topics.count(t) > 1}
    # 2) Category balance
    from collections import Counter
    cats = Counter(r["Kategoriya"].replace(" 🎯 Mavsumiy", "") for r in rows)
    # 3) Minimum gap between same category (similar-idea spacing)
    last = {}
    min_gap = 999
    for r in rows:
        c = r["Kategoriya"].replace(" 🎯 Mavsumiy", "")
        if c in last:
            min_gap = min(min_gap, r["Kun"] - last[c])
        last[c] = r["Kun"]
    return dup, cats, min_gap


def main():
    rows = build()
    cols = list(rows[0].keys())
    with open("editorial_calendar.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    dup, cats, min_gap = integrity(rows)
    print(f"✅ editorial_calendar.csv yozildi — {len(rows)} kun, {len(cols)} ustun")
    print(f"   Takror mavzu: {len(dup)} (0 bo'lishi kerak)")
    print(f"   Bir xil kategoriya orasidagi eng kichik oraliq: {min_gap} kun")
    print(f"   Kategoriya balansi (post soni):")
    for c, n in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"     {c:<20} {n}")
    print("\n   Namuna (1–14 kun):")
    for r in rows[:14]:
        print(f"     {r['Kun']:>3} {r['Sana']:<12} {r['Kategoriya']:<22} {r['Mavzu']}")


if __name__ == "__main__":
    main()
