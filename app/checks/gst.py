from __future__ import annotations
import re

CODEPOINTS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

GSTIN_RE = re.compile(
    r"^(?P<state>[0-9]{2})"
    r"(?P<pan>[A-Z]{5}[0-9]{4}[A-Z])"
    r"(?P<entity>[1-9A-Z])"
    r"(?P<z>[A-Z])"
    r"(?P<check>[0-9A-Z])$"
)

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")

STATE_CODES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
    "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu",
    "34": "Puducherry", "35": "Andaman and Nicobar Islands",
    "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
    "97": "Other Territory", "99": "Centre Jurisdiction",
}

# 4th char of PAN encodes entity type.
PAN_ENTITY_TYPE = {
    "C": "company", "P": "individual", "H": "huf", "F": "firm_or_llp",
    "A": "aop", "T": "trust", "B": "body_of_individuals",
    "L": "local_authority", "J": "artificial_juridical_person",
    "G": "government",
}


def clean(s: str | None) -> str:
    return (s or "").strip().upper().replace(" ", "")


def gstin_checksum(first14: str) -> str:
    """Weighted mod-36 checksum over the first 14 characters."""
    total = 0
    for i, ch in enumerate(first14):
        product = CODEPOINTS.index(ch) * (i % 2 + 1)
        total += product // 36 + product % 36
    return CODEPOINTS[(36 - total % 36) % 36]


def validate_gstin(gstin: str | None) -> dict:
    """Offline structural validation. Never raises."""
    g = clean(gstin)
    out: dict = {
        "input": g, "valid": False, "state_code": None, "state": None,
        "pan": None, "entity_type": None, "errors": [], "warnings": [],
    }

    if not g:
        out["errors"].append("missing: no GSTIN provided")
        return out

    m = GSTIN_RE.match(g)
    if not m:
        out["errors"].append(
            f"format: expected 15 characters as 2 digits + PAN + entity + Z + check, got {len(g)}"
        )
        return out

    state, pan = m.group("state"), m.group("pan")
    out["state_code"] = state
    out["state"] = STATE_CODES.get(state)
    out["pan"] = pan
    out["entity_type"] = PAN_ENTITY_TYPE.get(pan[3])

    if out["state"] is None:
        out["errors"].append(f"state: {state} is not an allotted state code")

    if out["entity_type"] is None:
        out["warnings"].append(f"pan: unrecognised entity character {pan[3]!r}")

    if m.group("z") != "Z":
        out["warnings"].append(
            f"structure: 14th character is {m.group('z')!r}, not 'Z' — unusual registration type"
        )

    expected = gstin_checksum(g[:14])
    if m.group("check") != expected:
        out["errors"].append(
            f"checksum: expected {expected!r}, got {m.group('check')!r}"
        )

    out["valid"] = not out["errors"]
    return out


def validate_pan(pan: str | None) -> dict:
    p = clean(pan)
    out: dict = {"input": p, "valid": False, "entity_type": None, "errors": []}
    if not p:
        out["errors"].append("missing: no PAN provided")
        return out
    if not PAN_RE.match(p):
        out["errors"].append("format: expected 5 letters, 4 digits, 1 letter")
        return out
    out["entity_type"] = PAN_ENTITY_TYPE.get(p[3])
    if out["entity_type"] is None:
        out["errors"].append(f"entity: unrecognised 4th character {p[3]!r}")
    out["valid"] = not out["errors"]
    return out


def validate_ifsc(ifsc: str | None) -> dict:
    """11 chars: 4-letter bank code, '0', 6-char branch code."""
    f = clean(ifsc)
    out: dict = {"input": f, "valid": False, "bank_code": None, "errors": []}
    if not f:
        out["errors"].append("missing: no IFSC provided")
        return out
    if not IFSC_RE.match(f):
        out["errors"].append(
            "format: expected 4 letters, '0', then 6 alphanumeric characters"
        )
        return out
    out["bank_code"] = f[:4]
    out["valid"] = True
    return out


def make_gstin(state: str, pan: str, entity: str = "1") -> str:
    """Build a checksum-valid GSTIN. For generating test data only."""
    body = f"{state}{clean(pan)}{entity}Z"
    return body + gstin_checksum(body)