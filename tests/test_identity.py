from app.checks.identity import (
    normalise_company, name_similarity, compare_bank_holder,
)


def test_legal_suffixes_stripped():
    assert normalise_company("Shagri Technologies Pvt Ltd").normalised == "shagri technologies"
    assert normalise_company("M/s Shagri Technologies Private Limited").normalised == "shagri technologies"


def test_case_and_punctuation_folded():
    a = "Shagri Technologies Pvt. Ltd."
    b = "SHAGRI TECHNOLOGIES PRIVATE LIMITED"
    assert name_similarity(a, b) == 100


def test_abbreviation_recognised():
    assert name_similarity("Shagri Tech", "Shagri Technologies Pvt Ltd") == 97


def test_different_companies_score_low():
    assert name_similarity("Shagri Technologies", "Kaveri Industries") < 60


def test_personal_account_rejected_for_company():
    m = compare_bank_holder("Shagri Technologies Pvt Ltd", "SUPREETH B M", "company")
    assert m.verdict == "mismatch"
    assert "individual" in m.message


def test_personal_account_allowed_for_individual():
    m = compare_bank_holder("Supreeth B M", "SUPREETH B M", "individual")
    assert m.verdict == "exact"


def test_proprietor_name_on_individual_registration():
    m = compare_bank_holder("Shagri Enterprises", "SUPREETH B M", "individual")
    assert m.verdict == "personal_name"