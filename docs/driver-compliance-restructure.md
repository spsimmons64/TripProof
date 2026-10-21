# Driver Compliance Restructure

The plan behind the driver compliance rebuild, written against the schema as it stands after the
first pass on 2026-10-20. Every table, column, file and function named here is real. It follows
`TripProof_Driver_Compliance_Restructure_Blueprint.md`; where this departs from the blueprint, it
says so and says why.

**Status in one line:** both rounds are live on dev.tripproofonline.com: the five build steps, and
the follow-up list (contracts, rule review, versioning, snapshots, wheelchair checks, enforcement
switch), and the last five items (passenger assistance split, trip geography, provenance, instant
re-checks, kept refusals). Trip eligibility runs in **shadow** until a company turns enforcement on, and even then
only **approved** rules are enforced. No rule has been legally reviewed yet: every rule is a
**draft**.

---

## 1. The idea

Compliance stops being one checklist every driver completes. It becomes six parts that work
together:

| Part | What it answers | Where it lives |
|---|---|---|
| Rule library | What requirements exist, from which authority, under what conditions | `compliancerules` |
| Operating profile | Where the company operates, which programs and contracts, how it engages drivers, what its vehicles are | `companyprofiles`, `companyprograms`, `companycontracts`, `vehicleassessments`, `drivers.engagement` |
| Qualification catalog | What TripProof can verify, once, with a permanent ID | `qualificationcatalog` |
| Evidence | Licenses, MVRs, screenings, tests, training, signatures, reviews | existing tables: `driverlicenses`, `drivermvrs`, `credentials`, `exclusionchecks`, `drugtests`, `documentsignatures`, `annualreviews`, `driverreports` |
| Evaluation engine | Whether each applicable requirement is satisfied, missing, expired or under review | `app/rules.py` (`for_driver`, `_by_qualification`), `app/facts.py`, `app/qualification.py` |
| Dispatch authorization | Whether this driver, in this vehicle, may take this trip | `app/tripcheck.py`, `tripeligibility` |

**The rule that matters most:** a qualification exists once in the catalog. It may have several
sources. The license is one qualification (`DRV-001`) with an FMCSA source and a Medicaid source,
not two license requirements.

---

## 2. What was built

### Step 1 - Qualification catalog and sources

Migration `311_qualification_catalog.sql`.

- `qualificationcatalog`: `code` (permanent, e.g. `DRV-001`), `name`, `area` (licensing,
  background, training, medical, drugalcohol, employment), `subject`, `description`, `sortorder`,
  `retiredon`. Seeded with 47 qualifications.
- New columns on `compliancerules`:
  - `qualificationcode`: which qualification the rule proves.
  - `authoritycategory`: one of `FEDERAL_GENERAL`, `STATE_GENERAL`, `FEDERAL_MEDICAID`,
    `STATE_MEDICAID`, `CONTRACT_COMPANY`.
  - `enforcement`: `dispatch` or `hr`.
  - `legalreview`, `legalreviewedby`, `legalreviewedon`: `draft`, `reviewed`, `approved` or
    `retired`. Every existing rule starts as `draft`.
- All 50 driver rules are mapped (section 3). None is left unmapped.
- `rules._by_qualification()` replaces the license-only merge (`_one_license`):
  - It groups the rules that reach a driver by qualification. Each source is still evaluated on
    its own.
  - The row takes the worst state among the sources that reach the driver, and lists every
    source in `sources`.
  - A merged row is blocking if any source blocks, and a hard stop if any source is one. It takes
    the earliest due stage.
  - A row counts toward every program if any source behind it is general.
- The requirement detail endpoint returns the catalog name and every source behind the
  qualification.
- On the driver's Requirements page, each row lists all its sources on one line.

Result on the dev account: 50 rules shown as 47 rows.
- **Valid Driver's License:** one row, FMCSA and CMS.
- **Pre-Employment Drug Test:** one row, DOT Part 382, the Florida intrastate statute and the CTD.

### Step 2 - HR split

- `I9` and `W4` have `enforcement = 'hr'`. The engine forces them non-blocking with gate
  `deficiency`. Dispatch (`dispatch.py`) and the driver gate (`vault._gate`) stop only on
  `hardstop`, so an HR item can never pull a driver off a trip.
- They sit in their own **Employment Onboarding** section on the Requirements page.
- Migration `312` makes the I-9 and W-4 apply only to employees, through the
  `driver.employee` fact.

### Step 3 - Operating profile

Migration `312_operating_profile.sql`, router `app/routers/operating.py`, screen
`web/src/pages/OperatingProfile.jsx` (Company - Operating Profile).

| Record | Fields | Notes |
|---|---|---|
| `companyprofiles` | operatingstates, employmentmodel (employee / contractor / mixed), fdot1490 (covered / notcovered / review), compliancecontact | One per account |
| `companyprofilehistory` | snapshot (JSON), savedon, savedby | Every save kept, never rewritten |
| `companyprograms` | program, state, status (active / planned / ended), effectivefrom, effectiveto | Private Pay, Medicaid NEMT, Medicare Advantage, Commercial Insurance, Workers' Compensation, Facility Contracts |
| `companycontracts` | broker, state, contractref, program, services, effective dates, reviewed / reviewedby / reviewedon, note | Unreviewed reads "Not Reviewed", never "none" |
| `vehicleassessments` | fmcsa, fdot1490 (covered / notcovered / review), note, assessedby, assessedon | One per vehicle |
| `drivers.engagement` | employee / contractor / subcontracted | Blank falls back to the company model |

The screen lists every open question at the top under **Needs Review**: no operating states, no
employment model, 14-90 not settled, no active program, an unreviewed contract, or a vehicle
without an FMCSA determination.

How the profile feeds the rules (`facts.assemble`):

| Fact | Comes from |
|---|---|
| `company.medicaid` | Any active Medicaid program, **once any program is recorded**. Until then, the old yes/no answer. |
| `company.programs` | The active programs |
| `company.employmentmodel`, `company.operatingstates` | The profile |
| `company.fdot1490` | covered = true, notcovered = false, review or blank = unknown |
| `driver.chapter1490` | The driver's tick box, **unless** the company says not covered (false) or under review with the box clear (unknown) |
| `driver.employee` | The driver's engagement, then the company model. Mixed or unset = unknown. |
| `fleet.cmv_federal` | True if any vehicle is determined covered. False if every vehicle is determined not covered. Otherwise worked out from weight and seats, as before. |

**Unknown is never exempt.** An unknown fact makes the rule read *Waiting On An Answer From The
Company*, with the reason, never *not applicable*.

### Step 4 - Qualification overview

`app/qualification.py`, returned as `overview` by `GET /api/drivers/{id}/requirements`, and shown
as the **Qualification Overview** card on the driver's Requirements page.

Four separate answers, never one "compliant":

| Answer | Logic |
|---|---|
| Employment | The driver's status: Applicant, Pending Hiring Decision, Hired, Not Employed, Not Hired |
| Employment Onboarding | HR items only. Overdue if any is failed or expired. Needs Review if applicability is unknown. In Progress if any is outstanding. Otherwise Complete. |
| One badge per program | Counts rules that are general or belong to that program, excluding HR. **Not Qualified** if any applicable blocking item is failed, expired, overdue or missing. **Review Required** if any is waiting to be read or has undecided applicability. Otherwise **Qualified**. Up to four reasons are shown. |

The programs come from the operating profile. With none recorded, it's Private Pay, plus Medicaid
if the company has said it carries Medicaid trips. Rules are tied to a program by
`compliancerules.program`. Migration `312` sets `program = 'medicaid'` on every `FEDERAL_MEDICAID`
and `STATE_MEDICAID` rule.

### Step 5 - Trip eligibility

`app/tripcheck.py`, migration `313_trip_eligibility.sql`.

- `POST /api/dispatch/eligibility-check` takes `{driverid, vehicleid?, legid?, program?, at?}` and
  returns:
  - `decision`: `eligible`, `notqualified` or `needsreview`.
  - `blockers[]` and `warnings[]`.
  - `rulesread[]`, the rule codes with their legal-review status.
  - `evaluationid`, `program` and `evaluatedfor`.
- Requirements are evaluated **as of the pickup time**, not today, using the same `for_driver`
  engine dispatch already uses. There's no second engine.
- Only rules of the trip's program count, plus general rules. HR items never count.
- Vehicle rules that are failed or expired block too.
- Every check is stored in `tripeligibility`: who, which vehicle and leg, program, evaluated for,
  evaluated on, by whom, decision, blockers, warnings, rules read, and shadow flag.
- **Shadow mode:** both assignment paths in `routers/trips.py` (booking onto a driver, and
  assigning a leg) run the check and store it with `shadow = 1`. It never refuses an assignment.
  The existing hard-stop gate in `dispatch.py` still decides.
- `GET /api/drivers/{id}/eligibility-checks` lists the last 100 checks on a driver.
- Payer to program: medicaid and broker map to Medicaid NEMT, commercial to Commercial
  Insurance, flatcontract to Facility Contracts, private to Private Pay. The broker mapping is an
  assumption; see section 6.

Verified on the dev server, in transactions that were rolled back:
- Hired drivers came out eligible under Private Pay and Medicaid.
- An applicant came out "not hired".
- Shawn Tannon was blocked on 05/17/2027, because his SAM.gov screening ran out on 10/23/2026.
- He was blocked again in January 2028 for his license (expires 05/18/2027), MVR and annual
  review.

---

## 3. Rule to qualification map

| Qualification | Name | Rules (sources) | Category |
|---|---|---|---|
| DRV-001 | Valid driver's license | DRIVER_LICENSE; DRIVER_LICENSE_COPY | Federal General; Federal Medicaid |
| DRV-002 | License class and endorsements | LICENSE_ENDORSEMENTS | Federal General |
| DRV-003 | Motor vehicle records | MVR_PREEMPLOYMENT | Federal General |
| DRV-004 | Annual inquiry and review of driving record | MVR_ANNUAL | Federal General |
| DRV-005 | Driver employment application | EMPLOYMENT_APPLICATION | Federal General |
| DRV-006 | Previous employer safety performance history | SAFETY_PERFORMANCE_HISTORY | Federal General |
| DRV-007 | Consent to release safety performance history | SAFETY_PERFORMANCE_CONSENT | Federal General |
| DRV-008 | Road test certificate or accepted equivalent | ROAD_TEST | Federal General |
| DRV-009 | Minimum age for interstate operation | DRIVER_AGE | Federal General |
| DRV-010 | Able to read and speak English | ENGLISH_PROFICIENCY | Federal General |
| DRV-011 | Previous 7 days' on-duty hours statement | PREV7_ONDUTY | Federal General |
| DRV-012 | Driver qualification file (Florida intrastate) | FL_INTRASTATE_FULL | State General |
| BKG-001 | OIG LEIE exclusion screening | EXCLUSION_OIG_LEIE | Federal Medicaid |
| BKG-002 | SAM.gov exclusion and debarment screening | EXCLUSION_SAM_GOV | Contract / Company |
| BKG-003 | Florida Level 1 background screening | FL_LEVEL1_DRIVER | State Medicaid |
| BKG-004 | Level 2 fingerprint screening | FL_LEVEL2_DRIVER | Contract / Company |
| BKG-005 | Background screening | BACKGROUND_SCREENING | Contract / Company |
| BKG-008 | Abuse registry check | ABUSE_REGISTRY_CHECK | Contract / Company |
| TRN-003 | Passenger assistance and wheelchair securement training | SECUREMENT_TRAINING_CERT | Federal General |
| TRN-004 | HIPAA privacy and security training | HIPAA_TRAINING_DRIVER | Federal General |
| TRN-005 | Bloodborne pathogens training | BBP_TRAINING | Federal General |
| TRN-006 | Defensive driving course | DEFENSIVE_DRIVING | Contract / Company |
| TRN-011 | Entry-level driver training verification | ELDT | Federal General |
| TRN-012 | First aid certification | FIRST_AID | Contract / Company |
| TRN-013 | CPR and AED certification | CPR | Contract / Company |
| MED-001 | Medical certificate | MEDICAL_CERT | Federal General |
| MED-002 | Bus transit medical examination | FL_TRANSIT_MEDICAL | State General |
| MED-003 | CDLIS medical certification status | CDL_MEDICAL_STATUS | Federal General |
| MED-004 | Skill performance evaluation certificate | SPE_CERTIFICATE | Federal General |
| DRA-001 | Pre-employment drug test | PREEMPLOYMENT_DRUG_TEST; FL_INTRASTATE_382; FL_TD_DRUG_TESTING | Federal General; State General; State General |
| DRA-002 | Clearinghouse pre-employment full query | CLEARINGHOUSE_PREEMP | Federal General |
| DRA-003 | Random testing pool membership | RANDOM_TESTING_RECORDS | Federal General |
| DRA-004 | Pre-employment drug screen (additional panels) | NONDOT_DRUG_SCREEN | Contract / Company |
| DRA-005 | Drug and alcohol policy - signed receipt | DA_POLICY_RECEIPT | Federal General |
| DRA-007 | Clearinghouse limited query general consent | CLEARINGHOUSE_CONSENT | Federal General |
| DRA-008 | Clearinghouse annual limited query | CLEARINGHOUSE | Federal General |
| DRA-009 | Pre-employment drug and alcohol questionnaire | PREEMP_DA_QUESTIONNAIRE | Federal General |
| DRA-010 | Prior DOT pre-employment violation / RTD verification | PRIOR_VIOLATION_RTD | Federal General |
| DRA-011 | Post-accident controlled substances and alcohol test | POSTACCIDENT_TEST | Federal General |
| DRA-012 | Test owed from a random selection | RANDOM_TEST_OWED | Federal General |
| DRA-013 | Follow-up testing after return to duty | FOLLOWUP_TESTING | Federal General |
| DRA-014 | Removed from safety-sensitive functions | DA_PROHIBITION | Federal General |
| EMP-002 | Form I-9 | I9 (hr) | Federal General |
| EMP-003 | Form W-4 | W4 (hr) | Federal General |
| EMP-006 | FCRA disclosure and authorization | FCRA_FORMS | Federal General |
| EMP-007 | License suspension reporting acknowledgement | FL_LICENSE_STATUS_NOTICE | State General |
| EMP-009 | PHI confidentiality acknowledgment | PHI_CONFIDENTIALITY | Contract / Company |

The IDs follow the blueprint's catalog. The blueprint's `DRV-005` (driver application) is used for
the employment application, so `EMP-001` is not used. IDs the blueprint names but nothing tracks
yet (for example `TRN-001`, `TRN-002`, `BKG-007`, `EMP-004`, `EMP-005`, `EMP-008`) are not seeded.
They are added when a rule needs them.

---

## 4. Statuses

The engine keeps the three blueprint dimensions separate, under the names it already used:

| Blueprint | TripProof | Values |
|---|---|---|
| Applicability | `applies` | true = REQUIRED, false = NOT_APPLICABLE, null = NEEDS_DETERMINATION |
| Qualification result | `status` | satisfied, expiring (satisfied with an alert), pending (missing), ordered (waiting on third party), review (received, waiting to be read), failed, expired, overdue, unknown, notapplicable |
| Evidence workflow | per evidence table | e.g. `drivermvrs.reviewstate`, `exclusionchecks.result` and `verifiedon`, `documentreads` |

A green check means one thing only: satisfied (or expiring) for the requirement's scope.

---

## 5. Round two - built on 2026-10-21

Migration `314_contracts_review_versions.sql`.

| Item | What was built | Where |
|---|---|---|
| Contract rule sets | A contract can carry driver requirements: a qualification, optional renewal days, and the clause. Each one is evaluated as one more source behind that qualification, reading the same evidence with the contract's own renewal. Only reviewed, current contracts count. | `contractrequirements`; `rules.contract_rules()`; the contract dialog on Operating Profile |
| Contract to trip | A contract links to the payer its trips are billed to (`payerid`). A trip billed to that payer brings in the contract's program and requirements. An unreviewed contract makes the check Needs Review. | `tripcheck.contract_for()` |
| Driver broker approvals | A contract can require approval. Drivers are approved or un-approved on their Company Information card. Approvals are ended, never deleted. A driver without approval is blocked from that contract's trips. | `driverauthorizations`; `GET/POST /api/drivers/{id}/authorizations`; Broker Approvals on the driver page |
| Legal review workflow | Platform staff set each rule to Draft, Reviewed, Approved or Retired. Each decision is stamped with who and when. | `GET /api/admin/rules`, `PUT /api/admin/rules/{code}/review`; admin Compliance - Rule review |
| Rule versioning | Every rule as it stood, each time it changed: full row, hash, when, by whom, why. Captured after every migration run and every review decision; a failure never stops the service starting. Trip checks record the version of each rule they read. | `compliancerulesversions`; `app/ruleversions.py` |
| Snapshots and reconciliation | Daily at 05:15 UTC: each pending and hired driver's standing per program is kept, and every assigned trip in the next 7 days is re-checked. The bell alerts on an upcoming trip whose driver no longer qualifies. | `programqualificationsnapshots`; `app/dailycompliance.py`; `app.cli daily-compliance`; cron |
| Shadow comparison | Operating Profile shows every trip check of the last 30 days that would have been refused or needed review, with the reason. | Trip Checks In Shadow card |
| Enforcement switch | "Refuse trip assignments that fail an approved requirement" on the profile. When on, an assignment failing anything enforceable is refused with the reason: an approved rule, not hired, not approved for the contract, no securement training for a wheelchair trip, or no lift. Draft rules are never enforced. | `companyprofiles.enforcetripcheck`; `trips._shadow_check` |
| Service type and vehicle fit | A wheelchair or bariatric wheelchair trip needs wheelchair securement training on file and current. Any lift service level needs a lift-equipped vehicle (from `dispatch.SERVICE`). | `tripcheck.check` |
| Explained not-applicable | A rule that doesn't reach a driver says which facts decided it, e.g. "Does not reach this driver - Medicaid trips: No". | `rules.explain_false()` |
| Multi-state | New `has` operator. The Florida rules now reach a company that operates in Florida, not only one headquartered there. | `rules.applies`; migration 314 |

Verified on the server:
- **Contract:** with a reviewed contract requiring approval and asking for a background screening every 30 days, Shawn Tannon was blocked from its trip until approved. Once approved, his Background Screening row showed the contract as a second source, and its 30-day renewal made the row read expiring. His wheelchair trip came out eligible under Medicaid. (Rolled back.)
- **Rule versions:** 100 recorded at the first run. An approval moved the license rule to version 2. (Rolled back.)
- **Daily job:** 8 snapshots taken.

### Round three - built on 2026-10-21

Migration `315_split_training_provenance_refusals.sql`.

| Item | What was built |
|---|---|
| Passenger assistance split from securement | New qualification `TRN-001` (passenger assistance and disability awareness), its own credential type `PASSENGER_ASSISTANCE` and rule `PASSENGER_ASSISTANCE_TRAINING`, with the same reach as securement. Where the driver has no separate record, the combined securement certificate answers it, and the row says so. `TRN-003` is now securement alone. |
| Trip geography | The trip check reads the pickup state from the leg's address ("..., FL 33602") and evaluates the state rules for that state, not for the company's headquarters. A Florida company's Georgia trip is held to Georgia's rules. With no state in the address, the company's states decide. |
| Evidence provenance | `credentials.provenance` (FDLE, AHCA Clearinghouse, screening vendor), required where `credentialtypes.requiresprovenance` is set (Florida Level 1). A Level 1 without a source, or from a vendor alone, is on file and under review until the source is recorded. The source is chosen when filing, or set on the Level 1 dialog. |
| Re-check on change | Whenever a driver's or vehicle's file changes, through the same hook that re-evaluates their trips, every trip they're assigned in the next 7 days is re-checked at once. The bell reads the newest check. |
| Refused assignments kept | A refused assignment rolls back, but the check that refused it is written again in its own transaction, marked `refused`. |

Verified on the server:
- **Passenger assistance:** Shawn Tannon's was answered by his combined certificate.
- **Level 1:** it read *review* until FDLE was recorded as the source. (Rolled back.)
- **Georgia pickup:** a pickup in Atlanta dropped the Florida rules. (Rolled back.)
- **Refusal:** with enforcement on, assigning a not-yet-hired driver was refused and the check was kept. The test row was deleted afterwards.

**Found and fixed while testing:** the "not hired" and "no such driver" blockers weren't marked enforceable, so enforcement wouldn't have stopped an unhired driver.

**Real effect on the dev data:** Shawn's Level 1 was filed before sources were recorded, so it now reads *review* until its source is set.

### Remaining

Nothing from the blueprint's build list is outstanding. What's left is review and rollout:
- approve rules on Rule Review;
- record the operating profile;
- watch the shadow list until it's clean;
- then turn enforcement on.

---

## 6. Decisions and assumptions to confirm

| # | Decision | Why it matters |
|---|---|---|
| 1 | Every rule is `draft`. Nothing has been signed off as law. | The blueprint requires review before enforcement. Somebody qualified has to approve each one. |
| 2 | A trip billed to a **transportation broker** is treated as Medicaid NEMT. | True for NEMT brokers. Wrong for a broker administering a commercial or Medicare Advantage plan. A contract's program should override this. |
| 3 | The I-9 and the W-4 apply only to employees. With no employment model and no driver engagement, they read "unknown". | Today every driver on the dev account shows onboarding as **Needs Review** until the model or engagement is set. |
| 4 | A recorded program list overrides the old "Do you carry Medicaid funded trips?" answer. | Adding any program without adding Medicaid switches every Medicaid rule off. |
| 5 | 14-90 "Needs Review" makes the FDOT bus-transit rules unknown, unless the driver's own 14-90 box is ticked. | Rules depending on it show as waiting on an answer until it's settled. |
| 6 | SAM.gov stays Contract / Company, not Federal Medicaid. | Its rule applies only when a contract, grant or program requires it. |
| 7 | OIG LEIE stays Federal Medicaid (`program = medicaid`). | It counts toward the Medicaid badge only, not Private Pay. |
| 8 | A contract's own requirements count as approved once the contract is marked reviewed. | They are the company's reading of its own contract, so they can be enforced without platform review. |
| 9 | With enforcement on, structural blockers are enforced regardless of rule review: not hired, not approved for the contract, no securement training for a wheelchair trip, no lift. | They are facts about the trip, not statements of law. |

---

## 7. How to check it

- **Company - Operating Profile:** record operating states, employment model, 14-90, programs,
  contracts and vehicle determinations. The Needs Review list shrinks as each is answered.
- **A driver's Requirements:** the Qualification Overview card is at the top. Each row lists every
  source. HR items are under Employment Onboarding.
- **A driver's Company Information:** set Engagement and watch the I-9 and W-4 move from waiting
  on an answer to required (employee) or not applicable (contractor).
- **Trip check:** `POST /api/dispatch/eligibility-check` with a driver and `at` set to a future
  date shows expiry blocking ahead of time. Shadow rows appear in `tripeligibility` after any
  assignment.

---

## 8. Blueprint test scenarios, where they stand

| # | Scenario | Now |
|---|---|---|
| 1 | FL private-pay sedan, no automatic Level 1 | Yes: Level 1 is `program = medicaid` and doesn't count toward Private Pay |
| 2 | Same driver on a Medicaid trip needs Level 1 | Yes, in the trip check (shadow) |
| 3 | Medicaid wheelchair trip adds contract and wheelchair competency | Yes: contract requirements, securement and lift |
| 4 | Unreviewed contract is Needs Review | Yes: its trips check as Needs Review |
| 5 | Covered 14-90 in a non-CDL vehicle | Yes: driver 14-90 plus company determination |
| 6 | FMCSA-covered CMV, non-CDL driver | Yes: `driver.cmv` and `driver.cdl` are separate |
| 7 | CDL / Part 382 operation | Yes: existing rules |
| 8 | Company MVR every 6 months beside an annual federal rule | Yes for contracts: a contract requirement with its own renewal is a separate source on the same row |
| 9 | Vendor Level 1 without FDLE provenance stays unresolved | Yes: it reads review until the source is recorded as FDLE or AHCA |
| 10 | License expires tomorrow: qualified today, blocked tomorrow | Yes: the trip check evaluates at pickup |
| 11 | License revoked today re-evaluates assignments | Yes: any change to the file re-checks the week's assignments at once, and the daily sweep catches dates passing |
| 12 | One certificate reused across broker and private pay | Yes: evidence is stored once and read by every rule |
| 13 | FL and GA operations by assignment geography | Yes: the trip check uses the pickup state |
| 14 | Contract change re-evaluates prospectively, history kept | Yes: contracts and requirements have dates, requirements are ended not deleted, profile and rule history kept |
| 15 | Missing 14-90 classification is Needs Determination | Yes |
| 16 | Missing W-4 is HR, not a dispatch block | Yes |
| 17 | Contractor gets no W-4 | Yes: `driver.employee` |
| 18 | Unverified exclusion match is review pending | Yes: possible match is "review" |
| 19 | Driver or vehicle substitution re-checks | Yes: every assignment runs the check |
| 20 | Tenant isolation | Yes: every query is scoped by `accountid` |
