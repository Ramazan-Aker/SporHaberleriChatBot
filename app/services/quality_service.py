from urllib.parse import urlparse


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
