# TripProof — Federal and Medicaid requirements research draft

Prepared November 7, 2026. Uses `tripproof-requirements/1`.

## Files

- `tripproof-medicaid-requirements.json`: **13** Medicaid-specific requirements, including direct federal Medicaid NEMT protections and conditional provider-enrollment/claim responsibilities.
- `tripproof-federal-requirements.json`: **60** federal requirements from ADA transportation, FMCSA, OSHA, HIPAA, FCRA, immigration employment verification and FTA.
- `tripproof-requirements.schema.json`: semantically reconstructed JSON Schema draft 2020-12 from the schema supplied in the conversation.
- `tripproof-import-review.json`: machine-readable list of unresolved `needs` and validation results.

## Verification result

- **PASS**: both JSON files validate structurally against the supplied schema's constraints; no duplicate requirement identifiers across the files; official-domain HTTPS citation links; separated MEDICAID/FEDERAL categories.
- **NOT VERIFIED**: quote-by-quote automated citation import validation against every official page; full historical rule-effective dates; comprehensive exhaustiveness of all conditional U.S. federal requirements. These files are **research drafts, not production-certified catalogs**.
- **WAITING ON NEEDS**: **61 of 73** requirements list missing applicability facts or evidence. TripProof's stated import behavior means those rows will be reported as waiting and will not enforce automatically until the listed `needs` are resolved. Do not treat schema validation as permission to dispatch.

## Important applicability boundaries

1. The direct Medicaid non-emergency medical transportation safeguards are established in 42 U.S.C. 1396a(a)(87). They exclude public transit authorities. TripProof must identify `company.public_transit_authority` before correctly determining applicability to each provider.
2. Federal Medicaid law does **not** prescribe a blanket vehicle inspection schedule or universal CPR, defensive-driving, fingerprint, annual-MVR, or wheelchair training certificate for all NEMT drivers. Such requirements ordinarily arise in other federal coverage, state rules, broker contracts, or company policies.
3. FMCSA conditions use TripProof's `reach.*` facts. Their calculation must account for scope, intrastate versus interstate, vehicle classifications, and the 49 CFR 390.3(f)(4) exemption for transportation of sick and injured persons where properly applicable. Do not assume all NEMT is exempt or covered.
4. Part 382 applies only to covered drivers/employers. FTA Part 655 is separately conditioned on funding and safety-sensitive work, not simply having a transit contract.
5. The current Federal CDL and CMV material is in the **FEDERAL** file and uses conditional reach facts; no state- or broker-specific rules are included.
6. `on_failure=track` is assigned to some administrative obligations which do not necessarily make a particular driver's trip unlawful, not because the duties are optional.
7. Operational proofs like wheelchair securement functionality, actual open defects, federal insurance limits, HOS eligibility, and background-report processes require **new evidence types** beyond document presence.

## Before enabling assignment blocking in production

- Implement and verify the outstanding `needs` items in `tripproof-import-review.json`.
- Compare **every** `citation_text` exactly to the currently operative cited section, accounting for suspended and temporary sections (notably 49 CFR 387.33T and 390.19T).
- Verify effective dates against Federal Register history and review all applicability rules with qualified legal/compliance counsel.
- Run simulated trip assignment tests, including expired licenses, suspended drivers, excluded providers, defective lifts, and carriers not covered by FMCSA.

## Selected official legal source pages

- <https://uscode.house.gov/us/usc/t42/s1396a/>
- <https://www.ecfr.gov/current/title-42/section-431.107>
- <https://www.ecfr.gov/current/title-49/section-37.173>
- <https://www.ecfr.gov/current/title-49/section-391.11>
- <https://www.ecfr.gov/current/title-49/section-387.33T>
- <https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.1030>
