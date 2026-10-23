# Fırsat Radarı

Yapay zeka hackathon'larını, girişimcilik programlarını, eğitim/bootcamp'leri ve
yarışmaları birçok kaynaktan **otomatik toplayan**, sana göre puanlayan ve yeni
fırsatlarla yaklaşan son tarihleri **Windows bildirimi + Telegram** ile haber veren
kişisel masaüstü uygulaması.

> **Kişisel bir proje.** Bu uygulamayı, yapay zeka alanında kendini geliştirmek ve
> girişimcilik yapmak isteyen bir öğrenci olarak **kendi kullanımım için** yaptım:
> hackathon'ları, girişimcilik programlarını ve eğitimleri tek tek sitelerde aramaya
> vaktim yoktu ve hiçbirini kaçırmak istemiyordum. Kaynaklar, puanlama ve varsayılan
> ayarlar bu ihtiyaca göre (Türkiye'de okuyan, AI ve girişimciliğe ilgi duyan bir
> öğrenci) seçildi. Aynı dertten muzdarip olan herkes kullanabilir, kendine göre
> değiştirebilir; ama bir ürün değil, bakımı kendi ihtiyacıma göre yapılan bir araç.

![Keşfet ekranı](docs/ekran-goruntusu.png)

## Ne yapar?

- **Tarar:** Devpost, MLH, Coderspace, Techcareer, Youthall, Eventbrite, GDG
  (Google Developer Groups), YTÜ Startup House ve Google News. Ayrıca Y Combinator,
  İTÜ Çekirdek, TEKNOFEST gibi program sayfalarındaki başvuru cümlelerini izler.
- **Eler:** Başvurusu kapanmış fırsatları hiç göstermez. Son başvuru tarihi
  sayfadan, detay sayfasından ya da haber metninden okunur.
- **Puanlar (0–10):** Yapay zeka, girişim ve hackathon içeriği ile Türkiye'de olması
  puanı artırır; konu dışı ya da yurt dışında fiziksel olanlar düşer.
- **Ayırır:** Türkiye / Yurt dışı ve Hackathon, Girişimcilik, Eğitim, Yarışma,
  Etkinlik, Haber kategorileri.
- **Hatırlatır:** Takibe aldıklarını son güne 7, 3 ve 1 gün kala bildirir.
- **Radar:** En iyi fırsatlar, son güne kalan süreye göre bir radarda gösterilir.

## Kurulum (Windows)

Gereken: Python 3.11+ ve (pencere için) Microsoft Edge WebView2 — Windows 10/11'de hazır gelir.

```powershell
git clone https://github.com/efecaliskan2/firsat-radari.git
cd firsat-radari
powershell -ExecutionPolicy Bypass -File .\kur.ps1
```

`kur.ps1` bağımlılıkları kurar, simgeyi üretir ve iki kısayol oluşturur:
Masaüstü (pencere) ve Başlangıç (bilgisayar açılınca tepside sessizce başlar).

Elle çalıştırmak istersen:

| Komut | Ne yapar |
|---|---|
| `python main.py` | Uygulama penceresini açar |
| `python main.py --tray` | Tepsiye yerleşir, 4 saatte bir tarar ve bildirir |
| `python main.py --scan` | Tek seferlik tarama yapıp çıkar |
| `python main.py --serve` | Sadece sunucu: http://127.0.0.1:8770 |

## Telegram bildirimi (isteğe bağlı)

1. Telegram'da **@BotFather** → `/newbot` ile bir bot oluştur, token'ı kopyala.
2. Kendi botuna `/start` yaz.
3. Uygulamada **Ayarlar → Telegram** kutusuna token'ı yapıştır ve kaydet.
   Sohbet numarası otomatik bulunur. Alternatif olarak `TELEGRAM_BOT_TOKEN` ve
   `TELEGRAM_CHAT_ID` ortam değişkenleri de okunur.

## Gizlilik ve güvenlik

- Her şey bilgisayarında çalışır (`127.0.0.1`). Hesap ya da şifre istemez.
- İnternete yalnızca halka açık sayfaları **okumak** için çıkar. Dışarı giden tek
  şey, açtıysan Telegram'a giden bildirim metnidir.
- Kişisel veriler (`data/` klasörü: fırsat veritabanı, ayarlar, Telegram token'ı)
  **depoya girmez**; `.gitignore` ile dışlanmıştır.

## Yapı

```
main.py              başlatıcı (pencere / tepsi / tek tarama / sunucu)
app/collectors.py    kaynak okuyucular, son tarih çıkarıcı, sayfa izleyici
app/scoring.py       kategori ve ilgi puanı
app/engine.py        paralel tarama, SQLite, bildirim, hatırlatma, zamanlayıcı
app/server.py        yerel Flask API
app/telegram.py      Telegram bildirimi
app/static/          arayüz (HTML/CSS/JS, framework yok)
kur.ps1              Windows kurulum betiği
PROJECT.md           ayrıntılı teknik belge (kaynak uçları, kurallar, tuzaklar)
```

Kaynakların çoğu resmi bir API sunmuyor; sayfa yapısı değişirse ilgili toplayıcı
hata verebilir. Hangi kaynağın düştüğü **Ayarlar → Kaynaklar** altında görünür.

## Kendine uyarlamak

- **İlgi alanların:** Ayarlar → "İlgi alanların" kutusuna kendi kelimelerini yaz
  (ör. `fintech, sağlık, robotik`); bu kelimeler puanı yükseltir.
- **Ek aramalar:** Ayarlar → "Ek haber aramaları" ile Google News'te kendi aramalarını ekle.
- **İzlenen sayfalar:** Takip etmek istediğin programların sayfalarını `Ad | https://…`
  biçiminde ekle; başvuru cümleleri değişince haber verir.
- **Yeni kaynak:** `app/collectors.py` içinde ortak sözlük biçimini döndüren bir fonksiyon
  yazıp `EVENT_SOURCES`'a eklemen yeterli.

## Sorumluluk reddi

- Uygulama yalnızca **halka açık** sayfaları, normal bir ziyaretçi gibi ve seyrek
  (varsayılan 4 saatte bir) okur. Kullanırken ilgili sitelerin kullanım koşullarına
  uymak kullanıcının sorumluluğundadır.
- Listelenen sitelerin hiçbiriyle bir bağlantım yoktur; adları yalnızca kaynağı
  belirtmek için geçer.
- Son başvuru tarihleri sayfalardan otomatik okunur ve **hatalı olabilir**. Başvurmadan
  önce tarihi her zaman fırsatın kendi sayfasından doğrula.

## Lisans

[MIT](LICENSE) — dilediğin gibi kullan, değiştir, paylaş; telif satırını koru.
