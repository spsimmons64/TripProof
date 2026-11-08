# Georgia TripProof Requirements — Research Draft

Two separate category files: Georgia State (`STATE`) and Georgia Medicaid (`MEDICAID`) in tripproof-requirements/1 format.

**Do not import as live automatic trip blockers yet.** The 2026 Georgia Medicaid manual is listed on MMIS (October 1, 2026), but this project quotes a July 2022 version, and flags all historic requirements as pending 2026 revalidation. State and broker statutory exemptions are important.

Critical Georgia exemption: O.C.G.A. §40-1-100(12)(B)(vii) excludes qualifying vehicles capable of carrying 10 or fewer persons, used exclusively to transport elderly/disabled persons for medical care/prescriptions, from the state motor-carrier definition; this is not a blanket exemption from all other requirements. Verida is the single statewide Medicaid NEMT broker effective April 1, 2026.

For data compatibility: `MEDICAID` is used for Georgia state Medicaid NEMT-specific obligations. The federal Medicaid rules remain in the separate national `MEDICAID` catalog. Georgia `STATE` is non-program-specific where applicable. `needs` flags are deliberate because the required fact/evidence evaluators do not yet exist.

Source URLs are embedded in every rule. See tripproof-georgia-import-review.json for precise limitations and validation results.
