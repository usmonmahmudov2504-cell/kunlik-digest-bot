"""AvtoPost — Publisher (Telegram Bot API orqali post tashlash).

Bitta Master Bot barcha mijoz kanallariga yozadi (har kanalda admin bo'lishi shart).
Yengil: aiohttp bilan async sendMessage. Token MB_BOT_TOKEN env'da.
"""
from __future__ import annotations
import os

BOT_TOKEN = os.environ.get("MB_BOT_TOKEN", "")
API = "https://api.telegram.org/bot{token}/{method}"


async def send(chat: str, text: str, disable_preview: bool = True) -> bool:
    """HTML matnli post yuboradi. Token yo'q / xato -> False (bot to'xtamaydi)."""
    if not BOT_TOKEN:
        print(f"  [{chat}] (token yo'q — yuborilmadi) preview:\n{text[:200]}")
        return False
    try:
        import aiohttp
    except Exception:
        print("  aiohttp yo'q — `pip install aiohttp`")
        return False

    data = {
        "chat_id": chat,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": '{"is_disabled": true}' if disable_preview else "{}",
    }
    url = API.format(token=BOT_TOKEN, method="sendMessage")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, data=data, timeout=30) as r:
                if r.status == 200:
                    return True
                body = await r.text()
                print(f"  [{chat}] Telegram {r.status}: {body[:160]}")
                # HTML xato bo'lsa -> teglarsiz qayta urinish
                import re
                data["text"] = re.sub(r"<[^>]+>", "", text)
                data.pop("parse_mode", None)
                async with s.post(url, data=data, timeout=30) as r2:
                    return r2.status == 200
    except Exception as e:
        print(f"  [{chat}] yuborish xato: {e}")
        return False
