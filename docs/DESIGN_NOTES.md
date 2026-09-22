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
- Recorded browser verification ~15:58–16:09 UTC (hover-contrast fix pushed 16:07 and
  re-verified); results recorded, demo reset and app left at login by 16:13 UTC.
- Total elapsed for the build: about 30 minutes of the 120-minute budget (15:43–16:13 UTC).
  Timestamps are from the session machine's clock; the earlier "16:06, 23 min" progress
  message was a misreading and was corrected in the chat.
- Follow-up (same budget): a CSRF failure was reported on the HTTPS preview at ~16:19;
  diagnosed, fixed, regression-tested and re-verified by the reporter through the preview
  by 16:44 UTC; hosting adapter for a public demo link added in the same window.
- Follow-up 2: "changes disappear" reported ~16:58; traced to Devin's own CLI reset (see
  below); presenter reset button, second manager account, 14 regression tests, restart
  verification and docs done by ~17:15 UTC. Cumulative Devin working time ≈ 95 of 120 min.

### Incident: "CSRF verification failed" on the preview URL

- **Symptom:** login POST through `https://8000--<session>.preview.devinapps.com` returned
  403; the same POST on localhost worked.
- **Cause (from the server log):** the preview proxy forwards `X-Forwarded-Proto: https`
  and the public host, but rewrites the browser's `Origin` header to `http://localhost`.
  Django's CSRF origin check compares `Origin` with the request host and rejected it:
  `Origin checking failed - http://localhost does not match any trusted origins`.
  Adding the public URL to `CSRF_TRUSTED_ORIGINS` (the first attempt) could not help,
  because the rejected origin was never the public URL.
- **Fix:** in proxy mode (`PORTAL_PUBLIC_ORIGIN` or `PORTAL_HTTPS_PROXY=1`) the rewritten
  origins (`PORTAL_PROXY_ORIGINS`, default `http://localhost,http://127.0.0.1`) are added
  to the trusted list; cookies become `Secure`. CSRF protection stays on: the per-session
  token is still required and any other origin is still refused. A custom failure page
  now shows Django's reason so this class of problem is diagnosable without log access.
- **Tests:** `core/tests.py` runs the login and logout with CSRF enforcement on
  (`Client(enforce_csrf_checks=True)`) using the proxy's real headers, and checks that a
  missing token, an untrusted origin, and the rewritten origin *outside* proxy mode are
  all still rejected. 52 tests pass.
- **Trade-off:** trusting `http://localhost` as an origin is acceptable for a demo behind
  an authenticated preview proxy; a production deployment would sit behind a proxy that
  preserves `Origin` (or sets `X-Forwarded-*` consistently) and would not need it.

### Incident: "changes disappear" on the preview (16:52 UTC)

- **Symptom:** an approval and a new request made through the preview reverted to the
  starting data after switching accounts.
- **Trace:** server log — `POST /refunds/payments/11/request/ → 302 → GET /refunds/9/ 200`
  at 16:51:58 and `POST /refunds/8/decide/ → 302 → GET /refunds/8/ 200` (approved page)
  at 16:52:35: both writes succeeded and were rendered back. The next list load at
  16:52:47 returned exactly the seeded 7-request page (4808 bytes, same as before any
  change). No server restart occurred in that window.
- **Cause:** Devin ran `seed_demo --reset` from the command line at ~16:52:40 (the
  original brief asked for a reset after testing; the reset was run while the reporter was
  still testing). It deleted all refund records and re-seeded RR-1..RR-7. The
  application's writes, transactions and persistence were not at fault; nothing in normal
  startup resets data (`seed_demo` without `--reset` returns early when payments exist).
- **Fix / guard rails:** the reset is now an explicit, visible product action: a
  `presenter` account (separate from operator/manager/auditor) gets a **Reset demo data**
  button, only when `PORTAL_DEMO_MODE=1`, with a confirmation page ("Delete all demo
  changes and restore the starting data?"); Cancel is a plain link and changes nothing;
  the POST is presenter-only server-side (403 for every other role, 404 outside demo
  mode), CSRF-protected, and restores the original IDs/examples while keeping all demo
  accounts. The CLI reset prints what it is about to delete. `seed_demo` no longer
  re-hashes unchanged passwords, so a startup or reset no longer logs users out.
  **Demo mode must be off in production** — the button deletes every business record.
- **Regression tests (`core/tests_seed.py`):** startup seed preserves a new request and
  a decision and is idempotent; only `--reset` deletes; presenter button/confirm/cancel;
  other roles and anonymous users cannot reset (UI and direct POST); missing CSRF token
  is rejected; feature is 404 outside demo mode; presenter cannot write refunds; a second
  manager (`manager2`) can approve `manager`'s own request while manager/operator/auditor
  cannot.
- **Verified on the running preview server (HTTP with the proxy's real headers, not
  through Devin's browser):** operator request on PAY-1012 → RR-8; operator, auditor and
  presenter POST decide → 403; `manager` on own RR-6 → 403; `manager2` approves RR-8;
  repeat approve → stale message; logout/login as auditor after a full server stop/start:
  RR-1..RR-8 present, RR-8 approved by manager2 with 2 history rows. The preview itself
  can only be opened with the account owner's Devin login.

### Results

- **Automated tests:** `make test` — 66 tests (42 behaviour + 10 CSRF/proxy + 14 demo
  data lifecycle / reset / two-manager), all passing,
  on Django's isolated in-memory test database.
- **Browser verification (Chrome, maximised 1600×1069, localhost, recorded):** all eight
  scenarios in `docs/ACCEPTANCE.md` → "Browser verification" passed: login banner and
  redirect, wrong-password error, all four amount/reason validation messages, $120
  request on PAY-1007, duplicate resubmission redirected with the duplicate message,
  manager approval with recorded reason, history rows, repeated decision refused with
  the stale message, manager self-approval blocked (UI and direct POST → 403), auditor
  has no write controls and direct POST → 403, KYC search/filters, records intact
  after stopping and restarting the server.
- **Known failure found and fixed during verification:** Approve/Reject buttons lost
  their colour on hover (white text on pale grey). Fixed in CSS and re-verified.
- **Deviation:** the "press Back and click Approve again" scenario could not be
  reproduced literally — Chrome reloaded the finalised page instead of restoring the
  stale form. The repeated-decision path was exercised with an authenticated POST from
  the browser instead, and is covered by automated tests.
- **Preview URL after the CSRF fix:** the reporter's own retry through the HTTPS preview
  (server log 16:41–16:44 UTC) logged in, searched/filtered refunds, browsed payments and
  KYC, and created a refund request (302 → detail page). Devin cannot open the preview
  itself (it requires the account owner's Devin login), so the full three-role
  walkthrough through that exact URL was not repeated by Devin; the reporter's own
  session (16:45–16:53 UTC) shows three role logins, two logouts, a request and an
  approval succeeding before the reset incident above. No public deployment has been made
  (held for the reporter's approval).
- **Not done:** no automated browser tests; no load or concurrency test beyond the
  duplicate/stale unit tests; no accessibility audit; no CI workflow in the repo.
- **Observed usage:** one Devin session (this one). No token or cost figures are
  available from inside the session, so none are claimed here.
