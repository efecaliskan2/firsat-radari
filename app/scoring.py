"""
Kategori ve ilgi puanı
======================
Her fırsatın başlık + açıklamasına bakarak bir kategori ve 0-10 arası bir
"bana uygun mu?" puanı verir. Anahtar kelimeler config.json'dan da
genişletilebilir (bkz. app/config.py).
"""

from __future__ import annotations

import re

# (desen listesi, puan) — küçük harfe çevrilmiş metinde aranır.
AI = ["yapay zeka", "yapay zekâ", "artificial intelligence", "machine learning",
      "makine öğren", "deep learning", "derin öğren", "llm", "genai", "generative",
      "üretken", "agentic", "ai agent", "veri bilim", "data science", "nlp",
      "computer vision", "görüntü işleme", "gemini", "openai", "claude", "chatgpt",
      "prompt", "neural"]
# Kısa kısaltmalar kelime sınırıyla aranır ("aile", "dubai" yanlış eşleşmesin).
AI_RE = re.compile(r"\b(ai|ml|rag|yz|llms?)\b")
STARTUP = ["girişim", "startup", "start-up", "kuluçka", "hızlandırma", "accelerator",
           "incubator", "founder", "kurucu", "yatırım", "pitch", "demo day",
           "ideathon", "venture", "bigg", "teknogirişim", "çekirdek"]
HACK = ["hackathon", "hackhaton", "datathon", "ideathon", "buildathon", "game jam",
        "codeathon", "hack "]
CONTEST = ["yarışma", "competition", "challenge", "contest", "teknofest", "ödül"]
LEARN = ["bootcamp", "eğitim", "akademi", "academy", "workshop", "atölye", "kurs",
         "course", "sertifika", "certif", "webinar", "study jam", "kamp", "program",
         "fellowship", "burs", "scholarship"]
STUDENT = ["öğrenci", "student", "üniversite", "university", "genç", "campus", "kampüs"]
NEGATIVE = ["senior", "4+ yıl", "5+ yıl", "deneyimli", "hiring day", "kariyer günü",
            "career day", "işe alım", "internship program", "staj programı"]

CATEGORIES = ["Hackathon", "Yarışma", "Girişimcilik", "Eğitim", "Etkinlik"]


def _has(text: str, words) -> int:
    return sum(1 for w in words if w in text)


def is_topical(title: str, desc: str = "", extra_keywords=None) -> bool:
    """Konu olarak ilgili mi (AI, girişim, hackathon, yarışma, eğitim ya da kendi kelimelerin)?
    Türkiye bonusu yalnızca bunlara verilir; yoksa sıradan kariyer/sosyal buluşmalar
    (ör. bir müze gezisi) sırf Türkiye'de diye listeye girer."""
    t = re.sub(r"\s+", " ", f" {title} {desc} ".lower())
    return bool(_has(t, AI) or AI_RE.search(t) or _has(t, STARTUP) or _has(t, HACK)
                or _has(t, CONTEST) or _has(t, LEARN)
                or _has(t, [k.lower() for k in (extra_keywords or [])]))


def classify(title: str, desc: str = "", extra_keywords=None) -> tuple[str, int]:
    """(kategori, puan) döner. Puan 0-10; 4+ = bildirime değer."""
    t = f" {title} {desc} ".lower()
    t = re.sub(r"\s+", " ", t)

    ai = _has(t, AI) + len(AI_RE.findall(t))
    st = _has(t, STARTUP)
    hk = _has(t, HACK)
    ct = _has(t, CONTEST)
    le = _has(t, LEARN)
    su = _has(t, STUDENT)
    ng = _has(t, NEGATIVE)
    ex = _has(t, [k.lower() for k in (extra_keywords or [])])

    if hk:
        cat = "Hackathon"
    elif ct:
        cat = "Yarışma"
    elif st:
        cat = "Girişimcilik"
    elif le:
        cat = "Eğitim"
    else:
        cat = "Etkinlik"

    score = (min(ai, 2) * 2 + min(st, 2) * 2 + (3 if hk else 0) + (1 if ct else 0)
             + (1 if le else 0) + (1 if su else 0) + min(ex, 2) * 2 - ng * 2)
    return cat, max(0, min(10, score))
