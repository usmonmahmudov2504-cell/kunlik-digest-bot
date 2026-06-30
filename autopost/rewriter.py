"""AvtoPost — algoritmik (AI'siz, BEPUL) tahrirlash quvuri.

Quvur: clean -> normalize -> restructure -> (spin) -> brand.
Sof Python + re. Tarmoq yo'q -> tez, yengil, testlash oson.
"""
from __future__ import annotations
import re
import html as _html

# Regex'lar bir marta kompilyatsiya (tezlik/xotira)
_FWD   = re.compile(r"(?im)^.*(переслано|forwarded from|via)\b.*$")
_USER  = re.compile(r"@\w+")
_URL   = re.compile(r"https?://\S+|t\.me/\S+")
_CTA   = re.compile(r"(?im)(reklama|obuna bo.?ling|подпи\w+|subscribe|join us).*$")
_WS    = re.compile(r"[ \t]+")
_NL    = re.compile(r"\n{3,}")
_SENT  = re.compile(r"(?<=[.!?…])\s+")
_WORD  = re.compile(r"[0-9A-Za-zЀ-ӿ'’]+")
_HWORD = re.compile(r"[A-Za-zЀ-ӿ]{4,}")

# O'zbek/rus stop-so'zlar (ekstraktiv baholash uchun)
STOP = {
    "va", "bilan", "uchun", "bu", "ham", "lekin", "yani", "yoki", "deb", "edi",
    "boldi", "boladi", "kerak", "shu", "ular", "biz", "men", "sen", "endi",
    "ushbu", "uning", "ularning", "hamda", "ammo", "agar", "chunki", "qilib",
    "и", "в", "на", "что", "это", "как", "по", "из", "за", "то", "не", "он",
    "the", "and", "for", "with", "this", "that", "from", "are", "was",
}
# Hashtag uchun QO'SHIMCHA chiqarib tashlanadigan (umumiy sifat/fe'llar -> ot/brend qolsin)
HASH_STOP = {
    "yangi", "katta", "yaxshi", "muhim", "kop", "ko'p", "tez", "zor", "ajoyib",
    "barobar", "million", "milliard", "dollar", "so'm", "yil", "kun", "bugun",
    "kompaniya", "model", "narxi", "keng", "taqdim", "etdi", "oldi", "boldi",
}

# Juda ehtiyotkor sinonim lug'ati (rewrite_lvl>=2). Agressiv emas -> sifat saqlanadi.
SYN = {
    "aytdi": "ta'kidladi", "dedi": "bildirdi", "katta": "yirik", "tez": "shiddatli",
    "yangi": "so'nggi", "ko'rsatdi": "namoyish etdi", "ortdi": "oshdi",
    "muhim": "ahamiyatli", "yaxshi": "sifatli", "ko'p": "salmoqli",
}


def clean(t: str) -> str:
    """Manba izlarini olib tashlaydi: forward, @user, havola, reklama CTA."""
    t = t or ""
    t = _html.unescape(t)                # &laquo; &nbsp; &amp; ... -> haqiqiy belgilar
    t = re.sub(r"<[^>]+>", " ", t)        # qolgan HTML teglar (summary'da bo'lishi mumkin)
    t = _FWD.sub("", t)
    t = _USER.sub("", t)
    t = _URL.sub("", t)
    t = _CTA.sub("", t)
    return t


def normalize(t: str) -> str:
    """Bo'shliq, tire, tirnoq, bosh harflarni tartibga soladi."""
    t = t.replace("«", "\"").replace("»", "\"").replace("\xa0", " ")
    t = _WS.sub(" ", t)
    t = _NL.sub("\n\n", t)
    # har jumlani bosh harf bilan boshlash
    out = []
    for s in _SENT.split(t.strip()):
        s = s.strip()
        if s:
            out.append(s[0].upper() + s[1:])
    return " ".join(out)


def _freq(text: str) -> dict:
    f: dict = {}
    for w in _WORD.findall(text.lower()):
        if w not in STOP and len(w) > 3:
            f[w] = f.get(w, 0) + 1
    return f


def restructure(t: str, top: int = 3) -> tuple[str, str]:
    """Ekstraktiv: sarlavha = 1-jumla; tana = qolganlardan eng muhim jumlalar.

    Sarlavha tanada TAKRORLANMAYDI (1-jumla tanaga kirmaydi)."""
    sents = []                             # yangi qator + jumla belgisi -> chegara
    for line in t.split("\n"):
        sents += [s.strip() for s in _SENT.split(line) if s.strip()]
    if not sents:
        return "", ""
    title = sents[0].rstrip(".!?…")[:120]
    rest = sents[1:]
    if not rest:
        return title, ""
    freq = _freq(t)

    def score(s: str) -> float:
        return sum(freq.get(w, 0) for w in _WORD.findall(s.lower())) / (len(s.split()) + 1)

    ranked = sorted(range(len(rest)), key=lambda i: score(rest[i]), reverse=True)
    keep = sorted(ranked[:top])            # asl tartibni saqlaymiz
    body = " ".join(rest[i] for i in keep)
    return title, body


def spin(t: str) -> str:
    """Yengil sinonim almashtirish (faqat ishonchli lug'at). Buzmaydi."""
    return _WORD.sub(lambda m: SYN.get(m.group().lower(), m.group()), t)


# Narx: raqam + valyuta (so'm/sum/$/dollar). 4+ raqamli -> tasodifiy sonni o'tkazib yuboradi.
_PRICE_AFTER = re.compile(
    r"(\d[\d\s. ,]{3,})\s*(so'm|so‘m|so’m|sum|сум|сўм|\$|dollar|y\.?\s?e\.?|у\.?\s?е\.?)", re.I)
_PRICE_USD = re.compile(r"\$\s?(\d(?:[\d\s,]*\d)?)")   # oxiri raqam -> nuqta/probel yutilmaydi


def _fmt_num(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def reprice(t: str, percent: int = 0) -> str:
    """Postdagi narxlarni `percent` foizga oshiradi (do'kon reseller uchun).

    so'm -> 1000 ga, dollar -> butun songa yaxlitlanadi. percent<=0 -> tegmaydi."""
    if percent <= 0 or not t:
        return t

    def bump_after(m):
        digits = re.sub(r"\D", "", m.group(1))
        if len(digits) < 4:                       # 4 raqamdan kam -> narx emas, tegmaymiz
            return m.group(0)
        new = int(digits) * (100 + percent) / 100
        new = round(new / 1000) * 1000
        return _fmt_num(new) + " " + m.group(2)

    def bump_usd(m):
        digits = re.sub(r"\D", "", m.group(1))
        if not digits:
            return m.group(0)
        new = round(int(digits) * (100 + percent) / 100)
        return "$" + _fmt_num(new)

    t = _PRICE_AFTER.sub(bump_after, t)
    t = _PRICE_USD.sub(bump_usd, t)
    return t


def make_hashtags(t: str, base: str = "", n: int = 2) -> str:
    """Hashtag: ot/brendlarni afzal ko'radi (bosh harfli so'z) + chastota.

    Umumiy sifat/fe'llar (HASH_STOP) chiqarib tashlanadi -> mazmunliroq teglar."""
    cand: dict[str, tuple] = {}              # lower -> (asl_yozuv, (bosh_harfli, chastota))
    low = t.lower()
    for w in _HWORD.findall(t):
        lw = w.lower()
        if lw in STOP or lw in HASH_STOP:
            continue
        cap = 1 if w[0].isupper() else 0     # bosh harfli -> ehtimol ot/brend
        if lw not in cand:
            cand[lw] = (w, (cap, low.count(lw)))
    top = sorted(cand.values(), key=lambda v: v[1], reverse=True)[:n]
    auto = " ".join("#" + w[0][0].upper() + w[0][1:] for w in top)
    return (base + " " + auto).strip()


def brandify(raw: str, pattern: dict | None = None, channel: str = "", markup: int = 0) -> str:
    """To'liq quvur: xom post -> AvtoPost brendidagi tayyor matn.

    markup>0 -> DO'KON rejimi: narx oshiriladi va to'liq matn saqlanadi (qisqartirilmaydi)."""
    pattern = pattern or {}
    lvl = int(pattern.get("rewrite_lvl", 1) or 0)

    t = normalize(clean(raw))
    if markup and markup > 0:             # do'kon posti: narxni oshir + to'liq saqla
        t = reprice(t, markup)
        title, body = "", t
    else:
        title, body = restructure(t)
        if lvl >= 2:
            body = spin(body)
        if lvl == 0:                      # faqat tozalash rejimi
            title, body = "", t

    tags = make_hashtags(t, pattern.get("hashtags", ""))
    header = pattern.get("header", "🚀 <b>AvtoPost</b>")
    footer = pattern.get("footer", "")
    if footer and channel:
        footer = footer.replace("{channel}", channel)

    parts = [header, "━━━━━━━━━━━"]
    if title:
        parts.append(f"<b>{title}</b>")
    if body:
        parts.append(body)
    if footer:
        parts += ["", footer]
    if tags:
        parts.append(tags)
    return "\n".join(p for p in parts if p)[:4096]


if __name__ == "__main__":
    demo = ("Переслано from @some_channel\n"
            "Yangi AI startap katta investitsiya oldi. Kompaniya 10 million dollar "
            "jamg'ardi. Bu yil ular bozorni kengaytirmoqchi. Obuna bo'ling @some_channel "
            "https://t.me/some_channel")
    pat = {"header": "🚀 <b>AvtoPost</b>", "footer": "👉 {channel} · obuna bo'ling 🔔",
           "hashtags": "#AvtoPost", "rewrite_lvl": 1}
    print(brandify(demo, pat, "@avtopost_demo"))
