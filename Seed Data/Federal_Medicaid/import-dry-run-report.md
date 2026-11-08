# Federal + Medicaid Import - Dry Run Report

Run 11/08/2026 on dev against `tripproof-medicaid-requirements-unchanged.json` and `tripproof-federal-requirements-corrected.json` (TripProof_Federal_Medicaid_Import_Corrections), with the two Operations questions (public transit authority, demand-response service) in place. **Nothing was changed in TripProof.**

| Requirements | Ready | Waiting | Refused | Current rules with no counterpart |
|---|---|---|---|---|
| 73 | 26 | 47 | 0 | 35 |

Every file passed the schema. Every citation was fetched from eCFR, govinfo or uscode.house.gov and compared word for word, and the cited section had to be the section linked.

## Refused - fix in the file


None. The three refused on 11/07 (FED-CO-018, FED-CO-023, FED-CO-024) are corrected and verified.

## Ready - can be evaluated today

Loaded as drafts; none can refuse a trip until approved in Rule Review. ✱ = the rule it replaces has its own code in TripProof, to be kept or retired on purpose.

| Id | Requirement | Category | Evidence TripProof reads | Replaces |
|---|---|---|---|---|
| MED-CO-001 | Medicaid NEMT provider must not be federally excluded | Medicaid | `exclusioncheck:OIG_LEIE` | new |
| MED-DRV-001 | Medicaid NEMT driver must not be federally excluded | Medicaid | `exclusioncheck:OIG_LEIE` | EXCLUSION_OIG_LEIE |
| MED-DRV-002 | Medicaid NEMT driver has a valid license | Medicaid | `license` | DRIVER_LICENSE_COPY ✱ |
| MED-CO-006 | State Medicaid provider enrollment and screening | Medicaid | `credential:MEDICAID_ENROLLMENT` | MEDICAID_ENROLLMENT |
| MED-CO-008 | Disclose relevant Medicaid program-related convictions | Medicaid | `credential:MEDICAID_CONVICTION_DISCLOSURE` | new |
| FED-DRV-003 | FMCSA driver minimum age 21 | FMCSA / DOT & CDL | `driverfact:driver.age21` | DRIVER_AGE |
| FED-DRV-004 | FMCSA driver English-language qualification | FMCSA / DOT & CDL | `driverfact:driver.english` | ENGLISH_PROFICIENCY |
| FED-DRV-005 | FMCSA valid license for covered CMV | FMCSA / DOT & CDL | `license` | new |
| FED-DRV-007 | Completed required CMV employment application | FMCSA / DOT & CDL | `signature:APPLICATION` | EMPLOYMENT_APPLICATION |
| FED-DRV-008 | Three-year initial licensing record inquiry | FMCSA / DOT & CDL | `mvr` | MVR_PREEMPLOYMENT ✱ |
| FED-DRV-009 | Investigate three-year regulated employer safety history | FMCSA / DOT & CDL | `credential:FMCSA_SAFETY_PERFORMANCE_INVESTIGATION` | new |
| FED-DRV-010 | Annual MVR inquiry under FMCSA rules | FMCSA / DOT & CDL | `mvr` | MVR_PREEMPLOYMENT ✱ |
| FED-DRV-011 | Annual MVR review documented | FMCSA / DOT & CDL | `annualreview` | MVR_ANNUAL ✱ |
| FED-DRV-012 | Road test or acceptable equivalent | FMCSA / DOT & CDL | `roadtest` | ROAD_TEST ✱ |
| FED-DRV-014 | FMCSA medical re-examination interval | FMCSA / DOT & CDL | `credential:DOT_MEDICAL_CARD` | MEDICAL_CERT |
| FED-DRV-018 | FMCSA drug/alcohol prohibition and return-to-duty | FMCSA / DOT & CDL | `prohibition` | DA_PROHIBITION ✱ |
| FED-DRV-019 | FMCSA Clearinghouse pre-employment query | FMCSA / DOT & CDL | `report:CLEARINGHOUSE_PREEMP` | CLEARINGHOUSE_PREEMP ✱ |
| FED-DRV-020 | FMCSA annual Clearinghouse query | FMCSA / DOT & CDL | `clearinghouse` | new |
| FED-VEH-001 | FMCSA annual vehicle inspection passed | FMCSA / DOT & CDL | `credential:DOT_ANNUAL_INSPECTION` | DOT_ANNUAL_INSPECTION |
| FED-VEH-005 | FMCSA vehicle in safe and proper working condition | FMCSA / DOT & CDL | `dvir` | DVIR ✱ |
| FED-CO-014 | OSHA bloodborne pathogen exposure control plan | Federal | `credential:BBP_EXPOSURE_PLAN` | BBP_EXPOSURE_PLAN |
| FED-DRV-024 | OSHA bloodborne pathogens worker training | Federal | `credential:BLOODBORNE_PATHOGENS` | BBP_TRAINING |
| FED-CO-019 | FCRA background report disclosure and authorization | Federal | `signature:FCRA_AUTH` | new |
| FED-CO-020 | Verify employee work eligibility under federal I-9 rules | Federal | `signature:I9` | new |
| FED-DRV-026 | OSHA bloodborne pathogens training at initial assignment | Federal | `credential:BLOODBORNE_PATHOGENS` | BBP_TRAINING |
| FED-VEH-007 | Do not dispatch an unsafe FMCSA regulated vehicle | FMCSA / DOT & CDL | `dvir` | DVIR ✱ |

## Waiting - needs something TripProof does not have yet

### A written policy template TripProof does not have yet (17)

| Id | Requirement | Waiting on |
|---|---|---|
| MED-CO-002 | Process for violations of state drug laws | no policy template yet for STATE_DRUG_LAW_VIOLATIONS |
| MED-CO-003 | Process for driver history disclosure to Medicaid | no policy template yet for DRIVER_HISTORY_DISCLOSURE |
| MED-CO-005 | Provide Medicaid records on authorized request | no policy template yet for MEDICAID_RECORD_PRODUCTION; evidence medicaid_record_production_on_request: An adopted policy alone does not prove production of specific records when requested. |
| MED-CO-009 | Accept Medicaid payment according to payment-in-full rule | no policy template yet for MEDICAID_PAYMENT_IN_FULL; evidence medicaid_billing_compliance: The engine lacks actual claim, billed charge, cost sharing, and patient charge data. |
| FED-CO-001 | Proficient disability passenger-assistance training program | no policy template yet for ADA_PERSONNEL_PROFICIENCY; evidence ada_personnel_proficiency: A written policy does not demonstrate that relevant staff have actually attained proficiency. |
| FED-CO-005 | Do not require wheelchair transfer to regular seat | no policy template yet for ADA_NO_FORCED_TRANSFER |
| FED-CO-006 | Allow service animals aboard covered vehicles | no policy template yet for ADA_SERVICE_ANIMALS |
| FED-CO-007 | Permit permissible portable oxygen and respirators | no policy template yet for ADA_OXYGEN_RESPIRATORS |
| FED-CO-008 | Allow adequate time for disability boarding | no policy template yet for ADA_BOARDING_TIME; evidence trip_accessibility_boarding_time: Trip timetable and real service behavior are not represented by an adopted policy. |
| FED-CO-009 | Accessible service information and scheduling | no policy template yet for ADA_ACCESSIBLE_COMMUNICATION |
| FED-CO-010 | Use required accessibility equipment | no policy template yet for ADA_ACCESSIBILITY_EQUIPMENT_USE |
| FED-CO-011 | FMCSA driver drug/alcohol education materials | no policy template yet for DOT_DRUG_ALCOHOL_POLICY; evidence dot_driver_policy_distribution: Having a policy does not prove its distribution to each covered driver. |
| FED-CO-012 | FMCSA random testing program | no policy template yet for DOT_RANDOM_TESTING_PROGRAM; evidence dot_random_program_operation: A written policy does not demonstrate random selection, testing and required annual percentages. |
| FED-CO-013 | FMCSA CMV periodic vehicle inspection program | no policy template yet for FMCSA_ANNUAL_INSPECTION_PROGRAM; evidence carrier_vehicle_inspection_program_evidence: Policy alone does not demonstrate each covered vehicle has passed inspection. |
| FED-CO-002 | FMCSA systematic vehicle inspection and maintenance | no policy template yet for FMCSA_MAINTENANCE_PROGRAM |
| FED-CO-017 | HIPAA covered-entity workforce privacy training | no policy template yet for HIPAA_WORKFORCE_TRAINING; evidence hipaa_workforce_training_records: A written policy alone does not prove training of relevant workforce. |
| FED-CO-021 | FTA drug and alcohol program for covered transit operations | no policy template yet for FTA_DRUG_ALCOHOL_PROGRAM; fact company.fta_part655_covered: company.transit is broader than grant/program coverage; Section 5310-only operators do not automatically trigger Part 655.; evidence fta_drug_alcohol_program_operations: The |

### A kind of evidence TripProof cannot read yet (24)

| Id | Requirement | Waiting on |
|---|---|---|
| MED-CO-004 | Maintain records of Medicaid services furnished | new evidence type: Audit-ready completed trip records with actual service and billed claims.; evidence medicaid_trip_service_records: The schema has no service-event or claim documentation evidence type. |
| MED-CO-011 | Include NPI on Medicaid claims when required | new evidence type: Validate the provider NPI on each eligible Medicaid claim.; fact company.npi_eligible: NPI eligibility must be known.; evidence medicaid_claim_npi: Claims are outside the current evidence vocabulary. |
| FED-DRV-001 | Driver trained to disability-assistance proficiency | evidence driver_ada_demonstrated_proficiency: A simple completion certificate does not necessarily establish the proficiency demanded by the regulation. |
| FED-VEH-002 | Maintain operative vehicle accessibility features | new evidence type: Current verified operability of required lift, ramp, securement, and accessible communication equipment.; evidence vehicle_accessibility_equipment_status: No current per-vehicle accessibility equipment operability evidence is defined. |
| FED-VEH-003 | Repair broken accessibility features promptly | new evidence type: Document accessibility defects, repair status and reasonable accommodation.; evidence accessibility_repair_and_accommodation_log: No defect, repair or accommodation workflow is available. |
| FED-VEH-004 | Use wheelchair securement system | new evidence type: Current presence, working condition and appropriate use of wheelchair securement system on the assigned vehicle.; evidence vehicle_securement_present_functional: TripProof lacks a current operational securement-system status and use verifica |
| FED-DRV-002 | Provide assistance with lifts ramps and restraints | evidence driver_ada_assistance_proficiency: A training document does not prove assistance was provided on an individual trip. |
| FED-DRV-006 | Not disqualified under Part 391 | new evidence type: Verified driver disqualification status under 49 CFR 391.15.; evidence driver_fmcsa_disqualification_status: The current driver facts do not establish all disqualifications under 49 CFR 391.15. |
| FED-DRV-013 | FMCSA medical qualification and certification | evidence fmcsamedical_certification_or_variance: The engine must reconcile current medical qualification from driver licensing authority or examiner and any applicable variance. |
| FED-DRV-015 | FMCSA driver qualification file | evidence fmcsa_driver_file_completeness: A placeholder credential cannot validate all § 391.51 documents and record-retention details. |
| FED-DRV-016 | CDL required for CDL-classified vehicle | evidence cdl_passenger_endorsement_and_restrictions: The current license evidence definition mentions class but not passenger endorsements and CDL restrictions. |
| FED-DRV-021 | FMCSA passenger-carrier 10-hour driving limit | new evidence type: Verified passenger carrier driving time and off-duty history for proposed assignment.; evidence driver_hos_time_and_trip_projections: Current evidence types do not include driving time or duty-status history. |
| FED-DRV-022 | FMCSA passenger-carrier 15-hour on-duty driving cut-off | new evidence type: Verified on-duty and off-duty records with anticipated trip times.; evidence driver_hos_time_and_trip_projections: The engine cannot currently evaluate duty hours. |
| FED-DRV-023 | FMCSA passenger-carrier 60/70-hour weekly limit | new evidence type: Driver rolling weekly on-duty totals and applicable carrier operating schedule.; fact company.operates_cmv_seven_days: Determines which weekly passenger carrier limit applies.; evidence driver_hos_time_and_trip_projections: The engine cannot |
| FED-CO-015 | Annual OSHA bloodborne pathogen plan review | evidence bbp_plan_review_date: Document existence and plan expiration alone do not establish the plan-review date. |
| FED-DRV-025 | OSHA hepatitis B vaccination offer | new evidence type: Confidential record that hepatitis B vaccination was offered, declined or otherwise addressed in compliance with the standard.; evidence bbp_hepatitis_b_offer_status: No confidential vaccination-offer workflow exists in the schema. |
| FED-CO-016 | HIPAA Security Rule risk analysis | evidence hipaa_current_risk_analysis_scope: Document presence alone does not establish accurate, thorough and up-to-date scope of the risk analysis. |
| FED-CO-018 | HIPAA business associate arrangements | new evidence type: Executed applicable business associate agreement containing required privacy obligations.; fact company.contracts_business_associates: Only relevant contracting relationships require these assurances.; evidence hipaa_business_associate_agree |
| FED-DRV-027 | CDL passenger endorsement for a passenger vehicle | new evidence type: Current CDL record showing the required passenger endorsement and correct class.; fact vehicle.passenger_endorsement_required: Not all CDL uses require a passenger endorsement; identify the vehicle and operation triggering one.; evidence dri |
| FED-DRV-028 | CMV driver inspection of essential equipment before driving | new evidence type: Timestamped pre-trip equipment inspection and disposition of safety-critical defects.; evidence driver_cmv_equipment_pretrip_inspection: Current credential types do not capture equipment-by-equipment inspection and defects. |
| FED-DRV-029 | CMV driver safe-operating-condition confirmation | new evidence type: Pre-trip vehicle safety acknowledgment with any disqualifying defects cleared.; evidence driver_pretrip_vehicle_safety_attestation: No current driver-vehicle-specific pre-trip safety confirmation evidence is defined. |
| FED-DRV-030 | CMV alcohol prohibition before duty | new evidence type: Legally appropriate current alcohol prohibition or out-of-service status and relevant confirmations.; evidence driver_3925_alcohol_prohibition_status: The current fact driver.prohibited tracks DOT Part 382 status, not every Part 392.5 violat |
| FED-VEH-008 | Emergency equipment on covered buses and trucks | new evidence type: Vehicle inventory and current inspection of required extinguishers and warning devices, with applicable exemptions.; fact vehicle.is_bus_or_truck: This regulation is not a universal equipment rule for every vehicle qualifying as a CMV by wei |
| FED-CO-023 | Interstate for-hire passenger carrier liability insurance | fact company.part387_for_hire_covered: Operating authority reach alone does not establish Part 387 coverage or a particular exemption.; fact fleet.highest_passenger_capacity: The limit depends on the highest seating capacity in the covered fleet; vehicle.seats |

### Another fact TripProof does not know yet (6)

| Id | Requirement | Waiting on |
|---|---|---|
| MED-CO-007 | Disclose Medicaid provider ownership and control | fact company.medicaid_disclosing_entity: The current facts do not identify entities subject to this disclosure rule. |
| MED-CO-010 | Furnish National Provider Identifier when eligible | fact company.npi_eligible: Only providers eligible for an NPI must furnish it; not all transportation firms have an NPI. |
| FED-DRV-017 | FMCSA pre-employment controlled substance test | fact driver.part382_prior_testing_exception: 49 CFR 382.301(b) permits a qualifying prior-program exception, not represented by the schema. |
| FED-VEH-006 | FMCSA bus emergency-exit inspection | fact vehicle.is_bus_with_pushout_windows_or_emergency_doors: Not all vehicles classified as CMVs are buses with regulated emergency exit equipment. |
| FED-CO-022 | FMCSA reasonable suspicion supervisor training | fact company.part382_designated_supervisors: Determine designated supervisors and owner-operator exceptions before requiring training. |
| FED-CO-024 | FMCSA covered carrier identification report | fact company.39019T_applicability: Identify whether the operator is subject to this section and its exceptions. |

## Current federal rules with no counterpart in the file

Decide for each: keep it (it comes from elsewhere - a broker, the company, a state), or retire it. ✱ = has its own code in TripProof.

| Code | Rule | Category |
|---|---|---|
| PHI_POLICY ✱ | Driver PHI confidentiality and privacy acknowledgment | Federal |
| LICENSE_ENDORSEMENTS | Endorsements for the vehicle this driver will operate | FMCSA / DOT & CDL |
| DER_DESIGNATION | Designated Employer Representative | FMCSA / DOT & CDL |
| TPA_AGREEMENT | DOT drug and alcohol testing procedures and service agent oversight policy | FMCSA / DOT & CDL |
| CLEARINGHOUSE_REGISTRATION | FMCSA Drug and Alcohol Clearinghouse employer registration | FMCSA / DOT & CDL |
| DRUG_ALCOHOL_POLICY ✱ | Drug and alcohol policy | FMCSA / DOT & CDL |
| POSTACCIDENT_TEST | Post-accident controlled substances and alcohol test | FMCSA / DOT & CDL |
| HIPAA_SECURITY_OFFICIAL | HIPAA Security Official | Federal |
| BBP_PLAN_ADMINISTRATOR | Bloodborne pathogens plan administrator | Federal |
| I9 ✱ | Form I-9 | Federal |
| W4 ✱ | Form W-4 | Federal |
| SAFETY_PERFORMANCE_CONSENT ✱ | Consent to release safety performance history | FMCSA / DOT & CDL |
| CLEARINGHOUSE | Clearinghouse annual limited query | FMCSA / DOT & CDL |
| DA_POLICY_RECEIPT | Drug and alcohol policy - signed receipt | FMCSA / DOT & CDL |
| PREEMP_DA_QUESTIONNAIRE ✱ | Pre-employment drug and alcohol questionnaire | FMCSA / DOT & CDL |
| PRIOR_VIOLATION_RTD ✱ | Prior DOT Pre-Employment Violation / RTD Verification | FMCSA / DOT & CDL |
| CDL_MEDICAL_STATUS | CDLIS medical certification status | FMCSA / DOT & CDL |
| BBP_EXPOSURE_DETERMINATION ✱ | Bloodborne pathogens exposure determination | Federal |
| MAINTENANCE_RECORDS | Systematic inspection, repair and maintenance | FMCSA / DOT & CDL |
| LIFT_CERTIFICATION | Wheelchair lift certification | Federal |
| ELDT | Entry-level driver training verification | FMCSA / DOT & CDL |
| HIPAA_TRAINING_DRIVER | HIPAA privacy and security training | Federal |
| FCRA_FORMS ✱ | FCRA disclosure and authorization | Federal |
| SPE_CERTIFICATE ✱ | Skill Performance Evaluation certificate | FMCSA / DOT & CDL |
| FOLLOWUP_TESTING | Follow-up testing after return to duty | FMCSA / DOT & CDL |
| RANDOM_TEST_OWED | Test owed from a random selection | FMCSA / DOT & CDL |
| SAFETY_PERFORMANCE_HISTORY ✱ | Previous employer safety performance history | FMCSA / DOT & CDL |
| CLEARINGHOUSE_CONSENT ✱ | Clearinghouse Limited Query General Consent | FMCSA / DOT & CDL |
| RANDOM_TESTING_RECORDS | Random testing pool membership | FMCSA / DOT & CDL |
| PREV7_ONDUTY ✱ | Previous 7 Days' On-Duty Hours Statement | FMCSA / DOT & CDL |
| RANDOM_TESTING_PROGRAM ✱ | DOT random drug and alcohol testing program | FMCSA / DOT & CDL |
| USDOT_AUTHORITY | USDOT number and operating authority | FMCSA / DOT & CDL |
| UCR | Unified Carrier Registration | FMCSA / DOT & CDL |
| MCS90B | MCS-90B endorsement on the liability policy | FMCSA / DOT & CDL |
| DA_MIS_REPORT | Drug and alcohol MIS report | FMCSA / DOT & CDL |

## New document types loading would create

`BUS_EMERGENCY_EXIT_INSPECTION`, `FMCSA_DRIVER_QUALIFICATION_FILE`, `FMCSA_SAFETY_PERFORMANCE_INVESTIGATION`, `MEDICAID_CONVICTION_DISCLOSURE`, `MEDICAID_OWNERSHIP_DISCLOSURE`
