"""Processes every submission and saves the results.

Run:  python run_all.py
"""
from __future__ import annotations

from pathlib import Path

from app.db.store import save_decision, save_submission
from app.graph.pipeline import process
from app.schemas.submission import VendorSubmission

SUBS = Path(__file__).resolve().parent / "data" / "submissions"


def main() -> None:
    for path in sorted(SUBS.glob("*.json")):
        sub = VendorSubmission.model_validate_json(path.read_text(encoding="utf-8"))
        save_submission(sub)
        decision = process(sub)
        save_decision(decision)
        counts = {}
        for f in decision.findings:
            counts[f.severity.value] = counts.get(f.severity.value, 0) + 1
        summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "clean"
        print(f"{sub.submission_id:10} {decision.status.value:14} {summary}")


if __name__ == "__main__":
    main()