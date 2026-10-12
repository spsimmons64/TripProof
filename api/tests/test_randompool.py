###################################################################################################
# The random testing pool denominator - 49 CFR 382.305.
#
# This arithmetic decides how many drivers a carrier must test all year. An off-by-one here
# understates that, and nothing downstream would notice: the number simply comes out smaller and
# every screen reports the carrier as compliant.
#
# It is also the arithmetic that replaced two disagreeing definitions of "the pool" - a headcount
# of CDL drivers used for the rate, and a date on the driver record used for the driver's own
# requirement - so it is worth being certain about.
###################################################################################################
from datetime import date

from app.randompool import mean_of, owed


def span(a, b=None):
    return {"joinedon": date.fromisoformat(a),
            "leftpoolon": date.fromisoformat(b) if b else None}


JAN, DEC = date(2026, 1, 1), date(2026, 12, 31)


def test_nobody_in_the_pool_is_an_average_of_nothing():
    assert mean_of([], JAN, DEC) == 0.0


def test_one_driver_all_year_is_one_position():
    assert mean_of([span("2026-01-01")], JAN, DEC) == 1.0
    assert mean_of([span("2026-01-01", "2026-12-31")], JAN, DEC) == 1.0


def test_both_ends_of_a_spell_are_days_in_the_pool():
    # In and out on the same day is one day, not nought. A driver tested that morning was in.
    assert mean_of([span("2026-06-01", "2026-06-01")],
                   date(2026, 6, 1), date(2026, 6, 1)) == 1.0


def test_half_a_year_is_half_a_position():
    # 2026 is not a leap year: 365 days, and 1 Jan to 30 Jun inclusive is 181 of them.
    assert round(mean_of([span("2026-01-01", "2026-06-30")], JAN, DEC), 4) == round(181 / 365, 4)


def test_a_spell_outside_the_period_counts_for_nothing():
    assert mean_of([span("2025-01-01", "2025-12-31")], JAN, DEC) == 0.0


def test_a_spell_is_clipped_to_the_period_at_both_ends():
    # Started before the year and still running: the whole year counts, not more.
    assert mean_of([span("2020-01-01")], JAN, DEC) == 1.0


def test_two_spells_for_one_driver_do_not_overlap_into_two_positions():
    # Out in June, back in July. Never two positions at once.
    held = [span("2026-01-01", "2026-06-30"), span("2026-07-01")]
    assert mean_of(held, JAN, DEC) == 1.0


def test_drivers_add_up():
    assert mean_of([span("2026-01-01"), span("2026-01-01"), span("2026-01-01")], JAN, DEC) == 3.0


def test_the_rate_rounds_up_because_rounding_down_tests_nobody():
    # 50% of 1.4 positions is 0.7 tests. A carrier that rounds that to nought has tested nobody
    # all year and reported that it met the rate.
    assert owed(1.4, 50) == 1
    assert owed(3.0, 50) == 2          # 1.5 -> 2
    assert owed(3.0, 10) == 1          # 0.3 -> 1
    assert owed(20, 50) == 10
    assert owed(20, 10) == 2


def test_an_empty_pool_owes_nothing():
    """The one case that is genuinely zero - and it must not round up to one, or a carrier with
    no CDL drivers is told it owes a test it has nobody to give."""
    assert owed(0, 50) == 0
    assert owed(0.0, 10) == 0
