import calendar
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from time import struct_time

import feedparser
import httpx

MAX_DESCRIPTION_LENGTH = 1200


class _FeedTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def clean_feed_description(value: str) -> str | None:
    extractor = _FeedTextExtractor()
    extractor.feed(value)
    text = re.sub(r"\s+", " ", unescape(" ".join(extractor.parts))).strip()
    if not text:
        return None
    if len(text) > MAX_DESCRIPTION_LENGTH:
        text = text[:MAX_DESCRIPTION_LENGTH].rsplit(" ", maxsplit=1)[0].rstrip()
    return text or None


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
            raw_description = str(
                raw.get("summary") or raw.get("description") or ""
            ).strip()
            description = clean_feed_description(raw_description)
            published = _to_datetime(
                raw.get("published_parsed") or raw.get("updated_parsed")
            )
            entries.append(
                FeedEntry(
                    title=title,
                    description=description,
                    url=url,
                    published_at=published,
                )
            )
        return FeedResult(
            entries=entries,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
        )
