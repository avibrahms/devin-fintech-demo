# Design notes

Purpose: evidence for a build-vs-buy decision (Power Apps at ~$250K/yr for a KYC
queue, refunds dashboard and feature-flag panel, with ten more tools planned)
versus building internal tools with Devin. This is a two-hour prototype. It is
**not production-ready**, and this document lists what would still be needed.

## What was built

- Shared foundation: Django project, login/logout (Django auth), three roles as auth
  Groups, base layout with navigation, role badge, flash messages, one stylesheet,
  403/404 pages, deterministic seed command, Makefile with setup/run/test/reset.
- Refunds tool: payments list, refund request form, refund list with search and
  status filter, detail page with request/decision/history, manager decision form.
- KYC queue tool: read-only list with search, risk and status filters.
- 42 server-side tests.

Adding a further tool means: a new Django app with models, a migration, views and
templates extending `base.html`, plus a nav link. The login, roles, layout,
messages, money formatting and test harness are already there.

## Key decisions and tradeoffs

| Decision | Why | Tradeoff |
| --- | --- | --- |
| Django + SQLite, server-rendered HTML, no JS build | Only Python was available in the environment; Django ships login, hashing, sessions, CSRF, forms, ORM, migrations, admin and a test runner. Fastest path to something correct. | Plain page reloads, no live updates. Not a SPA; a UI framework can be layered later if needed. |
| Roles as Django Groups checked in views **and** in the service layer | Rules hold for requests that bypass forms (tested with direct POSTs). Identity always comes from `request.user`. | Coarse roles only; no record-level or org-level permissions (not required by the brief). |
| Money as integer minor units + currency code | Exact storage; SQLite has no true DECIMAL type. Form accepts up to two decimals and converts. | Display formatting is hand-rolled (`money` filter); only USD/EUR. |
| One refund per payment via `OneToOneField` (DB UNIQUE) | Simplest correct duplicate guard, works under concurrent double-submits. | No partial / multiple refunds per payment. Would need a per-payment refundable-balance model. |
| Decision via compare-and-set (`UPDATE ... WHERE status='pending'`) inside `transaction.atomic` | Repeated clicks and stale tabs cannot overwrite a decision; message names who decided and when. | Relies on the DB for atomicity (fine on SQLite and Postgres). |
| History rows written in the same transaction as the business change; tests force failures on both sides | "Save the change and its history together". | It is an application-owned table, **not tamper-proof**: anyone with DB access can edit it. A real audit trail needs append-only storage / WORM, DB-level triggers or an external log. |
| DB CHECK constraints for status, decision-field consistency and no self-decision | Defence in depth beneath the application code. | Constraints are named and tested but not exhaustive. |
| `runserver --insecure`, `ALLOWED_HOSTS=*` by default | Demo behind Devin's preview proxy without extra config. | Not a production server configuration. |

## Known limitations (honest list)

- One refund request per payment; no partial refunds after a rejection, no cancellation
  of a pending request, no editing.
- Demo passwords are documented in the README; there is no password-reset, MFA or SSO.
- Roles are one Group per user. A user in no group can log in but can do nothing.
- Only two currencies, no FX, no per-currency rounding rules beyond two decimals.
- No pagination (lists are small), no export, no notifications.
- No rate limiting, no per-user lockout on failed logins.
- The KYC queue is display-only; there is no case detail page.
- Admin site is enabled at `/admin/` but no superuser is created by the seed.
- History is an application table, not an audit system (see above).
- Tests cover server behaviour; there are no automated browser tests.
- `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` are off so the demo works over plain http.

## Remaining production work

1. **Company login** — SSO (SAML/OIDC via e.g. `django-allauth` or `mozilla-django-oidc`),
   map IdP groups to portal roles, remove seeded passwords, enforce MFA at the IdP.
2. **Hosting** — containerise, run behind gunicorn + a reverse proxy with TLS,
   pin `ALLOWED_HOSTS`, secure cookies, `DEBUG=0`, secrets from a secret manager,
   static files via WhiteNoise or a CDN, health checks.
3. **Database migration** — move from SQLite to managed Postgres (settings change +
   `migrate`; the constraints and transactions used here work unchanged), connection
   pooling, `select_for_update` becomes a real lock.
4. **Security review** — threat model, dependency scanning, CSP headers, session
   lifetime policy, login throttling, review of every write path, penetration test;
   decide whether decisions need dual control or amount-based approval limits.
5. **Backups** — automated DB backups with restore drills; retention policy for history.
6. **Monitoring** — structured logs, error tracking (e.g. Sentry), request metrics,
   alerts on 5xx and on failed decision writes; audit log export to the SIEM.
7. **Support ownership** — a named engineering owner, on-call expectations, runbook,
   change management for new tools, and a definition of who can grant roles.
8. **Real audit trail** — append-only event store or DB-level triggers, signed or
   externally shipped, before anyone relies on the history for compliance.
9. **Integration** — this prototype never touches payment rails. Connecting approval
   to an actual refund execution is a separate, carefully controlled project.

## Elapsed time and results

- Start: 2026-09-22 15:43 UTC. Budget: 120 minutes (hard stop 17:43 UTC).
- Milestones: first page served ~15:52; refunds workflow + KYC + seed complete ~15:53;
  42 tests passing ~15:55; docs and PR ~16:05; browser verification and reset after that.
- End time and final elapsed: see the "Results" section below (filled in at handoff).

### Results (filled in at handoff)

See the bottom of this file.
