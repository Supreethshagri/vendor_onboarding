from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from app.config import settings
from app.schemas.decision import Decision
from app.schemas.submission import VendorSubmission


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """Supabase's transaction pooler doesn't support prepared statements,
    so they're disabled."""
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set")
    conn = psycopg.connect(
        settings.database_url, row_factory=dict_row, prepare_threshold=None
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_submission(sub: VendorSubmission) -> None:
    with connect() as conn:
        conn.execute(
            """
            insert into submissions
                (submission_id, submitted_at, legal_name, gstin, pan, payload)
            values (%s, %s, %s, %s, %s, %s)
            on conflict (submission_id) do update set
                submitted_at = excluded.submitted_at,
                legal_name   = excluded.legal_name,
                gstin        = excluded.gstin,
                pan          = excluded.pan,
                payload      = excluded.payload
            """,
            (
                sub.submission_id, sub.submitted_at, sub.legal_name,
                sub.gstin, sub.pan, json.dumps(sub.model_dump(mode="json")),
            ),
        )


def save_decision(decision: Decision) -> int:
    """Returns the new decision's id."""
    with connect() as conn:
        row = conn.execute(
            """
            insert into decisions
                (submission_id, status, vendor_message, trace, decided_at)
            values (%s, %s, %s, %s, %s)
            returning id
            """,
            (
                decision.submission_id,
                decision.status.value,
                decision.vendor_message,
                json.dumps([e.model_dump(mode="json") for e in decision.trace]),
                decision.decided_at,
            ),
        ).fetchone()
        decision_id = row["id"]

        if decision.findings:
            conn.cursor().executemany(
                """
                insert into findings
                    (decision_id, rule_id, severity, field, message, remedy, detail)
                values (%s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (decision_id, f.rule_id, f.severity.value, f.field,
                     f.message, f.remedy, json.dumps(f.detail))
                    for f in decision.findings
                ],
            )
        return decision_id

def latest_decision(submission_id: str) -> dict | None:
    with connect() as conn:
        d = conn.execute(
            """
            select * from decisions
            where submission_id = %s
            order by decided_at desc, id desc
            limit 1
            """,
            (submission_id,),
        ).fetchone()
        if d is None:
            return None
        d["findings"] = conn.execute(
            "select * from findings where decision_id = %s order by id",
            (d["id"],),
        ).fetchall()
        return d


def list_submissions(limit: int = 100) -> list[dict]:
    with connect() as conn:
        return conn.execute(
            """
            select
                s.submission_id,
                s.legal_name,
                s.gstin,
                d.status,
                d.decided_at
            from submissions s
            left join lateral (
                select status, decided_at
                from decisions
                where submission_id = s.submission_id
                order by decided_at desc, id desc
                limit 1
            ) d on true
            order by s.created_at desc
            limit %s
            """,
            (limit,),
        ).fetchall()


def rule_frequency() -> list[dict]:
    """Which checks actually fire. Useful in the writeup."""
    with connect() as conn:
        return conn.execute(
            """
            select rule_id, severity, count(*) as hits
            from findings
            group by rule_id, severity
            order by hits desc
            """
        ).fetchall()