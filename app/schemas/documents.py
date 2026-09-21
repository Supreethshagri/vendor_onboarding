from __future__ import annotations
from pydantic import BaseModel


class GstCertificateFacts(BaseModel):
    gstin: str | None = None
    legal_name: str | None = None
    trade_name: str | None = None
    state: str | None = None


class ChequeFacts(BaseModel):
    account_holder_name: str | None = None
    account_number: str | None = None
    ifsc: str | None = None
    bank_name: str | None = None


class PanCardFacts(BaseModel):
    pan: str | None = None
    name: str | None = None


class DocumentFacts(BaseModel):
    """Whatever we could read from the uploaded documents."""
    gst_certificate: GstCertificateFacts | None = None
    cheque: ChequeFacts | None = None
    pan_card: PanCardFacts | None = None