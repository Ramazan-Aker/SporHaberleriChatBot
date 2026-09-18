import pytest

from app.services.source_usage_policy import (
    SourceUsageStatus,
    classify_source_usage,
    source_is_approved_for_use,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.trthaber.com/spor", SourceUsageStatus.RSS_LINK_ONLY),
        ("https://www.aspor.com.tr", SourceUsageStatus.RSS_LINK_ONLY),
        (
            "https://www.haberturk.com/spor",
            SourceUsageStatus.PERMISSION_REQUIRED,
        ),
        (
            "https://www.ntvspor.net/futbol",
            SourceUsageStatus.PERMISSION_REQUIRED,
        ),
        (
            "https://www.transfermarkt.com.tr",
            SourceUsageStatus.PERMISSION_REQUIRED,
        ),
        ("https://spor.example.com", SourceUsageStatus.UNREVIEWED),
    ],
)
def test_classify_source_usage(url: str, expected: SourceUsageStatus) -> None:
    assert classify_source_usage(url, f"{url}/rss").status == expected


def test_classify_source_usage_matches_subdomains() -> None:
    policy = classify_source_usage(
        "https://spor.haberturk.com", "https://feeds.haberturk.com/spor.xml"
    )

    assert policy.status == SourceUsageStatus.PERMISSION_REQUIRED


def test_only_reviewed_rss_link_sources_are_approved() -> None:
    assert source_is_approved_for_use(
        "https://www.trthaber.com/spor",
        "https://www.trthaber.com/spor_articles.rss",
    )
    assert not source_is_approved_for_use(
        "https://spor.example.com", "https://spor.example.com/rss.xml"
    )
