# RSS kaynak kullanım incelemesi

Son kontrol: 18 Eylül 2026

Bu inceleme, uygulamanın RSS başlığı ve kısa açıklamasından yeniden yazılmış kısa
bir özet üretmesi, kaynak adını ve asıl haber bağlantısını göstermesi içindir.
Uygulama kaynak fotoğrafını veya videosunu indirmez ve yeniden yüklemez.

| Kaynak | Durum | Dayanak | Uygulama kararı |
|---|---|---|---|
| TRT Haber Spor | Ticari `unknown`, RSS `allowed` | [Resmî RSS listesi](https://www.trthaber.com/sitene_ekle.html) mevcut; açık ticari yeniden yayın lisansı bulunamadı. | FACT tabanlı özgün üretim, kaynak ve bağlantı ile etkin. Gelir elde etmeden önce yazılı teyit önerilir. |
| A Spor | Ticari `unknown`, RSS `allowed` | [Resmî RSS sayfası](https://www.aspor.com.tr/rss-bilgi) RSS'yi içerik takibi için sunuyor; açık ticari lisans bulunamadı. | FACT tabanlı özgün üretim, kaynak ve bağlantı ile etkin. Gelir elde etmeden önce yazılı teyit önerilir. |
| Transfermarkt Türkiye | Ticari `restricted`, RSS `restricted` | [Kullanım koşulları](https://www.transfermarkt.com.tr/intern/anb) içerik haklarını saklı tutuyor ve çoğaltmayı sınırlandırıyor. | Pasif; yazılı izin olmadan işlenmez. |
| Habertürk Spor | Ticari `restricted`, RSS `restricted` | [Kullanım koşulları](https://www.haberturk.com/kullanim-kosullari) haber ve materyal kullanımını açık yazılı izne bağlıyor. | Pasif; yazılı izin olmadan işlenmez. |
| NTV Spor Futbol | Ticari `restricted`, RSS `restricted` | [Kullanım koşulları](https://www.ntvspor.net/kullanim-kosullari) haber ve materyal kullanımını açık yazılı izne bağlıyor. | Pasif; yazılı izin olmadan işlenmez. |

## Uygulanan teknik sınırlar

- RSS kullanımı `restricted` veya ticari kullanım `prohibited` olan kaynak API
  üzerinden aktif edilemez.
- İncelenmemiş kaynaklar `unknown` kalır; izinli varsayılmaz ve Telegram'da açıkça
  uyarı gösterilir.
- Eski veritabanlarında bu kaynaklar Alembic migration ile pasifleştirilir.
- Collector, yanlışlıkla aktif kalsalar bile bu kaynakları ve başarısız haber
  kuyruğundaki kayıtlarını işlemez.
- RSS açıklamalarındaki HTML, script ve style içeriği silinir; metin 1.200
  karakterle sınırlandırılır.
- Ham RSS metni yalnız FACT extraction aşamasında kullanılır. Üretim structured
  olgulardan yapılır; benzerlik limiti aşılırsa yeniden üretim uygulanır.
- X paylaşımında kaynak adı ve asıl haber bağlantısı zorunlu olarak eklenir.
- Kaynak görseli veya videosu indirilmez; yalnız X'in bağlantı önizlemesi görünür.

Olguların özgün bir anlatımla yeniden yazılması riski azaltır; ancak kaynak
koşullarını veya gerekli izinleri ortadan kaldırmaz. Sistem RSS'i haber sinyali ve
olgu girdisi olarak kullanır, kaynak metni yeniden yayımlamaz.

Koşullar değişebileceği için kaynak eklerken ve en az üç ayda bir bu inceleme
yenilenmelidir. Yazılı izin alınırsa ilgili alan adı policy listesinden ancak izin
kapsamı doğrulandıktan sonra çıkarılmalıdır.
