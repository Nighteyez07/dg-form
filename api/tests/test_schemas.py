"""
Unit tests for all Pydantic models defined in models/schemas.py.
No I/O, no HTTP — pure validation logic.
"""

import pytest
from pydantic import ValidationError

from models.schemas import (
    AnalyzeRequest,
    CritiqueResponse,
    ThrowPhase,
    TrimRange,
)


# ---------------------------------------------------------------------------
# TrimRange
# ---------------------------------------------------------------------------

def test_trim_range_valid() -> None:
    t = TrimRange(start_ms=0, end_ms=1000)
    assert t.start_ms == 0
    assert t.end_ms == 1000


def test_trim_range_negative_start_raises() -> None:
    with pytest.raises(ValidationError):
        TrimRange(start_ms=-1, end_ms=1000)


def test_trim_range_negative_end_raises() -> None:
    with pytest.raises(ValidationError):
        TrimRange(start_ms=0, end_ms=-1)


def test_trim_range_equal_start_end_raises() -> None:
    with pytest.raises(ValidationError):
        TrimRange(start_ms=1000, end_ms=1000)


def test_trim_range_end_less_than_start_raises() -> None:
    with pytest.raises(ValidationError):
        TrimRange(start_ms=2000, end_ms=1000)


# ---------------------------------------------------------------------------
# AnalyzeRequest
# ---------------------------------------------------------------------------

def test_analyze_request_valid_round_trips() -> None:
    req = AnalyzeRequest(
        upload_id="c2a1b3d4-e5f6-7890-abcd-ef1234567890",
        trim=TrimRange(start_ms=0, end_ms=1000),
    )
    assert req.upload_id == "c2a1b3d4-e5f6-7890-abcd-ef1234567890"
    assert req.trim.start_ms == 0
    assert req.trim.end_ms == 1000


# ---------------------------------------------------------------------------
# CritiqueResponse
# ---------------------------------------------------------------------------

def test_critique_response_valid_backhand() -> None:
    c = CritiqueResponse(
        overall_score="8/10",
        summary="Solid throw with good mechanics.",
        throw_type="backhand",
        phases=[],
        key_focus="Follow through",
    )
    assert c.throw_type == "backhand"


def test_critique_response_invalid_throw_type_raises() -> None:
    with pytest.raises(ValidationError):
        CritiqueResponse(
            overall_score="7/10",
            summary="Decent form.",
            throw_type="sidearm",  # not a valid Literal
            phases=[],
            key_focus="Hip rotation",
        )


# ---------------------------------------------------------------------------
# ThrowPhase
# ---------------------------------------------------------------------------

def test_throw_phase_valid_with_empty_lists() -> None:
    phase = ThrowPhase(
        name="Release",
        timestamp_ms=2500,
        observations=[],
        recommendations=[],
    )
    assert phase.observations == []
    assert phase.recommendations == []
