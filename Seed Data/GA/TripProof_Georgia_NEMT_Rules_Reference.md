# TripProof Georgia NEMT Driver Rules (Draft)

**Research date:** 2026-10-21
**Primary source:** [Georgia DCH NEMT Policy Manual, October 2026](https://www.mmis.georgia.gov/portal/Portals/0/StaticContent/Public/ALL/Handbooks/Non-Emergency%20Medical%20Transportation%20%28NEMT%29%20-%20Q4%20October%202026%2020260918170726.pdf)
**Separate conditional source:** [Georgia DHS MAN1425](https://pamms.dhs.ga.gov/ofss/man1425/vehicle-management/driver-requirements-programs-and-recordkeeping/)

Do not enable production hard blocks for rules tagged CONTRACT_PENDING, LEGAL_APPLICABILITY_REVIEW, OFFICIAL_TIMING_AMBIGUOUS or APPLICABILITY_REVIEW without formal confirmation.

## Rules

| Rule ID | Qualification / duty | Rule layer | Source | Timing | Enforcement | Verification |
|---|---|---|---|---|---|---|
| GA-GEN-001 | Valid and appropriate driver license | GA_GENERAL | Georgia driver licensing statutes; GA Medicaid §914.1 | Valid continuously; verify before driving | ALL_APPLICABLE_DISPATCH | OFFICIAL |
| GA-GEN-002 | CDL and endorsements when vehicle/operation requires | GA_GENERAL_CONDITIONAL | GA DDS / applicable CDL laws | Before operation of vehicle requiring CDL | CONDITIONAL_DISPATCH | OFFICIAL |
| GA-MED-001 | Driver age at least 21 | GA_MEDICAID | DCH NEMT §914.2.1 | Before Medicaid driving; continuously | MEDICAID_DISPATCH | OFFICIAL |
| GA-MED-002 | Georgia or eligible bordering-state resident driver license | GA_MEDICAID | DCH NEMT §§914.1, 914.2.1 | Before driving; current at every assignment | MEDICAID_DISPATCH | OFFICIAL |
| GA-MED-003 | 3-year prior driving history record | GA_MEDICAID | DCH NEMT §1006.5.3 | At broker credentialing; refresh per broker contract | MEDICAID_DISPATCH | OFFICIAL_WITH_SOURCE_CLARIFICATION |
| GA-MED-004 | No DUI/drug/alcohol impaired driving conviction in 5 years before employment | GA_MEDICAID | DCH NEMT §914.2.3 | Before Medicaid service; reevaluate if violations occur | MEDICAID_DISPATCH | OFFICIAL |
| GA-MED-005 | 5-year driver license suspension/revocation restriction | GA_MEDICAID | DCH NEMT §914.2.4 and §907.15 | Before service; reevaluate after incident | MEDICAID_DISPATCH | OFFICIAL |
| GA-MED-006 | No prior convictions for sexual crimes/crimes of violence | GA_MEDICAID | DCH NEMT §914.2.2 | Before driver or attendant service | MEDICAID_DISPATCH | OFFICIAL |
| GA-MED-007 | Recent felony conviction requires broker and DCH/agent satisfactory review | GA_MEDICAID | DCH NEMT §914.2.3 | Before service if felony conviction within previous five years | MEDICAID_DISPATCH | OFFICIAL |
| GA-MED-008 | Two qualifying NEMT moving violations and/or at-fault accidents require removal | GA_MEDICAID | DCH NEMT §914.2.5 | Event-triggered; remove from Medicaid service when trigger verified | MEDICAID_DISPATCH | OFFICIAL |
| GA-MED-009 | Criminal background-check screening and fitness determination | GA_MEDICAID | DCH NEMT §§914,1006.5.4 | Before credentialing; thereafter per broker agreement | MEDICAID_DISPATCH | OFFICIAL_SCOPE_VENDOR_METHOD_PENDING |
| GA-FMED-001 | OIG LEIE federal healthcare exclusion eligibility | FEDERAL_MEDICAID | DCH NEMT §915.1.1; federal Medicaid NEMT safeguards | Before Medicaid service; ongoing broker monitoring | MEDICAID_DISPATCH | OFFICIAL |
| GA-MED-010 | SAM.gov exclusions monitoring | GA_MEDICAID_BROKER | DCH NEMT §§608.6,608.8,701.1.2 | Monthly per broker screening obligation | MEDICAID_DISPATCH | OFFICIAL |
| GA-MED-011 | SSA Death Master File screening | GA_MEDICAID_BROKER | DCH NEMT §§608.7,701.1.2 | At employment and annually thereafter | MEDICAID_DISPATCH | OFFICIAL |
| GA-FMED-002 | Valid license federal Medicaid safeguard | FEDERAL_MEDICAID | DCH NEMT §915.1.2 | Before Medicaid service; continuously | MEDICAID_DISPATCH | OFFICIAL |
| GA-FMED-003 | Employer procedure for state drug-law violations | FEDERAL_MEDICAID | DCH NEMT §915.1.3 | Before participation and continuously | COMPANY_REQUIREMENT | OFFICIAL |
| GA-FMED-004 | Employer reporting process for driver history and violations | FEDERAL_MEDICAID | DCH NEMT §915.1.4 | Before participation; event-driven | COMPANY_REQUIREMENT | OFFICIAL |
| GA-MED-012 | First aid training and maintained certificate | GA_MEDICAID | DCH NEMT §916.1 | §916.1 states before driving; §916.2 allows 90 days after assignment; clarify with Verida | MEDICAID_DISPATCH | OFFICIAL_TIMING_AMBIGUOUS |
| GA-MED-013 | Spill kit use and biohazard removal training | GA_MEDICAID | DCH NEMT §916.1 | §916.1 before driving vs §916.2 90-day allowance; clarify | MEDICAID_DISPATCH | OFFICIAL_TIMING_AMBIGUOUS |
| GA-MED-014 | Passenger assistance orientation training | GA_MEDICAID | DCH NEMT §916.1.1 | Per §§916.1-916.2 and broker approval | MEDICAID_DISPATCH | OFFICIAL_TIMING_AMBIGUOUS |
| GA-MED-015 | Safety and sensitivity training (ongoing) | GA_MEDICAID | DCH NEMT §916.1.2 | Ongoing; interval per approved broker/company curriculum | MEDICAID_DISPATCH | OFFICIAL_INTERVAL_UNSPECIFIED |
| GA-MED-016 | Defensive driving training | GA_MEDICAID | DCH NEMT §916.1.3 | Per §§916.1-916.2 and broker curriculum | MEDICAID_DISPATCH | OFFICIAL_TIMING_AMBIGUOUS |
| GA-MED-017 | Wheelchair lift and securement operational competency | GA_MEDICAID_SERVICE | DCH NEMT §§907.12-907.13,907.16; ADA 49 CFR 37.173 as applicable | Before wheelchair assignment; retraining after substantiated securement incident | WHEELCHAIR_DISPATCH | OFFICIAL |
| GA-MED-018 | Driver appearance, badge and professional behavior | GA_MEDICAID_CONDUCT | DCH NEMT §§914.1,907.1-907.8 | Throughout Medicaid service | MEDICAID_DISPATCH | OFFICIAL |
| GA-MED-019 | Passenger pickup, assistance, seatbelt and safe drop-off conduct | GA_MEDICAID_CONDUCT | DCH NEMT §§907.9-907.14 | Every applicable trip | MEDICAID_DISPATCH | OFFICIAL |
| GA-MED-020 | Child-restraint compliance | GA_MEDICAID_CONDUCT | DCH NEMT §907.12; O.C.G.A. §40-8-76 | Every trip carrying covered child | CHILD_TRANSPORT_DISPATCH | OFFICIAL |
| GA-MED-021 | No unsafe impairment; immediate removal if suspected | GA_MEDICAID_CONDUCT | DCH NEMT §§907.1,914.2.3 | At all times on duty; event-triggered | IMMEDIATE_SAFETY_BLOCK | OFFICIAL |
| GA-MED-022 | Wheelchair securement incident retraining clearance | GA_MEDICAID_CONDUCT | DCH NEMT §907.16 | Before restored service after confirmed failure | WHEELCHAIR_DISPATCH | OFFICIAL |
| GA-MED-023 | Daily driver trip manifest and required trip details | GA_MEDICAID_OPERATIONS | DCH NEMT §1007.1 | Each Medicaid service day | TRIP_VERIFICATION | OFFICIAL |
| GA-MED-024 | Maintain driving incidents, complaints and moving-violation records | GA_MEDICAID_OPERATIONS | DCH NEMT §1006.5.7 | Event-triggered and ongoing | MEDICAID_DISPATCH | OFFICIAL |
| GA-MED-025 | Vehicle inspection eligibility and equipment | GA_MEDICAID_VEHICLE | DCH NEMT §§908-910,913 | Before entering service; every 6 months | VEHICLE_DISPATCH | OFFICIAL |
| GA-MED-026 | Infection prevention and sanitization | GA_MEDICAID_CONDUCT | DCH NEMT §§907.18-907.19 | After trips as specified; passive symptom monitoring | SERVICE_PROCEDURE | OFFICIAL |
| GA-CONTRACT-001 | Verida-specific background and MVR package | BROKER_CONTRACT | Signed Verida provider agreement / DCH-approved broker policy | Contract-defined | BROKER_DISPATCH | CONTRACT_PENDING |
| GA-CONTRACT-002 | Verida-specific drug testing | BROKER_CONTRACT | Signed Verida provider agreement / DCH-approved broker policy | Contract-defined | BROKER_DISPATCH | CONTRACT_PENDING |
| GA-CONTRACT-003 | Verida-specific CPR and wheelchair/attendant course requirements | BROKER_CONTRACT | Signed Verida provider agreement / DCH-approved broker policy | Contract-defined | BROKER_DISPATCH | CONTRACT_PENDING |
| GA-CONTRACT-004 | Verida provider/driver credentialing confirmation | BROKER_CONTRACT | Signed Verida provider agreement | Before broker assignments; renewal per contract | BROKER_DISPATCH | CONTRACT_PENDING |
| GA-STATE-001 | Georgia motor passenger carrier registration/permit when applicable | GA_GENERAL_CONDITIONAL | O.C.G.A. §40-1-100; DCH §701.1.4, §1006.2; GA DPS rules | Before covered operations | COMPANY_VEHICLE_DISPATCH | LEGAL_APPLICABILITY_REVIEW |
| GA-DHS-001 | DHS coordinated transport: age >=21 plus 3 years driving experience | GA_DHS_CONDITIONAL | Georgia DHS MAN1425 Driver Requirements | Before DHS service | DHS_DISPATCH | CONDITIONAL_OFFICIAL |
| GA-DHS-002 | DHS coordinated transport: initial certified 7-year MVR and annual review | GA_DHS_CONDITIONAL | Georgia DHS MAN1425 Driver Requirements | Prehire; ongoing annual review | DHS_DISPATCH | CONDITIONAL_OFFICIAL |
| GA-DHS-003 | DHS coordinated transport: points, conviction and suspension checks | GA_DHS_CONDITIONAL | Georgia DHS MAN1425 Driver Requirements | Prehire and event-driven | DHS_DISPATCH | CONDITIONAL_OFFICIAL |
| GA-DHS-004 | DHS coordinated transport: fingerprint GCIC/FBI screening | GA_DHS_CONDITIONAL | Georgia DHS MAN1425 Driver Requirements | Before DHS assignment | DHS_DISPATCH | CONDITIONAL_OFFICIAL |
| GA-DHS-005 | DHS coordinated transport: drug and alcohol testing | GA_DHS_CONDITIONAL | Georgia DHS MAN1425 Driver Requirements | DHS program-defined; pre-hire and ongoing | DHS_DISPATCH | CONDITIONAL_OFFICIAL |
| GA-DHS-006 | DHS coordinated transport: first aid/CPR, passenger assistance, wheelchair, defensive driving | GA_DHS_CONDITIONAL | Georgia DHS MAN1425 Driver Requirements | Per DHS transportation agreement | DHS_DISPATCH | CONDITIONAL_OFFICIAL |
| GA-FMCSA-001 | FMCSA Part 391 driver qualification package | FEDERAL_MOTOR_CARRIER_CONDITIONAL | 49 CFR Parts 390,391 and exclusions | Per applicable FMCSA rule | FMCSA_DISPATCH | APPLICABILITY_REVIEW |
| GA-FMCSA-002 | DOT Part 382 drug/alcohol and Clearinghouse | FEDERAL_MOTOR_CARRIER_CONDITIONAL | 49 CFR Part 382 | Per applicable CDL-related regulation | FMCSA_DISPATCH | APPLICABILITY_REVIEW |
| GA-ADA-001 | ADA proficiency training when operator is covered | FEDERAL_ACCESSIBILITY_CONDITIONAL | 49 CFR §37.173 | Before duties requiring proficiency and ongoing | APPLICABLE_SERVICE_DISPATCH | APPLICABILITY_REVIEW |
| GA-HR-001 | Form I-9 for employees | FEDERAL_EMPLOYMENT | 8 CFR §274a.2 | Employment-eligibility timing | HR_ONBOARDING | OFFICIAL |
| GA-HR-002 | Form W-4 for employees | FEDERAL_EMPLOYMENT | IRS Form W-4 payroll rules | New hire/payroll onboarding | HR_ONBOARDING | OFFICIAL |
| GA-HR-003 | Bloodborne pathogens training if occupational exposure | FEDERAL_OCCUPATIONAL_CONDITIONAL | 29 CFR §1910.1030 | Initial and annual where exposed | OCCUPATIONAL_SAFETY | APPLICABILITY_REVIEW |
| GA-HR-004 | HIPAA workforce privacy training when applicable | FEDERAL_PRIVACY_CONDITIONAL | 45 CFR §§164.530(b),164.308(a)(5) | Per covered entity obligations and company policy | PRIVACY_WORKFORCE | APPLICABILITY_REVIEW |

## Outstanding validation before release

- Reconcile DCH §916.1 (training before driving) with §916.2 (90 days after assignment).
- Confirm DCH §1006.5.3 source “Georgia State Patrol” versus actual Georgia DDS certified MVR availability and bordering-state records.
- Obtain actual Verida provider agreement and DCH-approved credentialing/training standards; confirm background/criminal screenings, testing, and recurrence.
- Confirm Georgia DPS carrier registration applicability, including O.C.G.A. §40-1-100 exceptions.
- Establish per-company vehicle and interstate operation classifications before triggering FMCSA rules.
- Do not apply DHS MAN1425 rules unless the company performs DHS coordinated transportation.

## Sources

- https://www.mmis.georgia.gov/portal/Portals/0/StaticContent/Public/ALL/Handbooks/Non-Emergency%20Medical%20Transportation%20%28NEMT%29%20-%20Q4%20October%202026%2020260918170726.pdf
- https://pamms.dhs.ga.gov/ofss/man1425/vehicle-management/driver-requirements-programs-and-recordkeeping/
