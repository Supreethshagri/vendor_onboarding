from __future__ import annotations

from app.extract.llm import structure
from app.extract.pdf_text import NoTextLayer, extract_text
from app.schemas.documents import (
    ChequeFacts, DocumentFacts, GstCertificateFacts, PanCardFacts,
)
from app.schemas.submission import DocumentType, VendorSubmission

HINTS = {
    DocumentType.GST_CERTIFICATE:
        "This is a GST registration certificate (Form GST REG-06). Extract the "
        "15-character GSTIN, the legal name, the trade name if shown, and the state.",
    DocumentType.CANCELLED_CHEQUE:
        "This is a cancelled cheque. Extract the account holder name, the account "
        "number, the 11-character IFSC code, and the bank name.",
    DocumentType.PAN_CARD:
        "This is a PAN card. Extract the 10-character PAN and the name on the card.",
}

MODELS = {
    DocumentType.GST_CERTIFICATE: GstCertificateFacts,
    DocumentType.CANCELLED_CHEQUE: ChequeFacts,
    DocumentType.PAN_CARD: PanCardFacts,
}

FIELD = {
    DocumentType.GST_CERTIFICATE: "gst_certificate",
    DocumentType.CANCELLED_CHEQUE: "cheque",
    DocumentType.PAN_CARD: "pan_card",
}


def read_documents(sub: VendorSubmission) -> tuple[DocumentFacts, list[str]]:
    """Returns extracted facts and a list of problems encountered."""
    facts: dict = {}
    problems: list[str] = []

    for doc in sub.documents:
        if doc.type not in MODELS:
            continue
        try:
            text = extract_text(doc.path)
        except NoTextLayer as e:
            problems.append(str(e))
            continue
        except FileNotFoundError:
            problems.append(f"{doc.filename} is referenced but the file is missing.")
            continue

        parsed = structure(text, MODELS[doc.type], HINTS[doc.type])
        if parsed is None:
            problems.append(f"Could not read structured fields from {doc.filename}.")
            continue

        facts[FIELD[doc.type]] = parsed

    return DocumentFacts(**facts), problems