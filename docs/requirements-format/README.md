# TripProof Requirements File Format

Version: `tripproof-requirements/1`

This is the format for delivering compliance requirements to TripProof Online. One file holds any
number of requirements. A file in this format loads straight into TripProof's qualification engine
with no programming. Anything the engine cannot evaluate is refused at import and listed back,
never guessed at.

Start with the **Federal + Medicaid master matrix**. State, company and broker requirements use the
same format later.

Files in this folder:

| File | What it is |
|---|---|
| `README.md` | This guide |
| `requirements.schema.json` | JSON Schema (draft 2020-12). Validate the file against it before sending |
| `example.json` | A complete file with two real requirements |

---

## 1. How TripProof uses a requirement

For every trip, TripProof asks one question: may this company, this driver and this vehicle carry
this trip, on this date? Every requirement in the file is one condition in that answer.

* **`subject`** says what is tested: the `company`, the `driver` or the `vehicle`.
* **`applies_when`** says when the requirement reaches that subject (for example: only on Medicaid
  trips, only for a vehicle with a wheelchair lift).
* **`evidence`** says what TripProof looks at to decide it is met.
* **`validity`** says how long that evidence lasts.
* **`on_failure`** says what happens when it is not met: the trip is refused (`block`), or it is
  tracked and chased without refusing trips (`track`).

The result for each requirement is PASS, FAIL or UNVERIFIED (nothing on file, not yet read, or the
condition cannot be decided). FAIL and UNVERIFIED both stop automatic assignment when
`on_failure` is `block`.

---

## 2. The file

```json
{
  "format": "tripproof-requirements/1",
  "title": "Federal and Medicaid master requirements",
  "prepared_on": "2026-11-07",
  "prepared_by": "Name of the person or organisation",
  "requirements": [ { ... }, { ... } ]
}
```

---

## 3. One requirement

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Permanent identifier, never reused or renumbered. Pattern `CATEGORY-SUBJECT-NNN`, e.g. `MED-DRV-001`, `FED-VEH-004` |
| `qualification` | yes | The underlying thing being proven. Two requirements that prove the same thing for different reasons share one qualification. See section 7 |
| `name` | yes | Short title a dispatcher understands, e.g. "Copy of the driver's license in the file" |
| `category` | yes | `MEDICAID`, `FEDERAL`, `STATE`, `COMPANY`, `BROKER` or `CDL_CMV` |
| `jurisdiction` | yes | `US` for federal, or the two-letter state code (`FL`, `GA`) |
| `subject` | yes | `company`, `driver` or `vehicle` |
| `authority` | yes | Who requires it: `CMS`, `HHS OIG`, `FMCSA`, `FTA`, `OSHA`, `Florida AHCA`... |
| `citation` | yes | The exact section, e.g. `42 U.S.C. 1396a(a)(87)(B)` or `49 CFR 37.173` |
| `citation_url` | yes | Link to the official text (eCFR, uscode.house.gov, the state's own site) |
| `citation_text` | yes | The sentence or sentences of the cited section the requirement rests on, quoted exactly. TripProof checks the citation against this before loading it |
| `requirement_text` | yes | One plain sentence: what must be true. e.g. "The driver's file holds a copy of a valid driver's license." |
| `applies_when` | yes | A condition (section 4), or `null` if it reaches every subject of its kind |
| `programs` | yes | Trip programs it applies to: any of `medicaid`, `privatepay`, `medicareadvantage`, `commercialinsurance`, `workerscomp`, `facility`. `null` means every trip |
| `evidence` | yes | What proves it (section 5) |
| `validity` | yes | How long the evidence lasts (section 6) |
| `due` | yes | When it must be met: `prehire` (before the hiring decision), `predrive` (before the first trip), `athire` (at or soon after hire), `ongoing` |
| `due_within_days` | no | For `athire`: days after hire it must be met, e.g. `30` |
| `on_failure` | yes | `block` (refuses the trip) or `track` (chased, never refuses a trip, e.g. Form I-9) |
| `effective_from` | yes | Date the requirement took effect, `YYYY-MM-DD` |
| `effective_to` | no | Date it ended, if it has been repealed or replaced. Omit or `null` if still in force |
| `notes` | no | Anything a reviewer should know. Not shown to dispatchers |
| `needs` | no | Things this requirement depends on that TripProof does not know yet (section 8) |

Rules for writing them:

1. **One requirement per obligation.** "License, background check and training" is three.
2. **Only what the citation says.** If the law requires a check before hire and a broker requires it
   every year, that is two requirements (one `FEDERAL` or `MEDICAID`, one `BROKER`) sharing one
   `qualification`. Never write the stricter one under the law's citation.
3. **A state requirement adds only what that state demands.** Never repeat a federal requirement
   under a state's name.
4. **Conditional means conditional.** If a rule only applies to employers of CDL drivers, say so in
   `applies_when`; do not make it apply to everyone.

---

## 4. Conditions (`applies_when`)

A condition tests facts TripProof already knows about the company, the driver, the vehicle and the
trip. Only the facts listed below may be used. If a requirement turns on something not listed,
put it in `needs` (section 8) instead of inventing a fact name.

### Shapes

```json
{ "fact": "company.medicaid", "is": true }
{ "fact": "company.state", "eq": "FL" }
{ "fact": "company.operatingstates", "has": "GA" }
{ "fact": "driver.age", "gte": 21 }
{ "fact": "driver.status", "in": ["hired", "inactive"] }
{ "all": [ condition, condition ] }
{ "any": [ condition, condition ] }
{ "not": condition }
```

`is` tests true/false. `eq` / `in` test a value. `has` tests that a list contains a value.
`lt`, `lte`, `gt`, `gte` compare numbers. Anything unknown counts as unknown, never as false: a
requirement whose condition cannot be decided is UNVERIFIED, not skipped.

### Facts

**Company**

| Fact | Type | Meaning |
|---|---|---|
| `company.state` | text | Home state, two letters |
| `company.operatingstates` | list | States the company operates in |
| `company.medicaid` | yes/no | Carries Medicaid-funded trips |
| `company.medicaidstates` | list | States whose Medicaid program it carries trips for |
| `company.billsdirect` | yes/no | Bills Medicaid or a payer directly (rather than invoicing a broker) |
| `company.programs` | list | Programs it carries: `privatepay`, `medicaid`, `medicareadvantage`, `commercialinsurance`, `workerscomp`, `facility`, `dhscoordinated` |
| `company.hipaa` | yes/no | Is a HIPAA covered entity or business associate |
| `company.exposure` | yes/no | Drivers' duties involve occupational exposure to blood (OSHA determination made) |
| `company.cra` | yes/no | Obtains background reports from a consumer reporting agency |
| `company.samgov` | yes/no | A contract, grant or program requires SAM.gov screening |
| `company.hiredautos` | yes/no | Drivers drive vehicles the company does not own |
| `company.copec` | yes/no | A county it works in requires a Certificate of Public Convenience |
| `company.transit` | yes/no | Works under a Community Transportation Coordinator, a transit contract or state transit funding |
| `company.employmentmodel` | text | `employee`, `contractor` or `mixed` |
| `company.public_transit_authority` | yes/no | Is a public transit authority (city, county or regional transit agency) |
| `operation.ada_part37_covered` | yes/no | Operates a demand-response service, so the ADA rules in 49 CFR Part 37 reach it |
| `operation.interstate` | yes/no | Ever drives across a state line |

**Fleet** (all of the company's vehicles together)

| Fact | Type | Meaning |
|---|---|---|
| `fleet.vehicles` | number | Vehicles on file |
| `fleet.wheelchair` | yes/no | Any vehicle carries wheelchairs (lift or ramp) |
| `fleet.cmv_federal` | yes/no | Any vehicle is a commercial motor vehicle under 49 CFR 390.5 |
| `fleet.cdl_required` | yes/no | Any vehicle needs a CDL to drive |
| `fleet.multiplecmv` | yes/no | More than one commercial motor vehicle |
| `fleet.heaviest_gvwr` | number | Highest GVWR in the fleet, pounds |

**Driver**

| Fact | Type | Meaning |
|---|---|---|
| `driver.status` | text | `application`, `pending`, `hired`, `inactive`, `declined` |
| `driver.age` | number | Age in years on the date being checked |
| `driver.employee` | yes/no | An employee rather than a contractor |
| `driver.english` | yes/no | Can read and speak English |
| `driver.cmv` | yes/no | Will operate a commercial motor vehicle |
| `driver.cdl` | yes/no | Will operate a vehicle that requires a CDL |
| `driver.heavy` | yes/no | Will operate a vehicle rated 26,001 lb or more |
| `driver.licensecommercial` | yes/no | The license on file is a commercial license |
| `driver.licenseclass` | text | Class on the license on file |
| `driver.wheelchairvehicle` | yes/no | Drives a vehicle that carries wheelchairs |
| `driver.contracts` | list | Broker contract lines the driver is approved for |
| `driver.prohibited` | yes/no | Removed from safety-sensitive functions (drug and alcohol) |
| `driver.licenseaction` | yes/no | Said a license of theirs was revoked, suspended or denied in the last three years |
| `driver.priorviolation` | yes/no | Disclosed a prior DOT drug or alcohol violation |

**Vehicle**

| Fact | Type | Meaning |
|---|---|---|
| `vehicle.seats` | number | Seats including the driver |
| `vehicle.gvwr` | number | Gross vehicle weight rating, pounds |
| `vehicle.lift` | yes/no | Has a wheelchair lift or ramp |
| `vehicle.cmv_federal` | yes/no | Is a commercial motor vehicle under 49 CFR 390.5 |
| `vehicle.cdl_required` | yes/no | Needs a CDL to drive |
| `vehicle.medicaidstates` | list | States whose Medicaid broker lines it is approved for |
| `vehicle.contracts` | list | Broker contract lines it is approved for |

**Federal motor carrier reach** (worked out by TripProof from the facts above; use these rather
than re-deciding who FMCSA reaches)

| Fact | Meaning |
|---|---|
| `reach.fmcsr` | The Federal Motor Carrier Safety Regulations reach this operation or driver |
| `reach.part382` | 49 CFR Part 382 (drug and alcohol testing) reaches it |
| `reach.part391` | 49 CFR Part 391 (driver qualification) reaches it |
| `reach.part391interstate` | Part 391 reaches it through interstate operation |
| `reach.authority` | Interstate operating authority and registration apply |

---

## 5. Evidence (`evidence`)

What TripProof reads to decide the requirement is met. Use one of these types.

| `type` | Other fields | Met when |
|---|---|---|
| `license` | none | A valid driver's license is on file: not expired, not suspended, correct class for the vehicle, valid on the trip date |
| `license_copy` | none | A copy of that license is in the file |
| `credential` | `credential`: a code from the list below | A document of that kind is on file, read, and in date |
| `signature` | `document`: a code from the list below | The driver signed that document in TripProof |
| `exclusion_check` | `list`: `OIG_LEIE` or `SAM` | The person was screened against that federal exclusion list and not found |
| `driving_record` | `lookback_years` (number) | A driving record (MVR) covering that many years was obtained and read as acceptable |
| `drug_test` | `reason`: `preemployment`, `random`, `postaccident`, `followup`, `returntoduty` | A verified negative result for a test of that reason |
| `company_role` | `role`: `der`, `supervisor`, `safety`, `security`, `bbpadmin` | Somebody at the company holds that appointment |
| `policy` | `policy`: short code | The company has adopted that written policy, with an effective date |
| `fact` | `fact` and a test (`is`, `eq`, `gte`...) as in section 4 | The fact holds, e.g. `{"type": "fact", "fact": "driver.age", "gte": 21}` |
| `other` | `describe`: plain sentence | Anything else. Imported as needing a new evidence type, and listed back for review |

Credential codes TripProof already holds (use these where they fit; a new kind of document can be
named in `credential` with `"new": true` and a `credential_name`):

* **Driver:** `ABUSE_REGISTRY_CHECK`, `BLOODBORNE_PATHOGENS`, `CLEARINGHOUSE_QUERY`, `CPR`,
  `DEFENSIVE_DRIVING`, `DMF_CHECK`, `DOT_MEDICAL_CARD`, `DRUG_SCREEN`, `ELDT`, `FBI_FINGERPRINT`,
  `FIRST_AID`, `FL_LEVEL1`, `GENERAL_ORIENTATION`, `HIPAA_TRAINING`, `PASSENGER_ASSISTANCE`,
  `SAFETY_SENSITIVITY`, `SPE_CERTIFICATE`, `SPILL_KIT_BIOHAZARD`, `WHEELCHAIR_SECUREMENT`
* **Vehicle:** `BROKER_VEHICLE_INSPECTION`, `DOT_ANNUAL_INSPECTION`, `LIFT_CERTIFICATION`,
  `LIFT_LOAD_TEST`, `VEHICLE_INSPECTION`, `VEHICLE_INSURANCE`, `VEHICLE_REGISTRATION`
* **Company:** `ABUSE_MOLESTATION_COVERAGE`, `AUTO_LIABILITY_COI`, `BBP_EXPOSURE_PLAN`,
  `BUSINESS_LICENSE`, `COPEC`, `GENERAL_LIABILITY_COI`, `HIPAA_RISK_ANALYSIS`, `HNOA_COVERAGE`,
  `MCS90B`, `MEDICAID_ENROLLMENT`, `NPI_REGISTRATION`, `OWNER_EXCLUSION_CHECK`,
  `SAM_REGISTRATION`, `UCR_REGISTRATION`, `WORKERS_COMP_COI`

Documents a driver signs in TripProof (`signature`): `CLEARINGHOUSE_CONSENT`, `DRUG_POLICY`,
`FCRA_AUTH`, `FCRA_SUMMARY`, `I9`, `PHI_ACK`, `PREV7_ONDUTY`, `SAFETY_PERFORMANCE_CONSENT`, `W4`,
`WORKPLACE_POLICY`.

---

## 6. Validity (`validity`)

| `renewal` | Other fields | Meaning |
|---|---|---|
| `once` | none | Done once, never repeats (e.g. the employment application) |
| `perhire` | none | Once for each hire, again if the person is rehired (e.g. Form I-9) |
| `ondocument` | none | Lasts until the expiry date printed on the document (e.g. a license, a medical card) |
| `days` | `every`: number | Repeats every so many days |
| `months` | `every`: number | Repeats every so many months (e.g. OIG exclusion screening, `every: 1`) |

Optional `warn_days`: how many days before it lapses TripProof starts warning (default 30).

---

## 7. Qualifications (`qualification`)

A qualification is the underlying thing a requirement proves: "valid driver's license", "OIG
exclusion screening". Several requirements can prove the same qualification for different
reasons: Medicaid, the state and a broker might all require a license. TripProof shows the
qualification once on the driver's file, with every reason behind it, and judges it against the
strictest of them.

Use these codes where they match; propose a new code in the same pattern otherwise.

| Code | Qualification |
|---|---|
| `DRV-001` | Valid driver's license |
| `DRV-003` | Motor vehicle records |
| `BKG-001` | OIG LEIE exclusion screening |
| `BKG-002` | SAM.gov exclusion and debarment screening |
| `BKG-003` | Florida Level 1 background screening |
| `BKG-004` | Level 2 fingerprint screening |
| `BKG-005` | Background screening |
| `TRN-003` | Passenger assistance and wheelchair securement training |
| `TRN-004` | HIPAA privacy and security training |
| `TRN-005` | Bloodborne pathogens training |

---

## 8. What TripProof does not know yet (`needs`)

When a requirement depends on a fact or an evidence type not listed above, keep the requirement
and say what is missing:

```json
"needs": [
  { "kind": "fact", "name": "trip.crosses_county_line", "why": "The rule applies only to trips leaving the county of origin." }
]
```

`kind` is `fact` or `evidence`. TripProof imports the requirement as waiting on that, lists it
back, and does not enforce it until the fact or evidence type exists. Nothing is dropped and
nothing is invented.

---

## 9. Before sending

1. Validate the file against `requirements.schema.json`.
2. Check every `citation_text` is quoted exactly from `citation_url`.
3. Check every `id` is unique and every `applies_when` uses only the facts in section 4.

On import TripProof re-checks all three, verifies each citation against the official text, and
returns a report: loaded, refused (with the reason), and waiting on `needs`.
