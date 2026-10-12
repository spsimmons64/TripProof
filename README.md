# TripProof

Trip-by-trip credential proof for NEMT operators. It answers one question for every trip leg:
**was every required credential valid at this pickup time, under the rules of the broker that paid
for it - and what's the proof?**

- **Credential vault** - drivers, vehicles, company; every card versioned, never overwritten.
- **Trip ledger** - import a dispatch CSV export; each leg is stamped with the credential state at its pickup.
- **Pre-billing scrub** - unbilled trips that fail, with the reason, before they're billed.
- **Exposure dashboard** - "You have $X in trips at audit risk."
- **Audit packets** - paste the auditor's trip list, get one zip: PDF evidence summary, CSV, the saved
  checks, the rules used, the source documents, and SHA-256 sums.
- **Admin portal** - for TripProof staff: customers, users, rule sets (draft → preview → publish),
  credential types, brokers, the regulations library, and the platform-wide activity log.

Stack: React (Vite) · FastAPI · MariaDB (DBServer) · Docker.

## Layout

```
db/migrations/     numbered .sql files, applied at start-up (019 removed all regulatory content)
api/app/
  validity.py      the window math - pure functions, fully unit-tested
  evaluator.py     stamps legs against rules; saves every result under an evaluation run
  importer.py      CSV → staged preview → accepted trips (header auto-matching, stub drivers/vehicles)
  packets.py       audit packet zip
  crypto.py, phi.py, storage.py    AES-256-GCM for PHI rows and stored files
  routers/         auth, vault, trips, dashboard, audits, rules, admin
  cli.py           migrate, create-account, create-admin
  demo.py          fictional demo operator with ~385 trips
web/src/           React app - pages/ (customer), admin/ (admin portal), components/
```

## Run it

### Docker (against DBServer)

```sh
cp .env.example .env          # DB credentials, JWT_SECRET, PHI_KEYS (commands to generate are in the file)
docker compose up -d --build  # API applies migrations on start
docker compose exec api python -m app.cli create-admin --email you@example.com   # admin portal login
docker compose exec api python -m app.cli create-account --name "Customer Co" --email owner@example.com
# Uploaded documents and audit packets live in /data/storage inside the API container, so it needs a
# volume - without one every redeploy destroys them:
#   podman volume create tripproof-storage
#   podman run ... -v tripproof-storage:/data/storage ... tripproof-api
# open http://localhost:8080 - admins land in the admin portal, customers in their dashboard
```

On DBServer, create the database and user first:

```sql
CREATE DATABASE tripproof CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'tripproof'@'%' IDENTIFIED BY '...';
GRANT ALL ON tripproof.* TO 'tripproof'@'%';
```

If binary logging is on, creating the triggers needs `log_bin_trust_function_creators=1` (or run the
first migration as an admin). If `DBServer` doesn't resolve inside containers, uncomment
`extra_hosts` in `docker-compose.yml`.

A throwaway local MariaDB instead: `docker compose -f docker-compose.yml -f docker-compose.localdb.yml up -d --build`.

Demo data: `docker compose exec api python -m app.demo --password "a long password"` → sign in as `demo@tripproof.test`.

### Local development

```sh
cd api && python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp ../.env.example .env        # point DB_* at a dev database
.venv/bin/python -m app.cli migrate
.venv/bin/uvicorn app.main:app --reload --port 8000

cd web && npm install && npm run dev    # http://localhost:5173, proxies /api to :8000
```

### Tests

```sh
cd api
.venv/bin/pytest                                   # unit tests only
TEST_DB_NAME=tripproof_test TEST_DB_HOST=... TEST_DB_USER=... TEST_DB_PASSWORD=... .venv/bin/pytest
```

The integration test **drops every table** in `TEST_DB_NAME` - use a disposable database. It walks the
whole flow: vault → import → exposure → renewal → revocation → packet (hashes verified), and checks
that PHI is ciphertext at rest, PHI reads are logged, the activity log refuses deletes, and a second
account can't see any of the first account's data.

## How a check works

A credential covers the half-open window `[issuedon 00:00, end)`, where `end` is the earliest of:

- `expireson + 1 day` - the card is good through the whole printed day,
- `issuedon + maxagedays` - freshness limit (the requirement's, else the type's): a 365-day background
  check done 2025-06-01 stops covering at 2026-06-01 00:00,
- `revokedon` - the moment it was pulled,

plus the requirement's grace days (never after a revocation). All business times are the operator's
local wall clock (`accounts.timezone`); housekeeping stamps are UTC.

Each leg is checked against the published rule sets in force on the date of service. There are no
rule sets at present - regulatory content is being rebuilt - so trips are imported and stored but
nothing is checked yet (tests load their own rules from `api/tests/fixtures/test_rules.sql`).

## Company compliance documents

`compliancedocs` (migration 022, admin → Compliance → Company Compliance) is the paperwork an NEMT
company needs to operate, separate from the per-trip checks: `obligation` says whether the law
requires it or it is only recommended, `expires` and `renewal` say whether it carries a renewal date
and how often, `driversign` marks the policies each driver signs, and `appliesif` names the condition
that brings it into play. Scope is the transportation provider a broker hires, not the broker: duties that follow a Medicaid
provider agreement are conditional, since the broker usually holds it.

Two layers are loaded, both checked against statute/eCFR text on 2026-09-22: federal (`US`) and
Florida (`FL`), where a state row only adds what that state demands rather than repeating a federal
one. `db/tools/verify_citations.py` re-checks every citation against the section it names, and is
worth running after loading a jurisdiction - it is what caught a USDOT row citing 49 CFR 390.19
(Mexico-domiciled carriers) instead of 390.201.

## Admin portal

Admin roles: `superadmin` changes everything; `support` is read-only. Staff logins live in an internal
account that never appears as a customer.

Customers get an account number from a sequence (100001, 100002, …) when they're created. Their admin
contact is their primary login. Nobody is ever given a password: new logins and admin-triggered
resets get an emailed single-use link (`/reset?token=…`, 7 days for invitations, 72 hours for resets;
only the token's SHA-256 is stored). Set `SMTP_HOST` and the other `SMTP_` settings in `.env` so the
links are emailed; without them the admin portal shows the link to pass on by hand.

### Email

All mail goes out from **Trip Proof Online &lt;noreply@tripproofonline.com&gt;** through `SMTP_*` in `.env`
(port 587 with STARTTLS; set `SMTP_SSL=true` for port 465). Every email is HTML with a plain-text
alternative, built from one branded layout in `api/app/emails.py` (email-safe markup: tables,
inline styles, no images). Sending lives in `api/app/mailer.py`; a failed send is logged and never
breaks the action that triggered it. Preview a design with sample data at
`/api/admin/email-preview/invitation` (signed in as staff).

Invitation links point at `PUBLIC_URL` - set it to the real site address in production.

## Online application (`/apply`)

A four-step wizard for operators signing themselves up:

1. **Account information** - company and the admin's login. Creates the account in **Setup** and signs
   the applicant in; an unfinished application resumes after they sign in again, and shows as Setup in
   the admin portal.
2. **Subscription** - the applicant enters their fleet size and the matching plan is picked (see below).
   "Contact us" tiers can't be bought online.
3. **Payment card** - a Stripe SetupIntent confirmed with Stripe Elements; the server re-reads it from
   Stripe before the next step opens. Only Stripe ids and brand / last 4 / expiry are stored.
4. **Terms of Service** - must be scrolled to the end and accepted. Records the version, the SHA-256
   of the exact text, who, when and from which IP; then creates the Stripe customer with the card as its
   default, starts the Stripe subscription (with the plan's free trial), sets the account **Active** and
   sends them to the login page.

### Subscription plans

Pricing is by fleet size: each plan in `plans` covers a vehicle range, and an applicant's vehicle count
picks the active plan whose range contains it (active ranges may not overlap). Manage them in the admin
portal under **Billing → Subscription plans**. A plan with no price is "Contact us". Stripe prices can't
be edited, so when a plan's price changes a new Stripe price is created on next use and the old one is
archived; existing subscribers keep the price they signed up at (`subscriptions` snapshots the plan,
fleet size and price). **The seeded prices ($99 / $249 / $499 / $799) are placeholders.**

Set `STRIPE_SECRET_KEY` and `STRIPE_PUBLISHABLE_KEY` (test keys first). Without them the card step can
be skipped - development only. The Terms live in `api/app/legal/terms-<version>.md`; to change them add a
new file and bump `TOS_VERSION` in `api/app/routers/apply.py` (acceptances record which version).

### Billing after signup

Stripe does the billing: it charges the card when the free trial ends and then monthly on that day,
and retries failed payments. TripProof learns what happened from Stripe's webhooks at
`POST /api/billing/webhook` (verified with `STRIPE_WEBHOOK_SECRET`; each event is handled once, see
`stripeevents`), which keep `subscriptions` and `invoices` current.

- **Fleet size is re-checked before every bill.** Stripe sends `invoice.upcoming` ahead of each
  renewal (and `customer.subscription.trial_will_end` before the trial ends); TripProof counts the
  customer's vehicles on file (not deleted; stub vehicles seen only in trip imports don't count
  until confirmed; with none entered yet, the size given at signup) and, if that's a different tier,
  moves the subscription to that tier's price from the coming invoice (no proration). A fleet past
  the priced tiers keeps its current price and shows up in staff notifications for a quote.
  `python -m app.cli reprice --days 3` does the same for every subscription renewing within 3 days -
  run it daily from cron as a safety net.
- **Past due** (a charge failed, Stripe is retrying): full access, a red banner across the portal,
  and the failure on the Billing page and in the admin customer dialog.
- **Lapsed** (Stripe gave up - the subscription is `canceled` or `unpaid`): the account goes
  **Inactive** with a billing hold. Its users can still sign in, but see only the Billing page. A new
  card pays the balance (or starts a new subscription, no trial, on the plan today's fleet calls for)
  and the hold lifts. An account staff made inactive is never reactivated by a payment.
- Customers' owners/admins manage their card and see invoices under **Billing**; staff launched into
  the portal can look but not change the card.

**Stripe dashboard setup** (test mode first, then again in live mode):

1. Developers → Webhooks → add endpoint `https://<your domain>/api/billing/webhook` with events
   `customer.subscription.created/updated/deleted/paused/resumed/trial_will_end`, `invoice.upcoming`,
   `invoice.created/finalized/paid/payment_failed/payment_action_required/voided/marked_uncollectible`.
   Put its signing secret in `STRIPE_WEBHOOK_SECRET`.
2. Settings → Billing → Subscriptions and emails: turn on **Smart Retries**; set "if all retries fail"
   to **cancel the subscription** (or mark it unpaid - both put the account on a billing hold); set
   **upcoming renewal events** to 3-7 days; turn on the failed-payment and expiring-card emails.

In development, forward sandbox events with the Stripe CLI and use the secret it prints:

```sh
stripe listen --api-key sk_test_... --events customer.subscription.created,customer.subscription.updated,customer.subscription.deleted,customer.subscription.trial_will_end,invoice.upcoming,invoice.created,invoice.finalized,invoice.paid,invoice.payment_failed \
  --forward-to http://localhost:8080/api/billing/webhook
```

## Decisions taken on the open questions

| Question | What's built | Easy to change? |
|---|---|---|
| Matching drivers across systems | Dispatch ID first, then exact first+last name. Anyone unmatched becomes a **stub** record (no credentials), so their trips show up as exposure instead of vanishing. No fuzzy matching yet. | Yes - `importer._match_driver` |
| Per leg or per trip | **Per leg**; a trip is at risk if any leg fails. | Reporting only |
| Grace periods | `requirements.gracedays`, 0 everywhere in the seed. | Data |
| Primary-source checks (OIG lookups) | Their **own credential type** (`OIG_EXCLUSION`) with a 31-day age limit; each monthly lookup is a new credential with its screenshot attached. | Data |
| Tenant isolation | In the API: every query takes `accountid` from the signed-in user. MariaDB has no row-level security. Covered by the tenancy test. | - |

## Before real customer data (HIPAA)

Built in: PHI in one table, AES-256-GCM with versioned keys, each ciphertext bound to its row; stored
files encrypted the same way; PHI never in list responses, and member details revealed only on request
and logged; append-only activity log; audit packets hashed; `Cache-Control: no-store` on the API;
session-only tokens.

Still to do:

- [ ] Hosting under a signed **BAA**, with TLS in front of nginx and DBServer's disk encrypted at rest
- [ ] PHI keys in a secrets manager (not `.env`), plus a key-rotation runbook
- [ ] Encrypted, tested backups of the database **and** the storage volume
- [ ] Login rate limiting / lockout, MFA, password reset, user management UI
- [ ] Retention policy (how long trip PHI is kept)
- [ ] Rebuild regulatory content (rule sets) from primary sources

## Next pieces

- AI reading of uploaded cards and COIs (prefill type, number, dates for a person to confirm)
- Bulk driver roster import (reuse the DriverFilesOnline template/HMAC flow)
- Broker enrollment history (deactivations) as a checked requirement
- Multi-broker credentialing packets
- Dispatch API connectors, starting with whichever systems the first customers use
- Rule-set editor for admins
