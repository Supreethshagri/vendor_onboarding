from app.checks.gst import (
    gstin_checksum, validate_gstin, validate_pan, validate_ifsc, make_gstin,
)


def test_checksum_against_known_gstin():
    # Widely published example GSTIN; last char is the checksum.
    assert gstin_checksum("27AAPFU0939F1Z") == "V"


def test_valid_gstin_round_trip():
    g = make_gstin("29", "AABCU9603R")
    r = validate_gstin(g)
    assert r["valid"]
    assert r["state"] == "Karnataka"
    assert r["pan"] == "AABCU9603R"
    assert r["entity_type"] == "company"


def test_bad_checksum_is_caught():
    g = make_gstin("29", "AABCU9603R")
    tampered = g[:14] + ("A" if g[14] != "A" else "B")
    r = validate_gstin(tampered)
    assert not r["valid"]
    assert any(e.startswith("checksum") for e in r["errors"])


def test_unallotted_state_code():
    g = make_gstin("28", "AABCU9603R")   # 28 was Andhra Pradesh pre-split
    r = validate_gstin(g)
    assert not r["valid"]
    assert any(e.startswith("state") for e in r["errors"])


def test_pan_entity_types():
    assert validate_pan("AABCU9603R")["entity_type"] == "company"
    assert validate_pan("AABPU9603R")["entity_type"] == "individual"
    assert not validate_pan("AABXU9603R")["valid"]


def test_ifsc():
    assert validate_ifsc("HDFC0001234")["valid"]
    assert not validate_ifsc("HDFC1001234")["valid"]   # 5th char must be 0
    assert not validate_ifsc("HDF0001234")["valid"]    # too short