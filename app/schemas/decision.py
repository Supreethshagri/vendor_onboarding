from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class Severity(str, Enum):
    BLOCK = "block"                # disqualifying — cannot onboard
    REVIEW = "review"              # suspicious — a human must look
    REQUIRE_INFO = "require_info"  # fixable — ask the vendor
    WARN = "warn"                  # noted, does not stop onboarding
    INFO = "info"


class Status(str, Enum):
    APPROVED = "approved"
    PENDING_INFO = "pending_info"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


class Finding(BaseModel):
    rule_id: str                   # e.g. "gstin.checksum", "xref.pan_mismatch"
    severity: Severity
    field: str | None = None       # which submission field it concerns
    message: str                   # internal, precise
    remedy: str | None = None      # what the vendor should do about it
    detail: dict[str, Any] = {}


class AuditEvent(BaseModel):
    step: str
    at: datetime
    duration_ms: int
    summary: str
    detail: dict[str, Any] = {}


class Decision(BaseModel):
    submission_id: str
    status: Status
    findings: list[Finding]
    vendor_message: str | None = None   # only when status != APPROVED
    trace: list[AuditEvent]
    decided_at: datetime


# Precedence: worst outcome wins.
_PRECEDENCE: list[tuple[Severity, Status]] = [
    (Severity.BLOCK, Status.REJECTED),
    (Severity.REVIEW, Status.NEEDS_REVIEW),
    (Severity.REQUIRE_INFO, Status.PENDING_INFO),
]


def derive_status(findings: list[Finding]) -> Status:
    """Status is computed from findings. Nothing else may set it."""
    present = {f.severity for f in findings}
    for severity, status in _PRECEDENCE:
        if severity in present:
            return status
    return Status.APPROVED