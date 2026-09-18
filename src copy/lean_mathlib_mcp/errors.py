"""Structured error model (spec 5.2 / 6).

Errors are never free-form prose. Every failure returns an error *code*, a
machine-actionable ``fixable`` flag, optional disambiguation candidates, and
concrete ``suggested_params`` the caller can feed straight back into a retry.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class ErrorCode(str, Enum):
    OK = "ok"
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGUMENT = "invalid_argument"
    AMBIGUOUS_MATCH = "ambiguous_match"
    NO_MATCH = "no_match"
    NOT_FOUND = "not_found"
    INDEX_UNAVAILABLE = "index_unavailable"
    ENRICHMENT_UNAVAILABLE = "enrichment_unavailable"
    OUT_OF_SCOPE = "out_of_scope"
    INTERNAL = "internal"


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: ErrorCode
    message: str                         # short, no stack traces, no prose essay
    fixable: bool = True                 # True => caller can retry with suggested_params
    disambiguation: List[Dict[str, Any]] = []
    suggested_params: Dict[str, Any] = {}
    negative_feedback: Optional[Dict[str, Any]] = None  # on NO_MATCH: relaxation hints


def make_error(
    code: ErrorCode,
    message: str,
    *,
    fixable: bool = True,
    disambiguation: Optional[List[Dict[str, Any]]] = None,
    suggested_params: Optional[Dict[str, Any]] = None,
    negative_feedback: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a JSON-serializable structured error envelope."""
    err = ErrorDetail(
        code=code,
        message=message,
        fixable=fixable,
        disambiguation=disambiguation or [],
        suggested_params=suggested_params or {},
        negative_feedback=negative_feedback,
    )
    return err.model_dump(exclude_none=True)


def negative_feedback_hint(relax: Dict[str, Any]) -> Dict[str, Any]:
    """Standard 'no match' relaxation guidance (spec 6 negative-result feedback)."""
    return {
        "reason": "no matching entity for the given query",
        "relax_suggestions": relax,
    }
