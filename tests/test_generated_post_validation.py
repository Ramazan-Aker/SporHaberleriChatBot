import pytest
from pydantic import ValidationError

from app.schemas.generated_post import GeneratedPostValidation


def test_post_text_is_trimmed_and_validated() -> None:
    result = GeneratedPostValidation(text="  Hazır gönderi  ", max_length=20)
    assert result.text == "Hazır gönderi"


@pytest.mark.parametrize("text", ["", "   ", "x" * 11])
def test_invalid_post_text_is_rejected(text: str) -> None:
    with pytest.raises(ValidationError):
        GeneratedPostValidation(text=text, max_length=10)
