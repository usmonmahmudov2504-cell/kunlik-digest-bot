"""
Discussion AI Bot — Telegram kanal muhokama guruhida AI suhbatdoshi.

Ishlash tartibi:
  1. Kanalga discussion guruh ulanadi (Telegram kanal sozlamalari → Discussion).
  2. Bot o'sha guruhga admin qilib qo'shiladi.
  3. Guruhda kimdir xabar yozsa, bot AI yordamida javob beradi.
  4. Kanal persona va ovozi channels.json dagi voice_persona/voice_focus dan olinadi.

Ishga tushirish:
  python discussion_bot.py

Muhit o'zgaruvchilari:
  TELEGRAM_BOT_TOKEN   — bot tokeni (@BotFather dan)
  GEMINI_API_KEY       — Gemini (bepul, birinchi urinadi)
  ANTHROPIC_API_KEY    — Claude (zaxira)
"""

from __future__ import annotations
import os
import json
import datetime
import asyncio
import requests
from collections import defaultdict

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ------------------------------------------------------------------ SOZLAMALAR
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# Suhbat tarixi: {chat_id: [(role, text), ...]}
_history: dict[int, list[tuple[str, str]]] = defaultdict(list)
HISTORY_LEN = 6          # kontekst uchun oxirgi nechta juft saqlash

# Rate limiting: {user_id: oxirgi_javob_vaqti}
_rate: dict[int, datetime.datetime] = {}
RATE_SECONDS = 4         # bir foydalanuvchiga minimal javob oralig'i (soniya)

# Gemini modellari (ketma-ket sinanadi)
_GEMINI_USER = os.environ.get("GEMINI_MODEL", "").strip()
GEMINI_MODELS = list(dict.fromkeys(([_GEMINI_USER] if _GEMINI_USER else []) + [
    "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-latest"]))

HERE = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------ KANALLAR
def load_channels() -> list[dict]:
    p = os.path.join(HERE, "channels.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def find_cfg(chat_id: int) -> dict:
    """Discussion guruh chat_id bo'yicha kanal konfiguratsiyasini topadi.

    Topilmasa — standart (anonim) persona qaytaradi."""
    for cfg in load_channels():
        if cfg.get("discussion_chat_id") == chat_id:
            return cfg
    return {}


# ------------------------------------------------------------------ AI JAVOB
_SYS_TMPL = (
    "Sen {persona}san. "
    "Telegram kanalning muhokama guruhida o'quvchilar bilan suhbatlashyapsan. "
    "Javob talablari:\n"
    "- O'zbek tilida (lotin alifbosida) yoz.\n"
    "- Qisqa va aniq: 2–4 jumla, ortiqcha emas.\n"
    "- Samimiy, iliq, professional ohang — spam yoki clickbait yo'q.\n"
    "- HTML, markdown, yulduzcha (*) ishlatma — faqat oddiy matn.\n"
    "- Agar savol noaniq bo'lsa, aniqlashtiruvchi savol ber.\n"
    "Yo'nalish: {focus}"
)

DEFAULT_PERSONA = "bilimli, samimiy va iliq suhbatdosh"
DEFAULT_FOCUS   = "Savolga aniq, foydali va qisqa javob ber."


def _build_system(cfg: dict) -> str:
    persona = (cfg.get("voice_persona") or DEFAULT_PERSONA).strip()
    focus_raw = (cfg.get("voice_focus") or DEFAULT_FOCUS).strip()
    # voice_focus uzun bo'lsa (Morning Box kabi) — faqat birinchi jumlani olish
    focus = focus_raw.split(".")[0].strip() + "." if "." in focus_raw else focus_raw
    return _SYS_TMPL.format(persona=persona, focus=focus)


def _gemini(system: str, history: list[tuple[str, str]], user_text: str) -> str | None:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None

    # Barcha suhbatni bitta "user" xabari sifatida yig'amiz (Gemini 1-turn ham ishlaydi)
    ctx = system + "\n\n"
    for role, text in history:
        prefix = "Foydalanuvchi" if role == "user" else "Bot"
        ctx += f"{prefix}: {text}\n"
    ctx += f"Foydalanuvchi: {user_text}\nBot:"

    body = {
        "contents": [{"parts": [{"text": ctx}]}],
        "generationConfig": {
            "maxOutputTokens": 300,
            "temperature": 0.75,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    for model in GEMINI_MODELS:
        try:
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model}:generateContent?key={key}")
            r = requests.post(url, json=body, timeout=25)
            if r.status_code != 200:
                print(f"Gemini [{model}] {r.status_code}: {r.text[:120]}")
                continue
            cands = r.json().get("candidates") or []
            if not cands:
                continue
            parts = (cands[0].get("content") or {}).get("parts") or []
            txt = "".join(p.get("text", "") for p in parts).strip()
            if txt:
                return txt
        except Exception as e:
            print(f"Gemini [{model}] xato:", e)
    return None


def _claude(system: str, history: list[tuple[str, str]], user_text: str) -> str | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msgs = [{"role": r, "content": t} for r, t in history]
        msgs.append({"role": "user", "content": user_text})
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=system,
            messages=msgs,
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip() or None
    except Exception as e:
        print("Claude xato:", e)
        return None


def generate_reply(cfg: dict, history: list[tuple[str, str]], user_text: str) -> str:
    """Gemini → Claude → standart xabar."""
    system = _build_system(cfg)
    reply = _gemini(system, history, user_text)
    if not reply:
        reply = _claude(system, history, user_text)
    if not reply:
        reply = "Savolingiz uchun rahmat! Hozir javob bera olmayapman, biroz kutib qayta yozing."
    return reply


# ------------------------------------------------------------------ HANDLER
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or not msg.text:
        return

    # Bot o'z xabarlariga yoki boshqa bot xabarlariga javob bermaydi
    sender = msg.from_user
    if not sender or sender.is_bot:
        return

    user_text = msg.text.strip()
    if not user_text:
        return

    chat_id = msg.chat_id
    user_id = sender.id

    # Rate limiting — bir foydalanuvchiga juda tez-tez javob bermaymiz
    now = datetime.datetime.now()
    if user_id in _rate and (now - _rate[user_id]).total_seconds() < RATE_SECONDS:
        return
    _rate[user_id] = now

    # Kanal konfiguratsiyasi (persona, focus)
    cfg = find_cfg(chat_id)

    # Suhbat tarixi (kontekst)
    hist = _history[chat_id]

    # "Yozmoqda..." ko'rsatgichi
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # AI javob (blocking → thread pool ichida)
    loop = asyncio.get_event_loop()
    reply = await loop.run_in_executor(None, generate_reply, cfg, list(hist), user_text)

    # Tarixni yangilash (eski yozuvlar kesiladi)
    hist.append(("user", user_text))
    hist.append(("assistant", reply))
    _history[chat_id] = hist[-(HISTORY_LEN * 2):]

    await msg.reply_text(reply)
    print(f"[{chat_id}] @{sender.username or user_id}: {user_text[:60]} → {reply[:60]}")


# ------------------------------------------------------------------ ISHGA TUSHIRISH
def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN o'rnatilmagan!")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    # Faqat oddiy matn xabarlari (buyruqlar — /start va h.k. — alohida handler kerak emas)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    print("Discussion AI bot ishga tushdi (polling)...")
    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
