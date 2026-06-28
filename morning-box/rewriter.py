"""Morning Box — algoritmik (AI'siz, BEPUL) tahrirlash quvuri.

Quvur: clean -> normalize -> restructure -> (spin) -> brand.
Sof Python + re. Tarmoq yo'q -> tez, yengil, testlash oson.
"""
from __future__ import annotations
import re

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

# O'zbek/rus stop-so'zlar (qisqa ro'yxat — ekstraktiv baholash uchun)
STOP = {
    "va", "bilan", "uchun", "bu", "ham", "lekin", "yani", "yoki", "deb", "edi",
    "boldi", "boladi", "kerak", "shu", "ular", "biz", "men", "sen", "u",
    "и", "в", "на", "что", "это", "как", "по", "из", "за", "то", "не", "он",
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
    t = _FWD.sub("", t)
    t = _USER.sub("", t)
    t = _URL.sub("", t)
    t = _CTA.sub("", t)
    return t


def normalize(t: str) -> str:
    """Bo'shliq, tire, tirnoq, bosh harflarni tartibga soladi."""
    t = t.replace("«", "\"").replace("»", "\"").replace("—", "—")
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
    """Ekstraktiv: sarlavha + eng muhim `top` jumla (chastota+o'rin bo'yicha)."""
    sents = [s.strip() for s in _SENT.split(t) if s.strip()]
    if not sents:
        return "", ""
    freq = _freq(t)

    def score(i: int, s: str) -> float:
        sc = sum(freq.get(w, 0) for w in _WORD.findall(s.lower()))
        sc = sc / (len(s.split()) + 1)
        if i == 0:
            sc += 0.5                      # birinchi jumla bonus
        return sc

    ranked = sorted(enumerate(sents), key=lambda x: score(*x), reverse=True)
    keep_idx = sorted(i for i, _ in ranked[:top])
    body = " ".join(sents[i] for i in keep_idx)
    title = sents[0][:80].rstrip(".!?…")
    return title, body


def spin(t: str) -> str:
    """Yengil sinonim almashtirish (faqat ishonchli lug'at). Buzmaydi."""
    return _WORD.sub(lambda m: SYN.get(m.group().lower(), m.group()), t)


def make_hashtags(t: str, base: str = "", n: int = 2) -> str:
    """Eng tez-tez uchragan kalit so'zlardan hashtag yasaydi."""
    words = [w for w in _HWORD.findall(t) if w.lower() not in STOP]
    top = sorted(set(words), key=lambda w: t.lower().count(w.lower()), reverse=True)[:n]
    auto = " ".join("#" + w.capitalize() for w in top)
    return (base + " " + auto).strip()


def to_morning_box(raw: str, pattern: dict | None = None, channel: str = "") -> str:
    """To'liq quvur: xom post -> Morning Box brendidagi tayyor matn."""
    pattern = pattern or {}
    lvl = int(pattern.get("rewrite_lvl", 1) or 0)

    t = normalize(clean(raw))
    title, body = restructure(t)
    if lvl >= 2:
        body = spin(body)
    if lvl == 0:                          # faqat tozalash rejimi
        title, body = "", t

    tags = make_hashtags(t, pattern.get("hashtags", ""))
    header = pattern.get("header", "📦 <b>Morning Box</b>")
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
    pat = {"header": "📦 <b>Morning Box</b>", "footer": "👉 {channel} · obuna bo'ling 🔔",
           "hashtags": "#MorningBox", "rewrite_lvl": 1}
    print(to_morning_box(demo, pat, "@morningbox_demo"))
