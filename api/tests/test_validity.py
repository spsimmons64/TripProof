from datetime import date, datetime
from decimal import Decimal

from app.validity import (CredentialFact, credential_as_of, credential_window, driver_age_verdict, license_years_verdict,
                          trip_evidence_verdict, vehicle_age_verdict, vehicle_mileage_verdict)


def dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def test_card_covers_whole_printed_expiry_day():
    w = credential_window(date(2024, 4, 2), date(2026, 4, 2), None, None)
    assert w.covers(dt("2026-04-02 23:59:59"))
    assert not w.covers(dt("2026-04-03 00:00"))
    assert w.endcode == "expired"


def test_not_covered_before_issue():
    w = credential_window(date(2026, 1, 10), None, None, None)
    assert not w.covers(dt("2026-01-09 23:59"))
    assert w.covers(dt("2026-01-10 00:00"))
    assert w.end is None


def test_max_age_beats_printed_date():
    # Background check done 2025-06-01, broker allows 365 days: stops covering 2026-06-01 00:00.
    w = credential_window(date(2025, 6, 1), None, None, 365)
    assert w.covers(dt("2026-05-31 23:59"))
    assert not w.covers(dt("2026-06-01 00:00"))
    assert w.endcode == "maxage"


def test_revocation_ends_coverage_at_that_moment_without_grace():
    w = credential_window(date(2025, 1, 1), date(2027, 1, 1), dt("2026-02-10 14:30"), None, gracedays=10)
    assert w.covers(dt("2026-02-10 14:29"))
    assert not w.covers(dt("2026-02-10 14:30"))
    assert w.endcode == "revoked"


def test_grace_extends_expiry():
    w = credential_window(date(2025, 1, 1), date(2026, 1, 31), None, None, gracedays=5)
    assert w.covers(dt("2026-02-05 12:00"))
    assert not w.covers(dt("2026-02-06 00:00"))


def test_as_of_picks_renewal_and_explains_gaps():
    old = CredentialFact("old", date(2024, 4, 2), date(2026, 4, 2), None)
    new = CredentialFact("new", date(2026, 4, 10), date(2028, 4, 10), None)
    assert credential_as_of([old, new], dt("2026-03-01 09:00"), "CPR", None).credentialid == "old"
    assert credential_as_of([old, new], dt("2026-04-20 09:00"), "CPR", None).credentialid == "new"
    gap = credential_as_of([old, new], dt("2026-04-05 09:00"), "CPR", None)
    assert gap.outcome == "fail" and gap.reasoncode == "expired" and gap.credentialid == "old"
    assert gap.reason == "CPR expired 2026-04-02"


def test_overlapping_renewal_prefers_newest():
    old = CredentialFact("old", date(2024, 4, 2), date(2026, 4, 2), None)
    early = CredentialFact("early", date(2026, 3, 15), date(2028, 3, 15), None)
    assert credential_as_of([old, early], dt("2026-03-20 09:00"), "CPR", None).credentialid == "early"


def test_missing_and_not_yet():
    assert credential_as_of([], dt("2026-01-01 00:00"), "CPR", None).reasoncode == "missing"
    future = CredentialFact("f", date(2026, 5, 1), None, None)
    v = credential_as_of([future], dt("2026-04-01 00:00"), "CPR", None)
    assert v.reasoncode == "notyet"


def test_trip_before_revocation_still_covered():
    c = CredentialFact("c", date(2025, 1, 1), date(2027, 1, 1), dt("2026-02-10 14:30"), "Arrest reported")
    assert credential_as_of([c], dt("2026-02-09 08:00"), "Background", None).outcome == "pass"
    v = credential_as_of([c], dt("2026-02-11 08:00"), "Background", None)
    assert v.reasoncode == "revoked" and "Arrest reported" in v.reason


def test_vehicle_age():
    assert vehicle_age_verdict(2016, dt("2026-05-01 00:00"), 10).outcome == "pass"
    assert vehicle_age_verdict(2015, dt("2026-05-01 00:00"), 10).reasoncode == "toold"
    assert vehicle_age_verdict(None, dt("2026-05-01 00:00"), 10).reasoncode == "nomodelyear"


# --- catalog additions (003/004) -----------------------------------------------------------------


def test_default_validity_when_no_expiry_printed():
    # CPR card with nothing printed: good for 730 days from issue, through the day before.
    c = CredentialFact("c", date(2024, 5, 1), None, None)
    assert credential_as_of([c], dt("2026-04-30 12:00"), "CPR", None, defaultdays=730).outcome == "pass"
    v = credential_as_of([c], dt("2026-05-01 00:00"), "CPR", None, defaultdays=730)
    assert v.reasoncode == "expired" and v.reason == "CPR expired 2026-04-30"
    # A printed expiry always wins over the default.
    printed = CredentialFact("p", date(2024, 5, 1), date(2027, 5, 1), None)
    assert credential_as_of([printed], dt("2026-12-01 00:00"), "CPR", None, defaultdays=730).outcome == "pass"


def test_minimum_coverage_amount():
    low = CredentialFact("low", date(2026, 1, 1), date(2026, 12, 31), None, amount=Decimal("500000"))
    v = credential_as_of([low], dt("2026-06-01 09:00"), "Auto liability", None, minamount=1000000)
    assert v.reasoncode == "belowminimum" and "$500,000 is below the $1,000,000" in v.reason
    blank = CredentialFact("blank", date(2026, 1, 1), date(2026, 12, 31), None)
    assert "not entered" in credential_as_of([blank], dt("2026-06-01"), "Auto liability", None, minamount=1000000).reason
    high = CredentialFact("high", date(2026, 3, 1), date(2027, 3, 1), None, amount=Decimal("1500000"))
    assert credential_as_of([low, high], dt("2026-06-01"), "Auto liability", None, minamount=1000000).credentialid == "high"
    # Before the adequate policy started, the low one is what covered - and it is named.
    assert credential_as_of([low, high], dt("2026-02-01"), "Auto liability", None, minamount=1000000).credentialid == "low"


def test_driver_age_and_license_years():
    assert driver_age_verdict(date(2005, 6, 2), dt("2026-06-01 10:00"), 21).reasoncode == "underage"   # a day short
    assert driver_age_verdict(date(2005, 6, 1), dt("2026-06-01 10:00"), 21).outcome == "pass"
    assert driver_age_verdict(None, dt("2026-06-01"), 21).reasoncode == "nodob"
    assert license_years_verdict(date(2023, 7, 1), dt("2026-06-01"), 3).reasoncode == "licensetooshort"
    assert license_years_verdict(date(2023, 6, 1), dt("2026-06-01"), 3).outcome == "pass"


def test_mileage_and_trip_evidence():
    assert vehicle_mileage_verdict(300001, 300000).reasoncode == "toomanymiles"
    assert vehicle_mileage_verdict(300000, 300000).outcome == "pass"
    assert vehicle_mileage_verdict(None, 300000).reasoncode == "nomileage"
    assert trip_evidence_verdict(False, "signature").reasoncode == "nosignature"
    assert trip_evidence_verdict(True, "gps").outcome == "pass"
