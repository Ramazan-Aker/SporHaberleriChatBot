from app.integrations.rss.rss_client import (
    MAX_DESCRIPTION_LENGTH,
    clean_feed_description,
)


def test_clean_feed_description_removes_markup_and_unsafe_content() -> None:
    description = (
        "<p>Haber <strong>metni</strong></p>"
        "<script>window.alert('bad')</script><style>.hidden{}</style>"
    )

    assert clean_feed_description(description) == "Haber metni"


def test_clean_feed_description_limits_input_size() -> None:
    cleaned = clean_feed_description("kelime " * 300)

    assert cleaned is not None
    assert len(cleaned) <= MAX_DESCRIPTION_LENGTH
    assert cleaned.endswith("kelime")
