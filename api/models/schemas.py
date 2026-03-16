from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TrimRange(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_range(self) -> "TrimRange":
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class SuggestedTrim(BaseModel):
    start_ms: int
    end_ms: int


class UploadResponse(BaseModel):
    upload_id: str
    duration_ms: int
    suggested_trim: SuggestedTrim
    low_confidence: bool


class AnalyzeRequest(BaseModel):
    upload_id: str
    trim: TrimRange


class ThrowPhase(BaseModel):
    name: str
    timestamp_ms: int
    observations: list[str]
    recommendations: list[str]


class CritiqueResponse(BaseModel):
    overall_score: str
    summary: str
    throw_type: Literal["backhand", "forehand", "unknown"]
    phases: list[ThrowPhase]
    key_focus: str


class AnalyzeResponse(BaseModel):
    clip_id: str
    critique: CritiqueResponse
