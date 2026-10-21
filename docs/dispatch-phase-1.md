# Dispatch, Phase 1

A plan against the schema that exists, not a greenfield one. Every table, column, file and
function named here is real and was checked on 2026-10-14.

---

## 1. What is already built

| Thing | Where it lives | State |
|---|---|---|
| The reservation | `trips` - passenger, passengerphone, tripdate, servicelevel, brokerid, payer, billedamount, billingstatus, note, bookedby | exists |
| The legs | `triplegs` - legnumber, driverid, vehicleid, pickupat, dropoffat, pickupplace/lat/lng, dropoffplace/lat/lng, miles, loaded, signature, gps | exists |
| Per-leg compliance result | `legchecks` - runid, legid, requirementid, subject, subjectid, outcome, reasoncode, reason, credentialid, windowstart, windowend | exists |
| What a failure is worth | `tripexposure` - failures, billedamount, per trip | exists |
| Imports | `importbatches` - filename, sha256, source, status, rowcount, tripcount, mapping, errors, decidedon | exists |
| Manual booking | `components/BookTrip.jsx` -> `POST /api/trips` | exists |
| The compliance engine | `app/evaluator.py`: `load_requirements`, `applicable`, `Facts`, `check`, `evaluate` | exists |
| The trips grid | `pages/Trips.jsx` on `DataGrid`, server-sorted | exists |

So the spec's `reservations` + `trip_legs` is `trips` + `triplegs` under other names, and the
proof-of-service fields it asks for - signature, GPS, loaded mileage - are already columns on the
leg. Of the fourteen tables proposed, five exist in substance, four are worth adding now, and the
rest belong to Phase 2 or later.

**The single most important thing already in place:** `evaluator.check(q, leg, facts)` evaluates
one requirement against one leg, where `leg` is a plain dict carrying `driverid`, `vehicleid` and
`pickupat`. It does not care whether that leg is saved. Hand it a *hypothetical* leg - this driver,
this vehicle, this pickup time - and it answers whether they would be qualified, using the same
code path that later proves they were. Dispatch does not need a second eligibility engine, and
must not have one.

---

## 2. What Phase 1 adds to the data model

Four new tables and one column change. Nothing else.

### 2.1 `tripassignments` - who was on this leg, and who was on it before

The problem being fixed: `triplegs.driverid` and `triplegs.vehicleid` are columns. Reassigning a
driver overwrites the previous one. For a product whose claim is "we can prove who was qualified
for that trip", losing the original assignment is the one data loss that cannot be argued away.

```
recordid      char(36) pk
accountid     char(36)
legid         char(36)        -> triplegs.recordid
driverid      char(36) null
vehicleid     char(36) null
assignedon    datetime
assignedby    char(36)        -> users.recordid
endedon       datetime null   -- null = this is the assignment in force
endedby       char(36) null
endreason     varchar(32) null -- reassigned | driver-declined | trip-cancelled | corrected
acknowledgedon datetime null   -- the driver said yes (Phase 2 fills this; the column exists now)
declinedon    datetime null
override      tinyint(1) default 0   -- a warning was overridden
overridereason varchar(400) null     -- required when override = 1
```

`triplegs.driverid` and `.vehicleid` stay, and stay authoritative for the engine - they are the
assignment in force. The table is the history behind them, written by the same endpoint that sets
them. One writer, so they cannot drift.

Index: `(accountid, legid, endedon)`, `(accountid, driverid, assignedon)`.

### 2.2 `tripstatus` - the five status categories, as columns on the trip

Not a table. The spec asks for five independent status categories; one table per category is five
joins on every list query. They are columns on `trips`, each with its own CHECK constraint:

```
brokerstate     varchar(16)  offered | accepted | returnpending | returned | none
dispatchstate   varchar(16)  unassigned | assigned | needsreassign
executionstate  varchar(16)  scheduled | enroute | arrived | onboard | completed
outcomestate    varchar(16)  null | cancelled | noshow | aborted | disputed
verifystate     varchar(16)  notready | awaitingreview | verified | needscorrection
billingstatus   varchar(12)  (exists) unbilled | held | billed | paid
```

`brokerstate = 'none'` for a trip the company booked itself - a private-pay trip has no broker to
be offered by, and a nullable column would make every query say "or is null".

Execution state belongs on the **leg**, not the trip: one leg can be completed while the return is
still waiting. So `executionstate` and `outcomestate` go on `triplegs`; the rest on `trips`.

Backfill: every existing trip gets `brokerstate='accepted'` where `brokerid` is set and `'none'`
otherwise, `dispatchstate` from whether the leg has a driver, `executionstate='completed'` where
`dropoffat` is set and `'scheduled'` otherwise, `verifystate='notready'`.

### 2.3 `triprejections` - a return to a broker, and whether they ever acknowledged it

```
recordid      char(36) pk
accountid     char(36)
tripid        char(36)
reason        varchar(32)     -- drivershortage | vehicleunavailable | outsidearea |
                              --   outsidehours | wronglevel | capacity | other
note          varchar(600)
requestedon   datetime
requestedby   char(36)
senton        datetime null   -- when it actually left for the broker
sentby        varchar(16) null -- api | portal | phone
acknowledgedon datetime null  -- the broker said they have it
acknowledgedref varchar(64) null
```

The trip is **not deleted and not detached**. `brokerstate` goes to `returnpending`, and only an
acknowledgement moves it to `returned`. Until then it is still the company's problem and still
appears in the uncovered-trip count. This is the rule the spec is most right about and the one
easiest to get wrong once and never notice.

### 2.4 `driverunavailable` - when a driver cannot be assigned

Deliberately the negative. A table of when somebody *is* available has to be filled in before the
product works at all; a table of exceptions is empty on day one and still correct.

```
recordid   char(36) pk
accountid  char(36)
driverid   char(36)
fromat     datetime
untilat    datetime
reason     varchar(32)   -- timeoff | sick | training | other
note       varchar(200)
```

Vehicles get the same shape, `vehicleunavailable`, so a unit out for maintenance stops being
offered. Both are checked as warnings, not hard blocks - see §3.

### 2.5 Not in Phase 1

`trip_sources`, `trip_source_mappings`, `trip_gps_events`, `trip_proof`, `trip_exceptions`,
`recurring_trip_templates`. Each is real work with no screen to use it yet. Sources are already
answered by `trips.batchid` and `brokerid`; proof is already on the leg; GPS events need the driver
app, which is Phase 2.

---

## 3. Assignment with the compliance check

The screen a dispatcher spends the day on, and the reason this product is not a scheduling app.

### 3.1 The endpoint

```
GET /api/legs/{legid}/candidates
```

Returns every driver on the account, each with a verdict, and the same for vehicles:

```json
{"drivers": [
  {"recordid": "...", "name": "JOHN DAVIS", "verdict": "ok"},
  {"recordid": "...", "name": "LISA BROWN", "verdict": "warn",
   "reasons": ["Assigned to trip T-10098 from 08:30 to 09:40"]},
  {"recordid": "...", "name": "MIKE TAYLOR", "verdict": "blocked",
   "reasons": ["Wheelchair securement training expired 09/14/2026"]}
]}
```

How it is computed, for each candidate driver:

1. Build a hypothetical leg: `{legid, tripid, driverid: candidate, vehicleid: chosen-or-null,
   pickupat, brokerid, servicelevel, billedamount, signature, gps}`.
2. `reqs = evaluator.load_requirements(...)`, `evaluator.applicable(reqs, brokerid, pickupdate,
   servicelevel, ...)` - the same filtering the nightly run uses.
3. For each requirement, `evaluator.check(q, hypothetical, facts)`.
4. A `fail` outcome on a requirement whose rule is `blocking` is a **hard block**. Any other fail
   is a warning.
5. Then the scheduling checks, which are warnings: an overlapping assignment from
   `tripassignments` joined to `triplegs.pickupat/dropoffat`, and a row in `driverunavailable`
   covering the pickup.

`facts` is built once per request, not per candidate - `evaluator.Facts(conn, accountid)` already
loads in bulk.

### 3.2 The rule about overrides

- **Hard block has no override control at all.** Not a disabled one, not one behind a
  confirmation. The driver is not listed as choosable.
- **A warning can be overridden** by a user with the dispatch role, and the endpoint refuses the
  assignment without `overridereason`. It is stored on `tripassignments.overridereason` and written
  to the activity log.

This is the same shape as the existing hard-stop/deficiency split in the driver file, and should
use the same words on screen.

### 3.3 The write

```
POST /api/legs/{legid}/assign   {driverid, vehicleid, overridereason?}
```

In one transaction: close the current `tripassignments` row (`endedon`, `endreason='reassigned'`),
insert the new one, update `triplegs.driverid/vehicleid`, set `trips.dispatchstate='assigned'`,
re-run `evaluator.evaluate(conn, accountid, tripids=[tripid])` so `legchecks` and `tripexposure`
reflect the new driver immediately, and log it.

Re-running the evaluation on assignment is what makes the trips grid honest the moment a dispatcher
acts, instead of at the next nightly run.

---

## 4. The screens

Three, not nine.

### 4.1 Dispatch Board (`/dispatch`)

The day's work, one row per leg, newest problem first. Columns: pickup time, passenger, service
level, from, to, driver, vehicle, state. The state column is the one a dispatcher reads: Unassigned,
Assigned, En route, Completed, Returned.

Filters, as chips in the existing `.filterrow`: **Needs a driver** (default), Assigned, Today,
Tomorrow, All. Date picker beside them.

Clicking a row opens the leg. Clicking the driver cell opens the assignment dialog directly -
the row that asks is the row that acts.

### 4.2 The assignment dialog

Title is the trip and time. Body is two lists, drivers and vehicles, each row a name, what they are
on that day, and the verdict. Blocked candidates are listed but not choosable, with the reason in
plain words - a dispatcher needs to know *why* John cannot take it, or they will ring the office.

Footer: Assign. Where a warning was accepted, the reason box is required and sits above Assign.

### 4.3 Incoming (`/dispatch/incoming`)

Only trips with `brokerstate='offered'`. Accept, Return to broker, Hold. Return opens the reason
list from §2.3 and writes `triprejections` with `brokerstate='returnpending'`; the trip stays
visible with a "waiting on the broker" marker until acknowledged.

Where the import already marked a trip accepted by the broker, it never appears here. §2 of the
spec is right: an imported trip is not automatically an offer.

---

## 5. Endpoints, in full

```
GET    /api/dispatch/board?date=&state=&q=          the board, server-sorted and paged
GET    /api/legs/{legid}                            one leg with its trip, assignment and checks
GET    /api/legs/{legid}/candidates                 drivers and vehicles with verdicts
POST   /api/legs/{legid}/assign                     {driverid, vehicleid, overridereason?}
DELETE /api/legs/{legid}/assign                     unassign, endreason required
POST   /api/trips/{tripid}/accept                   brokerstate offered -> accepted
POST   /api/trips/{tripid}/return                   {reason, note} -> returnpending + triprejections
POST   /api/trips/{tripid}/return/acknowledged      {ref} -> returned
POST   /api/legs/{legid}/state                      {executionstate} - the dispatcher's manual
                                                    stand-in until the driver app exists
GET    /api/drivers/{id}/unavailable  POST  DELETE  time off
GET    /api/vehicles/{id}/unavailable POST  DELETE
```

All under the existing account scoping in `app/security.py`; none of them take an accountid from
the caller.

---

## 6. Sequence

Each slice is deployable on its own and proves something.

| # | Slice | Proves |
|---|---|---|
| 1 | Migrations: the five status columns + backfill, `tripassignments` + backfill from current legs, `triprejections`, the two unavailability tables | The model holds, existing screens still work, nothing visible changes |
| 2 | `GET /legs/{id}/candidates` + the assignment dialog, reachable from the existing trips grid | The compliance engine answers a hypothetical. The core of the product |
| 3 | `POST /assign` with history, re-evaluation and the override rule | Assignment is recorded, not overwritten |
| 4 | The Dispatch Board screen and nav entry | A dispatcher has somewhere to live |
| 5 | Incoming + accept/return + rejection tracking | The broker loop closes |
| 6 | Manual execution states on the leg | The board tells the truth during the day without a driver app |

Slice 1 is a session. Slices 2 and 3 are the expensive ones and should be built together but
deployed separately. Slices 4 to 6 are mostly screen work over endpoints that already exist by
then.

---

## 7. Decisions needed before slice 1

1. **Who may assign?** A new `dispatch` company role, or any user with the existing editor
   permission? A new role is right eventually; "editor can assign" is one line now.
2. **Override authority.** Can every dispatcher override a warning, or only an owner/admin?
3. **What a trip without legs means.** `POST /api/trips` can create a trip with no leg today. Does
   the board show it as unassigned work, or is a leg created with the trip?
4. **Will-call returns.** Phase 1 has no release mechanism. Is a return leg with a null `pickupat`
   acceptable until Phase 2, shown on the board as "waiting on release"?

---

## 8. What Phase 1 deliberately does not do

No driver app, no GPS, no live map, no recurring trips, no broker API, no auto-assignment, no route
optimisation, no schedule timeline board with drag and drop. The board is a list, and a list is
enough to dispatch from on day one. The timeline is Phase 2 and is a lot of work to build before
anybody has used the list.
