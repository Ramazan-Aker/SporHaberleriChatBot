# Spor Haberleri İçerik Üretim Sistemi

Bu servis RSS/Atom kaynaklarını tarar, yeni haberleri tekrar kontrolünden geçirir,
OpenAI veya Groq ile kısa bir Türkçe X gönderisi üretir ve kullanıcı onayı için
Telegram'a gönderir. X API kullanılmaz; son paylaşım kullanıcıya aittir.

## Mimari

Tek FastAPI süreci dört ana işi yürütür:

1. APScheduler aktif kaynakları periyodik olarak çağırır.
2. RSS istemcisi girdileri ayrıştırır; repository katmanı URL ve başlık hash'iyle
   tekrarları eler.
3. FactExtractor ham RSS başlığı ve kısa özetinden structured, doğrulanabilir
   olguları çıkarır. Duplicate ve kaynak politikası kontrolleri bundan önce çalışır.
4. İçerik servisi yalnız FACT verilerinden özgün gönderi üretir; benzerlik ve
   desteklenmeyen iddia kontrolleri sonucu doğrular.
5. Telegram botu metni onaylama, reddetme, düzenleme, yeniden yazma ve X paylaşım
   ekranını açma akışını sunar.

Her haber ayrı transaction içinde işlenir. Bir RSS, AI veya Telegram hatası diğer
kaynakları durdurmaz. Uygulama `app/models`, `schemas`, `repositories`, `services`,
`integrations`, `jobs` ve `api/routes` katmanlarına ayrılmıştır.

## Gereksinimler

- Python 3.12+
- PostgreSQL 14+ (Compose PostgreSQL 16 kullanır)
- OpenAI veya Groq API anahtarı ve erişilebilir bir model adı
- Telegram bot token'ı, hedef chat ID ve izin verilen kullanıcı ID'si
- Alternatif olarak Docker ve Docker Compose

## Yerel geliştirme

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Windows dışındaki sistemlerde `copy` yerine `cp` kullanın. Yalnızca API üzerinde
çalışırken `.env` içinde `SCHEDULER_ENABLED=false` ve `TELEGRAM_ENABLED=false`
ayarlanabilir. OpenAPI arayüzü `http://localhost:8000/docs`, health endpoint'i
`http://localhost:8000/health` adresindedir.

## Environment ayarları

| Değişken | Açıklama | Varsayılan |
|---|---|---|
| `DATABASE_URL` | Async SQLAlchemy PostgreSQL URL'si | local PostgreSQL |
| `AI_PROVIDER` | AI sağlayıcısı: `openai` veya `groq` | `openai` |
| `OPENAI_API_KEY` | OpenAI API anahtarı | boş |
| `OPENAI_MODEL` | Kullanılacak model kimliği | boş |
| `GROQ_API_KEY` | Groq API anahtarı | boş |
| `GROQ_MODEL` | Groq model kimliği | `openai/gpt-oss-20b` |
| `GROQ_REASONING_EFFORT` | GPT-OSS akıl yürütme düzeyi | `low` |
| `GROQ_MAX_COMPLETION_TOKENS` | Yanıt için token üst sınırı | `512` |
| `TELEGRAM_BOT_TOKEN` | BotFather token'ı | boş |
| `TELEGRAM_CHAT_ID` | Mesajların gönderileceği chat | boş |
| `TELEGRAM_ALLOWED_USER_ID` | Butonları kullanabilecek kullanıcı | boş |
| `NEWS_FETCH_INTERVAL_MINUTES` | RSS tarama aralığı | `5` |
| `NEWS_INITIAL_LOOKBACK_HOURS` | İlk taramada üretilecek geçmiş pencere | `24` |
| `NEWS_ONLY_CURRENT_DAY` | Yalnız yerel takvim günündeki haberleri işler | `true` |
| `NEWS_TIMEZONE` | Haber günü hesabında kullanılan saat dilimi | `Europe/Istanbul` |
| `ENFORCE_SOURCE_USAGE_POLICY` | Yazılı izin isteyen kaynakları engeller | `true` |
| `ENABLE_SOURCE_POLICY_CHECK` | Kaynak politika kontrolünü etkinleştirir | `true` |
| `MAX_POST_LENGTH` | AI ve düzenleme karakter sınırı | `260` |
| `MAX_SOURCE_SIMILARITY` | Kaynak başlığı/özeti için en yüksek benzerlik | `0.55` |
| `ALLOW_EXTERNAL_MEDIA` | Dış kaynak görsellerine gelecekte izin verir | `false` |
| `ALLOW_DIRECT_QUOTES` | AI doğrudan alıntılarına izin verir | `false` |
| `ENABLE_CLAIM_VALIDATION` | İkinci AI iddia doğrulamasını açar | `true` |
| `HTTP_TIMEOUT_SECONDS` | RSS/OpenAI zaman aşımı | `15` |
| `EXTERNAL_API_MAX_RETRIES` | AI deneme sayısı | `3` |
| `AI_MIN_REQUEST_INTERVAL_SECONDS` | AI çağrıları arasındaki en az süre | `12` |
| `AI_FAILED_RETRY_LIMIT` | Her job'da yeniden denenecek başarısız haber | `5` |
| `SCHEDULER_ENABLED` | RSS/AI pipeline'ını açar | `false` |
| `TELEGRAM_ENABLED` | Telegram polling'i açar | `false` |

Etkin bir entegrasyonun secret'ı eksikse uygulama açık bir config hatasıyla
başlamaz. `.env` Git tarafından yok sayılır; anahtarları repository'ye eklemeyin.

## PostgreSQL ve Alembic

`DATABASE_URL` SQLAlchemy async biçiminde olmalıdır:

```text
postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE
```

Migration uygulama: `alembic upgrade head`. Geri alma: `alembic downgrade -1`.
Model değişikliğinden sonra migration üretmek için
`alembic revision --autogenerate -m "aciklama"` kullanın ve çıktıyı inceleyin.

## AI sağlayıcısı kurulumu

Ücretsiz Groq katmanını kullanmak için:

```env
AI_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-20b
GROQ_REASONING_EFFORT=low
GROQ_MAX_COMPLETION_TOKENS=512
```

Groq istemcisi OpenAI uyumlu Chat Completions endpoint'ini ve strict JSON Schema
çıktısını kullanır. Üretilen sonuç ayrıca Pydantic ile doğrulanır.

OpenAI kullanmak için:

```env
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=hesabinizdaki-model
```

OpenAI platformundan bir API anahtarı oluşturun, `.env` içinde
`OPENAI_API_KEY` değerine yazın ve hesabınızda erişilebilir model kimliğini
`OPENAI_MODEL` olarak belirleyin. İstemci Responses API structured output kullanır;
modelin structured outputs desteklediğinden emin olun. Model cevabı yalnız haber
alanlarını alır ve sonuç 260 karakter sınırından ayrıca uygulama tarafında geçer.

## Telegram kurulumu

1. Telegram'da `@BotFather` ile bot oluşturup token'ı alın.
2. Botla özel sohbet başlatın ve bir mesaj gönderin.
3. Tarayıcıda `https://api.telegram.org/bot<TOKEN>/getUpdates` açın.
4. `message.chat.id` değerini `TELEGRAM_CHAT_ID`, `message.from.id` değerini
   `TELEGRAM_ALLOWED_USER_ID` olarak ayarlayın.
5. `TELEGRAM_ENABLED=true` yapın.

Bot hem kullanıcı hem chat kimliğini kontrol eder. Yeni haberde **Onayla**,
**Reddet**, **Düzenle**, **Yeniden Yaz**, **Metni Göster** ve **Kaynağı Aç**
düğmeleri gelir. Yeniden yazma ham RSS metnini AI'a tekrar göndermez; veritabanına
kaydedilmiş FACT verilerinden yeni, sürümlü bir post oluşturur. Düzenleme sonrasında
yeni metin veritabanına `final_text` olarak kaydedilir. Onaylanan gönderideki
**X'te Paylaş** düğmesi, metni, kaynak adını ve haber URL'sini X Web Intent ile
hazır paylaşım ekranında açar; son gönderim kullanıcıya aittir ve X API anahtarı
gerekmez. Long polling kullanıldığı için webhook veya public Telegram endpoint'i
gerekmez.

## RSS kaynağı ekleme

`POST /sources` örneği:

```json
{
  "name": "Kaynak adı",
  "url": "https://kaynak.example",
  "rss_url": "https://kaynak.example/feed.xml",
  "category": "football",
  "source_type": "news",
  "credibility_score": 8,
  "commercial_use_status": "unknown",
  "rss_usage_status": "unknown",
  "terms_url": null,
  "notes": "Kullanım koşulları incelenecek",
  "active": true
}
```

Gerçek ve kullanımına izin verilen RSS URL'lerini kendiniz eklemelisiniz. Projede
otomatik etkinleşen production kaynağı yoktur. Birden çok development kaynağını
JSON'dan eklemek için `scripts/sources.example.json` dosyasını gerçek bilgilerle
kopyalayıp düzenleyin, ardından çalıştırın:

```bash
python -m scripts.seed_sources seed_sources.json
```

`NEWS_ONLY_CURRENT_DAY=true` iken yalnız `NEWS_TIMEZONE` saat diliminde bugüne ait
tarihli haberler AI'a gider. Eski kayıtlar tekrar işlemeyi önlemek için başlangıç
verisi olarak saklanır. Bu ayar kapatılırsa ilk taramada son 24 saat politikası
kullanılır. Sonraki taramalarda yeni tarihsiz kayıtlar işlenir. ETag ve
Last-Modified değerleri gereksiz indirmeleri azaltır.

Kaynak hakları politikası varsayılan olarak açıktır. Yeni kaynaklar `unknown`
durumuyla başlar; sistem bunu izin verilmiş saymaz ve Telegram'da gösterir. RSS
kullanımı `restricted` veya ticari kullanım `prohibited` ise kaynak aktif edilemez.
Migration daha önce incelenen kısıtlı kaynakları pasifleştirir. `GET /sources`
yanıtında `commercial_use_status`, `rss_usage_status`, `terms_url` ve `notes`
alanları bulunur.
TRT Haber ve A Spor yalnız FACT tabanlı özgün üretim, kaynak adı ve asıl bağlantı
ile kullanılır. Güncel inceleme ve kararların ayrıntısı
[`docs/source-usage-review.md`](docs/source-usage-review.md) dosyasındadır.

## Content & Copyright Safety

Sistem RSS'i makale yeniden yayımlamak için değil, haber keşfi ve doğrulanabilir
olguları belirlemek için kullanır. Üretim hattı aşağıdaki sırayı izler:

```text
RSS → temel kalite → duplicate → kaynak politikası → FACT extraction
    → FACT tabanlı özgün üretim → kaynak benzerliği → iddia doğrulama → Telegram
```

- Duplicate veya engellenmiş bir kaynak için AI çağrısı yapılmaz.
- Normal bir yeni haber fact extraction, içerik üretimi ve iddia doğrulaması için
  üç structured AI çağrısı kullanır. `ENABLE_CLAIM_VALIDATION=false` üçüncü çağrıyı
  kapatır; doğruluk korumasını azaltır. Tüm aşamalar aynı
  `AI_MIN_REQUEST_INTERVAL_SECONDS` hız sınırını paylaşır.
- Ham başlık ve kısa RSS özeti yalnız FactExtractor aşamasında kullanılır.
- ContentGenerator yalnız structured FACT, entity, event type, kesinlik, sayı,
  kaynak türü ve güven skorlarını görür; orijinal URL ve RSS metni gönderilmez.
- RSS istemcisi full article scraping yapmaz. HTML temizlenmiş kısa özet en fazla
  1.200 karakter olarak saklanır.
- Üretilen metin başlık ve özetle `%55` değerinden daha benzerse bir kez yeniden
  üretilir. İkinci sonuç da yüksekse `content_review_required` olur.
- ContentValidator FACT listesinde olmayan spesifik iddiaları denetler. Kalıcı
  sorunlar normal onay akışına girmez ve Telegram'da inceleme uyarısı gösterir.
- Dış kaynak fotoğrafı, videosu, thumbnail'i veya maç görüntüsü indirilmez.
  `ALLOW_EXTERNAL_MEDIA=false` varsayılandır ve mevcut sürüm medya işlemez.
- Doğrudan alıntı varsayılan olarak kapalıdır. Sayılar structured alanlarda tutulur
  ve üretim sırasında yeni bir sayı eklenmesi reddedilir.
- Kaynak URL'si doğrulama için Telegram'da gösterilir. Son düzenleme ve paylaşım
  kararı kullanıcıya aittir.

Bu teknik önlemler hukuki danışmanlık veya hukuki uygunluk garantisi değildir.

## Docker Compose

`.env.example` dosyasını `.env` adıyla kopyalayın ve secret'ları doldurun:

```bash
docker compose up --build
```

Compose PostgreSQL'i healthcheck ile bekler, migration'ı uygular ve backend'i
8000 portunda açar. Veriler `postgres_data` volume'unda kalır. Durdurmak için
`docker compose down`; verileri de silmek için bilinçli olarak `-v` ekleyin.

## Testler ve kalite

```bash
ruff check .
black --check .
pytest
```

Testler SQLite ve mock istemciler kullanır; gerçek OpenAI, Groq, Telegram veya
RSS çağrısı yapmaz.

## Railway deploy

1. Repository'yi Railway projesine bağlayın ve PostgreSQL servisi ekleyin.
2. PostgreSQL bağlantısını asyncpg URL biçiminde `DATABASE_URL` olarak verin.
3. `.env.example` içindeki diğer değişkenleri Railway Variables alanına ekleyin.
4. `SCHEDULER_ENABLED=true` ve `TELEGRAM_ENABLED=true` ayarlayın.
5. Servisi tek replica ile çalıştırın. Birden fazla replica hem scheduler job'ını
   hem Telegram long polling'i çoğaltır.

Railway `Dockerfile` ve `railway.toml` dosyalarını kullanır. Başlangıçta migration
uygulanır, uygulama Railway'in `PORT` değerini dinler ve `/health` ile izlenir.

## Production notları

- API ilk sürümde authentication içermez. Kaynak yönetim endpoint'lerini herkese
  açık internete sunmadan önce gateway veya uygulama authentication'ı ekleyin.
- Database yedeği, merkezi log toplama, harcama limiti ve alarm kurun.
- Kaynak kullanım incelemesini en az üç ayda bir yenileyin ve gelir elde etmeden
  önce `rss_link_only` kaynaklardan yazılı ticari kullanım teyidi alın.
- Telegram ve AI anahtarlarını yalnız secret yönetiminde tutun.

## MVP dışında kalanlar

X API ve otomatik paylaşım, frontend/dashboard, web scraping, Redis/Celery,
semantic duplicate detection, çoklu kaynak doğrulama, görsel üretimi, canlı skor,
takım/lig filtreleri, trend/öncelik analizi, engagement analytics ve birden fazla
X hesabı bu sürümde uygulanmamıştır. Servis ve entegrasyon sınırları bu özellikler
için genişletilebilir tutulmuştur.
