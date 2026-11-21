"""Phone normalisation, India default (owner decision 2026-11-16). No DB."""
import pytest

from app.core.errors import ValidationFailed
from app.service.guest_service import normalize_phone


@pytest.mark.parametrize("raw", [
    "9876543210",
    "98765 43210",
    "98765-43210",
    "098765 43210",
    "919876543210",
    "+91 98765 43210",
    "+91-98765-43210",
])
def test_indian_forms_all_match(raw):
    assert normalize_phone(raw) == "+919876543210"


def test_landline_with_area_code_gets_the_india_prefix():
    # 0 + 10 digits, like a mobile written with a leading 0.
    assert normalize_phone("0471 2345678") == "+914712345678"


def test_foreign_number_keeps_its_country_code():
    assert normalize_phone("+44 20 7946 0958") == "+442079460958"


def test_other_lengths_keep_only_their_digits():
    assert normalize_phone("2345 678") == "2345678"  # 7 digits, no '+'


@pytest.mark.parametrize("raw", ["", "   ", "98765abcde", "12345", "+1234567890123456"])
def test_invalid_numbers_are_rejected(raw):
    with pytest.raises(ValidationFailed) as exc:
        normalize_phone(raw)
    assert exc.value.code == "invalid_phone"
