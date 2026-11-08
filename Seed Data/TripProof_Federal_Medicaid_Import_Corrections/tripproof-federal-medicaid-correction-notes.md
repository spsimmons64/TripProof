# TripProof Federal + Medicaid — Import Corrections (November 7, 2026)

## Contents

- `tripproof-federal-requirements-corrected.json` — 60 Federal records, same IDs as the original; 3 citation corrections.
- `tripproof-medicaid-requirements-unchanged.json` — 13 Medicaid records, unmodified.
- `tripproof-requirements.schema.json` — schema for validation.
- `tripproof-federal-medicaid-correction-review.json` — detailed changes, validation and unresolved issues.

## Exact corrections

- `FED-CO-018`: Replaced inaccurate HIPAA quote with exact text from 45 CFR 164.504(e)(2): `A contract between the covered entity and a business associate must:`
- `FED-CO-023`: Updated citation URL to eCFR's operative **49 CFR 387.33T**.
- `FED-CO-024`: Updated citation URL to eCFR's operative **49 CFR 390.19T**; the unsuffixed 390.19 is for certain Mexico-domiciled carriers.

## Validation

PASS: Both JSON files validate against the provided schema, with all 73 IDs unique. The previously refused *citations* were verified against eCFR. This is not an exhaustive legal audit.

## Expected reimport

All 3 refused records should cease being refused on the three listed citation grounds. They already include unresolved `needs` dependencies, so the likely distribution is **23 ready, 50 waiting, 0 refused**, if no other issues arise. The TripProof import report is authoritative for the actual result.

## Don't delete the 36 unmatched existing rules

No counterpart is not the same as invalid. Retain those rules until cross-referenced to specific legal authorities, company policies or broker requirements. The current report provides examples but not all 36 IDs; reconciliation of every unmatched rule requires that full export.

## Important legal-implementation risks still open

- Current insurance coverage must be verified for amount/term and applicability, not merely a certificate on file.
- USDOT registration and biennial filings require specific status/date evidence; FMCSA announced temporary suspension of enforcement of biennial updates due on/after June 1, 2026 during its registration-system transition.
- The ADA Part 37 coverage flag should be legally determined per service/operator type, not inferred from a company name.
- The public transit authority exception applies to the specified federal Medicaid NEMT driver/provider safeguards; it should not eliminate other applicable Medicaid/ADA obligations.
- A W-4 or I-9 may be a legally necessary employer record but normally belongs in tracking, not an operational trip-eligibility gate.

## Official sources

- https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-E/section-164.504
- https://www.ecfr.gov/current/title-49/subtitle-B/chapter-III/subchapter-B/part-387/subpart-B/section-387.33T
- https://www.ecfr.gov/current/title-49/subtitle-B/chapter-III/subchapter-B/part-390/subpart-B/section-390.19T
- https://www.fmcsa.dot.gov/registration/temporary-suspension-biennial-update-requirement
