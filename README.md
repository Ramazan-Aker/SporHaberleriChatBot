# Türkiye Fiyat / Fırsat Radarı

FastAPI tabanlı bu servis, izinli mağaza API/feed verisini tek ürün kataloğunda
normalize eder, fiyat geçmişini tutar, gerçek fiyat düşüşünü geçmiş verilere göre
ölçer ve yalnız yeterli skora ulaşan fırsatları Telegram onayına gönderir. Gönderi
üretimi varsayılan olarak deterministik template kullanır; AI zorunlu değildir.

Eski spor/RSS scheduler'ı artık runtime'a bağlanmaz ve spor haberi toplamaz. Üretim
verisini korumak için mevcut `sources`, `articles` ve `generated_posts` tabloları ile
onlara ait Alembic geçmişi silinmemiştir. Eski kayıtlar read/admin API'lerinden
erişilebilir; yeni ana sistem mağaza/fiyat hattıdır.

## Çalışma akışı

```text
APScheduler → etkin StoreAdapter'lar → normalize/eşleştir → listing güncelle
            → PriceHistory → gerçek indirim analizi → 0-100 fırsat skoru
            → cooldown/duplicate → template gönderi → Telegram onayı
```

Her mağaza ve her ürün ayrı hata sınırındadır. Bir adapter hatası diğer mağazaları
durdurmaz. Aynı fiyat ve stok tekrar gelirse history şişirilmez; fiyat/stok değişimi
veya periyodik snapshot zamanı geldiğinde yeni kayıt oluşur.

## Mimari

- `app/integrations/stores`: ortak `StoreAdapter`, Amazon Creators API, mock Amazon
  ve veri kaynağı sağlanana kadar kapalı Trendyol/Hepsiburada adapter'ları.
- `app/models`: mağaza, canonical ürün, listing, fiyat geçmişi, watchlist, fırsat ve
  sürümlü fırsat gönderisi modelleri.
- `app/services`: deterministic normalizer/matcher, tracker, detector, scorer,
  affiliate servisi, post template'leri ve orkestrasyon pipeline'ı.
- `app/repositories/commerce_repository.py`: async SQLAlchemy veri erişimi.
- `app/api/routes/commerce.py`: gelecekteki dashboard için salt-okuma API'leri.
- `app/services/telegram_service.py`: onay, red, düzenleme, regenerate, fiyat
  geçmişi ve X Web Intent akışı.

Product matching sırası: GTIN/EAN/UPC, MPN, marka+model, normalized key ve son
olarak yüksek eşikli fuzzy match. Kapasitesi çelişen (ör. 1 TB / 2 TB) ürünler
otomatik birleştirilmez; düşük güvenli eşleşme manuel incelemeye gider.

## Modeller ve migration

`20260924_0004_price_opportunity_radar.py` yalnız aşağıdaki yeni tabloları ekler:

- `stores`
- `products`
- `product_listings`
- `price_history`
- `product_watches`
- `opportunities`
- `opportunity_posts`

Migration eski tabloyu düşürmez, veritabanını resetlemez ve Article verisini
değiştirmez. Production öncesinde yine de PostgreSQL yedeği alın.

```bash
alembic upgrade head
```

## Fırsat analizi ve skor

Detector; önceki fiyat, 7/30/90 günlük ortalama, 30/90 günlük dip, tarihsel dip ve
tepe, gerçek düşüş, ilan edilen indirim ve mutlak tasarrufu ayrı hesaplar. Veri
yoksa tarihsel dip uydurmaz. Örneğin mağazanın `%30` etiketi olsa bile 30 günlük
ortalama yalnız `%3` yukarıdaysa skor gerçek `%3` üzerinden şekillenir.

| Sinyal | Varsayılan puan |
|---|---:|
| Gerçek fiyat düşüşü | 30 |
| Tarihsel/90 günlük dip seviyesine yakınlık | 25 |
| Ürün popülerliği | 15 |
| Satıcı kalitesi | 15 |
| Stokta olma | 10 |
| Mutlak tasarruf | 5 |

Toplam `MIN_OPPORTUNITY_SCORE` altındaysa Telegram mesajı oluşmaz. Aynı listing ve
aynı fiyat `OPPORTUNITY_COOLDOWN_HOURS` içinde yeniden fırsat üretmez. Fiyat sonra
değişirse bekleyen fırsat `expired` olur; onay sırasında listing fiyatı tekrar
karşılaştırılır ve eski fiyat doğrudan onaylanmaz.

## Telegram

Telegram ana yönetim ekranıdır. Mesajda ürün, mağaza, güncel/önceki fiyat, 30 günlük
ortalama, gerçek indirim, 90 günlük dip, skor, stok, satıcı ve hazır gönderi görünür.
Onayla, Düzenle, Reddet, Yeniden Oluştur, Metni Göster, Ürünü Aç ve Fiyat Geçmişi
butonları bulunur. Regenerate dış API çağrısı yapmaz; kayıtlı opportunity verisinden
yeni sürüm üretir. Onay sonrası X Web Intent açılır; X API entegrasyonu yoktur.

## Amazon Türkiye

Local ve test için credential gerekmez:

```env
ENABLE_AMAZON=true
USE_MOCK_STORE_DATA=true
```

Mock fixture aynı Samsung SSD için sırasıyla 8.499, 7.999 ve 6.999 TL üretir.

Production adapter resmi Amazon Creators API'yi, OAuth token cache'ini, batch
GetItems (10 ASIN), timeout, 429/5xx retry ve exponential backoff'u kullanır:

```env
USE_MOCK_STORE_DATA=false
AMAZON_CREDENTIAL_ID=...
AMAZON_CREDENTIAL_SECRET=...
AMAZON_PARTNER_TAG=...
AMAZON_MARKETPLACE=www.amazon.com.tr
AMAZON_ASINS=B0...,B0...
AMAZON_SEARCH_KEYWORDS=Samsung SSD,gaming monitor
```

Eski `AMAZON_ACCESS_KEY` / `AMAZON_SECRET_KEY` alanları config uyumluluğu için
korunur ancak production çağrısında kullanılmaz. Amazon PA-API 5'i Creators API
lehine deprecated etmiştir; yeni OAuth credentials Associates hesabından alınır.
Resmi kaynaklar: [Creators API geçişi](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/migrating-to-creatorsapi-from-paapi),
[OAuth örneği](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/get-started/using-curl).

## Trendyol ve Hepsiburada

İki adapter interface seviyesinde hazırdır ve varsayılan olarak kapalıdır:

```env
ENABLE_TRENDYOL=false
ENABLE_HEPSIBURADA=false
```

**DISABLED UNTIL DATA SOURCE IS CONFIGURED.** Resmi/izinli API, affiliate feed
veya kullanıcı tarafından sağlanan veri belirlenmeden scraping, browser automation,
undocumented endpoint ya da sahte production API kullanılmaz.

Her mağazanın API, feed, affiliate ve kullanım koşulları farklıdır. Bir mağaza için
teknik olarak veri çekmenin mümkün olması, bu verinin otomatik veya ticari kullanımına
izin verildiği anlamına gelmez. Adapter aktif edilmeden önce güncel koşullar kontrol
edilmelidir.

## Affiliate ve AI

Adapter affiliate URL sağlıyorsa post zorunlu `AFFILIATE_DISCLOSURE` değerini içerir;
affiliate yoksa normal ürün URL'si ve açıklamasız template kullanılır.

`ENABLE_AI_POST_POLISH=false` ile fiyat hattında AI çağrısı yapılmaz. `true` yalnız
structured opportunity verisiyle ürün adını kısaltır. Fiyat, yüzde, mağaza ve link
uygulamanın deterministic template'inden gelir; AI'nın ürün adına yeni sayı eklemesi
reddedilir ve sistem orijinal ürün adına güvenli şekilde döner.

## API

Pagination `offset` ve `limit` ile yapılır.

- `GET /stores`
- `GET /products?store=&category=`
- `GET /products/{id}`
- `GET /products/{id}/prices`
- `GET /listings?store=&category=`
- `GET /opportunities?store=&category=&min_score=&status=&date_from=&date_to=`
- `GET /opportunities/{id}`
- `GET /health`

Yeni frontend yoktur. API ilk MVP'de authentication içermez; public production
erişiminden önce gateway veya uygulama auth eklenmelidir.

## Yeni mağaza ekleme

1. `StoreAdapter` sınıfını extend edin ve yalnız izinli veri kaynağını kullanın.
2. Sonuçları `StoreProduct` olarak döndürün.
3. `slug`, `data_source_type`, koşul URL'si ve affiliate davranışını tanımlayın.
4. Adapter'ı `build_store_adapters` içine feature flag ile ekleyin.
5. HTTP retry/rate-limit ve failure-isolation testlerini yazın.
6. Adapter'ı açmadan önce mağazanın güncel kullanım şartlarını doğrulayın.

## Environment özeti

Tam liste `.env.example` içindedir. Kritik alanlar:

```env
DATABASE_URL=postgresql+asyncpg://...
SCHEDULER_ENABLED=true
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
TELEGRAM_ALLOWED_USER_ID=...
PRICE_CHECK_INTERVAL_MINUTES=15
PRICE_SNAPSHOT_INTERVAL_HOURS=24
MIN_OPPORTUNITY_SCORE=75
OPPORTUNITY_COOLDOWN_HOURS=24
AFFILIATE_DISCLOSURE=#reklam
```

Secret'ları repository'ye eklemeyin. `.env` Git tarafından yok sayılır ve structured
logging Telegram/OpenAI/Groq/PostgreSQL secret'larını redakte eder.

## Local çalıştırma

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

OpenAPI arayüzü `http://localhost:8000/docs` adresindedir.

## Docker

```bash
copy .env.example .env
docker compose up --build
```

Compose PostgreSQL 16 kullanır, migration'ı başlangıçta uygular ve kalıcı
`postgres_data` volume'u kullanır. `docker compose down -v` veriyi siler; production
veritabanında kullanmayın.

## Railway

Railway yapılandırması değişmedi: `Dockerfile`, `railway.toml` ve `scripts/start.sh`
migration sonrası Uvicorn'u başlatır. PostgreSQL `DATABASE_URL` ve `.env.example`
alanlarını Railway Variables'a girin. Scheduler/Telegram long polling duplicate
olmaması için tek replica çalıştırın. Deploy öncesi mock'u kapatıp Creators API
credentials ve ASIN/arama watchlist'i sağlayın.

## Testler

```bash
ruff check .
black --check .
pytest
```

Testler SQLite ve mock HTTP/store/Telegram istemcileri kullanır; gerçek Amazon,
Telegram veya AI çağrısı yapmaz. Normalization, identifier matching, kapasite
uyuşmazlığı, history suppression, 7/30/90 günlük istatistik, sahte indirim,
scoring/eşik, cooldown, expiry/onay fiyat kontrolü, disclosure/template/regenerate,
adapter izolasyonu, mock Amazon ve 429 retry kapsam dahilindedir.
