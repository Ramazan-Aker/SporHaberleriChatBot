import calendar
from dataclasses import dataclass
from datetime import UTC, datetime
from time import struct_time

import feedparser
import httpx


@dataclass(slots=True)
class FeedEntry:
    title: str
    description: str | None
    url: str
    published_at: datetime | None


@dataclass(slots=True)
class FeedResult:
    entries: list[FeedEntry]
    etag: str | None
    last_modified: str | None
    not_modified: bool = False


def _to_datetime(value: struct_time | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)


class RSSClient:
    def __init__(self, *, timeout_seconds: float = 15) -> None:
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=True,
            max_redirects=5,
            headers={"User-Agent": "SporHaberiChatBot/0.1 (+RSS reader)"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch(
        self, rss_url: str, *, etag: str | None = None, last_modified: str | None = None
    ) -> FeedResult:
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        response = await self._client.get(rss_url, headers=headers)
        if response.status_code == httpx.codes.NOT_MODIFIED:
            return FeedResult([], etag, last_modified, not_modified=True)
        response.raise_for_status()

        feed = feedparser.parse(response.content)
        if feed.bozo and not feed.entries:
            raise ValueError(f"Invalid RSS/Atom response: {feed.bozo_exception}")

        entries = []
        for raw in feed.entries:
            title = str(raw.get("title", "")).strip()
            url = str(raw.get("link", "")).strip()
            description = str(
                raw.get("summary") or raw.get("description") or ""
            ).strip()
            published = _to_datetime(
                raw.get("published_parsed") or raw.get("updated_parsed")
            )
            entries.append(
                FeedEntry(
                    title=title,
                    description=description or None,
                    url=url,
                    published_at=published,
                )
            )
        return FeedResult(
            entries=entries,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
        )
