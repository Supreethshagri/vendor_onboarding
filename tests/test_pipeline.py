import json
from pathlib import Path

import pytest

from app.checks.cross_reference import run_checks
from app.schemas.decision import Severity, derive_status
from app.schemas.documents import DocumentFacts
from app.schemas.submission import VendorSubmission

ROOT = Path(__file__).resolve().parents[1]
SUBS = ROOT / "data" / "submissions"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLDEN = json.loads((ROOT / "data" / "golden.json").read_text(encoding="utf-8"))


def load_case(sid: str) -> tuple[VendorSubmission, DocumentFacts]:
    sub = VendorSubmission.model_validate_json(
        (SUBS / f"{sid}.json").read_text(encoding="utf-8")
    )
    fixture = json.loads((FIXTURES / f"{sid}.json").read_text(encoding="utf-8"))
    return sub, DocumentFacts.model_validate(fixture["facts"])


def describe(findings) -> str:
    if not findings:
        return "    (no findings)"
    return "\n".join(
        f"    [{f.severity.value}] {f.rule_id}: {f.message}" for f in findings
    )


@pytest.mark.parametrize("sid", sorted(GOLDEN))
def test_golden_verdicts(sid):
    sub, docs = load_case(sid)
    findings = run_checks(sub, docs)
    status = derive_status(findings)

    assert status.value == GOLDEN[sid]["expect"], (
        f"\n{sid}: expected {GOLDEN[sid]['expect']}, got {status.value}"
        f"\n  Case: {GOLDEN[sid]['why']}"
        f"\n  Findings:\n{describe(findings)}"
    )

def rule_ids(sid: str) -> set[str]:
    sub, docs = load_case(sid)
    return {f.rule_id for f in run_checks(sub, docs)}


def test_edge1_pan_mismatch_is_the_blocking_rule():
    sub, docs = load_case("SUB-003")
    findings = run_checks(sub, docs)
    blocking = [f for f in findings if f.severity is Severity.BLOCK]
    assert [f.rule_id for f in blocking] == ["xref.pan_in_gstin"]
    # The GSTIN itself is structurally valid — only the cross-reference fails.
    assert "gstin.checksum" not in rule_ids("SUB-003")


def test_edge2_personal_account_depends_on_entity_type():
    assert "xref.bank_holder" in rule_ids("SUB-004")   # company → review
    assert "xref.bank_holder" not in rule_ids("SUB-002")  # proprietor → fine


def test_edge3_certificate_state_mismatch():
    sub, docs = load_case("SUB-005")
    assert docs.gst_certificate is not None
    assert docs.gst_certificate.gstin.startswith("27")   # Maharashtra
    assert sub.gstin.startswith("29")                    # Karnataka
    assert "xref.cert_gstin" in rule_ids("SUB-005")


def test_edge4_malformed_udyam_warns_but_approves():
    sub, docs = load_case("SUB-006")
    findings = run_checks(sub, docs)
    msme = [f for f in findings if f.rule_id == "msme.format"]
    assert len(msme) == 1
    assert msme[0].severity is Severity.WARN
    assert derive_status(findings).value == "approved"


def test_checksum_failure_blocks():
    assert "gstin.checksum" in rule_ids("SUB-008")


def test_every_vendor_facing_finding_has_a_remedy():
    """A REQUIRE_INFO with no remedy would produce an empty vendor message."""
    missing = []
    for sid in GOLDEN:
        sub, docs = load_case(sid)
        for f in run_checks(sub, docs):
            if f.severity is Severity.REQUIRE_INFO and not f.remedy:
                missing.append(f"{sid}: {f.rule_id}")
    assert not missing, f"REQUIRE_INFO findings without a remedy: {missing}"