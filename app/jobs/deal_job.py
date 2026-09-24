import structlog

from app.services.deal_pipeline import DealPipeline

logger = structlog.get_logger(__name__)


class DealJob:
    def __init__(self, pipeline: DealPipeline) -> None:
        self.pipeline = pipeline

    async def run(self) -> None:
        logger.info("deal_job_started", operation="fetch_prices")
        await self.pipeline.run()
        logger.info("deal_job_finished", operation="fetch_prices")
