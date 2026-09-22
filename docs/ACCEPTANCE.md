# Acceptance checklist

Status legend: `[x]` verified (test or browser), `[ ]` not done, `[~]` partial.

## Stack choice (recorded before building)

Environment found: Ubuntu 22.04, Python 3.10, no Node, SQLite 3.37 (via Python's
`sqlite3`), writable home directory, Chrome available via the Computer view, a
Devin browser-preview proxy for port forwarding, `git` authenticated to the
target repo only.

Chosen: **Django 5.2 + SQLite + server-rendered templates, no JavaScript build.**
- Login, password hashing (PBKDF2), sessions and CSRF come from `django.contrib.auth`
  and the standard middleware — nothing custom.
- Forms and validation use Django forms; database access uses the ORM with
  `transaction.atomic`, `CheckConstraint`s and a `UNIQUE` (OneToOne) constraint.
- Roles are Django auth Groups (`operator`, `manager`, `auditor`).
- SQLite keeps setup to one command and persists to `data/portal.sqlite3`.
  Swapping to Postgres is a settings change plus `migrate`.

## Foundation
- [ ] Shared login page, top navigation, role badge, logout (POST), messages, base CSS.
- [ ] "Demo data — no payments executed" banner on every page.
- [ ] Unauthenticated users are redirected to login for every portal page.
- [ ] Setup command, run command that never erases data, explicit reset command.
- [ ] Generated DB, secret key and local config are git-ignored.

## Refunds
- [ ] Searchable list with status filter; detail page with request, decision, history.
- [ ] Payments list; request refund against a payment with amount + reason.
- [ ] Amount validation: > 0, <= payment amount, at most 2 decimal places.
- [ ] Money stored as integer minor units + currency (USD/EUR only, DB CHECK).
- [ ] One refund request per payment, enforced by DB unique constraint.
- [ ] Manager approve / reject with required reason.
- [ ] Detail shows who requested / decided, when, and why.
- [ ] Decided requests are immutable; repeated decision returns a clear stale message.
- [ ] Approval only records a decision; nothing is sent anywhere.
- [ ] Business row and history row written in one transaction.

## Roles (enforced server-side, identity from session)
- [ ] Operator: read, request; cannot decide (403 on direct POST).
- [ ] Manager: request, decide others' requests; cannot decide own (403 + DB CHECK).
- [ ] Auditor: read only; any write returns 403.

## KYC queue (read-only)
- [ ] Case ID, customer, risk, status, assigned reviewer; search + risk/status filters.
- [ ] No write endpoints.

## Tests (isolated in-memory test DB via `manage.py test`)
- [ ] Unauthenticated access and unauthorized writes.
- [ ] Auditor restrictions and manager self-approval.
- [ ] Valid approval and rejection.
- [ ] Invalid amounts and missing reasons.
- [ ] Duplicate requests and repeated decisions.
- [ ] Business change + history consistent when a write fails.

## Demo data
- [ ] Mira Chen, PAY-1007, $200.00 USD, no refund request.
- [ ] Manager-created pending request (RR-6, PAY-1008) for the self-approval demo.

## Browser verification
- [ ] Full workflow (operator request $120 → manager approve → history).
- [ ] Validation and permission messages visible.
- [ ] Server restart preserves records.
- [ ] Demo data reset and app left at login screen.
