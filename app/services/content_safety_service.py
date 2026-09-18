from dataclasses import dataclass
from difflib import SequenceMatcher

from app.services.duplicate_detector import normalize_title


@dataclass(frozen=True, slots=True)
class SimilarityResult:
    score: float
    title_score: float
    summary_score: float
    safe: bool


class ContentSafetyService:
    def __init__(self, max_similarity: float = 0.55) -> None:
        self.max_similarity = max_similarity

    @staticmethod
    def _score(first: str, second: str) -> float:
        normalized_first = normalize_title(first)
        normalized_second = normalize_title(second)
        if not normalized_first or not normalized_second:
            return 0.0
        sequence = SequenceMatcher(
            None, normalized_first, normalized_second, autojunk=False
        ).ratio()
        first_tokens = set(normalized_first.split())
        second_tokens = set(normalized_second.split())
        union = first_tokens | second_tokens
        jaccard = len(first_tokens & second_tokens) / len(union) if union else 0.0
        return max(sequence, jaccard)

    def evaluate(
        self, *, generated_text: str, source_title: str, source_summary: str | None
    ) -> SimilarityResult:
        title_score = self._score(generated_text, source_title)
        summary_score = self._score(generated_text, source_summary or "")
        score = max(title_score, summary_score)
        return SimilarityResult(
            score=score,
            title_score=title_score,
            summary_score=summary_score,
            safe=score <= self.max_similarity,
        )
