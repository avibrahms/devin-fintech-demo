# Demonstration checklist — the $120 example

Before recording: `make reset` (wipes demo records, re-seeds), then `make run`.
Confirm the login page shows and the yellow "Demo data — no payments executed"
banner is visible.

Accounts: `operator` / `operator-demo-2026`, `manager` / `manager-demo-2026`,
`auditor` / `auditor-demo-2026`.

## 1. Operator requests $120 on Mira Chen's payment
1. Sign in as `operator`. Note the OPERATOR badge and Log out link top right.
2. Open **Payments**. Search `Mira`. Row `PAY-1007`, Mira Chen, $200.00 USD, refund request "None".
3. Click **Request refund**.
4. Optional validation demo: enter `250` → "Amount cannot exceed the original payment."
   Enter `120.005` → "Amount cannot have more than two decimal places."
   Leave reason empty → "A reason is required."
5. Enter amount `120.00`, reason e.g. "Customer downgraded plan; partial refund agreed." Submit.
6. You land on the detail page: RR-8, Pending, $120.00, submitted by operator with timestamp.
   The decision panel says "Only a manager can approve or reject this request."
7. Optional: use the browser back button and submit the form again → redirected to the
   same RR-8 with "A refund request already exists for payment PAY-1007." (one request per payment).
8. Log out.

## 2. Manager approves it
1. Sign in as `manager`. Note the MANAGER badge.
2. **Refunds** → filter Status = Pending. Open RR-8 (PAY-1007, Mira Chen).
3. Enter a decision reason, e.g. "Approved per downgrade policy." Click **Approve**.
4. Green message: "Refund request RR-8 approved. Decision recorded; no money moved."
   The Decision panel now shows Approved, decided by manager, timestamp, reason,
   and the note that it is final.
5. Optional: press the browser back button and click Approve/Reject again →
   "This request was already approved by manager at … No further decision is possible."

## 3. Show the history
1. Scroll to **History** on RR-8: two rows — `requested` by operator (— → pending, $120.00)
   and `approved` by manager (pending → approved, $120.00) with both reasons.
2. Optional: sign in as `auditor`; open RR-8 — same history, no action buttons anywhere,
   no "Request a refund" button.

## 4. Self-approval is blocked
1. Still as `manager`, open RR-6 (PAY-1008, Tomás Herrera) — a pending request the manager
   submitted. The page says "You submitted this request. Managers cannot approve or reject
   their own requests; another manager must decide it." There are no Approve/Reject buttons.
2. (For the sceptic) a direct `POST /refunds/6/decide/` as the manager returns HTTP 403 —
   covered by `test_manager_cannot_approve_own_request`, and the database also has a
   CHECK constraint `refund_no_self_decision`.

## 5. Persistence
1. Stop the server (Ctrl-C), `make run` again, sign in — RR-8 is still approved.

## Reset for the next run
`make reset` then `make run`.
