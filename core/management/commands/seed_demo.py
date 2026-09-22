"""
Deterministic demo data. Idempotent: without --reset it only seeds when the
database has no payments, so normal startup never erases data. With --reset
it deletes refund/KYC/payment demo records and re-seeds; demo accounts are
kept (passwords reset to the documented values).
"""
from datetime import datetime, timezone as dt_tz

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.core.management.color import no_style
from django.db import connection, transaction

from core.roles import AUDITOR, MANAGER, OPERATOR, ROLES
from kyc.models import KycCase
from refunds.models import Payment, RefundEvent, RefundRequest, RefundStatus

DEMO_ACCOUNTS = [
    # username, password, role, first, last
    ("operator", "operator-demo-2026", OPERATOR, "Olivia", "Park"),
    ("manager", "manager-demo-2026", MANAGER, "Marcus", "Reed"),
    ("auditor", "auditor-demo-2026", AUDITOR, "Ava", "Lindqvist"),
]


def ts(y, m, d, hh=9, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=dt_tz.utc)


PAYMENTS = [
    # reference, customer, amount_minor, currency, paid_at, description
    ("PAY-1001", "Daniel Okafor", 45_000, "USD", ts(2026, 8, 3, 10, 12), "Annual plan"),
    ("PAY-1002", "Sofia Marchetti", 12_950, "EUR", ts(2026, 8, 5, 14, 30), "Monthly plan"),
    ("PAY-1003", "Liam Patel", 89_900, "USD", ts(2026, 8, 9, 8, 45), "Hardware order #4471"),
    ("PAY-1004", "Hannah Weiss", 7_500, "EUR", ts(2026, 8, 12, 16, 5), "Add-on seats"),
    ("PAY-1005", "Noah Bergström", 250_000, "USD", ts(2026, 8, 15, 11, 20), "Enterprise onboarding"),
    ("PAY-1006", "Amara Nwosu", 3_299, "USD", ts(2026, 8, 18, 9, 0), "Monthly plan"),
    ("PAY-1007", "Mira Chen", 20_000, "USD", ts(2026, 8, 21, 13, 40), "Annual plan"),
    ("PAY-1008", "Tomás Herrera", 64_000, "EUR", ts(2026, 8, 24, 10, 55), "Hardware order #4502"),
    ("PAY-1009", "Grace Adeyemi", 15_000, "USD", ts(2026, 8, 27, 15, 15), "Consulting hours"),
    ("PAY-1010", "Yuki Tanaka", 9_999, "EUR", ts(2026, 9, 1, 12, 0), "Monthly plan"),
    ("PAY-1011", "Elena Petrova", 120_000, "USD", ts(2026, 9, 4, 9, 30), "Enterprise onboarding"),
    ("PAY-1012", "Jonas Müller", 5_400, "EUR", ts(2026, 9, 8, 17, 25), "Add-on seats"),
]

# reference, requester, amount_minor, reason, requested_at, decision (None or (decider, status, reason, decided_at))
REFUNDS = [
    ("PAY-1001", "operator", 45_000, "Customer cancelled within 14-day cooling-off period.", ts(2026, 8, 6, 9, 5),
     ("manager", RefundStatus.APPROVED, "Within policy; full refund.", ts(2026, 8, 6, 11, 40))),
    ("PAY-1002", "operator", 12_950, "Duplicate charge reported by customer.", ts(2026, 8, 7, 10, 15),
     ("manager", RefundStatus.REJECTED, "No duplicate found in ledger; asked ops to re-verify with customer.", ts(2026, 8, 7, 12, 2))),
    ("PAY-1003", "operator", 25_000, "Partial refund: one unit returned damaged.", ts(2026, 8, 14, 15, 30),
     ("manager", RefundStatus.APPROVED, "Return confirmed by warehouse.", ts(2026, 8, 15, 8, 10))),
    ("PAY-1004", "operator", 7_500, "Seats never activated.", ts(2026, 8, 20, 11, 0), None),
    ("PAY-1006", "operator", 3_299, "Customer disputes renewal.", ts(2026, 8, 28, 9, 45), None),
    ("PAY-1008", "manager", 64_000, "Order cancelled before shipment; customer requested reversal.", ts(2026, 9, 2, 14, 20), None),
    ("PAY-1010", "operator", 5_000, "Goodwill credit after outage.", ts(2026, 9, 9, 10, 30),
     ("manager", RefundStatus.REJECTED, "Goodwill credits are issued as account credit, not refunds.", ts(2026, 9, 9, 16, 45))),
]

KYC_CASES = [
    ("KYC-2201", "Daniel Okafor", "low", "closed", "r.singh", ts(2026, 7, 28, 9, 0)),
    ("KYC-2202", "Sofia Marchetti", "medium", "in_review", "j.alvarez", ts(2026, 8, 1, 10, 30)),
    ("KYC-2203", "Noah Bergström", "high", "escalated", "k.osei", ts(2026, 8, 4, 14, 15)),
    ("KYC-2204", "Hannah Weiss", "low", "closed", "r.singh", ts(2026, 8, 6, 11, 45)),
    ("KYC-2205", "Amara Nwosu", "medium", "waiting_on_customer", "j.alvarez", ts(2026, 8, 11, 16, 0)),
    ("KYC-2206", "Mira Chen", "low", "in_review", "r.singh", ts(2026, 8, 19, 9, 20)),
    ("KYC-2207", "Tomás Herrera", "high", "in_review", "k.osei", ts(2026, 8, 22, 13, 10)),
    ("KYC-2208", "Grace Adeyemi", "medium", "new", "", ts(2026, 8, 29, 8, 50)),
    ("KYC-2209", "Yuki Tanaka", "low", "new", "", ts(2026, 9, 2, 12, 35)),
    ("KYC-2210", "Elena Petrova", "high", "escalated", "k.osei", ts(2026, 9, 5, 15, 5)),
    ("KYC-2211", "Jonas Müller", "medium", "in_review", "j.alvarez", ts(2026, 9, 9, 10, 10)),
    ("KYC-2212", "Priya Raman", "low", "waiting_on_customer", "r.singh", ts(2026, 9, 12, 14, 40)),
]


class Command(BaseCommand):
    help = "Seed deterministic demo data. Use --reset to wipe demo records and re-seed."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete demo records and re-seed.")

    @transaction.atomic
    def handle(self, *args, reset=False, **options):
        users = self._ensure_accounts()
        if reset:
            RefundEvent.objects.all().delete()
            RefundRequest.objects.all().delete()
            Payment.objects.all().delete()
            KycCase.objects.all().delete()
            # Restart ID sequences so RR-1..RR-7 / PAY ids are stable after every reset.
            reset_sql = connection.ops.sequence_reset_by_name_sql(
                no_style(),
                [
                    {"table": m._meta.db_table, "column": "id"}
                    for m in (RefundEvent, RefundRequest, Payment, KycCase)
                ],
            )
            with connection.cursor() as cursor:
                for sql in reset_sql:
                    cursor.execute(sql)
            self.stdout.write("Demo records deleted.")
        elif Payment.objects.exists():
            self.stdout.write("Database already contains data; nothing seeded (use --reset to re-seed).")
            return

        payments = {}
        for ref, customer, amount_minor, currency, paid_at, description in PAYMENTS:
            payments[ref] = Payment.objects.create(
                reference=ref, customer_name=customer, amount_minor=amount_minor, currency=currency,
                paid_at=paid_at, description=description,
            )

        for ref, requester, amount_minor, reason, requested_at, decision in REFUNDS:
            payment = payments[ref]
            refund = RefundRequest(
                payment=payment, amount_minor=amount_minor, currency=payment.currency, reason=reason,
                status=RefundStatus.PENDING, requested_by=users[requester], requested_at=requested_at,
            )
            if decision:
                decider, status, decision_reason, decided_at = decision
                refund.status = status
                refund.decided_by = users[decider]
                refund.decided_at = decided_at
                refund.decision_reason = decision_reason
            refund.save()
            RefundEvent.objects.create(
                refund=refund, action=RefundEvent.Action.REQUESTED, actor=users[requester], occurred_at=requested_at,
                from_status="", to_status=RefundStatus.PENDING, amount_minor=amount_minor, currency=payment.currency,
                reason=reason,
            )
            if decision:
                RefundEvent.objects.create(
                    refund=refund, action=status, actor=users[decider], occurred_at=decided_at,
                    from_status=RefundStatus.PENDING, to_status=status, amount_minor=amount_minor,
                    currency=payment.currency, reason=decision_reason,
                )

        for case_id, customer, risk, status, reviewer, opened_at in KYC_CASES:
            KycCase.objects.create(
                case_id=case_id, customer_name=customer, risk_level=risk, status=status,
                assigned_reviewer=reviewer, opened_at=opened_at,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(PAYMENTS)} payments, {len(REFUNDS)} refund requests, {len(KYC_CASES)} KYC cases."
            )
        )

    def _ensure_accounts(self):
        groups = {role: Group.objects.get_or_create(name=role)[0] for role in ROLES}
        users = {}
        for username, password, role, first, last in DEMO_ACCOUNTS:
            user, _ = User.objects.get_or_create(username=username, defaults={"first_name": first, "last_name": last})
            user.first_name, user.last_name = first, last
            user.set_password(password)
            user.save()
            user.groups.set([groups[role]])
            users[username] = user
        return users
