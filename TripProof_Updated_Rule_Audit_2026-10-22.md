# TripProof updated rule audit — October 22, 2026

This is a **technical risk review** of the user-supplied 125-rule JSON, cross-checked against its 13-page PDF summary. This does not certify the entire rule library as legally correct.

- Rules: **125**; draft: **125**; open-question records: **51**.
- Enforcement actions: **78** proposed trip blocks and **47** no-trip-block records.
- Conflict: **41** rules have `blocking=true` and `enforcement_action=NONE_ON_TRIP`.

## Action register (32 findings: P0=8, P1=17, P2=7)

### P0: ENGINE
**Issue:** 41 rules set blocking=true while enforcement_action=NONE_ON_TRIP; old and new control fields may conflict.
**Fix:** Make enforcement_action the sole dispatch authority; migrate/remove legacy blocking and gate or formally distinguish them; test every legacy caller.
**Basis:** JSON field comparison; **Validation:** Code search and live dispatch tests.

### P0: FL_TRANSIT_DAILY_INSPECTION
**Issue:** Rule says before daily operation but recurrence is once; one historic DVIR may permanently satisfy it.
**Fix:** Evaluate each vehicle for each operating day/shift before release, with matching time, inspection outcome, and resolved defects.
**Basis:** JSON; F.A.C. 14-90.006(8); **Validation:** Dispatch test on consecutive dates.

### P0: FL_INTRASTATE_FULL
**Issue:** Blocking rule has process evidence source=null, so there may be no possible way to satisfy it.
**Fix:** Replace with an applicability fact that activates individual federal/state driver qualification rules; retire unenforceable umbrella blocker.
**Basis:** JSON; **Validation:** Validate applicability against Florida statutes.

### P0: GA_NET_SECUREMENT_CLEARED
**Issue:** Rule describes retraining only after a confirmed securement incident but applies unconditionally to every GA Medicaid driver.
**Fix:** Condition it on an unresolved confirmed securement event, require retraining dated after incident plus authorized clearance, and reset upon new incident.
**Basis:** JSON; **Validation:** Georgia DCH applicability and event tests.

### P0: ROAD_TEST
**Issue:** Accepted license classes A/B/C are not proof of a valid CDL; ordinary state Class C license might be treated as equivalent road test.
**Fix:** Require a verified CDL as defined by 49 CFR 383.5 and matched vehicle category, or a valid recent road-test certificate permitted by 49 CFR 391.33.
**Basis:** JSON; 49 CFR 391.33; **Validation:** Automated non-CDL Class C negative test.

### P0: AUTO_LIABILITY
**Issue:** No condition; a simple uploaded COI passes even without validated limits, vehicles, covered period or insurer. Never stops trips despite potentially lacking legally required coverage.
**Fix:** Split company policy compliance from per-vehicle/operation coverage eligibility; verify effective dates, named insured, covered vehicles, minimum applicable limits, and contract requirements.
**Basis:** JSON; PDF p4; **Validation:** Legal coverage matrix and dispatch tests.

### P0: GA_NET_LICENSE
**Issue:** Any license record satisfies GA Medicaid rule; no check of issuing state, bordering state, residence, license class or expiration in validation logic.
**Fix:** Validate issuer/residency and required class, expiry, active status; use verified license facts, not uploaded presence alone.
**Basis:** JSON; **Validation:** State Medicaid manual plus broker approval.

### P0: GA_NET_BACKGROUND
**Issue:** Review is required, but plain evidence is a background report; no structured Georgia disqualifier/felony broker clearance and verified-source checks.
**Fix:** Add explicit findings, disqualification categories, look-back, authorized clearance, and broker-produced screening provenance; never auto-clear on report upload.
**Basis:** JSON; PDF p1; **Validation:** Georgia DCH manual and Verida.

### P1: DVIR
**Issue:** Ongoing, per-day duty modeled recurrence once; report says daily no-defect passenger DVIR, but currently published 49 CFR 396.11 text includes a no-defect exemption.
**Fix:** Model applicable defect-reporting duties by current regulatory scope; review 2026 text, exceptions, previous defects and repair certification; no permanent once-based satisfaction.
**Basis:** JSON; current 49 CFR 396.11; **Validation:** Federal compliance review of 2026 amendment.

### P1: GA_NET_VEHICLE_INSPECTION
**Issue:** Calendar-six-month interval corrected, but initial inspection must satisfy program entry window and approved inspection.
**Fix:** Implement new-entry initial-window validator and 6 calendar-month renewal; confirm date of entering service and broker approval.
**Basis:** JSON; Georgia DCH 910.2; **Validation:** Verida/DCH verification.

### P1: CLEARINGHOUSE_CONSENT
**Issue:** Annual renewal is hardcoded despite multi-year general limited-query consent being permitted.
**Fix:** Use stated consent effective/expiration dates and permitted employment scope, not automatic annual re-signing.
**Basis:** JSON; 49 CFR 382.701/382.703; **Validation:** FMCSA current guidance.

### P1: FL_INTRASTATE_382
**Issue:** Rule claims a whole DOT drug/alcohol program but validates only a preemployment test; related downstream rules use reach.part382 and may never fire.
**Fix:** Separate operating program applicability from preemployment screening and each random, post-accident, reasonable suspicion and other obligation.
**Basis:** JSON; **Validation:** Florida statute and operations applicability review.

### P1: LIFT_LOAD_TEST
**Issue:** Regulatory citation 49 CFR 37.163 concerns maintenance of lifts by public entities, not a universal lift load-test certificate.
**Fix:** Reclassify as an explicit contract/manufacturer/company requirement when supported; preserve actual lift operational maintenance obligations separately.
**Basis:** JSON; 49 CFR 37.163; **Validation:** Contract/OEM evidence.

### P1: FL_TRANSIT_MAINTENANCE
**Issue:** Annual recurrence for preventive maintenance despite description requiring manufacturer-based mileage/time maintenance.
**Fix:** Replace annual timer with per-vehicle OEM time/mileage schedules plus overdue maintenance and defect work orders.
**Basis:** JSON; **Validation:** F.A.C. 14-90 and OEM maintenance.

### P1: GA_NET_PROVIDER_REGISTRATION
**Issue:** Requires uploaded DPS/county registration for every GA Medicaid company even when legal registration is conditional; due text copied from BBP plan.
**Fix:** Add adjudicated required/not-required/unknown registration status per authority and vehicle/operation; remove copied annual review text.
**Basis:** JSON; PDF p2; **Validation:** Georgia DPS/county and DCH.

### P1: MEDICAID_ENROLLMENT
**Issue:** Description says a broker-paid company does not need Medicaid enrollment and that the broker is the enrolled provider; this is not a safe nationwide universal statement.
**Fix:** Determine whether each state/program requires direct enrollment, ordering/referring enrollment, rendering/provider registration or broker-only credentialing. Never infer from payment channel alone.
**Basis:** JSON; **Validation:** State Medicaid and signed payer contract.

### P1: GA_NET_DMF
**Issue:** Broker-controlled death-master-file duty is represented as a blanket company driver record.
**Fix:** Make broker oversight default; activate company requirement only if specifically delegated by an actual contract.
**Basis:** JSON; Georgia DCH 608.7; **Validation:** Verida contract verification.

### P1: DHS_FINGERPRINT
**Issue:** FBI fingerprint document automatically satisfies a two-source GCIC/FBI screening; renewal policy unresolved.
**Fix:** Require verified screening scope and results through authorized process, plus eligibility determination; verify renewals with DHS.
**Basis:** JSON; **Validation:** GA DHS manual and agreement.

### P1: DHS_SECUREMENT
**Issue:** Applied to all DHS drivers regardless of service/equipment; 90-day training timing not verified.
**Fix:** Scope to covered passenger-assistance duties and any program-wide DHS contractual rule; confirm deadline before enforcing.
**Basis:** JSON; **Validation:** Georgia DHS manual/contract.

### P1: GA_NET_FIRST_AID
**Issue:** Initial deadline set to 90 days even though Georgia Medicaid manual includes before-driving language; automatic hard block may be wrong in either direction.
**Fix:** Obtain DCH/Verida written clarification; encode conditional grace policy separately from required qualification.
**Basis:** JSON; Georgia DCH 916; **Validation:** DCH/Verida.

### P1: GA_NET_MVR
**Issue:** MVR upload and review stand in for 5-year suspension and licensing disqualifications; approved source ambiguity remains.
**Fix:** Split report acquisition, findings evaluation, and broker review; verify DDS/GSP accepted source and lookbacks.
**Basis:** JSON; Georgia DCH 914/1006; **Validation:** Verida/DCH.

### P1: EXCLUSION_SAM_GOV
**Issue:** Fixed 3-day recurrence is a product choice rather than cited legal interval; can incorrectly show expired compliance.
**Fix:** Store legal/contract check frequency separately from dataset freshness and service execution cadence.
**Basis:** JSON; **Validation:** Payer/contract requirements.

### P1: CLEARINGHOUSE_PREEMP
**Issue:** JSON corrected recurrence to once, but still retains an open question claiming every 365 days; review summary is stale.
**Fix:** Mark question resolved after reviewer confirms 49 CFR 382.701(a); distinguish annual limited query as separate requirement.
**Basis:** JSON/PDF; **Validation:** Review metadata consistency.

### P1: GA_NET_VEHICLE_INSPECTION
**Issue:** PDF top-15 summary still says 183 days even though JSON has 6 calendar months.
**Fix:** Generate summary only from current rule values; show note as historical correction, not outstanding finding once fixed.
**Basis:** PDF p2 / JSON; **Validation:** Report generator test.

### P1: DHS_FINGERPRINT
**Issue:** PDF top-15 summary references old Florida Level 2 text/5-year recurrence while JSON now has GA GCIC/FBI and once; remaining real issue is verification of accepted evidence and renewal.
**Fix:** Refresh issue text to align with current JSON; separate resolved historical error from open question.
**Basis:** PDF p1 / JSON; **Validation:** Report generator.

### P2: PHI_POLICY
**Issue:** Policy record and driver acknowledgment use related citations but company policy describes an acknowledgment.
**Fix:** Separate versioned company policy publication from per-driver acknowledgment signature; label required-by-contract vs law accurately.
**Basis:** JSON; **Validation:** HIPAA/BAA legal review.

### P2: BBP_PLAN_ADMINISTRATOR
**Issue:** TripProof convention is presented as OSHA regulation rather than optional operational ownership.
**Fix:** Classify as company policy/workflow best practice; do not represent as distinct OSHA mandate.
**Basis:** JSON; **Validation:** OSHA regulation comparison.

### P2: BUSINESS_LICENSE
**Issue:** Florida-specific local business tax receipt has US jurisdiction and every-company reach.
**Fix:** Create locality-specific business license requirement based on actual city/county; rename neutral master qualification.
**Basis:** JSON; **Validation:** Local jurisdiction review.

### P2: FCRA_FORMS
**Issue:** Disclosure/authorization evidence is treated as a driver trip qualifier when it is a prerequisite to obtaining a CRA report.
**Fix:** Model screening authorization as prerequisite to vendor order and adverse action, not independently a lasting trip qualification.
**Basis:** JSON; **Validation:** FCRA workflow.

### P2: POSTACCIDENT_TEST
**Issue:** Accident-triggered test modeled as a once-based qualification; response evidence contains only test result, not required timing, refusal, or documented exceptions.
**Fix:** Create accident-specific task with regulatory eligibility, collection windows, result, exceptions and disposition.
**Basis:** JSON; **Validation:** 49 CFR 382.303 and Part 40.

### P2: GA_NET_ATFAULT
**Issue:** Incident-based restriction has one-time recurrence; ensure new accidents/convictions trigger re-evaluation.
**Fix:** Use event-driven recalculation and keep evidence register complete, including conviction and at-fault determination.
**Basis:** JSON; **Validation:** Georgia DCH 914.2.5.

### P2: FL_TD_DRUG_TESTING
**Issue:** Condition uses company.transit rather than a confirmed Transportation Disadvantaged program applicability determination.
**Fix:** Use confirmed CTD/TD-service contract and exact program scope, not general FDOT covered transit flag.
**Basis:** JSON; **Validation:** Florida CTD program authority.

## Recommended implementation order

1. Keep all legal rules in Draft; ensure draft metadata does not mask safety-critical statutory restrictions in live operations.
2. Repair the dispatch enforcement interface and retire legacy `blocking` / `gate` ambiguity.
3. Repair unrecoverable blockers, unsafe evidence shortcuts, and per-shift/event-based evaluations.
4. Resolve authoritative legal and broker ambiguities and obtain written determinations.
5. Run all four company profiles (FL private pay, FL Medicaid, GA Medicaid, GA DHS), including wheelchair/nonwheelchair and CMV/non-CMV vehicles.
6. Approve rules individually with test evidence, then roll out under a feature flag.

## Recommended minimum acceptance tests

- A company record with `NONE_ON_TRIP` cannot refuse a trip merely because `blocking=true` in the legacy field.
- A missing legally required vehicle insurance/authorization can still trigger the *proper, reviewed* operational restriction; do not simply disable all company-level protections.
- Yesterday’s pre-operational inspection cannot authorize today’s covered 14-90 vehicle operation.
- A state Class C noncommercial license cannot substitute for a CDL road-test equivalent.
- GA Medicaid securement-retraining applies only after a qualifying confirmed incident, but a later incident reopens it.
- An unresolved or insufficient criminal screening does not count as a cleared Georgia Medicaid driver.
- A valid multi-year Clearinghouse consent does not expire just because 365 days elapsed.
- An approved state rule never blocks a trip in the other state.
- Every eligibility event saves matched facts, versioned rules, evidence, timestamp and reason.
