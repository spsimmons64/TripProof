-- ################################################################################################
-- # Seed: credential types, brokers, and Florida rule sets.
-- #
-- # EVERY RULE SET HERE IS A PLACEHOLDER (verified = 0). The requirements are a plausible starting
-- # shape for Florida NEMT, not a reading of any contract. Before an operator relies on a result,
-- # replace each set with a new version whose `source` and `citation` point at the actual broker
-- # contract / provider handbook page, and set verified = 1. The UI shows unverified sets as such.
-- #
-- # IDs are deterministic (uuid5) so this file can be re-run: INSERT IGNORE skips existing rows.
-- ################################################################################################

INSERT IGNORE INTO credentialtypes (recordid, code, name, subject, maxagedays, description) VALUES
  ('e0457c31-a47c-5c95-bdec-064cf5b2e57b', 'DRIVER_LICENSE', 'Driver license', 'driver', NULL, 'State-issued license, valid class for the vehicle'),
  ('6d791a1c-b532-5513-95c5-a1f6faa65fa2', 'BACKGROUND_CHECK', 'Background screening', 'driver', NULL, 'Criminal background screening result'),
  ('feae26a6-fdd9-5656-90f5-14f62ad1c910', 'OIG_EXCLUSION', 'OIG / state exclusion check', 'driver', 31, 'Primary-source lookup against LEIE and the state exclusion list'),
  ('33e586ba-ef8f-5c19-9b4a-8a6a7e3a4667', 'MVR', 'Motor vehicle record', 'driver', NULL, 'Driving record pull'),
  ('40065983-f0bb-58d4-9159-84cd3a3677c2', 'DRUG_SCREEN', 'Drug screen', 'driver', NULL, 'Pre-employment or random drug test result'),
  ('36a60519-dfac-50e8-b3f4-8aa2d714dd03', 'CPR', 'CPR certification', 'driver', NULL, 'CPR card'),
  ('64884277-dc04-5410-9287-73f721966fac', 'FIRST_AID', 'First aid certification', 'driver', NULL, 'First aid card'),
  ('44cf1da2-f0f3-54fe-bf5e-943ff4ed847a', 'DEFENSIVE_DRIVING', 'Defensive driving course', 'driver', NULL, 'Completion certificate'),
  ('8bec7c7a-99c2-5124-ad25-70a5d9fb6570', 'HIPAA_TRAINING', 'HIPAA training', 'driver', NULL, 'Completion certificate'),
  ('339d84e5-640d-500c-98f6-bb8998a96e00', 'PASSENGER_ASSIST', 'Passenger assistance / securement training', 'driver', NULL, 'Wheelchair securement and passenger assistance (e.g. PASS)'),
  ('4f2c7389-b381-555d-992c-0376be37cac1', 'VEHICLE_INSPECTION', 'Vehicle inspection', 'vehicle', 365, 'Safety inspection report'),
  ('abd4f340-e332-565c-a3ef-34b8f089e4da', 'VEHICLE_REGISTRATION', 'Vehicle registration', 'vehicle', NULL, 'State registration'),
  ('e8e034fe-4ce4-5019-b00d-856b8566a4a3', 'VEHICLE_INSURANCE', 'Vehicle insurance card', 'vehicle', NULL, 'Proof of auto insurance for this unit'),
  ('6dc8545e-b012-592d-9fd6-b4c3188aeac9', 'AUTO_LIABILITY_COI', 'Auto liability COI', 'company', NULL, 'Certificate of insurance, commercial auto'),
  ('876d9d86-86bd-55f3-b3c5-325d7a16f266', 'GENERAL_LIABILITY_COI', 'General liability COI', 'company', NULL, 'Certificate of insurance, general liability'),
  ('7048f632-7113-57f1-8f3e-610238dc988c', 'WORKERS_COMP_COI', 'Workers compensation COI', 'company', NULL, 'Certificate or exemption'),
  ('e3ea7e0b-d4a1-5aba-aa00-59cbaf18f666', 'BUSINESS_LICENSE', 'Local business tax receipt', 'company', NULL, 'County/city business tax receipt');

INSERT IGNORE INTO brokers (recordid, code, name) VALUES
  ('e94298dc-2ff8-5598-81c1-9876c9f054c3', 'MTM', 'MTM Health'),
  ('751257e0-8ce8-56eb-8cff-d273de5aab81', 'MODIVCARE', 'ModivCare');

INSERT IGNORE INTO rulesets (recordid, family, state, brokerid, version, name, effectivefrom, effectiveto, source, verified, notes) VALUES
  ('eb9ba455-a002-50b3-9618-dbe96e3a93b7', 'FL-BASE', 'FL', NULL, 1, 'Florida baseline (all brokers)', '2024-01-01', NULL, 'PLACEHOLDER - replace with contract/handbook reference', 0, 'Applies to every Florida trip in addition to the paying broker''s set.');
INSERT IGNORE INTO requirements (recordid, rulesetid, code, kind, subject, credentialtypeid, maxagedays, gracedays, servicelevels, params, description, citation) VALUES
  ('19b049f1-b65d-5db2-bb25-38fe8bbba258', 'eb9ba455-a002-50b3-9618-dbe96e3a93b7', 'DRIVER_LICENSE', 'credential', 'driver', 'e0457c31-a47c-5c95-bdec-064cf5b2e57b', NULL, 0, NULL, NULL, 'Driver holds a current license', NULL),
  ('e03289a0-ab1b-58bd-93c4-b503e8dde2de', 'eb9ba455-a002-50b3-9618-dbe96e3a93b7', 'DRIVER_BACKGROUND', 'credential', 'driver', '6d791a1c-b532-5513-95c5-a1f6faa65fa2', 1825, 0, NULL, NULL, 'Background screening on file and not older than 5 years', NULL),
  ('7b49482a-7533-558b-b8d0-a10d233e6706', 'eb9ba455-a002-50b3-9618-dbe96e3a93b7', 'VEHICLE_REGISTRATION', 'credential', 'vehicle', 'abd4f340-e332-565c-a3ef-34b8f089e4da', NULL, 0, NULL, NULL, 'Vehicle registration current', NULL),
  ('3679c674-21dc-581c-a589-0a90d1e79128', 'eb9ba455-a002-50b3-9618-dbe96e3a93b7', 'VEHICLE_INSURANCE', 'credential', 'vehicle', 'e8e034fe-4ce4-5019-b00d-856b8566a4a3', NULL, 0, NULL, NULL, 'Vehicle insurance current', NULL),
  ('d09e367e-6f4a-5048-a539-17571fe1ddf2', 'eb9ba455-a002-50b3-9618-dbe96e3a93b7', 'COMPANY_AUTO_LIABILITY', 'credential', 'company', '6dc8545e-b012-592d-9fd6-b4c3188aeac9', NULL, 0, NULL, NULL, 'Commercial auto liability in force', NULL);

INSERT IGNORE INTO rulesets (recordid, family, state, brokerid, version, name, effectivefrom, effectiveto, source, verified, notes) VALUES
  ('9b9e3543-79e8-5590-bf3f-d5037cb2c640', 'FL-MTM', 'FL', 'e94298dc-2ff8-5598-81c1-9876c9f054c3', 1, 'MTM Florida', '2026-03-01', NULL, 'PLACEHOLDER - replace with contract/handbook reference', 0, 'MTM began managing UHC Community Plan of Florida NEMT on 2026-03-01.');
INSERT IGNORE INTO requirements (recordid, rulesetid, code, kind, subject, credentialtypeid, maxagedays, gracedays, servicelevels, params, description, citation) VALUES
  ('54e52f6c-0cb5-518b-bf2b-e66250e9696a', '9b9e3543-79e8-5590-bf3f-d5037cb2c640', 'DRIVER_CPR', 'credential', 'driver', '36a60519-dfac-50e8-b3f4-8aa2d714dd03', NULL, 0, NULL, NULL, 'CPR certification current', NULL),
  ('20c44370-f441-54cc-9a4a-408e2098aa85', '9b9e3543-79e8-5590-bf3f-d5037cb2c640', 'DRIVER_FIRST_AID', 'credential', 'driver', '64884277-dc04-5410-9287-73f721966fac', NULL, 0, NULL, NULL, 'First aid certification current', NULL),
  ('9b9b9b1f-1ba2-5fb5-a306-f995c2cbafe0', '9b9e3543-79e8-5590-bf3f-d5037cb2c640', 'DRIVER_OIG', 'credential', 'driver', 'feae26a6-fdd9-5656-90f5-14f62ad1c910', 31, 0, NULL, NULL, 'Exclusion check run within the last month', NULL),
  ('c019b6fb-0159-5e71-84f8-826e847b5901', '9b9e3543-79e8-5590-bf3f-d5037cb2c640', 'DRIVER_DRUG', 'credential', 'driver', '40065983-f0bb-58d4-9159-84cd3a3677c2', 365, 0, NULL, NULL, 'Drug screen within the last year', NULL),
  ('1868b905-23ba-5679-ba6e-6ee93d903501', '9b9e3543-79e8-5590-bf3f-d5037cb2c640', 'DRIVER_ASSIST', 'credential', 'driver', '339d84e5-640d-500c-98f6-bb8998a96e00', NULL, 0, '["wheelchair","stretcher"]', NULL, 'Securement training for wheelchair/stretcher trips', NULL),
  ('e8d047da-882e-5919-9548-5b127099985d', '9b9e3543-79e8-5590-bf3f-d5037cb2c640', 'VEHICLE_INSPECTION', 'credential', 'vehicle', '4f2c7389-b381-555d-992c-0376be37cac1', 365, 0, NULL, NULL, 'Vehicle inspected within the last year', NULL),
  ('9a4f4aa7-bf6a-5822-b9bf-0ab22c1bda60', '9b9e3543-79e8-5590-bf3f-d5037cb2c640', 'VEHICLE_AGE', 'vehicleage', 'vehicle', NULL, NULL, 0, NULL, '{"maxyears": 10}', 'Vehicle no more than 10 model years old', NULL);

INSERT IGNORE INTO rulesets (recordid, family, state, brokerid, version, name, effectivefrom, effectiveto, source, verified, notes) VALUES
  ('511222c5-c082-5d31-a822-b8402b035cd1', 'FL-MODIVCARE', 'FL', '751257e0-8ce8-56eb-8cff-d273de5aab81', 1, 'ModivCare Florida', '2024-01-01', NULL, 'PLACEHOLDER - replace with contract/handbook reference', 0, 'ModivCare deactivates drivers whose background check is more than 365 days old.');
INSERT IGNORE INTO requirements (recordid, rulesetid, code, kind, subject, credentialtypeid, maxagedays, gracedays, servicelevels, params, description, citation) VALUES
  ('9990db17-83b3-5866-a0d3-318396bc9fec', '511222c5-c082-5d31-a822-b8402b035cd1', 'DRIVER_BACKGROUND_365', 'credential', 'driver', '6d791a1c-b532-5513-95c5-a1f6faa65fa2', 365, 0, NULL, NULL, 'Background check not older than 365 days', NULL),
  ('907d9027-a609-5eb4-9434-5836491cd411', '511222c5-c082-5d31-a822-b8402b035cd1', 'DRIVER_CPR', 'credential', 'driver', '36a60519-dfac-50e8-b3f4-8aa2d714dd03', NULL, 0, NULL, NULL, 'CPR certification current', NULL),
  ('6d5dd6a0-c448-58e5-820c-3f4820dde5e4', '511222c5-c082-5d31-a822-b8402b035cd1', 'DRIVER_FIRST_AID', 'credential', 'driver', '64884277-dc04-5410-9287-73f721966fac', NULL, 0, NULL, NULL, 'First aid certification current', NULL),
  ('ffa9c07c-ab39-57bc-972c-2959c8dcdf48', '511222c5-c082-5d31-a822-b8402b035cd1', 'DRIVER_OIG', 'credential', 'driver', 'feae26a6-fdd9-5656-90f5-14f62ad1c910', 31, 0, NULL, NULL, 'Exclusion check run within the last month', NULL),
  ('51c1d20a-cd67-5969-87b9-3b4fda666792', '511222c5-c082-5d31-a822-b8402b035cd1', 'DRIVER_ASSIST', 'credential', 'driver', '339d84e5-640d-500c-98f6-bb8998a96e00', NULL, 0, '["wheelchair","stretcher"]', NULL, 'Securement training for wheelchair/stretcher trips', NULL),
  ('41be5986-5cd8-5469-af14-e28ffdc226b5', '511222c5-c082-5d31-a822-b8402b035cd1', 'VEHICLE_INSPECTION', 'credential', 'vehicle', '4f2c7389-b381-555d-992c-0376be37cac1', 365, 0, NULL, NULL, 'Vehicle inspected within the last year', NULL),
  ('7fee35c4-8a60-5793-80a0-f59cd6582586', '511222c5-c082-5d31-a822-b8402b035cd1', 'VEHICLE_AGE', 'vehicleage', 'vehicle', NULL, NULL, 0, NULL, '{"maxyears": 10}', 'Vehicle no more than 10 model years old', NULL);
