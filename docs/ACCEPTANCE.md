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
- [x] Shared login page, top navigation, role badge, logout (POST), messages, base CSS.
- [x] "Demo data — no payments executed" banner on every page.
- [x] Unauthenticated users are redirected to login for every portal page.
- [x] Setup command, run command that never erases data, explicit reset command.
- [x] Generated DB, secret key and local config are git-ignored.

## Refunds
- [x] Searchable list with status filter; detail page with request, decision, history.
- [x] Payments list; request refund against a payment with amount + reason.
- [x] Amount validation: > 0, <= payment amount, at most 2 decimal places.
- [x] Money stored as integer minor units + currency (USD/EUR only, DB CHECK).
- [x] One refund request per payment, enforced by DB unique constraint.
- [x] Manager approve / reject with required reason.
- [x] Detail shows who requested / decided, when, and why.
- [x] Decided requests are immutable; repeated decision returns a clear stale message.
- [x] Approval only records a decision; nothing is sent anywhere.
- [x] Business row and history row written in one transaction.

## Roles (enforced server-side, identity from session)
- [x] Operator: read, request; cannot decide (403 on direct POST).
- [x] Manager: request, decide others' requests; cannot decide own (403 + DB CHECK).
- [x] Auditor: read only; any write returns 403.

## KYC queue (read-only)
- [x] Case ID, customer, risk, status, assigned reviewer; search + risk/status filters.
- [x] No write endpoints.

## Tests (isolated in-memory test DB via `manage.py test`)
- [x] Unauthenticated access and unauthorized writes.
- [x] Auditor restrictions and manager self-approval.
- [x] Valid approval and rejection.
- [x] Invalid amounts and missing reasons.
- [x] Duplicate requests and repeated decisions.
- [x] Business change + history consistent when a write fails.

## Demo data
- [x] Mira Chen, PAY-1007, $200.00 USD, no refund request.
- [x] Manager-created pending request (RR-6, PAY-1008) for the self-approval demo.

## Browser verification (Chrome, recorded, 2026-09-22 16:06–16:30 UTC)
- [x] Full workflow (operator request $120 → manager approve → history).
- [x] Validation and permission messages visible (exact texts matched).
- [x] Duplicate request, repeated decision (via authenticated POST — see design notes),
      manager self-approval (UI + direct POST 403), auditor direct POST 403.
- [x] Server restart preserves records.
- [x] Hover contrast defect on Approve/Reject found, fixed, re-verified.
- [ ] Not done: automated browser tests, accessibility audit, CI workflow.
- [x] Demo data reset and app left at login screen (done at handoff).
