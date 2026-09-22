# Vendor onboarding — submission to decision
live: https://vendor-onboarding-muh2.onrender.com/

Takes a vendor's onboarding submission — form fields plus supporting
documents — and produces a status with the reasoning attached: approved,
pending information, needs review, or rejected. For anything not approved,
it produces a message back to the vendor.

The interesting problem isn't validating fields. Any submission where a
single field is malformed is easy. The hard case is the submission where
every field is individually valid and the *relationships between them* are
wrong — that's where payment fraud lives, and it's what most of this system
is built to catch.

## Running it

```bat
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
python -m pytest
```

The test suite runs offline. No API key, no database — document extraction
is frozen as fixtures in `tests/fixtures/`, so all 43 tests including every
edge case pass on a fresh clone.

To run the full pipeline against live services, create `.env`:

```
GROQ_API_KEY=...
GROQ_MODEL=openai/gpt-oss-20b
DATABASE_URL=postgresql://...
```

Then:

```bat
python generate_data.py     # synthetic submissions and documents
python build_fixtures.py    # re-extract documents (needs GROQ_API_KEY)
python run_all.py           # process everything, persist to Postgres
uvicorn app.api.main:app --port 8080
```

Tested against `openai/gpt-oss-20b` on Groq. Groq retires models on a short
cycle — if that one is gone, set `GROQ_MODEL` to anything current. The test
suite is unaffected.

## Design

### Deterministic code decides. The model only reads and writes.

The LLM does two jobs: turning document text into structured fields, and
drafting the message to the vendor. It has no role in the decision.

This isn't a convention, it's enforced by the interface. `derive_status()`
takes a list of findings and returns a status. It has no other parameters.
There is no code path — not a prompt, not a fallback, not an error handler —
where model output can influence whether a vendor is approved. The graph
node that calls it reads only `state["findings"]`.

The extraction prompt reinforces this from the other side: *copy values
exactly as printed, do not correct, reformat, or complete them.* A helpful
model would silently fix a GSTIN with a bad checksum, which would destroy
the signal the cross-reference layer depends on. The model's job is
transcription, not interpretation.

### Four statuses, not two

| Status | Meaning |
|---|---|
| `approved` | Onboard. Warnings may still be attached. |
| `pending_info` | Fixable. The vendor is told what's needed. |
| `needs_review` | Suspicious. A human looks at it. |
| `rejected` | Disqualifying. |

Real submissions don't sort into approve/reject. Most of them land in the
middle, and collapsing that middle throws away exactly the judgement the
system exists to make. A submission that's missing a document and one where
the bank account belongs to someone else are both "not approved" — but one
needs an email and the other needs a human.

Severity precedence: `block` > `review` > `require_info` > `warn`.

`review` outranking `require_info` is deliberate. If a submission has both
a missing document *and* something suspicious, the vendor gets nothing —
it goes to a human first. Sending a friendly "please upload your cancelled
cheque" email to a submission you suspect tips off the submitter and wastes
the signal.

### What the vendor is told, and what they aren't

Findings carry two separate fields. `message` is for the reviewer and is
precise: *"GSTIN embeds PAN AABCU9603R, but the declared PAN is AAFCS5566L."*
`remedy` is for the vendor and is actionable without being diagnostic.

Only `require_info` and `warn` findings reach the vendor. Anything rejected
or under review gets a neutral holding message instead:

> Thank you for your submission. Your details are with our procurement team
> for verification. We will contact you once the review is complete.

If you email a vendor "your GSTIN and PAN belong to different entities,"
you've told a potential fraudster exactly which check caught them, and the
next submission arrives with it fixed. The detailed finding goes to the
internal reviewer; the vendor gets an acknowledgement.

This is why the review UI labels withheld remedies explicitly — the
reviewer can see what *would* have been said without it having been sent.

## The checks

Structural validation runs first, then cross-field. The structural layer is
unremarkable: format and checksum on GSTIN, PAN, IFSC, Udyam. The
cross-field layer is where the real failures live.

| Check | Compares | Severity |
|---|---|---|
| `xref.pan_in_gstin` | PAN embedded in GSTIN vs declared PAN | block |
| `xref.bank_holder` | Account holder vs legal name, by entity type | review / warn |
| `xref.gstin_state` | GSTIN state code vs address state | require_info |
| `xref.cert_gstin` | GSTIN on certificate vs on form | require_info |
| `xref.cheque_ifsc` | IFSC on cheque vs on form | review |
| `xref.cheque_holder` | Holder on cheque vs on form | review |
| `xref.pan_card` | PAN on card vs on form | review |
| `xref.pincode_state` | PIN postal circle vs address state | warn |

### GSTIN validation

A GSTIN is 15 characters and every part is meaningful:

```
2 9 A A B C U 9 6 0 3 R 1 Z X
│─│ │───────────────────│ │ │ │
│    PAN (10)             │ │ └─ checksum, base-36
│                         │ └─── 'Z' for normal taxpayers
state code                └───── nth registration on this PAN in this state
```

The last character is a weighted mod-36 checksum over the first fourteen.
That makes a fabricated GSTIN provably invalid *offline* — no API call, no
registry lookup, no network. It's the cheapest high-value check in the
system: about twenty lines, catches something a human reviewer never would.

The PAN sitting at positions 2–12 is what makes check 1 possible, and the
4th character of that PAN encodes entity type (`C` company, `P` individual,
`F` firm, `H` HUF), which is what makes check 2 possible. Two of the
strongest checks in the system come from parsing one field carefully.

Rate slabs and state codes were verified against CBIC material at the time
of writing; both change, and the state code table would need maintaining.

### Name matching

Normalise, then fuzzy-match. Normalisation strips legal-form indicators
(`pvt`, `private`, `ltd`, `limited`, `llp`), the `M/s` prefix, punctuation,
and case. After that, "Shagri Technologies Pvt. Ltd." and "SHAGRI
TECHNOLOGIES PRIVATE LIMITED" are an exact match — the suffix carries no
identifying information, every company has one.

Only what survives normalisation goes to `rapidfuzz`, and the score is the
`max()` of token-sort and token-set ratios rather than a mean. That's
deliberate: a false mismatch bounces a legitimate vendor and makes someone
chase them, while a false match still lands in `needs_review` because the
threshold sits below the auto-approve bar. Asymmetric costs, so an
asymmetric metric.

A separate prefix-alignment check catches genuine abbreviations — "Shagri
Tech" against "Shagri Technologies" — requiring each token to be at least
three characters, since two-character prefixes are noise rather than
abbreviation.

One known weakness: `looks_personal` decides whether a bank account name
looks like a person by checking for absent legal suffixes and four or fewer
tokens. "Shagri Enterprises" trips it. But the failure direction is safe —
for a company entity it lands in `needs_review`, which is where an unclear
case belongs anyway. The heuristic being imperfect costs an extra human
look, never a wrong approval.

## Edge cases

### 1. Valid GSTIN, valid PAN, different entities (`SUB-003`) → rejected

<!-- YOURS. Why this one is the strongest check in the system. -->

### 2. Personal bank account (`SUB-004` vs `SUB-002`) → depends on entity type

<!-- YOURS. Same input shape, opposite verdicts, and why that distinction
     is the thing a naive validator gets wrong. -->

### 3. Certificate from a different state (`SUB-005`) → pending_info

<!-- YOURS. Why this one can't be caught without reading the document, and
     what the extraction prompt has to do to preserve the signal. -->

### 4. Malformed Udyam number (`SUB-006`) → approved with a warning

<!-- YOURS. Why you included a case that doesn't stop anything. -->

## Tests

43 tests, all offline, 0.2 seconds.

Beyond asserting verdicts, the suite pins down *why* each edge case
resolves the way it does. `test_edge1_pan_mismatch_is_the_blocking_rule`
asserts that the GSTIN is structurally valid and that
`xref.pan_in_gstin` is the only blocking finding — so the test fails if
the right verdict ever arrives for the wrong reason.

`test_every_vendor_facing_finding_has_a_remedy` walks every submission and
fails if any `require_info` finding lacks vendor-facing text, since that
would silently produce an empty message.

Extraction output is frozen in `tests/fixtures/`, rebuilt by
`build_fixtures.py`. That keeps the suite deterministic, network-free, and
runnable by anyone without an API key — a test suite that calls an LLM
isn't a test suite.

## What I left out

**OCR.** Documents are assumed to have a text layer. A scanned upload
raises `NoTextLayer` and becomes a `require_info` finding rather than
failing silently or being treated as blank. Production would need Tesseract
or a vision model feeding the same structuring prompt, with lower extraction
confidence and recalibrated thresholds. The seam is one named exception.

**Live registry verification.** Every check is offline and structural. A
GSTIN can be well-formed, internally consistent, and cancelled — catching
that needs the GST portal. Same for bank account name verification, which
needs a penny-drop.

**Extraction latency.** Three documents take around 20 seconds, sequential
Groq calls against a reasoning model that spends most of its tokens
thinking. Parallelising the three calls would cut it to roughly 7s. Left
sequential because decision latency wasn't the point of the exercise, but
it's the first thing I'd fix.

**Access control.** Database access is server-side only via the Postgres
connection string; the Supabase anon key is unused. RLS is enabled with no
policies rather than relied on for access control.

**Resubmission flow.** `decisions` is append-only and keyed by submission,
so re-running after a vendor fixes something creates a second decision and
the history is the audit trail. But there's no mechanism to *receive* a
correction — no vendor-facing form, no threading of replies.

## Structure

```
app/
  checks/      gst.py, identity.py, cross_reference.py  — pure functions, no I/O
  extract/     pdf_text.py, llm.py, documents.py, messages.py
  graph/       pipeline.py  — LangGraph nodes and state
  schemas/     submission.py, decision.py, documents.py
  db/          store.py
  api/         main.py
tests/         43 tests + frozen extraction fixtures
data/          synthetic submissions, generated PDFs, golden verdicts
```

Everything in `checks/` is pure — no network, no database, no model. That's
what makes the decision logic testable in isolation and why the suite runs
in 0.2 seconds.

Deployed at **https://vendor-onboarding-muh2.onrender.com/** — free tier, so the
first request after idle takes around 50 seconds to wake.
