"""
Kaynak toplayıcıları
====================
Her fonksiyon halka açık bir kaynaktan fırsatları okur ve ortak biçimde
sözlük listesi döner:

    {source, title, url, org, location, online, start, end, deadline, desc, kind}

kind: "event" (tarihli fırsat) | "news" (haber/duyuru) | "page" (izlenen sayfa değişti)
Tarihler ISO "YYYY-MM-DD" (bilinmiyorsa None).

Hiçbir kaynağa giriş yapılmaz, hiçbir veri gönderilmez — yalnızca OKUNUR.
"""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"}
TIMEOUT = 20


def _get(url: str) -> requests.Response:
    """GET + kısa aralıklarla 3 deneme. Bağlantı anlık koptuğunda (uykudan çıkış,
    Wi-Fi değişimi) tek bir hata yüzünden kaynağın düşmesini önler."""
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=TIMEOUT)
            r.raise_for_status()
            return r
        except (requests.ConnectionError, requests.Timeout):
            if attempt == 2:
                raise
            time.sleep(2 + attempt * 3)


def online() -> bool:
    """İnternet var mı? Taramadan önce bakılır; yoksa tarama hiç başlamaz."""
    for host in ("https://www.google.com/generate_204", "https://1.1.1.1"):
        try:
            requests.head(host, timeout=6)
            return True
        except requests.RequestException:
            continue
    return False


def _iso(s) -> str | None:
    """'2026-10-23T07:00+00:00' gibi değerlerden 'YYYY-MM-DD' çıkarır."""
    if not s:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(s))
    return m.group(1) if m else None


def _abs(u: str | None) -> str | None:
    """'//cdn…' gibi protokolsüz adresleri https'e çevirir."""
    if not u:
        return None
    return "https:" + u if u.startswith("//") else u


def _img(v) -> str | None:
    """JSON-LD 'image' alanı metin, liste ya da {url: …} olabilir."""
    if isinstance(v, list):
        v = v[0] if v else None
    if isinstance(v, dict):
        v = v.get("url")
    return _abs(v) if isinstance(v, str) else None


def _clean(s: str | None, n: int = 400) -> str:
    s = html_lib.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()[:n]


TR_MONTHS = {"ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
             "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12}
EN_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _guess_year(month: int, day: int) -> str:
    """Yılsız tarih ('24 Ekim') için en yakın gelecek/yakın geçmiş yılı seçer."""
    today = date.today()
    y = today.year
    try:
        d = date(y, month, day)
    except ValueError:
        return None
    if (today - d).days > 60:          # 2 aydan eskiyse aslında gelecek yıl
        d = date(y + 1, month, day)
    return d.isoformat()


def _tr_date(s: str) -> str | None:
    m = re.search(r"(\d{1,2})\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)(?:\s+(\d{4}))?", s or "")
    if not m:
        return None
    mon = TR_MONTHS.get(m.group(2).lower().replace("i̇", "i"))
    if not mon:
        return None
    if m.group(3):
        return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    return _guess_year(mon, int(m.group(1)))


_TR_MON_RE = "(?:" + "|".join(TR_MONTHS) + ")"
_DATE_RE = rf"(\d{{1,2}}\s+{_TR_MON_RE}(?:\s+\d{{4}})?|\d{{1,2}}[./]\d{{1,2}}[./]\d{{4}})"


def _any_date(s: str) -> str | None:
    m = re.match(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return _tr_date(s)


def extract_deadline(text: str) -> str | None:
    """Duyuru metninden son başvuru tarihini çıkarır. Tanıdığı kalıplar:
      'Son başvuru (tarihi): 11 Ekim 2026'   'Başvuru: 21 Eylül - 11 Ekim 2026'
      'Başvurular 11 Ekim'e kadar'           '11.10.2026 tarihine kadar'
    Aralık verilmişse bitiş tarihi alınır. Bulamazsa None."""
    t = re.sub(r"\s+", " ", text or "").lower()
    t = t.replace("i̇", "i")
    pats = [
        rf"son başvuru(?: tarihi)?(?: ise| olarak)?\s*[:\-–]?\s*{_DATE_RE}",
        rf"başvuru(?:lar|ları)?(?: tarihleri| dönemi)?\s*[:\-–]?\s*{_DATE_RE}\s*[-–]\s*{_DATE_RE}",
        rf"{_DATE_RE}\s*[-–]\s*{_DATE_RE}\s+tarihleri arasında[^.]{{0,50}}başvur",
        rf"başvuru(?:lar|ları)?[^.]{{0,40}}?{_DATE_RE}(?:'?\w*)?\s+(?:tarihine )?kadar",
        rf"{_DATE_RE}(?:'?\w*)?\s+(?:tarihine )?kadar[^.]{{0,30}}başvur",
        rf"(?:deadline|apply by|applications close)\s*[:\-–]?\s*{_DATE_RE}",
    ]
    for p in pats:
        m = re.search(p, t)
        if m:
            groups = [g for g in m.groups() if g]
            end = groups[-1]
            if not re.search(r"\d{4}", end):         # '11 ekim' → yılı aralığın başından/yakından al
                y = re.search(r"\d{4}", m.group(0))
                if y:
                    end = f"{end} {y.group(0)}"
            d = _any_date(end)
            if d:
                return d
    return None


def _devpost_range(s: str) -> tuple[str | None, str | None]:
    """'Aug 31 - Oct 23, 2026' / 'Oct 01 - 23, 2026' / 'Dec 15, 2026 - Jan 10, 2027'."""
    s = (s or "").replace("–", "-")
    parts = [p.strip() for p in s.split(" - ")]
    if len(parts) != 2:
        return None, None
    m_end = re.match(r"(?:([A-Za-z]{3})\s+)?(\d{1,2}),\s*(\d{4})", parts[1])
    if not m_end:
        return None, None
    m_start = re.match(r"([A-Za-z]{3})\s+(\d{1,2})(?:,\s*(\d{4}))?", parts[0])
    if not m_start:
        return None, None
    end_y = int(m_end.group(3))
    s_mon = EN_MONTHS.get(m_start.group(1).lower()[:3])
    e_mon = EN_MONTHS.get((m_end.group(1) or m_start.group(1)).lower()[:3])
    if not (s_mon and e_mon):
        return None, None
    s_y = int(m_start.group(3)) if m_start.group(3) else (end_y if s_mon <= e_mon else end_y - 1)
    try:
        return (date(s_y, s_mon, int(m_start.group(2))).isoformat(),
                date(end_y, e_mon, int(m_end.group(2))).isoformat())
    except ValueError:
        return None, None


# --------------------------------------------------------------------------- #
#  Etkinlik kaynakları
# --------------------------------------------------------------------------- #
def devpost() -> list[dict]:
    """Devpost — dünya çapında açık/yaklaşan AI temalı hackathon'lar (çoğu online)."""
    out = []
    for page in range(1, 5):
        url = ("https://devpost.com/api/hackathons?themes[]=Machine%20Learning%2FAI"
               f"&status[]=upcoming&status[]=open&page={page}")
        data = _get(url).json()
        for h in data.get("hackathons", []):
            start, end = _devpost_range(h.get("submission_period_dates", ""))
            loc = (h.get("displayed_location") or {}).get("location", "")
            prize = _clean(h.get("prize_amount"))
            themes = ", ".join(t["name"] for t in h.get("themes", []))
            out.append(dict(
                source="Devpost", title=h["title"], url=h["url"],
                org=h.get("organization_name") or "", location=loc,
                online=loc.lower() == "online", start=start, end=end, deadline=end,
                desc=f"Hackathon · Ödül: {prize} · {themes} · "
                     f"{h.get('registrations_count', 0)} kayıt", kind="event",
                image=_abs(h.get("thumbnail_url"))))
        if len(data.get("hackathons", [])) < 9:
            break
    return out


def mlh() -> list[dict]:
    """MLH — resmi öğrenci hackathon ligi (fiziksel + online)."""
    year = date.today().year + (1 if date.today().month >= 7 else 0)
    r = _get(f"https://mlh.io/seasons/{year}/events")
    s = BeautifulSoup(r.text, "lxml")
    tag = s.find("script", attrs={"data-page": "app"})
    page = json.loads(tag.string)
    out = []
    for e in page["props"].get("upcomingEvents", []):
        online = e.get("formatType") in ("digital", "online")
        out.append(dict(
            source="MLH", title=e["name"].strip(), url=e.get("websiteUrl") or
            f"https://mlh.io{e.get('url', '')}", org="Major League Hacking",
            location="Online" if online else e.get("location", ""), online=online,
            start=_iso(e.get("startsAt")), end=_iso(e.get("endsAt")), deadline=None,
            desc=f"Öğrenci hackathon'u · {e.get('region', '')} · {e.get('formatType', '')}",
            kind="event", image=e.get("backgroundUrl") or e.get("logoUrl")))
    return out


def _jsonld_events(html_text: str) -> list[dict]:
    found = []
    for raw in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>',
                          html_text, re.S):
        try:
            x = json.loads(raw)
        except Exception:
            continue
        stack = x if isinstance(x, list) else [x]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                if o.get("@type") == "Event":
                    found.append(o)
                stack.extend(v for v in o.values() if isinstance(v, (dict, list)))
            elif isinstance(o, list):
                stack.extend(o)
    return found


def _coderspace_detail(url: str) -> tuple[str | None, bool]:
    """Detay sayfasından (son başvuru tarihi, başvurular kapandı mı) okur.
    Liste sayfasında yalnızca etkinlik tarihleri var; son başvuru burada yazıyor."""
    try:
        lines = BeautifulSoup(_get(url).text, "lxml").get_text("\n", strip=True).split("\n")
    except Exception:
        return None, False
    closed = any(ln == "Başvurular Tamamlandı" for ln in lines)
    deadline = None
    for i, ln in enumerate(lines[:-1]):
        if ln == "Son Başvuru Tarihi":
            deadline = _tr_date(lines[i + 1])
            break
    return deadline, closed


def coderspace() -> list[dict]:
    """Coderspace — Türkiye'deki hackathon, bootcamp ve teknoloji etkinlikleri."""
    out = []
    for e in _jsonld_events(_get("https://coderspace.io/etkinlikler").text):
        loc = e.get("location") or {}
        online = loc.get("@type") == "VirtualLocation"
        url = loc.get("url") or e.get("url") or "https://coderspace.io/etkinlikler"
        deadline, closed = _coderspace_detail(url)
        out.append(dict(
            source="Coderspace", title=e.get("name", ""), url=url,
            org=(e.get("organizer") or {}).get("name", ""),
            location="Online" if online else (loc.get("name") or "Türkiye"),
            online=online, start=_iso(e.get("startDate")), end=_iso(e.get("endDate")),
            deadline=deadline, closed=closed, desc=_clean(e.get("description")),
            kind="event", image=_img(e.get("image"))))
    return out


def ytu_startup_house() -> list[dict]:
    """YTÜ Startup House — kuluçka, BİGG, bootcamp ve hackathon programları + duyurular."""
    base = "https://ytustartuphouse.com.tr"
    home = BeautifulSoup(_get(base + "/").text, "lxml")
    progs = BeautifulSoup(_get(base + "/programlar").text, "lxml")

    # Ana sayfa kartı: "StarBİGG Son Başvuru Tarihi: 25.10.2026" / "...: Başvurular Kapandı"
    info: dict[str, dict] = {}
    for a in home.find_all("a", href=re.compile(r"/programlar/[a-z0-9-]+")):
        txt = a.get_text(" ", strip=True)
        if "Son Başvuru" not in txt:
            continue
        name, _, rest = txt.partition("Son Başvuru Tarihi")
        m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", rest)
        info[a["href"].rstrip("/")] = dict(
            name=name.strip(), deadline=f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None,
            closed=bool(re.search(r"kapan", rest, re.I)))

    # Program sayfası: başlık (h6) + açıklama (p); ana sayfada olmayanları da yakalar.
    out, seen = [], set()
    for a in progs.find_all("a", href=re.compile(r"/programlar/[a-z0-9-]+")):
        href = a["href"].rstrip("/")
        if href in seen:
            continue
        seen.add(href)
        box = a.find_parent("div", class_="buttons")
        box = box.parent if box else None
        h = box.find("h6") if box else None
        p = box.find("p") if box else None
        meta = info.get(href, {})
        name = meta.get("name") or (h.get_text(strip=True) if h else href.rsplit("/", 1)[-1])
        deadline, closed = meta.get("deadline"), meta.get("closed", False)
        if href not in info:                       # ana sayfada yoksa detay sayfasına bak
            try:
                t = BeautifulSoup(_get(href).text, "lxml").get_text(" ", strip=True)
                m = re.search(r"Son Başvuru Tarihi:?\s*(\d{2})\.(\d{2})\.(\d{4})", t)
                deadline = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None
                closed = bool(re.search(r"Başvurular? Kapan", t, re.I)) or not m
            except Exception:
                continue
        out.append(dict(
            source="YTÜ Startup House", title=f"{name} — YTÜ Startup House", url=href,
            org="YTÜ Startup House", location="İstanbul (YTÜ Davutpaşa)", online=False,
            start=None, end=None, deadline=deadline, closed=closed,
            desc="Girişimcilik programı · " + (p.get_text(" ", strip=True)[:300] if p else ""),
            kind="event"))

    # Blog duyuruları (ör. "Meta'dan lisans öğrencilerine…"). Yazının içinden son
    # başvuru tarihi okunur; geçmişse motor bu duyuruyu hiç eklemez.
    seen_blog = set()
    for a in home.find_all("a", href=re.compile(r"/blog/[a-z0-9-]+")):
        txt = a.get_text(" ", strip=True)
        m = re.match(r"(\d{4}-\d{2}-\d{2})\s+(.*)", txt)
        if not m or a["href"] in seen_blog:
            continue
        seen_blog.add(a["href"])
        deadline, summary = None, "YTÜ Startup House duyurusu"
        try:
            body = BeautifulSoup(_get(a["href"]).text, "lxml").get_text("\n", strip=True)
            body = body.split("Öne Çıkanlar")[0]          # alttaki diğer yazıları karıştırma
            deadline = extract_deadline(body)
            paras = [p for p in body.split("\n") if len(p) > 80]
            if paras:
                summary = paras[1 if len(paras) > 1 else 0][:300]
        except Exception:
            pass
        out.append(dict(source="YTÜ Startup House", title=m.group(2)[:200], url=a["href"],
                        org="YTÜ Startup House", location="İstanbul", online=False,
                        start=m.group(1), end=None, deadline=deadline,
                        desc=summary, kind="news", region="Türkiye"))
    return out


def eventbrite() -> list[dict]:
    """Eventbrite — Türkiye'deki yapay zeka etkinlikleri."""
    out = []
    for q in ("ai", "startup"):
        for e in _jsonld_events(_get(f"https://www.eventbrite.com/d/turkey/{q}/").text):
            loc = e.get("location") or {}
            addr = loc.get("address") or {}
            city = addr.get("addressLocality", "") if isinstance(addr, dict) else ""
            online = "Online" in (e.get("eventAttendanceMode") or "")
            out.append(dict(
                source="Eventbrite", title=e.get("name", ""), url=e.get("url", ""),
                org=(e.get("organizer") or {}).get("name", "") if isinstance(
                    e.get("organizer"), dict) else "",
                location="Online" if online else (city or loc.get("name", "")),
                online=online, start=_iso(e.get("startDate")), end=_iso(e.get("endDate")),
                deadline=None, desc=_clean(e.get("description")), kind="event",
                image=_img(e.get("image"))))
    return out


def techcareer() -> list[dict]:
    """Techcareer — Türkiye'deki hackathon ve ücretsiz bootcamp'ler."""
    out = []
    for slug in ("hackathon", "bootcamp"):
        t = _get(f"https://www.techcareer.net/{slug}").text
        m = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
        pp = json.loads(m.group(1))["props"]["pageProps"]
        for key in ("openEvents", "alternativeEvents"):
            for e in (pp.get(key) or {}).get("data", []):
                a = e.get("attributes", {})
                if a.get("isCompleted"):
                    continue
                out.append(dict(
                    source="Techcareer", title=a.get("title", ""),
                    url=a.get("externalLink") or
                    f"https://www.techcareer.net/{a.get('eventTypeSlug', slug)}/{a.get('slug')}",
                    org="Techcareer", location="Türkiye / Online", online=True,
                    start=None, end=None, deadline=_iso(a.get("deadline")),
                    desc=f"{a.get('eventType', '')} · {a.get('subTitle', '')}", kind="event",
                    image=a.get("image")))
    return out


def youthall() -> list[dict]:
    """Youthall — öğrenci/genç etkinlikleri (zirve, ideathon, hackathon, akademi)."""
    s = BeautifulSoup(_get("https://www.youthall.com/tr/etkinlikler/tumu").text, "lxml")
    out = []
    for card in s.select("article.events-card"):
        a = card.select_one("a.events-card__link")
        title = card.select_one(".events-card__title")
        if not (a and title):
            continue
        loc, tags = "", []
        for t in card.select(".events-card__tag"):
            txt = t.get_text(" ", strip=True)
            if t.select_one(".fa-map-marker-alt") or txt.lower() == "online":
                loc = txt                               # konum etiketi ikonlu olandır
            else:
                tags.append(txt)
        when = card.select_one(".events-card__when .events-card__val")
        dl = card.select_one(".events-card__deadline-val")
        org = card.select_one(".events-card__org-name")
        out.append(dict(
            source="Youthall", title=title.get_text(strip=True),
            url="https://www.youthall.com" + a["href"] if a["href"].startswith("/") else a["href"],
            org=org.get_text(strip=True) if org else "", location=loc,
            online="online" in loc.lower(),
            start=_tr_date(when.get_text()) if when else None, end=None,
            deadline=_tr_date(dl.get_text()) if dl else None,
            desc=" · ".join(tags), kind="event",
            image=(card.select_one("img.events-card__img") or {}).get("src")))
    return out


def gdg() -> list[dict]:
    """Google Developer Groups — Türkiye'deki GDG / DevFest / Study Jam etkinlikleri."""
    r = _get("https://gdg.community.dev/api/search/?result_types=upcoming_event"
             "&country_code=TR&page_size=100").json()
    out = []
    for e in r.get("results", []):
        ch = e.get("chapter") or {}
        if ch.get("country") != "TR":
            continue
        out.append(dict(
            source="GDG", title=e.get("title", ""), url=e.get("url", ""),
            org=ch.get("title") or "Google Developer Groups", location=e.get("city", ""),
            online=False, start=_iso(e.get("start_date")), end=None, deadline=None,
            desc=_clean(e.get("description_short")) + " · " + ", ".join(e.get("tags") or []),
            kind="event", image=(e.get("picture") or {}).get("url")))
    return out


# --------------------------------------------------------------------------- #
#  Haber/duyuru taraması (Google News RSS)
# --------------------------------------------------------------------------- #
NEWS_QUERIES_TR = [
    'hackathon "yapay zeka" başvuru', "datathon başvuru", "ideathon başvuru",
    "girişimcilik programı başvurular başladı", "kuluçka programı başvuru girişim",
    "hızlandırma programı başvuru startup", '"yapay zeka" eğitimi ücretsiz başvuru öğrenci',
    "öğrenci yarışması yapay zeka başvuru", "teknofest yapay zeka yarışması başvuru",
]
NEWS_QUERIES_EN = [
    '"AI hackathon" registration open', 'AI startup accelerator "applications open"',
    'AI fellowship students "apply"',
]


def google_news(extra_queries=None) -> list[dict]:
    """Google News — 'başvurular başladı' türü duyuruları yakalar (son 14 gün)."""
    out, seen = [], set()
    jobs = [(q, "tr", "TR", "TR:tr") for q in NEWS_QUERIES_TR + list(extra_queries or [])]
    jobs += [(q, "en", "US", "US:en") for q in NEWS_QUERIES_EN]
    for q, hl, gl, ceid in jobs:
        url = (f"https://news.google.com/rss/search?q={quote_plus(q + ' when:14d')}"
               f"&hl={hl}&gl={gl}&ceid={ceid}")
        try:
            s = BeautifulSoup(_get(url).content, "xml")
        except Exception:
            continue
        for it in s.find_all("item")[:12]:
            title = it.title.get_text(strip=True) if it.title else ""
            key = re.sub(r"\W+", "", title.lower())[:80]
            if not title or key in seen:
                continue
            seen.add(key)
            src = it.source.get_text(strip=True) if it.source else ""
            try:
                pub = parsedate_to_datetime(it.pubDate.get_text()).date().isoformat()
            except Exception:
                pub = None
            out.append(dict(
                source="Haber", title=title, url=it.link.get_text(strip=True),
                org=src, location="", online=False, start=pub, end=None, deadline=None,
                desc=f"Arama: {q}", kind="news",
                region="Türkiye" if hl == "tr" else "Yurt dışı"))
    _enrich_news(out)
    return out


# --------------------------------------------------------------------------- #
#  Haber metninden son başvuru tarihi
# --------------------------------------------------------------------------- #
NEWS_CACHE = Path(__file__).resolve().parent.parent / "data" / "news_cache.json"


def _gnews_decode(link: str) -> str:
    """news.google.com/rss/articles/… bağlantısını haberin asıl adresine çevirir.
    Sayfadaki imza (data-n-a-sg) ve zaman damgasıyla Google'ın kendi çözme ucunu çağırır."""
    t = _get(link).text
    g = lambda a: re.search(a + r'="([^"]+)"', t).group(1)
    inner = json.dumps(["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1,
                                        None, None, None, None, None, 0, 1],
                                       "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
                        g("data-n-a-id"), int(g("data-n-a-ts")), g("data-n-a-sg")])
    r = requests.post("https://news.google.com/_/DotsSplashUi/data/batchexecute",
                      headers={**UA, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                      data={"f.req": json.dumps([[["Fbv4je", inner, None, "generic"]]])},
                      timeout=TIMEOUT)
    part = json.loads(r.text.split("\n\n")[1])[:-2]
    return json.loads(part[0][2])[1]


def _article_text(url: str) -> str:
    s = BeautifulSoup(_get(url).text, "lxml")
    for x in s(["script", "style", "nav", "footer", "header", "aside", "form"]):
        x.decompose()
    body = s.find("article") or s.body or s
    return " ".join(p.get_text(" ", strip=True) for p in body.find_all(["p", "li", "h1", "h2", "h3", "strong"]))


def _enrich_news(items: list[dict]) -> None:
    """Haberlerin asıl sayfasını açıp son başvuru tarihini okur.
    Her haber bir kez okunur (data/news_cache.json); asıl adres de saklanır ki
    'Aç' doğrudan habere gitsin. Okunamazsa haber tarihsiz kalır."""
    try:
        cache = json.loads(NEWS_CACHE.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    lock = threading.Lock()

    def work(it):
        link = it["url"]
        if link not in cache:
            entry = {"url": None, "deadline": None, "seen": date.today().isoformat()}
            for _ in range(2):                   # Google arada bir reddediyor: bir kez daha dene
                try:
                    entry["url"] = entry["url"] or _gnews_decode(link)
                    entry["deadline"] = extract_deadline(_article_text(entry["url"]))
                    break
                except Exception:
                    continue
            if not entry["url"]:                 # çözülemedi: önbelleğe alma, sonra tekrar dene
                return
            with lock:
                cache[link] = entry
        e = cache[link]
        if e.get("url"):
            it["url"] = e["url"]
        it["deadline"] = e.get("deadline")

    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(work, items))

    cut = (date.today() - timedelta(days=45)).isoformat()   # eski kayıtları buda
    cache = {k: v for k, v in cache.items() if v.get("seen", "9") >= cut}
    try:
        NEWS_CACHE.parent.mkdir(exist_ok=True)
        NEWS_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
#  Sayfa izleyici — düzenli program sayfalarındaki "başvuru" metinlerini izler
# --------------------------------------------------------------------------- #
WATCH_WORDS = re.compile(
    r"(başvur|son tarih|deadline|apply|application|applications|cohort|batch|kayıt|"
    r"registration|202\d|ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|"
    r"ekim|kasım|aralık|january|february|march|april|june|july|august|september|"
    r"october|november|december)", re.I)


def page_signature(url: str) -> tuple[str, list[str]]:
    """Sayfadaki başvuru/tarih içeren cümlelerin özetini (hash) ve kendilerini döner.
    Tüm sayfanın hash'i yerine bunu kullanmak, reklam/menü değişikliklerinden
    doğan sahte alarmları azaltır."""
    s = BeautifulSoup(_get(url).text, "lxml")
    for t in s(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        t.decompose()
    text = s.get_text("\n", strip=True)
    lines = []
    for ln in text.split("\n"):
        ln = re.sub(r"\s+", " ", ln).strip()
        if 12 <= len(ln) <= 300 and WATCH_WORDS.search(ln) and ln not in lines:
            lines.append(ln)
    return hashlib.sha1("\n".join(lines).encode("utf-8")).hexdigest(), lines


# Kaynak adı -> fonksiyon. Arayüzdeki "Kaynaklar" listesi buradan gelir.
EVENT_SOURCES = {
    "Devpost": devpost,
    "MLH": mlh,
    "Coderspace": coderspace,
    "Techcareer": techcareer,
    "Youthall": youthall,
    "Eventbrite": eventbrite,
    "GDG": gdg,
    "YTÜ Startup House": ytu_startup_house,
}
