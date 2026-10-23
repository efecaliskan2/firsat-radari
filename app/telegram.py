"""
Telegram bildirimi
==================
Bildirimleri kullanıcının kendi Telegram botu üzerinden telefona da gönderir.

Kimlik bilgisi sırası: ortam değişkenleri (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)
> data/telegram.json (Ayarlar sekmesinden kaydedilir).
Token yalnızca bu bilgisayarda durur; arayüze hiçbir zaman geri gönderilmez.
Giden tek şey bildirim metnidir (fırsat başlıkları), yalnızca api.telegram.org'a.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests

PATH = Path(__file__).resolve().parent.parent / "data" / "telegram.json"


def _load() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def creds() -> tuple[str | None, str | None]:
    f = _load()
    return (os.environ.get("TELEGRAM_BOT_TOKEN") or f.get("token"),
            os.environ.get("TELEGRAM_CHAT_ID") or f.get("chat_id"))


def save(token: str | None = None, chat_id: str | None = None, enabled: bool | None = None):
    f = _load()
    if token is not None:
        f["token"] = token.strip()
    if chat_id is not None:
        f["chat_id"] = str(chat_id).strip()
    if enabled is not None:
        f["enabled"] = bool(enabled)
    PATH.parent.mkdir(exist_ok=True)
    PATH.write_text(json.dumps(f, indent=2), encoding="utf-8")


def info() -> dict:
    """Arayüz için durum — token'ın kendisi değil, yalnızca var/yok bilgisi."""
    token, chat = creds()
    return {"has_token": bool(token), "chat_id": chat or "",
            "enabled": _load().get("enabled", True),
            "from_env": bool(os.environ.get("TELEGRAM_BOT_TOKEN"))}


def find_chat_id() -> str | None:
    """Bota en son mesaj atan sohbetin id'sini getUpdates ile bulur
    (kullanıcı önce Telegram'da bota /start yazmalı)."""
    token, _ = creds()
    if not token:
        return None
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15).json()
    for u in reversed(r.get("result", [])):
        msg = u.get("message") or u.get("channel_post") or {}
        if msg.get("chat", {}).get("id"):
            return str(msg["chat"]["id"])
    return None


def send(title: str, message: str, force: bool = False) -> bool:
    token, chat = creds()
    if token and not chat:                   # kullanıcı sonradan /start yazdıysa sohbeti bul
        try:
            chat = find_chat_id()
        except Exception:
            chat = None
        if chat:
            save(chat_id=chat)
    if not (token and chat) or not (force or _load().get("enabled", True)):
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          data={"chat_id": chat, "text": f"📡 {title}\n{message}",
                                "disable_web_page_preview": True}, timeout=15)
        return r.ok
    except Exception:
        return False
