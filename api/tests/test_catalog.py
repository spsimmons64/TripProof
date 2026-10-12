###################################################################################################
# The catalog must not contradict itself.
#
# Every rule carries its own hand-written `applieswhen`, and for a long time nothing compared one
# against another. Read on its own, each of the rules below was defensible. Read together they
# said the carrier owed a 49 CFR Part 382 prohibition on its driver and owed no Part 382
# programme - no policy, no DER, no random selections, no supervisor training, no Clearinghouse
# account - because twelve company rules asked "do you cross a state line?" and the driver rules
# asked the question that actually decides it.
#
# Nobody could have caught that by reviewing a rule. It is only visible across the catalog, which
# is what this reads. It is here rather than in a script because a check somebody has to remember
# to run is a check that stops being run.
###################################################################################################
import pytest

from app import catalogcheck


def test_authority_parsing():
    assert catalogcheck.authority_of("49 CFR 382.301(a)") == "49 CFR 382"
    assert catalogcheck.authority_of("49 CFR Part 40 Subpart O") == "49 CFR 40"
    assert catalogcheck.authority_of("49 CFR 382.303(d)(2); 49 CFR 382.303(e)") == "49 CFR 382"
    # A state statute is not something federal rules can be checked against.
    assert catalogcheck.authority_of("F.S. 316.302(1)(b)") is None
    assert catalogcheck.authority_of(None) is None


def test_fact_extraction_reaches_every_nesting():
    where = {"all": [{"fact": "operation.interstate", "is": True},
                     {"any": [{"fact": "company.cdldrivers", "is": True},
                              {"fact": "fleet.cdl_required", "is": True}]}]}
    assert catalogcheck.facts_in(where) == {
        "operation.interstate", "company.cdldrivers", "fleet.cdl_required"}
    # Stored as text on the row, so the string form has to work too.
    import json
    assert catalogcheck.facts_in(json.dumps(where)) == catalogcheck.facts_in(where)
    assert catalogcheck.facts_in(None) == set()


@pytest.fixture(scope="module")
def loaded(db):
    """The catalog as shipped, with the fact vocabulary the engine can actually produce."""
    from app.db import engine
    from app.facts import assemble, vehicle_facts
    from app.cli import create_account
    create_account("Catalog Check Transport", "owner@catalog.test", "Owner C", "FL",
                   "America/New_York", "correct horse battery")
    with engine.begin() as conn:
        acct = conn.exec_driver_sql(
            "SELECT recordid FROM accounts WHERE name = %s",
            ("Catalog Check Transport",)).scalar()
        driver = conn.exec_driver_sql(
            "SELECT recordid FROM drivers WHERE accountid = %s LIMIT 1", (acct,)).scalar()
        vehicle = conn.exec_driver_sql(
            "SELECT recordid FROM vehicles WHERE accountid = %s LIMIT 1", (acct,)).scalar()
        # Every fact name the engine can hand a rule. A rule gating on anything else is gating on
        # something that will never be known.
        known = set(assemble(conn, acct, None)["facts"])
        if driver:
            known |= set(assemble(conn, acct, driver)["facts"])
        if vehicle:
            known |= set(vehicle_facts(conn, acct, vehicle))
        else:
            known |= {"vehicle.cmv_federal", "vehicle.cmv_florida", "vehicle.cdl_required",
                      "vehicle.seats", "vehicle.gvwr", "vehicle.lift", "vehicle.forcompensation"}
        yield catalogcheck.check(conn, known), acct


def test_no_rule_gates_on_a_fact_nothing_produces(loaded):
    """A rule whose fact is never produced can never be decided. It sits on the list for ever
    saying "not known", and no amount of work by the office changes it."""
    found, _ = loaded
    assert not found["vocabulary"], "\n" + catalogcheck.report(
        {"reach": [], "vocabulary": found["vocabulary"], "deadend": [], "orphan": []})


def test_every_rule_has_somewhere_to_be_answered(loaded):
    """A requirement with no form behind it is a red mark the office cannot clear. See the
    no-dead-ends rule: the screen that shows a process must be able to run it.

    `offscreen` is deliberately NOT asserted on here. Those are answerable - just not from the
    requirement - and failing the build on them would mean shipping a red test for a thing that
    works, which teaches everybody to ignore it."""
    found, _ = loaded
    assert not found["deadend"] and not found["orphan"], "\n" + catalogcheck.report(
        {"reach": [], "vocabulary": [], "deadend": found["deadend"], "orphan": found["orphan"]})


def test_one_regulation_has_one_answer_about_who_it_reaches(loaded):
    """Part 382 either reaches this carrier or it does not. It cannot reach the driver and not
    the employer, and that is precisely the state this catalog was in.

    A requirement may add its OWN trigger on top - a prohibition fires on driver.prohibited, a
    post-accident test on driver.postaccidentowed - so what is compared is the reach predicate,
    not the whole condition. Rules under one regulation must share one."""
    found, _ = loaded
    assert not found["reach"], "\n" + catalogcheck.report(
        {"reach": found["reach"], "vocabulary": [], "deadend": [], "orphan": []})


def test_snapshot_of_a_catalog_change_is_empty_when_nothing_changed(loaded):
    """The harness that proves a rule edit moved what it meant to move, and nothing else.

    If this ever fails, the engine is not deterministic and no before/after comparison of a
    catalog change can be trusted - which makes every other guarantee here worthless."""
    from app.db import engine
    _, acct = loaded
    with engine.begin() as conn:
        before = catalogcheck.snapshot(conn, acct)
        after = catalogcheck.snapshot(conn, acct)
    assert before, "snapshot captured nothing - the harness is not reading the catalog"
    assert catalogcheck.diff(before, after) == []
