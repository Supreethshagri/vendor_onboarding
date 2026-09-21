"""Runs document extraction against every submission and saves the results
as fixtures, so tests never hit the API.

Run:  python build_fixtures.py
"""
from __future__ import annotations

import json
from pathlib import Path

from app.extract.documents import read_documents
from app.schemas.submission import VendorSubmission

ROOT = Path(__file__).resolve().parent
SUBS = ROOT / "data" / "submissions"
OUT = ROOT / "tests" / "fixtures"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for path in sorted(SUBS.glob("*.json")):
        sub = VendorSubmission.model_validate_json(path.read_text(encoding="utf-8"))
        facts, problems = read_documents(sub)
        (OUT / f"{sub.submission_id}.json").write_text(
            json.dumps(
                {"facts": facts.model_dump(), "problems": problems},
                indent=2, default=str,
            ),
            encoding="utf-8",
        )
        flag = " (problems)" if problems else ""
        print(f"{sub.submission_id}{flag}")


if __name__ == "__main__":
    main()