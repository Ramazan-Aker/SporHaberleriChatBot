import re
import unicodedata
from urllib.parse import urlparse

_LIVE_EVENT_TITLE = re.compile(
    r"^(gol|penaltı|kırmızı kart|sarı kart|var|canlı|ilk yarı|devre arası|"
    r"maç başladı|ikinci yarı)\s*[|:]"
)


def is_live_match_update(title: str) -> bool:
    lowered = title.translate(str.maketrans({"I": "ı", "İ": "i"})).lower()
    normalized = unicodedata.normalize("NFKC", lowered).strip()
    return bool(_LIVE_EVENT_TITLE.match(normalized))


def is_quality_article(*, title: str, description: str | None, url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    clean_title = title.strip()
    if not clean_title:
        return False
    meaningful = "".join(
        character
        for character in f"{clean_title} {description or ''}"
        if character.isalnum()
    )
    return len(meaningful) >= 20
