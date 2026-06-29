"""AvtoPost — Telethon StringSession yaratuvchi (BIR MARTA, lokal ishga tushiriladi).

Bu sizning akkountingiz orqali kanallarni O'QISH (skraping) uchun "session" yaratadi.
Bot EMAS — bu sizning Telegram akkountingiz seansi.

QADAMLAR:
  1) https://my.telegram.org -> "API development tools" -> API_ID va API_HASH oling.
  2) pip install telethon
  3) python make_session.py
  4) Telefon raqam (+998...) va Telegram'dan kelgan KODNI kiriting.
     (2FA parolingiz bo'lsa, uni ham so'raydi.)
  5) Chiqqan uzun matnni nusxalab, GitHub secret qiling:  MB_TG_SESSION

⚠️ Bu matn = akkountingizga to'liq kirish. Hech kimga bermang, kodga yozmang.
"""
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

if __name__ == "__main__":
    api_id = int(input("API_ID: ").strip())
    api_hash = input("API_HASH: ").strip()
    with TelegramClient(StringSession(), api_id, api_hash) as client:
        s = client.session.save()
        me = client.get_me()
        print(f"\n✅ Kirildi: {me.first_name} (@{me.username})")
        print("\n===== MB_TG_SESSION (shuni to'liq nusxa oling) =====\n")
        print(s)
        print("\n====================================================")
        print("Endi GitHub: Settings -> Secrets -> MB_TG_SESSION = yuqoridagi matn")
