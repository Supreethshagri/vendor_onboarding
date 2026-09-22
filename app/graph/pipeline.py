from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph

from app.checks.cross_reference import run_checks
from app.extract.documents import read_documents
from app.schemas.decision import (
    AuditEvent, Decision, Finding, Severity, Status, derive_status,
)
from app.schemas.documents import DocumentFacts
from app.schemas.submission import VendorSubmission


def append(a: list, b: list) -> list:
    return a + b


class State(TypedDict, total=False):
    submission: VendorSubmission
    doc_facts: DocumentFacts
    findings: Annotated[list[Finding], append]
    trace: Annotated[list[AuditEvent], append]
    status: Status
    vendor_message: str | None


def _event(step: str, started: float, summary: str, **detail) -> AuditEvent:
    return AuditEvent(
        step=step,
        at=datetime.now(timezone.utc),
        duration_ms=int((time.perf_counter() - started) * 1000),
        summary=summary,
        detail=detail,
    )


def node_read_documents(state: State) -> State:
    t = time.perf_counter()
    sub = state["submission"]
    facts, problems = read_documents(sub)

    findings = [
        Finding(
            rule_id="doc.unreadable", severity=Severity.REQUIRE_INFO,
            field="documents", message=p,
            remedy="We could not read one of your uploaded documents. Please "
                   "re-upload it as a clear PDF.",
        )
        for p in problems
    ]

    read = [k for k, v in facts.model_dump().items() if v]
    return {
        "doc_facts": facts,
        "findings": findings,
        "trace": [_event("read_documents", t,
                         f"Read {len(read)} of {len(sub.documents)} documents.",
                         documents_read=read, problems=problems)],
    }


def node_run_checks(state: State) -> State:
    t = time.perf_counter()
    findings = run_checks(state["submission"], state.get("doc_facts"))
    by_sev: dict[str, int] = {}
    for f in findings:
        by_sev[f.severity.value] = by_sev.get(f.severity.value, 0) + 1
    return {
        "findings": findings,
        "trace": [_event("run_checks", t,
                         f"{len(findings)} findings across "
                         f"{len(by_sev)} severity levels.",
                         by_severity=by_sev,
                         rules_fired=[f.rule_id for f in findings])],
    }


def node_decide(state: State) -> State:
    t = time.perf_counter()
    status = derive_status(state.get("findings", []))
    return {
        "status": status,
        "trace": [_event("decide", t, f"Status: {status.value}.",
                         status=status.value)],
    }


def node_vendor_message(state: State) -> State:
    from app.extract.messages import draft_vendor_message

    t = time.perf_counter()
    msg = draft_vendor_message(
        state["submission"], state["status"], state.get("findings", [])
    )
    return {
        "vendor_message": msg,
        "trace": [_event("vendor_message", t, "Drafted message to vendor.")],
    }


def _needs_message(state: State) -> str:
    return "draft" if state["status"] is not Status.APPROVED else "done"


def build_graph():
    g = StateGraph(State)
    g.add_node("read_documents", node_read_documents)
    g.add_node("run_checks", node_run_checks)
    g.add_node("decide", node_decide)
    g.add_node("draft_message", node_vendor_message)

    g.set_entry_point("read_documents")
    g.add_edge("read_documents", "run_checks")
    g.add_edge("run_checks", "decide")
    g.add_conditional_edges("decide", _needs_message,
                            {"draft": "draft_message", "done": END})
    g.add_edge("draft_message", END)
    return g.compile()


_graph = None


def process(sub: VendorSubmission) -> Decision:
    global _graph
    if _graph is None:
        _graph = build_graph()

    final = _graph.invoke({"submission": sub, "findings": [], "trace": []})

    return Decision(
        submission_id=sub.submission_id,
        status=final["status"],
        findings=final.get("findings", []),
        vendor_message=final.get("vendor_message"),
        trace=final.get("trace", []),
        decided_at=datetime.now(timezone.utc),
    )