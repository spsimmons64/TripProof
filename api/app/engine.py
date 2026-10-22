"""The version of the rule engine - how rules are evaluated, as distinct from what they say.

A rule's own text and settings carry their version (compliancerulesversions). This is the other
half: when the evaluator changes how it reads a rule - which line a vehicle's approval counts for,
whether a draft may block - every decision made after says so, so one made before can be read
against the engine that made it.

2.0 - every trip decision made by app/tripcheck.py.
2.1 (2026-10-22) - a vehicle's state Medicaid rules reach it through its own broker approval for
    the trip's exact line; drafts never block dispatch; screenings and inspections are answered by
    their recorded result, not by being read; annual review findings read as recorded.
2.2 (2026-10-22) - a driving record read as disqualifying fails and one read as restricted clears
    nobody outright; an annual review with corrective action noted stays open until a later review
    records it done; every decision keeps the snapshot hash of each rule it read.
"""
ENGINE_VERSION = "2.2"
