import pytest

from app import formats


def test_phone():
    for raw in ("8135550142", "813-555-0142", "(813) 555 0142", "+1 813.555.0142", "1-813-555-0142"):
        assert formats.phone(raw) == "(813) 555-0142"
    assert formats.phone("") is None and formats.phone(None) is None
    with pytest.raises(ValueError, match="Fax must be"):
        formats.phone("555-0142", "Fax")


def test_ein_and_ssn():
    assert formats.ein("591234567") == formats.ein("59-1234567") == "59-1234567"
    assert formats.ssn("123456789") == formats.ssn("123 45 6789") == "123-45-6789"
    assert formats.ein(" ") is None and formats.ssn(None) is None
    with pytest.raises(ValueError):
        formats.ein("12-345")
    with pytest.raises(ValueError):
        formats.ssn("12345678")
