from app.models.source import Source, SourceType
from app.services.credibility_service import CredibilityService


def test_article_credibility_starts_from_source() -> None:
    source = Source(
        name="Official",
        url="https://example.com",
        rss_url="https://example.com/feed",
        category="football",
        source_type=SourceType.OFFICIAL,
        credibility_score=10,
        active=True,
    )
    assert CredibilityService().calculate(source) == 10
