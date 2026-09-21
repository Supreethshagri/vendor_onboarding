from __future__ import annotations
import re

from app.checks.gst import (
    STATE_CODES, clean, validate_gstin, validate_ifsc, validate_pan,
)
from app.checks.identity import compare_bank_holder, name_similarity
from app.schemas.decision import Finding, Severity
from app.schemas.documents import DocumentFacts
from app.schemas.submission import DocumentType, VendorSubmission

UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")

REQUIRED_DOCS = (DocumentType.GST_CERTIFICATE, DocumentType.CANCELLED_CHEQUE)

# First two digits of a PIN code map to a postal circle. Approximate —
# a few circles span more than one state, so only used for a warning.
PIN_PREFIX_STATE = {
    "11": "Delhi", "12": "Haryana", "13": "Haryana", "14": "Punjab",
    "15": "Punjab", "16": "Chandigarh", "17": "Himachal Pradesh",
    "18": "Jammu and Kashmir", "19": "Jammu and Kashmir",
    "20": "Uttar Pradesh", "21": "Uttar Pradesh", "22": "Uttar Pradesh",
    "23": "Uttar Pradesh", "24": "Uttar Pradesh", "25": "Uttar Pradesh",
    "26": "Uttar Pradesh", "27": "Uttar Pradesh", "28": "Uttar Pradesh",
    "30": "Rajasthan", "31": "Rajasthan", "32": "Rajasthan",
    "33": "Rajasthan", "34": "Rajasthan",
    "36": "Gujarat", "37": "Gujarat", "38": "Gujarat", "39": "Gujarat",
    "40": "Maharashtra", "41": "Maharashtra", "42": "Maharashtra",
    "43": "Maharashtra", "44": "Maharashtra",
    "45": "Madhya Pradesh", "46": "Madhya Pradesh", "47": "Madhya Pradesh",
    "48": "Madhya Pradesh",
    "50": "Telangana", "51": "Andhra Pradesh", "52": "Andhra Pradesh",
    "53": "Andhra Pradesh",
    "56": "Karnataka", "57": "Karnataka", "58": "Karnataka", "59": "Karnataka",
    "60": "Tamil Nadu", "61": "Tamil Nadu", "62": "Tamil Nadu",
    "63": "Tamil Nadu", "64": "Tamil Nadu",
    "67": "Kerala", "68": "Kerala", "69": "Kerala",
    "70": "West Bengal", "71": "West Bengal", "72": "West Bengal",
    "73": "West Bengal", "74": "West Bengal",
    "75": "Odisha", "76": "Odisha", "77": "Odisha",
    "78": "Assam", "79": "Arunachal Pradesh",
    "80": "Bihar", "81": "Bihar", "82": "Bihar",
    "83": "Jharkhand", "84": "Bihar", "85": "Bihar",
}


def _same_state(a: str | None, b: str | None) -> bool:
    return clean(a).replace("&", "AND") == clean(b).replace("&", "AND")

def _structural(sub: VendorSubmission) -> list[Finding]:
    out: list[Finding] = []

    g = validate_gstin(sub.gstin)
    if not g["valid"]:
        for err in g["errors"]:
            kind = err.split(":", 1)[0]
            if kind == "checksum":
                out.append(Finding(
                    rule_id="gstin.checksum", severity=Severity.BLOCK,
                    field="gstin", message=f"GSTIN {err}",
                    remedy="The GSTIN provided is not a valid number. Please "
                           "supply the GSTIN exactly as printed on your "
                           "registration certificate.",
                    detail={"gstin": g["input"]},
                ))
            elif kind == "state":
                out.append(Finding(
                    rule_id="gstin.state", severity=Severity.BLOCK,
                    field="gstin", message=f"GSTIN {err}",
                    remedy="The state code in your GSTIN is not recognised. "
                           "Please re-check and resubmit.",
                ))
            else:
                out.append(Finding(
                    rule_id=f"gstin.{kind}", severity=Severity.REQUIRE_INFO,
                    field="gstin", message=f"GSTIN {err}",
                    remedy="Please provide your 15-character GSTIN.",
                ))
    for w in g["warnings"]:
        out.append(Finding(rule_id="gstin.unusual", severity=Severity.WARN,
                           field="gstin", message=f"GSTIN {w}"))

    p = validate_pan(sub.pan)
    if not p["valid"]:
        out.append(Finding(
            rule_id="pan.invalid", severity=Severity.REQUIRE_INFO, field="pan",
            message="PAN " + "; ".join(p["errors"]),
            remedy="Please provide a valid 10-character PAN.",
        ))

    f = validate_ifsc(sub.bank.ifsc)
    if not f["valid"]:
        out.append(Finding(
            rule_id="ifsc.invalid", severity=Severity.REQUIRE_INFO, field="bank.ifsc",
            message="IFSC " + "; ".join(f["errors"]),
            remedy="Please provide the 11-character IFSC code of your bank branch.",
        ))

    if not clean(sub.bank.account_number):
        out.append(Finding(
            rule_id="bank.account_missing", severity=Severity.REQUIRE_INFO,
            field="bank.account_number", message="Bank account number is missing.",
            remedy="Please provide your bank account number.",
        ))

    if sub.msme_udyam and not UDYAM_RE.match(clean(sub.msme_udyam)):
        out.append(Finding(
            rule_id="msme.format", severity=Severity.WARN, field="msme_udyam",
            message=f"Udyam registration {sub.msme_udyam!r} is not in the "
                    f"UDYAM-XX-00-0000000 format.",
            remedy="If you are MSME registered, please provide the Udyam number "
                   "in the format UDYAM-XX-00-0000000. This affects payment "
                   "terms only and does not delay onboarding.",
        ))

    for kind in REQUIRED_DOCS:
        if sub.document(kind) is None:
            label = kind.value.replace("_", " ")
            out.append(Finding(
                rule_id="doc.missing", severity=Severity.REQUIRE_INFO,
                field="documents", message=f"No {label} uploaded.",
                remedy=f"Please upload your {label}.",
                detail={"document_type": kind.value},
            ))

    return out

def _cross_field(sub: VendorSubmission, docs: DocumentFacts) -> list[Finding]:
    out: list[Finding] = []

    g = validate_gstin(sub.gstin)
    embedded_pan = g.get("pan")
    entity_type = g.get("entity_type")
    declared_pan = clean(sub.pan)

    # 1. The PAN inside the GSTIN must be the declared PAN.
    if embedded_pan and declared_pan and embedded_pan != declared_pan:
        out.append(Finding(
            rule_id="xref.pan_in_gstin", severity=Severity.BLOCK, field="gstin",
            message=f"GSTIN embeds PAN {embedded_pan}, but the declared PAN is "
                    f"{declared_pan}. A GSTIN is issued against exactly one PAN, "
                    f"so these identify two different entities.",
            remedy="The GSTIN and PAN you provided belong to different entities. "
                   "Please confirm which entity we are onboarding and resubmit "
                   "matching details.",
            detail={"gstin_pan": embedded_pan, "declared_pan": declared_pan},
        ))

    # 2. Bank account holder vs legal name, interpreted by entity type.
    if sub.bank.account_holder_name and sub.legal_name:
        m = compare_bank_holder(sub.legal_name, sub.bank.account_holder_name, entity_type)
        if m.verdict == "mismatch":
            out.append(Finding(
                rule_id="xref.bank_holder", severity=Severity.REVIEW,
                field="bank.account_holder_name", message=m.message,
                remedy="The bank account name does not match your registered "
                       "legal name. Please provide an account held in the "
                       "registered entity's name.",
                detail={"similarity": m.score, "entity_type": entity_type},
            ))
        elif m.verdict in ("close", "personal_name"):
            out.append(Finding(
                rule_id="xref.bank_holder", severity=Severity.WARN,
                field="bank.account_holder_name", message=m.message,
                detail={"similarity": m.score, "entity_type": entity_type},
            ))

    # 3. GSTIN state vs declared address state.
    gstin_state = g.get("state")
    addr_state = sub.registered_address.state
    if gstin_state and addr_state and not _same_state(gstin_state, addr_state):
        out.append(Finding(
            rule_id="xref.gstin_state", severity=Severity.REQUIRE_INFO,
            field="registered_address.state",
            message=f"GSTIN is registered in {gstin_state} but the address "
                    f"states {addr_state}.",
            remedy=f"Your GSTIN is a {gstin_state} registration while your "
                   f"address is in {addr_state}. Please confirm the address of "
                   f"the principal place of business for this GSTIN.",
            detail={"gstin_state": gstin_state, "address_state": addr_state},
        ))

    # 4. PIN code circle vs declared state. Approximate, so a warning only.
    pin = clean(sub.registered_address.pincode)
    circle = PIN_PREFIX_STATE.get(pin[:2]) if len(pin) == 6 else None
    if circle and addr_state and not _same_state(circle, addr_state):
        out.append(Finding(
            rule_id="xref.pincode_state", severity=Severity.WARN,
            field="registered_address.pincode",
            message=f"PIN {pin} falls in the {circle} postal circle but the "
                    f"address states {addr_state}.",
            detail={"pin_circle": circle, "address_state": addr_state},
        ))

    # 5. GST certificate against the form.
    cert = docs.gst_certificate
    if cert:
        if cert.gstin and sub.gstin and clean(cert.gstin) != clean(sub.gstin):
            cert_state = STATE_CODES.get(clean(cert.gstin)[:2])
            out.append(Finding(
                rule_id="xref.cert_gstin", severity=Severity.REQUIRE_INFO,
                field="documents",
                message=f"Certificate shows GSTIN {clean(cert.gstin)} "
                        f"({cert_state or 'unknown state'}), form declares "
                        f"{clean(sub.gstin)} ({gstin_state or 'unknown state'}).",
                remedy="The GST certificate you uploaded is for a different "
                       "registration than the GSTIN on your form. Please upload "
                       "the certificate for the GSTIN you are onboarding under, "
                       "or correct the GSTIN.",
                detail={"certificate_gstin": clean(cert.gstin),
                        "form_gstin": clean(sub.gstin)},
            ))
        if cert.legal_name and sub.legal_name:
            score = name_similarity(cert.legal_name, sub.legal_name)
            if score < 88:
                out.append(Finding(
                    rule_id="xref.cert_legal_name", severity=Severity.REVIEW,
                    field="legal_name",
                    message=f"Certificate legal name {cert.legal_name!r} does not "
                            f"match the form {sub.legal_name!r} (similarity {score}).",
                    remedy="The legal name on your GST certificate differs from "
                           "the name on the form. Please use your registered "
                           "legal name exactly as it appears on the certificate.",
                    detail={"similarity": score},
                ))

    # 6. Cancelled cheque against the form.
    cq = docs.cheque
    if cq:
        if cq.ifsc and sub.bank.ifsc and clean(cq.ifsc) != clean(sub.bank.ifsc):
            out.append(Finding(
                rule_id="xref.cheque_ifsc", severity=Severity.REVIEW,
                field="bank.ifsc",
                message=f"Cheque shows IFSC {clean(cq.ifsc)}, form declares "
                        f"{clean(sub.bank.ifsc)}.",
                remedy="The IFSC on your cancelled cheque does not match the one "
                       "on the form. Please confirm the correct branch.",
                detail={"cheque_ifsc": clean(cq.ifsc), "form_ifsc": clean(sub.bank.ifsc)},
            ))
        if cq.account_number and sub.bank.account_number:
            if clean(cq.account_number) != clean(sub.bank.account_number):
                out.append(Finding(
                    rule_id="xref.cheque_account", severity=Severity.REVIEW,
                    field="bank.account_number",
                    message=f"Cheque account number differs from the form.",
                    remedy="The account number on your cheque does not match the "
                           "form. Please confirm which account should be paid.",
                ))
        if cq.account_holder_name and sub.bank.account_holder_name:
            score = name_similarity(cq.account_holder_name, sub.bank.account_holder_name)
            if score < 88:
                out.append(Finding(
                    rule_id="xref.cheque_holder", severity=Severity.REVIEW,
                    field="bank.account_holder_name",
                    message=f"Cheque holder {cq.account_holder_name!r} differs from "
                            f"the declared holder {sub.bank.account_holder_name!r} "
                            f"(similarity {score}).",
                    remedy="The account holder name on your cheque does not match "
                           "the name you entered. Please confirm.",
                    detail={"similarity": score},
                ))

    # 7. PAN card against the form.
    pc = docs.pan_card
    if pc and pc.pan and declared_pan and clean(pc.pan) != declared_pan:
        out.append(Finding(
            rule_id="xref.pan_card", severity=Severity.REVIEW, field="pan",
            message=f"PAN card shows {clean(pc.pan)}, form declares {declared_pan}.",
            remedy="The PAN card you uploaded does not match the PAN on your form. "
                   "Please upload the correct document.",
        ))

    return out


def run_checks(sub: VendorSubmission, docs: DocumentFacts | None = None) -> list[Finding]:
    return _structural(sub) + _cross_field(sub, docs or DocumentFacts())