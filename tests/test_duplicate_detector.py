from app.services.duplicate_detector import make_content_hash, normalize_title


def test_normalize_title_handles_turkish_case_punctuation_and_spaces() -> None:
    assert normalize_title("  İLK 11: GALATASARAY!  ") == "ilk 11 galatasaray"
    assert normalize_title("IŞIK---spor") == "ışık spor"


def test_equivalent_titles_have_same_hash() -> None:
    left = make_content_hash("Transfer: görüşmeler sürüyor!")
    right = make_content_hash("transfer   görüşmeler sürüyor")
    assert left == right
    assert len(left) == 64
