from app.models.source import Source


class CredibilityService:
    def calculate(self, source: Source) -> int:
        return source.credibility_score
