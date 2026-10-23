"""
Yerel API + arayüz (yalnızca 127.0.0.1)
"""

from __future__ import annotations

import re
import threading
import webbrowser
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from flask import Flask, jsonify, request, send_from_directory

from . import collectors, engine, telegram

STATIC = Path(__file__).resolve().parent / "static"
app = Flask(__name__, static_folder=None)

STATUSES = {"new", "seen", "saved", "applied", "hidden"}


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/static/<path:p>")
def static_files(p):
    return send_from_directory(STATIC, p)


def _active_filter() -> str:
    """Başvurusu kapanmış fırsatları gizler (takipte/başvurulanlar hariç).
    Kural engine.is_open ile aynı: son başvuru > (yoksa) başlangıç > (yoksa) bitiş."""
    today = date.today().isoformat()
    news_cut = (date.today() - timedelta(days=30)).isoformat()
    return f"""(status IN ('saved','applied')
        OR (kind = 'event' AND COALESCE(deadline, start, "end", '9999') >= '{today}')
        OR (kind IN ('news','page') AND (deadline >= '{today}'
            OR (deadline IS NULL AND COALESCE(start, '0') >= '{news_cut}'))))"""


@app.get("/api/items")
def items():
    con = engine.db()
    rows = con.execute(f"""SELECT * FROM items WHERE {_active_filter()}
                           ORDER BY score DESC, COALESCE(deadline, start, '9999')""").fetchall()
    con.close()
    return jsonify([dict(r) for r in rows])


@app.post("/api/items/<iid>/status")
def set_status(iid):
    st = (request.json or {}).get("status")
    if st not in STATUSES:
        return jsonify(ok=False), 400
    con = engine.db()
    con.execute("UPDATE items SET status=? WHERE id=?", (st, iid))
    con.commit()
    con.close()
    return jsonify(ok=True)


@app.post("/api/seen-all")
def seen_all():
    con = engine.db()
    con.execute("UPDATE items SET status='seen' WHERE status='new'")
    con.commit()
    con.close()
    return jsonify(ok=True)


def _item(iid):
    con = engine.db()
    r = con.execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
    con.close()
    return r


@app.post("/api/items/<iid>/open")
def open_item(iid):
    """Bağlantıyı sistem tarayıcısında açar (yalnızca veritabanındaki http(s) adresleri)."""
    r = _item(iid)
    if not r or not str(r["url"]).startswith(("http://", "https://")):
        return jsonify(ok=False), 404
    webbrowser.open(r["url"])
    return jsonify(ok=True)


@app.post("/api/items/<iid>/calendar")
def calendar(iid):
    """Google Takvim'e 'etkinlik ekle' sayfasını açar (kaydetmeyi sen onaylarsın)."""
    r = _item(iid)
    if not r:
        return jsonify(ok=False), 404
    day = r["deadline"] or r["start"]
    if not day:
        return jsonify(ok=False, msg="Tarih bilinmiyor"), 400
    d = date.fromisoformat(day)
    label = "Son başvuru: " if r["deadline"] else ""
    q = urlencode({"action": "TEMPLATE", "text": label + r["title"],
                   "dates": f"{d:%Y%m%d}/{d + timedelta(days=1):%Y%m%d}",
                   "details": f"{r['url']}\n\n{r['desc']}"[:900]})
    webbrowser.open("https://calendar.google.com/calendar/render?" + q)
    return jsonify(ok=True)


@app.post("/api/scan")
def scan():
    if engine.status["running"]:
        return jsonify(ok=False, msg="Tarama sürüyor")
    threading.Thread(target=engine.run_scan, daemon=True).start()
    return jsonify(ok=True)


@app.get("/api/status")
def status():
    return jsonify(dict(engine.status, last_run=engine.last_run(),
                        sources=list(collectors.EVENT_SOURCES) + ["Haber", "Sayfa izleyici"]))


@app.get("/api/telegram")
def tg_info():
    return jsonify(telegram.info())


@app.post("/api/telegram")
def tg_save():
    """Token'ı yalnızca data/telegram.json'a yazar; geri döndürmez."""
    body = request.json or {}
    token = (body.get("token") or "").strip()
    if token and not re.fullmatch(r"\d{5,15}:[\w-]{20,80}", token):
        return jsonify(ok=False, msg="Token biçimi hatalı (123456:ABC… olmalı)"), 400
    telegram.save(token=token or None, enabled=body.get("enabled"))
    msg = "Kaydedildi."
    if telegram.creds()[0] and not telegram.creds()[1]:
        try:
            chat = telegram.find_chat_id()
        except Exception:
            chat = None
        if chat:
            telegram.save(chat_id=chat)
            msg = "Kaydedildi, sohbet bulundu."
        else:
            msg = "Token kaydedildi. Şimdi Telegram'da bota /start yaz ve tekrar Kaydet'e bas."
    return jsonify(ok=True, msg=msg, info=telegram.info())


@app.post("/api/telegram/test")
def tg_test():
    ok = telegram.send("Fırsat Radarı bağlandı",
                       "Yeni fırsatlar ve son tarih hatırlatmaları buraya da gelecek.", force=True)
    return jsonify(ok=ok)


@app.get("/api/config")
def get_config():
    return jsonify(engine.load_config())


@app.post("/api/config")
def set_config():
    cfg = engine.load_config()
    body = request.json or {}
    for k in ("scan_hours", "notify_min_score"):
        if k in body:
            cfg[k] = max(1, min(48, int(body[k])))
    for k in ("disabled_sources", "extra_keywords", "extra_news_queries"):
        if k in body and isinstance(body[k], list):
            cfg[k] = [str(x).strip()[:100] for x in body[k] if str(x).strip()][:40]
    if isinstance(body.get("watch_pages"), list):
        cfg["watch_pages"] = [
            {"name": str(p.get("name", ""))[:80], "url": str(p.get("url", ""))[:500]}
            for p in body["watch_pages"]
            if str(p.get("url", "")).startswith(("http://", "https://"))][:30]
    engine.save_config(cfg)
    return jsonify(ok=True, config=cfg)
