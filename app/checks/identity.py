from __future__ import annotations
import re
from dataclasses import dataclass

from rapidfuzz import fuzz

# Legal form indicators. Stripped before comparison because they carry no
# identifying information — every company has one.
LEGAL_SUFFIXES = {
    "pvt", "private", "ltd", "limited", "llp", "llc", "inc", "incorporated",
    "corp", "corporation", "co", "company", "plc", "opc",
}

# Honorific prefix, extremely common on Indian invoices and forms.
MS_PREFIX = re.compile(r"^m\s*/?\s*s\.?\s+", re.IGNORECASE)

PUNCT = re.compile(r"[^\w\s]")
WS = re.compile(r"\s+")


@dataclass(frozen=True)
class NormalisedName:
    original: str
    normalised: str
    tokens: tuple[str, ...]
    had_legal_suffix: bool


def normalise_company(name: str | None) -> NormalisedName:
    raw = (name or "").strip()
    s = MS_PREFIX.sub("", raw)
    s = PUNCT.sub(" ", s)
    s = WS.sub(" ", s).strip().lower()

    tokens = s.split()
    kept = [t for t in tokens if t not in LEGAL_SUFFIXES]
    had_suffix = len(kept) < len(tokens)

    # Everything was a suffix — keep the original tokens rather than nothing.
    if not kept:
        kept = tokens

    return NormalisedName(
        original=raw,
        normalised=" ".join(kept),
        tokens=tuple(kept),
        had_legal_suffix=had_suffix,
    )


def _prefix_aligned(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """True if every token of the shorter name prefixes the longer one's.

    Catches 'Shagri Tech' vs 'Shagri Technologies' — a real abbreviation,
    not a different company.
    """
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if not short or len(short) > len(long):
        return False
    for s, l in zip(short, long):
        if not (l.startswith(s) and len(s) >= 3):
            return False
    return True


def name_similarity(a: str | None, b: str | None) -> int:
    """0-100. Takes the most generous of several metrics, deliberately."""
    na, nb = normalise_company(a), normalise_company(b)
    if not na.normalised or not nb.normalised:
        return 0
    if na.normalised == nb.normalised:
        return 100
    if _prefix_aligned(na.tokens, nb.tokens):
        return 97

    return max(
        int(fuzz.token_sort_ratio(na.normalised, nb.normalised)),
        int(fuzz.token_set_ratio(na.normalised, nb.normalised)),
    )

    # Entity types where a personal-name bank account is legitimate.
PERSONAL_ACCOUNT_OK = {"individual", "huf"}


@dataclass(frozen=True)
class NameMatch:
    score: int
    verdict: str          # exact | abbreviation | close | personal_name | mismatch
    message: str


def compare_bank_holder(
    legal_name: str | None,
    holder_name: str | None,
    entity_type: str | None,
    threshold: int = 88,
) -> NameMatch:
    score = name_similarity(legal_name, holder_name)

    if score == 100:
        return NameMatch(score, "exact", "Bank account holder matches legal name.")
    if score >= 97:
        return NameMatch(
            score, "abbreviation",
            "Bank account holder appears to be an abbreviated form of the legal name.",
        )
    if score >= threshold:
        return NameMatch(
            score, "close",
            f"Bank account holder differs slightly from legal name (similarity {score}).",
        )

    holder = normalise_company(holder_name)
    looks_personal = not holder.had_legal_suffix and len(holder.tokens) <= 4

    if looks_personal:
        if entity_type in PERSONAL_ACCOUNT_OK:
            return NameMatch(
                score, "personal_name",
                f"Bank account is in a personal name. Consistent with a "
                f"{entity_type} registration, but confirm the holder is the proprietor.",
            )
        return NameMatch(
            score, "mismatch",
            f"Bank account is in a personal name ({holder.original!r}) while the "
            f"vendor is registered as a {entity_type or 'non-individual'} entity. "
            f"Funds would be paid to an individual, not the company.",
        )

    return NameMatch(
        score, "mismatch",
        f"Bank account holder {holder.original!r} does not match legal name "
        f"{(legal_name or '').strip()!r} (similarity {score}).",
    )