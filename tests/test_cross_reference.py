import json
from pathlib import Path

import pytest

from app.checks.cross_reference import run_checks
from app.schemas.decision import derive_status
from app.schemas.submission import VendorSubmission

ROOT = Path(__file__).resolve().parents[1]
SUBS = ROOT / "data" / "submissions"

# Cases decidable from form fields alone, without reading documents.
FORM_ONLY = {
    "SUB-001": "approved",
    "SUB-002": "approved",
    "SUB-003": "rejected",       # PAN inside GSTIN
    "SUB-004": "needs_review",   # personal account, company entity
    "SUB-006": "approved",       # malformed Udyam, warning only
    "SUB-007": "pending_info",   # missing cheque + blank IFSC
    "SUB-008": "rejected",       # bad checksum
    "SUB-009": "approved",       # abbreviated holder name
}


def load(sid: str) -> VendorSubmission:
    return VendorSubmission.model_validate_json(
        (SUBS / f"{sid}.json").read_text(encoding="utf-8")
    )


@pytest.mark.parametrize("sid,expected", FORM_ONLY.items())
def test_form_only_verdicts(sid, expected):
    findings = run_checks(load(sid))
    status = derive_status(findings)
    assert status.value == expected, (
        f"{sid}: expected {expected}, got {status.value}\n"
        + "\n".join(f"  [{f.severity.value}] {f.rule_id}: {f.message}" for f in findings)
    )


def test_pan_in_gstin_is_the_blocking_rule():
    findings = run_checks(load("SUB-003"))
    blocking = [f.rule_id for f in findings if f.severity.value == "block"]
    assert blocking == ["xref.pan_in_gstin"]