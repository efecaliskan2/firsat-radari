# Fırsat Radarı — Proje Belgesi

Son güncelleme: 2026-10-21

AI hackathon'larını, girişimcilik programlarını, eğitim/bootcamp'leri ve yarışmaları
birçok kaynaktan **otomatik toplayan**, sana göre puanlayan ve yeni fırsatlarla son
tarihleri **Windows bildirimiyle** haber veren lokal masaüstü uygulaması.

İlkeler: her şey `127.0.0.1:8770`'te lokal; yalnızca halka açık sayfalar **okunur**;
hesap/şifre yok, dışarı veri gönderilmez. "Takvim" düğmesi yalnızca sen tıklayınca
Google Takvim'in "etkinlik ekle" sayfasını açar.

## Çalıştırma
| Yol | Komut |
|---|---|
| Masaüstü kısayolu "Fırsat Radarı" | `pythonw main.py` → pencere (son tarama 4 saatten eskiyse tarar) |
| Başlangıç klasörü (otomatik) | `pythonw main.py --tray` → tepside sessiz, 4 saatte bir tarar, bildirir |
| Tek tarama (test) | `python main.py --scan` |
| Sadece sunucu | `python main.py --serve` (launch.json: `firsat-radari`) |

Gerçek python: `%LOCALAPPDATA%\Python\bin\python.exe`. Otomatik açılışı kapatmak:
`Win+R` → `shell:startup` → "Fırsat Radarı" kısayolunu sil.

## Dosyalar
```
main.py              başlatıcı (pencere / --tray / --scan / --serve)
app/collectors.py    kaynak okuyucular + sayfa izleyici imzası
app/scoring.py       kategori + 0-10 ilgi puanı (anahtar kelime)
app/engine.py        paralel tarama, SQLite, bildirim, hatırlatma, zamanlayıcı
app/server.py        Flask API
app/static/          arayüz (vanilla JS)
data/radar.db        fırsatlar (status: new/seen/saved/applied/hidden)
data/config.json     ayarlar (arayüzdeki Ayarlar sekmesi yazar)
```

## Kaynaklar (2026-10 itibarıyla çalışıyor)
| Kaynak | Yöntem | Ne getirir |
|---|---|---|
| Devpost | `devpost.com/api/hackathons?themes[]=Machine Learning/AI` JSON | Global online AI hackathon'ları |
| MLH | `mlh.io/seasons/<yıl>/events` → `<script data-page="app">` JSON | Öğrenci hackathon'ları (çoğu ABD, puanı düşük) |
| Coderspace | liste JSON-LD Event + her etkinliğin detay sayfası ("Son Başvuru Tarihi", "Başvurular Tamamlandı") | TR hackathon / etkinlik |
| YTÜ Startup House | ana sayfa kartları ("Son Başvuru Tarihi: dd.mm.yyyy" / "Kapandı") + `/programlar` açıklamaları + blog duyuruları | Kuluçka, BİGG, bootcamp, hackathon |
| Techcareer | `/hackathon`, `/bootcamp` → `__NEXT_DATA__` | TR bootcamp/hackathon |
| Youthall | `/tr/etkinlikler/tumu` HTML kartları (`article.events-card`) | TR öğrenci etkinlikleri |
| Eventbrite | `/d/turkey/ai/`, `/d/turkey/startup/` JSON-LD | TR AI/girişim etkinlikleri (gürültülü) |
| GDG | `gdg.community.dev/api/search/` → istemcide `chapter.country=='TR'` süzgeci | GDG/DevFest |
| Haber | Google News RSS (son 14 gün), TR+EN aramalar | "Başvurular başladı" duyuruları |
| Sayfa izleyici | config'teki sayfalarda başvuru/tarih içeren cümlelerin hash'i | YC, Google for Startups, İTÜ Çekirdek, TEKNOFEST, Imagine Cup |

Denenip **çalışmayan**: Kaggle (reCAPTCHA / API anahtarı ister), lu.ma API (404),
Devfolio API (404), anbean.com (park edilmiş alan).

## Puanlama
`classify()`: AI, girişim, hackathon, yarışma, eğitim, öğrenci kelimeleri artırır;
"senior / kariyer günü / işe alım" düşürür. `engine._score()`: başlık ve başlık+açıklama
puanının ortalaması (Devpost'un genel "ML/AI" etiketi şişirmesin), **Türkiye +2**,
yurt dışı fiziksel −3. Haberde "başvuru/kayıt/apply" yoksa −3. Sayfa değişikliği hep 8.
Bildirim eşiği varsayılan 5. İlk taramada bildirim atılmaz (taban çizgisi).

## Başvurusu kapanmış fırsatlar (2026-10-21 kuralı)
`engine.is_open()`: kaynak "kapandı" diyorsa (`closed`) ya da son başvuru geçtiyse kapalı.
Son başvuru bilinmiyorsa **etkinlik başladıysa** kapalı sayılır. Haber/sayfa kayıtları 30 gün.
Kapalılar hiç eklenmez; önceden eklendiyse silinir (takipte/başvurulanlar hariç).
Arayüz sorgusu (`server._active_filter`) aynı kuralı uygular.

**Duyurular:** `collectors.extract_deadline()` metinden son başvuruyu okur ("Son başvuru: …",
"Başvuru: 21 Eylül – 11 Ekim 2026", "… tarihine kadar"). YTÜ blog yazıları tek tek açılıp
okunur; tarih geçmişse eklenmez. **Google News** bağlantıları `_gnews_decode()` ile asıl
habere çevrilir (sayfadaki `data-n-a-sg/ts/id` → `news.google.com/_/DotsSplashUi/data/batchexecute`,
`garturlreq`), haber metni okunup son tarih çıkarılır; asıl adres saklanır ("Aç" doğrudan habere
gider). Sonuçlar `data/news_cache.json`'da (45 gün; çözülemeyenler önbelleğe alınmaz, sonraki
taramada tekrar denenir). 3 paralel istek + 1 tekrar: Google fazla paralelde reddediyor.
İlk tarama ~75 sn, sonrakiler ~15 sn. Hâlâ tarihsiz kalanlar arayüzde kesik çerçeve +
"son başvuru tarihi belirtilmemiş" ile ayrılır. Başlığında "kazananlar/announced/sona erdi"
geçen haberler −4 (`engine.NEWS_DONE`).
**Konu kapısı:** `scoring.is_topical()` — konu dışı (AI/girişim/hackathon/yarışma/eğitim
kelimesi geçmeyen) etkinlik Türkiye +2 bonusunu almaz (ör. Eczacıbaşı müze buluşması 3→1).

## Bölge: Türkiye / Yurt dışı
`engine.region_of()`: TR kaynakları, TR şehir adları, `.tr` alan adı ya da Türk/İTÜ/ODTÜ/
TEKNOFEST/TÜBİTAK gibi ipuçları → Türkiye; Türkçe Google News aramaları → Türkiye.
Online global yarışmalar (Devpost vb.) → Yurt dışı. Arayüzde üstte bölge seçici
(varsayılan Türkiye, tarayıcıda hatırlanır); Telegram mesajı da 🇹🇷 / 🌍 gruplu.

## Bağlantı kopması (2026-10-23)
Belirti: tüm kaynaklar aynı anda `SSLEOFError` / `RemoteDisconnected` (uykudan çıkış, Wi-Fi
değişimi). Önlemler: `collectors._get` 3 deneme; `collectors.online()` ön kontrolü — yoksa
tarama başlamaz; kaynakların ≥%75'i düşerse sonuç kaydedilmez (`status.offline`), son tarama
güncellenmez. Zamanlayıcı 5 dk'da bir duvar saatine bakar (`due()`), uyku sonrası gecikmeyi
hemen telafi eder, çevrimdışıysa 5 dk sonra tekrar dener. Arayüz ham hata yerine
"internet yok · birazdan yeniden denenecek" gösterir.

## Hatırlatmalar
Takibe alınan (`saved`) fırsatlar için 7/3/1 gün kala bildirim. Tarih: son başvuru >
(başlamadıysa) başlangıç > bitiş. Aynı eşik bir daha bildirilmez (`reminded` sütunu).

## Telegram
`app/telegram.py`: kullanıcının kendi botuyla telefona da bildirim gönderir
(token `data/telegram.json`'da, depoya girmez). Token sırası:
`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` ortam değişkenleri > `data/telegram.json`
(Ayarlar → Telegram kutusu yazar). Token arayüze hiç geri dönmez. Sohbet id'si
`getUpdates` ile otomatik bulunur (kullanıcı önce bota /start yazmalı). Yeni fırsat
mesajı: ilk 8 fırsat + kategori/tarih + bağlantı. Hatırlatmalar da gider.
Pencere modundaki taramalar da Telegram'a gönderir (tepsi baloncuğu yalnızca --tray'de).

## Arayüz tasarımı (2026-10-21 yeniden tasarım)
Sıcak koyu tema (`--bg #0d0c0a`), tek vurgu rengi amber `#f0a646`, kategori tonları aynı
kısık aileden. Yazı tipleri Google Fonts'tan: Bricolage Grotesque (başlık), Geist (gövde),
Geist Mono (tarih/sayı); internet yoksa Segoe UI'a düşer. Keşfet: dinamik başlık
("Bu hafta N başvuru kapanıyor") + istatistikler + **radar** (merkeze uzaklık = son güne
kalan gün, karekök ölçek; nokta boyu = puan; tıklayınca açılır). Altında takip geri sayım
şeridi, 2 öne çıkan kart (görsel üst bantta — afiş yazıları başlıkla çakışmasın diye),
sonra satır listesi (tarih sütunu, görsel/harf amblemi, puan halkası, üzerine gelince
eylemler). Görseller kaynaklardan (`items.image`), yoksa kategori renginde harf amblemi.
Görsel doğrulama: Browser pane gizliyken `msedge --headless=new --screenshot` kullanıldı.

## Olası geliştirmeler
- Claude API ile açıklamadan son tarih çıkarma / daha akıllı puanlama (veri dışarı çıkar; onay gerek).
- Yeni kaynaklar: üniversite kulüpleri, Teknopark duyuruları, KOSGEB/TÜBİTAK çağrıları.
