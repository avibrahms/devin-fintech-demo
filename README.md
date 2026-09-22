# devin-fintech-demo — Internal Operations Portal (prototype)

A two-hour prototype built with Devin to inform a build-vs-buy decision
(Power Apps vs. building internal tools with Devin). It is an internal
operations portal with:

- a complete **refunds workflow** (request → manager approve/reject → history), and
- a small **read-only KYC queue**,

sharing one login, navigation, role model and component set, so further tools
can be added without rebuilding the foundation.

**This is a prototype, not production software.** See `docs/DESIGN_NOTES.md`
for scope, tradeoffs and the remaining production work.

Runnable branch: `devin/1790091892-ops-portal` (pull request against `main`).

## Stack

Django 5.2 + SQLite, server-rendered templates, one CSS file, no JavaScript
build. Login, password hashing, sessions, CSRF protection, forms and database
access all use Django's standard components. Roles are Django auth Groups.
Money is stored as integer minor units (cents) plus an ISO currency code.

## Requirements

- Python 3.10+ (tested on 3.10 / Ubuntu 22.04)
- `make` (optional; the underlying commands are listed below)

## Setup, run, test, reset

```bash
git clone https://github.com/avibrahms/devin-fintech-demo.git
cd devin-fintech-demo
git checkout devin/1790091892-ops-portal

make setup      # venv + deps + migrate + seed demo data (only if DB is empty). Safe to re-run.
make run        # http://localhost:8000  — migrates, seeds only if empty, never erases data
make test       # 42 tests against an isolated in-memory database
make reset      # EXPLICIT demo reset: wipes refund/payment/KYC records and re-seeds
```

Without `make`:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo            # idempotent
.venv/bin/python manage.py runserver --insecure 0.0.0.0:8000
.venv/bin/python manage.py test
.venv/bin/python manage.py seed_demo --reset    # explicit reset
```

Restarting: stop the server (Ctrl-C) and run `make run` again. Data lives in
`data/portal.sqlite3` and survives restarts. `make run` never deletes it.

### Local configuration (environment variables, all optional)

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORTAL_DATA_DIR` | `./data` | Where the SQLite DB and generated secret key live (git-ignored) |
| `PORTAL_SECRET_KEY` | auto-generated into `data/secret_key.txt` | Django secret key |
| `PORTAL_DEBUG` | `0` | Set `1` for Django debug pages |
| `PORTAL_ALLOWED_HOSTS` | `*` | Comma-separated hosts (demo default is permissive) |
| `PORTAL_CSRF_TRUSTED_ORIGINS` | empty | Needed when served behind a proxy on another origin, e.g. `https://8000--<id>.preview.devinapps.com` |

Nothing secret is committed: the database, secret key, `.env*` and `data/` are
in `.gitignore`. No Microsoft, Dataverse or payment-provider credentials are
needed.

## Demo accounts

| Username | Password | Role | Can |
| --- | --- | --- | --- |
| `operator` | `operator-demo-2026` | Operator | Read everything, submit refund requests |
| `manager` | `manager-demo-2026` | Manager | Submit requests, approve/reject **other users'** requests |
| `auditor` | `auditor-demo-2026` | Auditor | Read everything including history; no writes |

Passwords are demo-only and reset by `seed_demo`. Roles are enforced on the
server from the session user; form fields are never trusted for identity.

## Demo data (deterministic)

- 12 payments (USD/EUR), 7 refund requests (2 approved, 2 rejected, 3 pending), 12 KYC cases.
- **Reserved for the recording:** `PAY-1007`, customer **Mira Chen**, **$200.00**, no refund request.
- **Self-approval demo:** `RR-6` on `PAY-1008` is a pending request *created by the manager*;
  the manager sees why they cannot decide it, and a direct POST returns 403.

See `docs/DEMO_CHECKLIST.md` for the step-by-step $120 walkthrough.

## Where to view it during the Devin session

Devin's browser preview (requires your Devin login):
`https://8000--f75945dde9794497af71c122dbea3810.preview.devinapps.com/login/`

This only exists while the Devin session machine is up. The repository contains
everything needed to recreate the demo locally with the commands above.

## Business rules implemented

- Refund amount: > 0, ≤ original payment, at most two decimal places; USD/EUR only.
- One refund request per payment — `UNIQUE` constraint in the database (demo limitation:
  no partial/multiple refunds per payment).
- Manager decision requires a reason; operator/auditor cannot decide (HTTP 403 on direct POST).
- Manager cannot decide their own request (403 and a database `CHECK` constraint).
- Once approved or rejected a request is final; a second decision (double click, stale tab,
  other manager) is refused with a message naming who decided and when.
- Business row and history row are written in one transaction; if either write fails, neither persists.
- Approval records a decision only. **No money is moved anywhere.**

## Tests

`make test` runs 42 tests (`refunds/tests.py`) covering: unauthenticated access and
writes; operator/auditor restrictions; manager self-approval (view, service, DB
constraint); valid approval and rejection with who/when/why and history; missing
reasons; zero/negative/over-payment/3-decimal/non-numeric amounts; duplicate
requests (repeated POST, other user, DB constraint, service race); repeated and
stale decisions; rollback when the history write or the business update fails;
list search/filters for refunds and KYC. Django creates a separate in-memory test
database; `data/portal.sqlite3` is never touched by tests.

## Documents

- `docs/ACCEPTANCE.md` — acceptance checklist with what was verified.
- `docs/DEMO_CHECKLIST.md` — demonstration script ($120 example).
- `docs/DESIGN_NOTES.md` — scope, tradeoffs, remaining production work, elapsed time, results.
