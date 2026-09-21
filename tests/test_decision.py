from app.schemas.decision import Finding, Severity, Status, derive_status


def f(sev: Severity) -> Finding:
    return Finding(rule_id="t", severity=sev, message="x")


def test_empty_findings_approve():
    assert derive_status([]) is Status.APPROVED


def test_warn_only_still_approves():
    assert derive_status([f(Severity.WARN), f(Severity.INFO)]) is Status.APPROVED


def test_require_info_pends():
    assert derive_status([f(Severity.WARN), f(Severity.REQUIRE_INFO)]) is Status.PENDING_INFO


def test_review_outranks_require_info():
    findings = [f(Severity.REQUIRE_INFO), f(Severity.REVIEW)]
    assert derive_status(findings) is Status.NEEDS_REVIEW


def test_block_outranks_everything():
    findings = [f(Severity.REQUIRE_INFO), f(Severity.REVIEW), f(Severity.BLOCK)]
    assert derive_status(findings) is Status.REJECTED