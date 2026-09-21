from __future__ import annotations
from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    GST_CERTIFICATE = "gst_certificate"
    CANCELLED_CHEQUE = "cancelled_cheque"
    PAN_CARD = "pan_card"
    MSME_CERTIFICATE = "msme_certificate"
    OTHER = "other"


class Document(BaseModel):
    type: DocumentType
    filename: str
    path: str


class Address(BaseModel):
    line1: str | None = None
    line2: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None


class BankDetails(BaseModel):
    account_holder_name: str | None = None
    account_number: str | None = None
    ifsc: str | None = None
    bank_name: str | None = None


class Contact(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None


class VendorSubmission(BaseModel):
    """What the vendor sends us. Every field optional — incompleteness
    is a finding, not a parse failure."""

    submission_id: str
    submitted_at: date

    legal_name: str | None = None
    trade_name: str | None = None
    gstin: str | None = None
    pan: str | None = None
    msme_udyam: str | None = None

    registered_address: Address = Address()
    bank: BankDetails = BankDetails()
    contact: Contact = Contact()

    documents: list[Document] = []

    def document(self, kind: DocumentType) -> Document | None:
        return next((d for d in self.documents if d.type is kind), None)