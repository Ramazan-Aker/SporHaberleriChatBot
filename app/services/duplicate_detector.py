import hashlib
import re
import unicodedata

from app.repositories.article_repository import ArticleRepository


def normalize_title(title: str) -> str:
    turkish_lower = title.translate(str.maketrans({"I": "ı", "İ": "i"})).lower()
    normalized = unicodedata.normalize("NFKC", turkish_lower)
    normalized = "".join(
        character if character.isalnum() else " " for character in normalized
    )
    return re.sub(r"\s+", " ", normalized).strip()


def make_content_hash(title: str) -> str:
    return hashlib.sha256(normalize_title(title).encode("utf-8")).hexdigest()


class DuplicateDetector:
    def __init__(self, repository: ArticleRepository) -> None:
        self.repository = repository

    async def is_duplicate(self, *, url: str, title: str) -> bool:
        return await self.repository.duplicate_exists(
            url=url, content_hash=make_content_hash(title)
        )
