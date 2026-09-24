from unittest.mock import AsyncMock

import pytest

from app.services.opportunity_ai_polisher import (
    OpportunityAIPolisher,
    PolishedProductName,
)


@pytest.mark.asyncio
async def test_ai_polisher_rejects_invented_product_number() -> None:
    client = AsyncMock()
    client.parse.return_value = PolishedProductName(short_name="Samsung 999 PRO 2TB")
    polisher = OpportunityAIPolisher(client)

    with pytest.raises(ValueError, match="unsupported number"):
        await polisher.shorten_name(
            {
                "product_name": "Samsung 990 PRO 2TB",
                "brand": "Samsung",
                "category": "SSD",
                "store": "Amazon",
                "current_price": 6999,
            }
        )
