# TripProof Driver Compliance — Definitive Restructuring Blueprint

**Version:** 1.0 | **Prepared:** 2026-10-20 | **Scope:** Florida-first, multi-state NEMT SaaS design

> **Implementation status:** Proposed software architecture, not a legal opinion. Regulatory applicability rules must be reviewed and approved against actual state programs, operations, and contracts before deployment. Do not silently mark a rule inapplicable when essential facts are unknown.

## Locked architectural decisions

1. One *qualification catalog* identifies what evidence or competency TripProof can track; a qualification is not itself universally required.
2. Many versioned *requirement rules* (federal general, state general, federal Medicaid, state Medicaid, broker/payer contract, company policy) may point to the same qualification.
3. *Applicability* is evaluated using structured company, operation, vehicle, driver, program, geography, and contract facts. It is separate from *satisfaction*.
4. Evidence is stored once, reused for multiple requirements if and only if it meets each rule's exact evidence and currency conditions.
5. Hire status, employment onboarding status, program qualification, and trip-level dispatch authorization are independent decisions.
6. Drivers are never globally 'compliant' or 'noncompliant' without a scope and evaluation timestamp.
7. Unknown legal applicability means `NEEDS_DETERMINATION`, not `NOT_APPLICABLE`.
8. Cannot override a legally required hard block with an ordinary 'admin override'; certified exceptions need evidence, authority and specific scope.
9. Regulations, rules, source documents, rule evaluation results and changes are versioned and audited. Never overwrite historical decisions.
10. Dispatch evaluates the candidate driver+vehicle+trip+program+contract+date-time combination before assignment and again before service.

## Taxonomy

**Authority categories:** `FEDERAL_GENERAL`, `STATE_GENERAL`, `FEDERAL_MEDICAID`, `STATE_MEDICAID`, `CONTRACT_OR_COMPANY`.

**Authority types:** `STATUTE`, `REGULATION`, `AGENCY_GUIDANCE`, `CONTRACT`, `PAYER_POLICY`, `COMPANY_POLICY`.

**Scope / enforcement levels:** `HR_ONBOARDING`, `COMPANY`, `DRIVER_GENERAL`, `PROGRAM`, `BROKER`, `SERVICE_TYPE`, `VEHICLE_CLASS`, `TRIP_ASSIGNMENT`.

**Decision status:** `QUALIFIED`, `NOT_QUALIFIED`, `NEEDS_REVIEW`, `NOT_APPLICABLE` (requires affirmative inapplicability evidence), optionally `NOT_EVALUATED`.

**Evidence status:** `MISSING`, `AWAITING_DRIVER`, `AWAITING_COMPANY`, `AWAITING_THIRD_PARTY`, `RECEIVED`, `UNDER_REVIEW`, `VERIFIED`, `REJECTED`, `EXPIRED`, `REVOKED`.

**Applicability status:** `REQUIRED`, `NOT_APPLICABLE`, `NEEDS_DETERMINATION`.

**Enforcement behavior:** `HARD_BLOCK`, `SCOPED_BLOCK`, `WARNING`, `ADMIN_ONLY`, `NO_DISPATCH_EFFECT`. These are separate from legal source category.

## 1. Company operating profile: source of facts

Save as *versioned* `company_operating_profiles`, including `company_id`, effective dates, approver, location/state, W-2/contractor/mixed engagement types, offered programs, state Medicaid program participation, and the compliance point of contact. Never assume headquarters=service state.

Save separate `company_operations` for each operational model and geography. Facts include actual interstate activity, passenger-for-compensation status, types of vehicles used, relationships to covered bus transit systems, contracting model, and service area.

Save `company_programs`, `company_contracts`, `contract_rule_sets` for payer/broker specific enrollment and terms. Every contract has specific effective dates, program, state, service types, source document, scope and review status. An unreviewed contract is `NEEDS_REVIEW`, not blank.

Save `vehicle_profiles` and `vehicle_regulatory_assessments` with manufacturer capacity (including driver), GVWR and other relevant weights, wheelchair features, operating contexts, relevant license class/endorsement, CMV and CDL independent assessments, State chapter 14-90 coverage, assessor, assessment date, authority and explanation. CMV status is not the same as CDL status.

Save `driver_profiles` with employment/contractor classification, job role, state(s) of operation, allowed vehicle classes, service competencies, service program authorizations, broker approvals, and assignment restrictions.

**Company setup should not be 'Approved' until all material scope questions have been resolved or explicitly flagged for human regulatory review.** Restrict impacted operations pending determination; unaffected services may proceed.

## 2. Single master qualification catalog

Use stable IDs, not mutable labels. Initial set:

- `DRV-001` valid driver's license; `DRV-002` correct license class and endorsements; `DRV-003` driving history / MVR process; `DRV-004` annual MVR inquiry and review when applicable; `DRV-005` driver application/employment history; `DRV-006` FMCSA safety performance history investigation when applicable.
- `BKG-001` OIG LEIE; `BKG-002` SAM.gov exclusions; `BKG-003` Florida Level 1; `BKG-004` Level 2 where independently applicable; `BKG-005` commercial criminal screen; `BKG-007` other-state checks; `BKG-008` protective registries. Avoid treating FDLE/NSOPW/employment-history Level 1 subchecks as independent top-level requirements.
- `TRN-001` disability/passenger assistance competency; `TRN-002` lift/ramp; `TRN-003` wheelchair securement; `TRN-004` privacy/HIPAA when applicable; `TRN-005` bloodborne pathogens when occupational exposure exists; `TRN-006` defensive driving; `TRN-007` safety orientation; `TRN-008` emergency response; `TRN-009` named PASS certification only when actually required; `TRN-010` broker training.
- `MED-001` FMCSA medical qualification; `MED-002` FDOT transit medical exam when covered; `DRA-001` DOT pre-employment test; `DRA-002` Clearinghouse when Part 382 covered; `DRA-003` covered testing program; `DRA-004` non-DOT company drug screen; `DRA-005` policy acknowledgment; `DRA-006` supervisor reasonable-suspicion training.
- `EMP-001` application; `EMP-002` I-9; `EMP-003` W-4; `EMP-004` contractor agreement; `EMP-005` handbook; `EMP-006` CRA authorization; `EMP-007` license reporting acknowledgment; `EMP-008` Florida screening attestation when applicable.

Catalog item = what TripProof can verify. Rule = why, for whom, when. Evidence = what actually occurred.

## 3. Rule engine

### Rule record

`rule_id`, `qualification_id`, `authority_category`, `authority_type`, `authority_citation`, `authority_document_id`, `authority_section`, `jurisdiction`, `program_ids`, `contract_id`, `effective_from`, `effective_to`, `scope_expression`, `prerequisite_expression`, `accepted_evidence_rules`, `due_rule`, `renewal_rule`, `enforcement_scope`, `enforcement_action`, `disqualifier_logic`, `legal_review_status`, `approved_by`, `approved_at`, `version`, `supersedes_rule_id`.

### Applicability logic

Only evaluate published, effective rules. Inputs are immutable snapshots of company+driver+vehicle+trip+date context. Use three-valued logic `TRUE / FALSE / UNKNOWN`, with explanations for unknown facts. `TRUE` creates obligation; `FALSE` records reason for not applicable; `UNKNOWN` creates needs determination. Reassess on profile, evidence, contract, rule or assignment change and once daily for expirations.

### Satisfaction logic

Compare obligation to records and accept a piece of evidence only if type, subject, source, operating program, dates, verification and specific contractual criteria match. Do not infer recurrence from vendor report completion. Every satisfied evaluation identifies exact evidence IDs and rule versions.

### Rule precedence

Treat multiple sources as a conjunction of separately evaluated obligations, not as a single overwritten source. A more stringent contract may add evidence or shorter renewal. An actual statutory exemption must be precisely scoped and approved; do not let a lower-authority company policy erase a legal requirement.

### Temporal rules

Distinguish `issue_date`, `effective_date`, `expiration_date`, `last_screened_at`, `next_due_at`, `document_received_at`, `vendor_completed_at`, `reviewed_at`, `service_date`. Save timezone-aware timestamps and explicit date-only semantics for licenses. Evaluate at time of assignment *and* time of service.

## 4. Legal seed rules for Florida: approval required before go-live

- Florida Medicaid NEMT driver Level 1 / authorized equivalent — F.S. 409.907(8)(a)4, F.S. 435.03, applicable program and contracting conditions. **Not universal to private pay.** Review equivalence before acceptance.
- Federal Medicaid driver safeguards — Social Security Act §1902(a)(87), CMS transportation guidance: OIG/federal program exclusion, valid driver's license, provider process for state drug-law violations, provider process for reporting driver's history and traffic violations. The law specifies mechanisms/provider processes; do not translate every safeguard into an automatic recurring document requirement.
- FMCSA Parts 390/391 qualification framework — only when covered based on operation, vehicle and exceptions; separate CMV applicability from CDL requirement. 49 CFR 391.25 annual MVR applies to relevant covered operations, not every non-CDL driver.
- DOT Part 382 drug testing — linked to CDL-covered operations; never infer applicability from paid transportation alone.
- Florida FDOT Chapter 14-90 — ascertain bus transit system scope under Rule 14-90.002, including some private transit contracts and smaller paratransit vehicles. Medical exam under Rule 14-90.0041 only when covered.
- ADA §37.173 proficiency-based training — covered fixed-route and demand-responsive transport personnel must have appropriate training; do not mandate one branded PASS certificate as federal law.
- OSHA 29 CFR 1910.1030 — exposure determination controls; initial/annual training for covered employees with occupational exposure.
- I-9 (employees) and W-4 (payroll) — HR obligations with distinct timing; do not treat every administrative defect as a driver safety disqualification.

## 5. Four separate gates

1. **Hiring decision**: employer determines whether to hire; screening and employment prerequisites depend on law and company policy; do not equate 'not fully onboarded' to illegal to hire.
2. **HR onboarding**: I-9/payroll/company documents and deadlines; HR-specific compliance workflow.
3. **Program qualification**: federal/general + state/general + federal/state Medicaid, contract/service-specific obligations evaluated for this driver's authorized programs.
4. **Dispatch authorization**: live evaluation of `company + driver + vehicle + service type + payer/program + broker contract + trip geography + time`; also vehicle compliance, safety/shift status, and scheduling conflict.

Hard legal blocks cannot be overridden via generic button. For non-legal warning exceptions require RBAC, reason, approver, expiration, documented basis. Expiration mid-route: flag and prevent new assignment; route immediate safety handling rather than unsafe forced stoppage.

## 6. User interface

**Company Settings → Compliance Configuration**: Operating Profile; State/Program Participation; FMCSA/FDOT Assessments; Broker Contracts; Company Policies; Approved Rule Sets; Change History.

**Drivers → Driver Profile**: Overview; HR Onboarding; Requirements; Documents & Evidence; Screenings; Training; Service Qualifications; Expirations; Audit History.

**Requirement details drawer**: stable ID; plain-English rule; authority category + citations; date/version; why applicable; required evidence; collected evidence; completion/renewal; reviewing user; next action/owner; exactly which operations are blocked; prior decisions.

**Driver overview**: hired status ≠ onboarding status ≠ program qualification; show separate indicators for Private Pay Ambulatory, Medicaid Ambulatory, Medicaid Wheelchair, each contracted broker, covered CMV operations. Only current satisfied status uses green check. `Not Applicable` uses neutral state with reason; `Needs Review` stays visible.

**Dispatch**: `POST /dispatch/assignments/eligibility-check` evaluates exact contextual combination; response includes `eligible`, `blockers[]`, `warnings[]`, `evaluation_id`, `rule_versions[]`, `expires_at`/snapshot hash; recheck when committing assignment and when starting service.

## 7. Suggested normalized persistence model

- Master: `qualification_catalog`, `rule_sources`, `rule_source_versions`, `requirement_rules`, `requirement_rule_versions`, `approved_exceptions`.
- Operating facts: `company_operating_profiles`, `company_operations`, `company_programs`, `company_contracts`, `contract_rules`, `vehicle_profiles`, `vehicle_regulatory_assessments`, `driver_profiles`, `driver_service_authorizations`.
- Screening and evidence: `driver_licenses`, `evidence_records`, `evidence_files`, `screening_cases`, `screening_components`, `training_records`, `qualification_reviews`, `requirement_evidence_links`.
- Evaluation: `requirement_obligations`, `applicability_evaluations`, `satisfaction_evaluations`, `program_qualification_snapshots`, `dispatch_eligibility_evaluations`.
- Workflow and governance: `compliance_tasks`, `compliance_notifications`, `regulatory_reviews`, `audit_events`, `migration_legacy_links`.

Use UUID primary keys, company_id on tenant-controlled records, `created_at`, `updated_at`, valid/effective timestamps, source/version IDs and actor ID. Configure database Row-Level Security or equivalent robust application isolation. Use immutability for decisions, audit logs, source versions, and screening results; add new versions instead of rewriting.

### Evaluation pseudocode

```
for rule in approved_effective_rules(service_datetime):
    applies = evaluate_trivalent(rule.scope_expression, context)
    record_applicability(rule, context_hash, applies)
    if applies == UNKNOWN:
        add_review_required(rule, missing_fact_names)
    elif applies == TRUE:
        obligation = upsert_obligation(driver, rule, scope)
        evidence = collect_candidate_evidence(obligation)
        result = verify_evidence_against_rule(evidence, rule, service_datetime)
        record_satisfaction(obligation, result, evidence_ids)

blocks = relevant_unsatisfied_hard_obligations + unresolved_material_scope
status = NOT_QUALIFIED if blocks else QUALIFIED
record_snapshot(status, context_hash, source_rule_versions, evidence_ids)
```

Separate safety-critical `not qualified` from `needs legal determination` in UI, but do not release the affected assignment while the material rule is unresolved.

## 8. Source-to-current-screen migration map

- Valid Driver's License → `DRV-001`, preserve document and verification.
- Motor Vehicle Records → `DRV-003`, migrate company policy independently from the federal Medicaid driving-history disclosure obligation.
- OIG LEIE → `BKG-001`, federal Medicaid when applicable; keep historical screening events.
- SAM.gov → `BKG-002`, apply only the verified program/contract rules; not automatic universal requirement.
- Form I-9 → `EMP-002`, HR onboarding; not a blanket pre-hire dispatch block.
- Form W-4 → `EMP-003`, payroll onboarding only for employees.
- HIPAA Privacy and Security Training → `TRN-004`, apply under covered workforce/policy/contract analysis.
- Passenger Assistance and Wheelchair Securement → split competency (`TRN-001`/`TRN-003`) when separately verifiable; reuse same certificate as evidence as appropriate.
- Bloodborne Pathogens Training → `TRN-005`, apply via exposure determination or contract.
- Annual Inquiry/Review Driving Record → `DRV-004`, conditional FMCSA or contract/company policy.
- Pre-Employment Drug Screen (Additional Panels) → `DRA-004`, company policy or contract, separate from DOT Part 382.
- Add Level 1 → `BKG-003` for FL Medicaid driver program; subcomponents FDLE statewide, employment history, NSOPW and disqualification review.
- Review all old global `required` flags; migrate to `legacy_requirement_configuration` for traceability but do not treat as legislative truth.

## 9. Migration sequence (no destructive cutover)

**M0 Freeze and backup:** feature flag; snapshot DB and files; export existing requirement definitions, classifications, completions, reviews, due dates and assignments. Assign historical legacy IDs. Do not delete legacy fields.

**M1 Create source library and catalog:** create approved catalog IDs and draft mapping. Legal/compliance reviewer approves source and applicability before production enablement.

**M2 Add operating profiles:** request minimum missing company and vehicle facts; label unresolved determinations; maintain old app behavior while shadow mode runs.

**M3 Backfill evidence:** migrate driver documents once into evidence records; hash files, preserve dates and reviewers; migrate check history. Mark uncertain migrated records `UNDER_REVIEW`.

**M4 Run shadow evaluation:** calculate new status without enforcing it; compare per driver/vehicle/program to current system; categorize discrepancies by missing facts, incorrectly universal legacy rules, invalid evidence, stale contract or true compliance issues. Resolve every material discrepancy.

**M5 Pilot per tenant:** first with a test FL private-pay company; then a FL Medicaid NEMT company; then a covered 14-90 fleet, a federal CMV operation, and mixed broker/vehicle company. Keep rollback to old UI without destroying new record history.

**M6 Switch application views:** Replace generic green check icons and broad Federal/State lists; show scoped program qualifications. Employment forms move to HR tab. Preserve read-only old archive for audits.

**M7 Enable enforcement:** hard blocks only after verified legal applicability and tested data. Enable dispatch preflight and transaction-time recheck; alert on profile changes.

**M8 Expand:** versioned new state packs and broker requirements; no schema changes necessary for routine rule additions.

## 10. Scenarios / required tests

1. FL small sedan, private pay only, not covered by 14-90/FMCSA: valid license and applicable safety/training; **no automatic FL Medicaid Level 1**.
2. Same driver assigned FL Medicaid trip: Level 1/authorized equivalent required; federal Medicaid safeguards apply; block if screening missing.
3. FL Medicaid + Modivcare wheelchair trip: add documented contract provisions and verified wheelchair competency, vehicle eligibility.
4. Broker contract unreviewed: `NEEDS_REVIEW`; don't invent PASS or background-frequency requirements; block affected release when an unknown could cause noncompliance.
5. Covered 14-90 operation in non-CDL vehicle: apply covered FDOT rules despite non-CDL license.
6. FMCSA-covered CMV with non-CDL driver: apply applicable FMCSA safety qualification rules; do not assume DOT Part 382 without CDL coverage.
7. CDL/Part 382-covered operation: enable correct DOT drug-testing/Clearinghouse requirements.
8. Annual MVR policy every 6 months while federal rule annual: separate obligations; same verified record can satisfy both when conditions align.
9. A completed vendor package lacking direct-FDLE provenance: Level 1 remains unresolved.
10. License expires tomorrow: qualified today, blocked for tomorrow's scheduled trip.
11. License revoked today: re-evaluate existing assignments and flag affected ones.
12. One driver has verified wheelchair training and uses both broker and private-pay services: reuse evidence but evaluate two separate sets of rules.
13. One company has FL and GA operations: state applicability based on actual assignment geography and operations, not HQ.
14. Company changes broker contract: prospective re-evaluation, no historic status erasure.
15. Missing 14-90 classification: `NEEDS_DETERMINATION`, not exempt.
16. W-4 missing from W-2 driver: HR/payroll action, not an automatic Medicaid driving-qualification block.
17. Contractor with company policy: do not create an employee W-4 obligation.
18. Potential background-match without verification: review pending, not false positive as automatic permanent disqualification.
19. A second driver/vehicle substitution must cause dispatch eligibility re-evaluation.
20. Tenant A's evidence, keys and evaluations invisible to Tenant B in APIs, queries and reports.

## 11. Security and audit requirements

Restrict criminal history reports, SSNs and sensitive medical qualifications to authorized compliance/HR roles; driver dispatchers see only qualification outcome and actionable non-sensitive reason. Use encrypted object storage, tenant isolation, signed download URLs, role checks, access logging, immutable evidence versions and retention/deletion policy by governing law/contract. Vendor credentials in secrets manager. Use consent and FCRA adverse-action workflow for covered CRA checks. TripProof should log legal-review status and confidence; do not market draft rule definitions as definitive legal advice.

## 12. Rollout / definition of done

- **Release A:** source library, operating profiles, master catalog, rule schema, initial FL seed, evidence mapping, shadow evaluations.
- **Release B:** new driver UI, legal reviews, migration reconciliation, program qualification outcomes, old UI read-only.
- **Release C:** dispatch real-time eligibility checks, notifications and expired-evidence restrictions, contract-specific qualification.
- **Release D:** automated vendor results, bulk renewals, audit export, additional states and brokers.

**Done means:** every active requirement displayed for a driver identifies an approved source and explanation, every evidence-derived completion is traceable, unknown applicability never looks approved, HR and dispatch statuses remain independent, and test cases pass without manual source-code changes to support each new state or broker.

## Primary source references (review on each rule-pack update)

- CMS Medicaid Assurance of Transportation: https://www.medicaid.gov/medicaid/benefits/assurance-of-transportation
- Florida 2026 Statute 409.907: https://m.flsenate.gov/Statutes/409.907
- Florida 2026 Statute 435.03: https://www.flsenate.gov/Laws/Statutes/2026/435.03
- Florida 2026 Statute 316.87: https://www.flsenate.gov/Laws/Statutes/2026/316.87
- FDOT 14-90 definition: https://flrules.org/gateway/RuleNo.asp?ID=14-90.002
- FDOT 14-90 medical: https://flrules.org/gateway/RuleNo.asp?ID=14-90.0041
- FMCSA Passenger-carrier Rules: https://www.fmcsa.dot.gov/safety/passenger-safety/guidelines-and-driver-qualifications-motor-carriers-passengers-parts-390-391
- 49 CFR 391.25 annual MVR: https://www.law.cornell.edu/cfr/text/49/391.25
- 49 CFR 382.103 CDL drug testing: https://www.law.cornell.edu/cfr/text/49/382.103
- ADA 49 CFR 37.173: https://www.law.cornell.edu/cfr/text/49/37.173
- OSHA bloodborne pathogens: https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.1030/
- USCIS I-9 instructions: https://www.uscis.gov/sites/default/files/document/forms/i-9instr.pdf

