from enum import Enum

from pydantic import BaseModel, Field, model_validator

_TRIM_MAX_MS: int = 30_000  # 30-second hard cap on trim window


class ThrowType(str, Enum):
    backhand = "backhand"
    forehand = "forehand"
    unknown = "unknown"


class CameraPerspective(str, Enum):
    front = "front"
    back = "back"
    side_facing = "side_facing"
    side_away = "side_away"
    unknown = "unknown"


class TrimRange(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_range(self) -> "TrimRange":
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        if self.end_ms - self.start_ms > _TRIM_MAX_MS:
            raise ValueError(
                f"Trim window must not exceed {_TRIM_MAX_MS // 1000} seconds"
            )
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
    upload_id: str = Field(max_length=36)
    trim: TrimRange
    throw_type: ThrowType
    camera_perspective: CameraPerspective


class ThrowPhase(BaseModel):
    name: str
    timestamp_ms: int
    observations: list[str]
    recommendations: list[str]


class CritiqueResponse(BaseModel):
    overall_score: str
    summary: str
    throw_type: ThrowType
    phases: list[ThrowPhase]
    key_focus: str
    camera_perspective: CameraPerspective


class AnalyzeResponse(BaseModel):
    clip_id: str
    critique: CritiqueResponse
