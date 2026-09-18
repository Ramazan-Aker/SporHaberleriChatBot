"""JSON dosyasindan development kaynaklari ekler.

Kullanim: python -m scripts.seed_sources path/to/sources.json
"""

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.repositories.source_repository import SourceRepository
from app.schemas.source import SourceCreate


async def seed(payload: list[dict[str, object]]) -> None:
    sources = [SourceCreate.model_validate(item) for item in payload]
    async with SessionLocal() as session:
        repository = SourceRepository(session)
        for data in sources:
            try:
                await repository.create(data)
                await session.commit()
                print(f"Added: {data.name}")
            except IntegrityError:
                await session.rollback()
                print(f"Skipped existing RSS URL: {data.rss_url}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_file", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.json_file.read_text(encoding="utf-8"))
    asyncio.run(seed(payload))


if __name__ == "__main__":
    main()
