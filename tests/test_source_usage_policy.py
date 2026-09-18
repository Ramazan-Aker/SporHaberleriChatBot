import pytest

from app.models.source import CommercialUseStatus, RSSUsageStatus
from app.services.source_usage_policy import (
    classify_source_usage,
    source_policy_blocks_processing,
    source_policy_warning,
)


@pytest.mark.parametrize(
    ("url", "commercial", "rss"),
    [
        (
            "https://www.trthaber.com/spor",
            CommercialUseStatus.UNKNOWN,
            RSSUsageStatus.ALLOWED,
        ),
        (
            "https://www.aspor.com.tr",
            CommercialUseStatus.UNKNOWN,
            RSSUsageStatus.ALLOWED,
        ),
        (
            "https://www.haberturk.com/spor",
            CommercialUseStatus.RESTRICTED,
            RSSUsageStatus.RESTRICTED,
        ),
        (
            "https://www.ntvspor.net/futbol",
            CommercialUseStatus.RESTRICTED,
            RSSUsageStatus.RESTRICTED,
        ),
        (
            "https://spor.example.com",
            CommercialUseStatus.UNKNOWN,
            RSSUsageStatus.UNKNOWN,
        ),
    ],
)
def test_classify_source_usage(
    url: str, commercial: CommercialUseStatus, rss: RSSUsageStatus
) -> None:
    policy = classify_source_usage(url, f"{url}/rss")
    assert policy.commercial_use_status == commercial
    assert policy.rss_usage_status == rss


def test_source_policy_block_and_warning_rules() -> None:
    assert source_policy_blocks_processing(
        CommercialUseStatus.PROHIBITED, RSSUsageStatus.ALLOWED
    )
    assert source_policy_blocks_processing(
        CommercialUseStatus.RESTRICTED, RSSUsageStatus.RESTRICTED
    )
    assert source_policy_warning(CommercialUseStatus.UNKNOWN, RSSUsageStatus.UNKNOWN)
    assert not source_policy_blocks_processing(
        CommercialUseStatus.RESTRICTED, RSSUsageStatus.ALLOWED
    )
