from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EventType(StrEnum):
    TRANSFER = "transfer"
    TRANSFER_RUMOR = "transfer_rumor"
    OFFICIAL_TRANSFER = "official_transfer"
    INJURY = "injury"
    MATCH_RESULT = "match_result"
    LINEUP = "lineup"
    STATEMENT = "statement"
    STATISTICS = "statistics"
    DISCIPLINARY = "disciplinary"
    BREAKING_NEWS = "breaking_news"
    GENERAL = "general"


class ClaimCertainty(StrEnum):
    CONFIRMED = "confirmed"
    REPORTED = "reported"
    RUMOR = "rumor"
    UNKNOWN = "unknown"


class FactClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=500)
    certainty: ClaimCertainty


class FactEntities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team: str | None
    player: str | None
    other_team: str | None
    person: str | None
    organization: str | None
    opponent: str | None
    competition: str | None


class FactNumbers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fee: str | None
    currency: str | None
    contract_years: str | None
    goals: str | None
    assists: str | None
    score: str | None
    minute: str | None
    date: str | None
    age: str | None


class ExtractedFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    entities: FactEntities
    facts: list[str] = Field(min_length=1, max_length=12)
    claims: list[FactClaim] = Field(max_length=12)
    numbers: FactNumbers
    official: bool
    confidence: float = Field(ge=0, le=1)


class ClaimValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    unsupported_claims: list[str] = Field(max_length=10)
    confidence: float = Field(ge=0, le=1)
