from __future__ import annotations

from app.config import settings
from app.extract.llm import client
from app.schemas.decision import Finding, Severity, Status
from app.schemas.submission import VendorSubmission

# Severities the vendor is allowed to hear about.
VENDOR_VISIBLE = {Severity.REQUIRE_INFO, Severity.WARN}

SYSTEM = """You write short, polite emails to vendors on behalf of a company's
procurement team in India.

Rules:
- Use only the points given. Never invent a reason or add a requirement.
- Do not mention internal terms: checksum, similarity score, rule, severity,
  fraud, risk, review queue.
- Plain text. No markdown, no subject line, no placeholders in brackets.
- Under 140 words. Greeting, one line of context, the numbered points, one
  closing line.
"""

REVIEW_HOLDING = (
    "Thank you for your submission. Your details are with our procurement team "
    "for verification. We will contact you once the review is complete."
)


def draft_vendor_message(
    sub: VendorSubmission, status: Status, findings: list[Finding]
) -> str | None:
    if status is Status.APPROVED:
        return None

    if status in (Status.NEEDS_REVIEW, Status.REJECTED):
        return REVIEW_HOLDING

    points = [
        f.remedy for f in findings
        if f.severity in VENDOR_VISIBLE and f.remedy
    ]
    if not points:
        return REVIEW_HOLDING

    numbered = "\n".join(f"{i}. {p}" for i, p in enumerate(points, 1))
    company = sub.legal_name or "your organisation"

    resp = client().chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Vendor: {company}\n"
                    f"Contact: {sub.contact.name or 'Sir/Madam'}\n\n"
                    f"Points to communicate:\n{numbered}"
                ),
            },
        ],
        temperature=0.3,
        max_tokens=1200,
    )
    choice = resp.choices[0]
    if choice.finish_reason == "length":
        return REVIEW_HOLDING

    text = (choice.message.content or "").strip()
    return text or REVIEW_HOLDING