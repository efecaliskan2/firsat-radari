"""
Tarama motoru
=============
Tüm kaynakları paralel okur, puanlar, SQLite'a yazar, yeni fırsatları ve
yaklaşan son başvuru tarihlerini bildirir.

Veri: data/radar.db  ·  Ayarlar: data/config.json (ilk açılışta oluşur)
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

from . import collectors, telegram
from .scoring import classify, is_topical

DATA = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA / "radar.db"
CONFIG_PATH = DATA / "config.json"

DEFAULT_CONFIG = {
    "scan_hours": 4,             # tepsi modunda kaç saatte bir taransın
    "notify_min_score": 5,       # bu puan ve üstü yeni fırsatlar bildirilir
    "remind_days": [7, 3, 1],    # kaydettiklerin için son tarih hatırlatmaları
    "disabled_sources": [],
    "extra_keywords": [],        # puanı artıran kendi kelimelerin (ör. "fintech")
    "extra_news_queries": [],    # Google News'te ek aramalar
    "watch_pages": [
        {"name": "Y Combinator başvuru", "url": "https://www.ycombinator.com/apply"},
        {"name": "Google for Startups Accelerator", "url": "https://startup.google.com/programs/accelerator/"},
        {"name": "İTÜ Çekirdek", "url": "https://itucekirdek.com/"},
        {"name": "TEKNOFEST yarışmaları", "url": "https://www.teknofest.org/tr/yarismalar/"},
        {"name": "Microsoft Imagine Cup", "url": "https://imaginecup.microsoft.com/"},
    ],
}

TR_PLACES = ("türkiye", "turkey", "istanbul", "i̇stanbul", "ankara", "izmir", "i̇zmir",
             "bursa", "antalya", "eskişehir", "kocaeli", "konya", "adana", "trabzon",
             "kayseri", "gaziantep", "şanlıurfa", "diyarbakır", "samsun", "online")
TR_SOURCES = ("Coderspace", "Techcareer", "Youthall", "GDG", "YTÜ Startup House")
TR_HINT = re.compile(r"(\.tr(/|$)|türk|turkey|teknofest|i̇tü|itü|odtü|ytü|boğaziçi|tübitak|"
                     r"kosgeb|istanbul|ankara|izmir)", re.I)


def region_of(it: dict) -> str:
    """'Türkiye' ya da 'Yurt dışı'. Online global yarışmalar (Devpost vb.) yurt dışı sayılır."""
    if it.get("region"):
        return it["region"]
    if it["source"] in TR_SOURCES:
        return "Türkiye"
    loc = (it.get("location") or "").lower()
    if any(p in loc for p in TR_PLACES if p != "online"):
        return "Türkiye"
    if TR_HINT.search(f"{it.get('org', '')} {it.get('title', '')} {it.get('url', '')}"):
        return "Türkiye"
    return "Yurt dışı"


def is_open(it: dict, today: str | None = None) -> bool:
    """Başvurusu hâlâ açık mı? Son başvuru geçmişse, kaynak 'kapandı' diyorsa ya da
    (son başvuru bilinmiyorsa) etkinlik çoktan başlamışsa kapalı sayılır."""
    today = today or date.today().isoformat()
    if it.get("closed"):
        return False
    if it.get("deadline"):                   # duyurularda da metinden okunan son tarih geçerli
        return it["deadline"] >= today
    if it.get("kind") != "event":            # tarihi bilinmeyen haber/duyuru: 30 gün
        cut = (date.fromisoformat(today) - timedelta(days=30)).isoformat()
        return not it.get("start") or it["start"] >= cut
    if it.get("start"):
        return it["start"] >= today
    if it.get("end"):
        return it["end"] >= today
    return True
NEWS_DONE = re.compile(r"(winners?|announced|kazanan|birincisi|ikincisi|üçüncüsü|derece(ye| aldı)|"
                       r"ödül töreni|sona erdi|tamamlandı|gerçekleştirildi|düzenlendi|hosts|hosted|"
                       r"concluded|wraps up)", re.I)
NEWS_ACTION = re.compile(r"(başvuru|başvur|kayıt|açıldı|başladı|son gün|apply|applications|"
                         r"registration|deadline|call for)", re.I)

_lock = threading.Lock()
status = {"running": False, "last_run": None, "last_new": 0, "errors": {}, "offline": False}


# --------------------------------------------------------------------------- #
#  Ayarlar & veritabanı
# --------------------------------------------------------------------------- #
def load_config() -> dict:
    DATA.mkdir(exist_ok=True)
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    else:
        save_config(cfg)
    return cfg


def save_config(cfg: dict) -> None:
    DATA.mkdir(exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def db() -> sqlite3.Connection:
    DATA.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS items (
        id TEXT PRIMARY KEY, source TEXT, kind TEXT, title TEXT, url TEXT, org TEXT,
        location TEXT, online INTEGER, start TEXT, "end" TEXT, deadline TEXT,
        "desc" TEXT, category TEXT, score INTEGER,
        first_seen TEXT, last_seen TEXT,
        status TEXT DEFAULT 'new',          -- new | seen | saved | applied | hidden
        notified INTEGER DEFAULT 0, reminded TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS pages (
        url TEXT PRIMARY KEY, name TEXT, hash TEXT, lines TEXT, checked TEXT
    );
    CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
    """)
    cols = {r[1] for r in con.execute("PRAGMA table_info(items)")}
    if "region" not in cols:                 # eski veritabanı → sütunu ekle
        con.execute("ALTER TABLE items ADD COLUMN region TEXT DEFAULT 'Yurt dışı'")
    if "image" not in cols:
        con.execute("ALTER TABLE items ADD COLUMN image TEXT")
    return con


def _id(it: dict) -> str:
    key = it["url"] if it["kind"] != "news" else re.sub(r"\W+", "", it["title"].lower())
    return hashlib.sha1(f"{it['source'] if it['kind'] != 'news' else 'news'}|{key}"
                        .encode("utf-8")).hexdigest()[:16]


def _score(it: dict, cfg: dict) -> tuple[str, int]:
    extra = cfg.get("extra_keywords") or []
    if it["kind"] == "page":                 # izlediğin program sayfası değişti: hep bildir
        return classify(it["title"], it.get("desc", ""), extra)[0], 8
    if it["kind"] == "news":
        cat, sc = classify(it["title"], "", extra)
        if not NEWS_ACTION.search(it["title"]):
            sc -= 3                      # "başvuru/kayıt" geçmeyen haber = muhtemelen fırsat değil
        if NEWS_DONE.search(it["title"]):
            sc -= 4                      # "kazananlar açıklandı / sona erdi" = bitmiş etkinlik
        return cat, max(0, sc)
    # Başlık daha belirleyici: açıklamadaki genel etiketler (ör. Devpost'un her
    # yarışmaya koyduğu "Machine Learning/AI" teması) puanı tek başına şişirmesin.
    cat, sc_all = classify(it["title"], it.get("desc", ""), extra)
    _, sc_title = classify(it["title"], "", extra)
    sc = round((sc_all + sc_title) / 2)
    loc = (it.get("location") or "").lower()
    if not is_topical(it["title"], it.get("desc", ""), extra):
        pass                             # konu dışıysa Türkiye'de olması puan kazandırmaz
    elif it["source"] in TR_SOURCES or any(p in loc for p in TR_PLACES if p != "online"):
        sc += 2                          # Türkiye'de = en ulaşılabilir
    elif not it.get("online"):
        sc -= 3                          # yurt dışında fiziksel = ulaşması zor
    return cat, max(0, min(10, sc))


# --------------------------------------------------------------------------- #
#  Tarama
# --------------------------------------------------------------------------- #
def _check_pages(cfg: dict, con: sqlite3.Connection) -> list[dict]:
    """İzlenen sayfaların 'başvuru' cümleleri değiştiyse bir fırsat kaydı üretir."""
    out = []
    for p in cfg.get("watch_pages", []):
        try:
            h, lines = collectors.page_signature(p["url"])
        except Exception as e:
            status["errors"][f"Sayfa: {p['name']}"] = str(e)[:150]
            continue
        row = con.execute("SELECT hash, lines FROM pages WHERE url=?", (p["url"],)).fetchone()
        now = datetime.now().isoformat(timespec="seconds")
        if row and row["hash"] != h:
            old = set(json.loads(row["lines"] or "[]"))
            new_lines = [ln for ln in lines if ln not in old][:6]
            if new_lines:
                out.append(dict(
                    source="Sayfa izleyici", kind="page",
                    title=f"{p['name']} sayfası güncellendi",
                    url=p["url"], org=p["name"], location="", online=True,
                    start=date.today().isoformat(), end=None, deadline=None,
                    desc=" · ".join(new_lines)[:500],
                    _id=hashlib.sha1(f"page|{p['url']}|{h}".encode()).hexdigest()[:16]))
        con.execute("INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?)",
                    (p["url"], p["name"], h, json.dumps(lines, ensure_ascii=False), now))
    return out


def run_scan(notify=None) -> dict:
    """Tüm kaynakları tarar. Aynı anda tek tarama çalışır."""
    if not _lock.acquire(blocking=False):
        return {"ok": False, "msg": "Tarama zaten sürüyor"}
    status.update(running=True, errors={}, offline=False)
    try:
        # İnternet yoksa hiç tarama: eski liste olduğu gibi kalsın, "son tarama"
        # güncellenmesin ve zamanlayıcı birkaç dakika sonra tekrar denesin.
        if not collectors.online():
            status["offline"] = True
            return {"ok": False, "offline": True, "msg": "İnternet bağlantısı yok"}

        cfg = load_config()
        off = set(cfg.get("disabled_sources") or [])
        jobs = {n: f for n, f in collectors.EVENT_SOURCES.items() if n not in off}
        if "Haber" not in off:
            jobs["Haber"] = lambda: collectors.google_news(cfg.get("extra_news_queries"))

        items: list[dict] = []
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {n: ex.submit(f) for n, f in jobs.items()}
            for n, fu in futs.items():
                try:
                    items += fu.result(timeout=180)
                except Exception as e:
                    status["errors"][n] = f"{type(e).__name__}: {str(e)[:150]}"

        # Kaynakların çoğu aynı anda düştüyse sorun sitelerde değil bağlantıdadır
        # (tarama sırasında kopmuş). Yarım sonuçla kapalı fırsat temizliği yapma.
        if jobs and len(status["errors"]) >= max(2, len(jobs) * 0.75):
            status["offline"] = True
            return {"ok": False, "offline": True, "msg": "Bağlantı tarama sırasında koptu",
                    "errors": status["errors"]}

        con = db()
        if "Sayfa izleyici" not in off:
            items += _check_pages(cfg, con)

        now = datetime.now().isoformat(timespec="seconds")
        new_items, seen_ids = [], set()
        for it in items:
            if not it.get("title") or not it.get("url"):
                continue
            iid = it.pop("_id", None) or _id(it)
            if iid in seen_ids:
                continue
            seen_ids.add(iid)
            if not is_open(it):
                # Başvurusu kapanmış: hiç ekleme; önceden eklendiyse sil
                # (takibe aldıkların/başvurdukların kalır).
                con.execute("""DELETE FROM items WHERE id=?
                               AND status NOT IN ('saved','applied')""", (iid,))
                continue
            cat, sc = _score(it, cfg)
            region = region_of(it)
            row = con.execute("SELECT id FROM items WHERE id=?", (iid,)).fetchone()
            vals = (it["source"], it["kind"], it["title"], it["url"], it.get("org", ""),
                    it.get("location", ""), int(bool(it.get("online"))), it.get("start"),
                    it.get("end"), it.get("deadline"), it.get("desc", ""), cat, sc, region,
                    it.get("image"))
            if row:
                con.execute("""UPDATE items SET source=?,kind=?,title=?,url=?,org=?,location=?,
                    online=?,start=?,"end"=?,deadline=?,"desc"=?,category=?,score=?,region=?,
                    image=?,last_seen=? WHERE id=?""", vals + (now, iid))
            else:
                con.execute("""INSERT INTO items (source,kind,title,url,org,location,online,
                    start,"end",deadline,"desc",category,score,region,image,id,first_seen,
                    last_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            vals + (iid, now, now))
                new_items.append(dict(it, id=iid, category=cat, score=sc, region=region))

        # Kaynakta artık görünmeyen ama tarihi geçmiş eski kayıtları da temizle.
        _purge_closed(con)

        first_run = con.execute("SELECT v FROM meta WHERE k='first_run_done'").fetchone() is None
        con.execute("INSERT OR REPLACE INTO meta VALUES ('first_run_done','1')")
        con.execute("INSERT OR REPLACE INTO meta VALUES ('last_run',?)", (now,))
        con.commit()

        worth = sorted([i for i in new_items if i["score"] >= cfg["notify_min_score"]],
                       key=lambda i: -i["score"])
        if notify and worth and not first_run:
            head = ", ".join(i["title"][:45] for i in worth[:3])
            more = f" (+{len(worth) - 3} daha)" if len(worth) > 3 else ""
            notify(f"{len(worth)} yeni fırsat", head + more)
        if worth and not first_run:
            telegram.send(f"{len(worth)} yeni fırsat", _tg_list(worth))
        if worth:
            con.execute(f"UPDATE items SET notified=1 WHERE id IN ({','.join('?' * len(worth))})",
                        [i["id"] for i in worth])
        _reminders(con, cfg, notify)
        con.commit()
        con.close()
        status.update(last_run=now, last_new=len(new_items))
        return {"ok": True, "new": len(new_items), "worth": len(worth),
                "errors": status["errors"]}
    finally:
        status["running"] = False
        _lock.release()


def _purge_closed(con) -> None:
    today = date.today().isoformat()
    rows = con.execute("""SELECT id,kind,deadline,start,"end" FROM items
                          WHERE status NOT IN ('saved','applied')""").fetchall()
    dead = [r["id"] for r in rows if not is_open(dict(r), today)]
    if dead:
        con.execute(f"DELETE FROM items WHERE id IN ({','.join('?' * len(dead))})", dead)


def _tg_list(items: list[dict], limit: int = 8) -> str:
    """Telegram için: Türkiye / Yurt dışı başlıkları altında başlık, tarih ve bağlantı."""
    blocks, shown = [], 0
    for reg, flag in (("Türkiye", "🇹🇷"), ("Yurt dışı", "🌍")):
        group = [i for i in items if i.get("region", "Yurt dışı") == reg][:max(0, limit - shown)]
        if not group:
            continue
        shown += len(group)
        lines = [f"{flag} {reg.upper()}"]
        for i in group:
            when = (f"son başvuru {i['deadline']}" if i.get("deadline")
                    else f"başlangıç {i['start']}" if i.get("start") else "")
            meta = " · ".join(x for x in (i["category"], i.get("location"), when) if x)
            lines.append(f"• {i['title']}  [{i['score']}/10]\n  {meta}\n  {i['url']}")
        blocks.append("\n\n".join(lines))
    if len(items) > shown:
        blocks.append(f"…ve {len(items) - shown} tane daha — uygulamada gör.")
    return "\n\n".join(blocks)


def _reminders(con, cfg, notify) -> None:
    """Kaydedilen fırsatların son başvuru/başlangıç tarihi yaklaşınca hatırlatır."""
    today = date.today()
    rows = con.execute("""SELECT id,title,url,deadline,start,"end",reminded FROM items
                          WHERE status='saved'""").fetchall()
    for r in rows:
        # Önemli tarih: son başvuru > henüz başlamadıysa başlangıç > bitiş
        target, what = r["deadline"], "son başvuru"
        if not target and r["start"] and r["start"] >= today.isoformat():
            target, what = r["start"], "başlangıç"
        if not target and r["end"]:
            target, what = r["end"], "bitiş"
        if not target:
            continue
        left = (date.fromisoformat(target) - today).days
        done = set(filter(None, (r["reminded"] or "").split(",")))
        for d in sorted(cfg.get("remind_days", [7, 3, 1])):
            if 0 <= left <= d and str(d) not in done:
                if notify:
                    notify(f"⏰ {left} gün kaldı", f"{r['title'][:80]} — {what}: {target}")
                telegram.send(f"⏰ {left} gün kaldı",
                              f"{r['title']}\n{what}: {target}\n{r['url']}")
                done.update(str(x) for x in cfg["remind_days"] if x >= d)
                con.execute("UPDATE items SET reminded=? WHERE id=?", (",".join(done), r["id"]))
                break


def last_run() -> str | None:
    try:
        con = db()
        r = con.execute("SELECT v FROM meta WHERE k='last_run'").fetchone()
        con.close()
        return r["v"] if r else None
    except Exception:
        return None


def start_scheduler(notify=None) -> None:
    """Arka planda periyodik tarama (tepsi modu).
    Uzun bir sleep yerine 5 dakikada bir duvar saatine bakar: bilgisayar uykudan
    uyandığında gecikmiş tarama hemen yapılır; internet yoksa 5 dk sonra tekrar denenir."""
    def due() -> bool:
        lr = last_run()
        hours = max(1, load_config().get("scan_hours", 4))
        return not lr or datetime.fromisoformat(lr) < datetime.now() - timedelta(hours=hours)

    def loop():
        time.sleep(20)                      # açılışta ağın hazır olmasına zaman tanı
        while True:
            try:
                if due():
                    run_scan(notify)
            except Exception as e:
                print(f"[tarama hatası] {e}")
            time.sleep(300)
    threading.Thread(target=loop, daemon=True).start()
