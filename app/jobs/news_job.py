import structlog

from app.services.news_collector import NewsCollector

logger = structlog.get_logger(__name__)


class NewsJob:
    def __init__(self, collector: NewsCollector) -> None:
        self.collector = collector

    async def run(self) -> None:
        logger.info("news_job_started", operation="fetch_news")
        await self.collector.fetch_news()
        logger.info("news_job_finished", operation="fetch_news")
