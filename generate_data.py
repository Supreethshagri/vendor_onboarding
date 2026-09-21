"""Generates synthetic vendor submissions and their supporting documents.

Documents are digital PDFs with a real text layer — no OCR needed.
Run:  python generate_data.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.checks.gst import make_gstin

ROOT = Path(__file__).resolve().parent
SUBS = ROOT / "data" / "submissions"
DOCS = ROOT / "data" / "documents"

W, H = A4


def _page(c: canvas.Canvas, title: str, rows: list[tuple[str, str]], footer: str = ""):
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, H - 25 * mm, title)
    c.setFont("Helvetica", 10)
    y = H - 40 * mm
    for label, value in rows:
        c.drawString(20 * mm, y, f"{label}:")
        c.drawString(75 * mm, y, str(value))
        y -= 7 * mm
    if footer:
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(20 * mm, 20 * mm, footer)
    c.showPage()
    c.save()


def gst_certificate(path: Path, *, gstin, legal_name, trade_name, address, state, valid_from):
    _page(
        canvas.Canvas(str(path), pagesize=A4),
        "FORM GST REG-06 - Registration Certificate",
        [
            ("Registration Number", gstin),
            ("Legal Name", legal_name),
            ("Trade Name", trade_name or "-"),
            ("Constitution of Business", "As per PAN"),
            ("Address of Principal Place", address),
            ("State", state),
            ("Date of Liability", valid_from),
            ("Type of Registration", "Regular"),
        ],
        "System generated certificate. Synthetic document for testing.",
    )


def cancelled_cheque(path: Path, *, holder, account_number, ifsc, bank_name, branch):
    _page(
        canvas.Canvas(str(path), pagesize=A4),
        f"{bank_name} - CANCELLED CHEQUE",
        [
            ("Account Holder", holder),
            ("Account Number", account_number),
            ("IFSC Code", ifsc),
            ("Branch", branch),
            ("MICR", "560240011"),
        ],
        "CANCELLED. Synthetic document for testing.",
    )


def pan_card(path: Path, *, pan, name, father_or_entity):
    _page(
        canvas.Canvas(str(path), pagesize=A4),
        "INCOME TAX DEPARTMENT - Permanent Account Number",
        [
            ("Permanent Account Number", pan),
            ("Name", name),
            ("Father's Name / Entity", father_or_entity),
            ("Date of Incorporation", "14/06/2019"),
        ],
        "Synthetic document for testing.",
    )

KA, MH = "29", "27"

CASES: list[dict] = [
    {
        "id": "SUB-001",
        "expect": "approved",
        "why": "Happy path. Company, everything consistent.",
        "pan": "AABCU9603R",
        "gstin_state": KA,
        "form": {
            "legal_name": "Shagri Technologies Private Limited",
            "trade_name": "Shagri Tech",
            "state": "Karnataka",
            "holder": "SHAGRI TECHNOLOGIES PRIVATE LIMITED",
            "ifsc": "HDFC0001234",
            "msme": "UDYAM-KR-03-0012345",
        },
    },
    {
        "id": "SUB-002",
        "expect": "approved",
        "why": "Proprietorship. Personal bank account is legitimate here.",
        "pan": "AAAPU7788K",
        "gstin_state": KA,
        "form": {
            "legal_name": "Supreeth B M",
            "trade_name": "Kaveri Traders",
            "state": "Karnataka",
            "holder": "SUPREETH B M",
            "ifsc": "SBIN0007788",
            "msme": "UDYAM-KR-03-0099887",
        },
    },
    {
        "id": "SUB-003",
        "expect": "rejected",
        "why": "EDGE 1. GSTIN valid, PAN valid, names match — but the PAN "
               "embedded in the GSTIN belongs to a different entity.",
        "pan": "AAFCS5566L",
        "gstin_pan": "AABCU9603R",          # GSTIN built from a different PAN
        "gstin_state": KA,
        "form": {
            "legal_name": "Nandi Supply Chain Private Limited",
            "trade_name": "Nandi Supply",
            "state": "Karnataka",
            "holder": "NANDI SUPPLY CHAIN PRIVATE LIMITED",
            "ifsc": "ICIC0004455",
            "msme": "UDYAM-KR-03-0044556",
        },
    },
    {
        "id": "SUB-004",
        "expect": "needs_review",
        "why": "EDGE 2. Company entity, but funds would go to an individual.",
        "pan": "AADCK1122M",
        "gstin_state": KA,
        "form": {
            "legal_name": "Kaveri Industrial Works Private Limited",
            "trade_name": "Kaveri Works",
            "state": "Karnataka",
            "holder": "RAMESH KUMAR N",
            "ifsc": "AXIS0001122",
            "msme": "UDYAM-KR-03-0011223",
        },
    },
    {
        "id": "SUB-005",
        "expect": "pending_info",
        "why": "EDGE 3. Certificate is a Maharashtra registration, form claims "
               "Karnataka. Both real, inconsistent together.",
        "pan": "AAGCT3344N",
        "gstin_state": KA,
        "cert_gstin_state": MH,              # certificate disagrees
        "form": {
            "legal_name": "Tungabhadra Components Private Limited",
            "trade_name": "Tunga Components",
            "state": "Karnataka",
            "holder": "TUNGABHADRA COMPONENTS PRIVATE LIMITED",
            "ifsc": "KKBK0003344",
            "msme": "UDYAM-KR-03-0033445",
        },
    },
    {
        "id": "SUB-006",
        "expect": "approved",
        "why": "EDGE 4. Malformed Udyam number. Affects payment terms under "
               "MSMED, not legitimacy. Warning only.",
        "pan": "AAHCP6677Q",
        "gstin_state": KA,
        "form": {
            "legal_name": "Pushpagiri Packaging Private Limited",
            "trade_name": "Pushpagiri Pack",
            "state": "Karnataka",
            "holder": "PUSHPAGIRI PACKAGING PRIVATE LIMITED",
            "ifsc": "UTIB0006677",
            "msme": "KR-0012345",            # wrong format
        },
    },
    {
        "id": "SUB-007",
        "expect": "pending_info",
        "why": "Ordinary incompleteness. No cheque uploaded, IFSC blank.",
        "pan": "AABCM2233R",
        "gstin_state": KA,
        "skip_docs": ["cancelled_cheque"],
        "form": {
            "legal_name": "Malnad Fabricators Private Limited",
            "trade_name": "Malnad Fab",
            "state": "Karnataka",
            "holder": "MALNAD FABRICATORS PRIVATE LIMITED",
            "ifsc": None,
            "msme": "UDYAM-KR-03-0022334",
        },
    },
    {
        "id": "SUB-008",
        "expect": "rejected",
        "why": "GSTIN passes the format check, fails the checksum. Fabricated.",
        "pan": "AABCH4455T",
        "gstin_state": KA,
        "tamper_checksum": True,
        "form": {
            "legal_name": "Hemavathi Logistics Private Limited",
            "trade_name": "Hemavathi Logistics",
            "state": "Karnataka",
            "holder": "HEMAVATHI LOGISTICS PRIVATE LIMITED",
            "ifsc": "YESB0004455",
            "msme": "UDYAM-KR-03-0055667",
        },
    },
    {
        "id": "SUB-009",
        "expect": "approved",
        "why": "Bank holder is an abbreviation of the legal name. Cosmetic, "
               "not suspicious.",
        "pan": "AABCV8899W",
        "gstin_state": KA,
        "form": {
            "legal_name": "Vidyaranya Electricals Private Limited",
            "trade_name": "Vidyaranya",
            "state": "Karnataka",
            "holder": "VIDYARANYA ELECTRICALS",
            "ifsc": "IDIB0008899",
            "msme": "UDYAM-KR-03-0088990",
        },
    },
    {
        "id": "SUB-010",
        "expect": "needs_review",
        "why": "Cheque IFSC differs from the form. Typo or account swap — "
               "a human decides.",
        "pan": "AABCB1177X",
        "gstin_state": KA,
        "cheque_ifsc": "HDFC0009999",        # document disagrees with form
        "form": {
            "legal_name": "Baragi Chemicals Private Limited",
            "trade_name": "Baragi Chem",
            "state": "Karnataka",
            "holder": "BARAGI CHEMICALS PRIVATE LIMITED",
            "ifsc": "HDFC0001177",
            "msme": "UDYAM-KR-03-0011771",
        },
    },
]

def build() -> None:
    for d in (SUBS, DOCS):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    golden = {}

    for case in CASES:
        sid, form = case["id"], case["form"]

        gstin = make_gstin(case["gstin_state"], case.get("gstin_pan", case["pan"]))
        if case.get("tamper_checksum"):
            gstin = gstin[:14] + ("A" if gstin[14] != "A" else "B")

        cert_gstin = (
            make_gstin(case["cert_gstin_state"], case["pan"])
            if case.get("cert_gstin_state") else gstin
        )

        skip = set(case.get("skip_docs", []))
        docs = []

        if "gst_certificate" not in skip:
            p = DOCS / f"{sid}_gst_certificate.pdf"
            gst_certificate(
                p, gstin=cert_gstin, legal_name=form["legal_name"],
                trade_name=form["trade_name"],
                address=f"12 Industrial Layout, {form['state']}",
                state=form["state"], valid_from="01/07/2021",
            )
            docs.append({"type": "gst_certificate", "filename": p.name, "path": str(p)})

        if "cancelled_cheque" not in skip:
            p = DOCS / f"{sid}_cancelled_cheque.pdf"
            cancelled_cheque(
                p, holder=form["holder"],
                account_number=f"50100{sid[-3:]}887766",
                ifsc=case.get("cheque_ifsc") or form["ifsc"] or "HDFC0001234",
                bank_name="HDFC Bank", branch="Rajajinagar, Bengaluru",
            )
            docs.append({"type": "cancelled_cheque", "filename": p.name, "path": str(p)})

        if "pan_card" not in skip:
            p = DOCS / f"{sid}_pan_card.pdf"
            pan_card(p, pan=case["pan"], name=form["legal_name"],
                     father_or_entity=form["legal_name"])
            docs.append({"type": "pan_card", "filename": p.name, "path": str(p)})

        submission = {
            "submission_id": sid,
            "submitted_at": "2026-09-15",
            "legal_name": form["legal_name"],
            "trade_name": form["trade_name"],
            "gstin": gstin,
            "pan": case["pan"],
            "msme_udyam": form["msme"],
            "registered_address": {
                "line1": "12 Industrial Layout",
                "city": "Bengaluru",
                "state": form["state"],
                "pincode": "560010",
            },
            "bank": {
                "account_holder_name": form["holder"],
                "account_number": f"50100{sid[-3:]}887766",
                "ifsc": form["ifsc"],
                "bank_name": "HDFC Bank",
            },
            "contact": {
                "name": "Accounts Team",
                "email": f"accounts@{sid.lower()}.example.in",
                "phone": "9900112233",
            },
            "documents": docs,
        }

        (SUBS / f"{sid}.json").write_text(
            json.dumps(submission, indent=2), encoding="utf-8"
        )
        golden[sid] = {"expect": case["expect"], "why": case["why"]}

    (ROOT / "data" / "golden.json").write_text(
        json.dumps(golden, indent=2), encoding="utf-8"
    )
    print(f"{len(CASES)} submissions -> {SUBS}")
    print(f"documents -> {DOCS}")


if __name__ == "__main__":
    build()