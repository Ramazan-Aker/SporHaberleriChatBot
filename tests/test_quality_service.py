import pytest

from app.services.quality_service import is_live_match_update


@pytest.mark.parametrize(
    "title",
    [
        "GOL | Orduspor 1967 8-0 Torul Belediye Spor",
        "PENALTI: Beşiktaş gole çok yaklaştı",
        "KIRMIZI KART | Ev sahibi 10 kişi kaldı",
        "İLK YARI: Beşiktaş 1-1 Rakibi",
        "CANLI | Galatasaray - Fenerbahçe",
    ],
)
def test_live_match_titles_are_detected(title: str) -> None:
    assert is_live_match_update(title)


def test_completed_match_article_is_not_filtered() -> None:
    assert not is_live_match_update("Maç sonucu: Beşiktaş rakibini 4-1 mağlup etti")
