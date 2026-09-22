"""
Server-side behaviour tests. `manage.py test` runs these against a separate
in-memory SQLite database, never against data/portal.sqlite3.
"""
from datetime import datetime, timezone as dt_tz
from unittest import mock

from django.contrib.auth.models import Group, User
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from core.roles import AUDITOR, MANAGER, OPERATOR
from kyc.models import KycCase

from . import services
from .models import Payment, RefundEvent, RefundRequest, RefundStatus


def make_user(username, role):
    user = User.objects.create_user(username=username, password="pw-" + username)
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    return user


class RefundsTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operator = make_user("op", OPERATOR)
        cls.manager = make_user("mgr", MANAGER)
        cls.manager2 = make_user("mgr2", MANAGER)
        cls.auditor = make_user("aud", AUDITOR)
        cls.payment = Payment.objects.create(
            reference="PAY-T1", customer_name="Mira Chen", amount_minor=20_000, currency="USD",
            paid_at=datetime(2026, 8, 21, tzinfo=dt_tz.utc), description="Annual plan",
        )
        cls.payment2 = Payment.objects.create(
            reference="PAY-T2", customer_name="Sofia Marchetti", amount_minor=12_950, currency="EUR",
            paid_at=datetime(2026, 8, 5, tzinfo=dt_tz.utc),
        )
        KycCase.objects.create(
            case_id="KYC-T1", customer_name="Mira Chen", risk_level="low", status="new",
            opened_at=datetime(2026, 8, 1, tzinfo=dt_tz.utc),
        )

    def login(self, user):
        self.client.force_login(user)

    def pending_request(self, payment=None, by=None, amount_minor=12_000):
        return services.request_refund(
            payment=payment or self.payment, user=by or self.operator, amount_minor=amount_minor, reason="Customer asked"
        )

    def post_request(self, payment, amount, reason):
        return self.client.post(reverse("refunds:request", args=[payment.pk]), {"amount": amount, "reason": reason})

    def post_decision(self, refund, decision, reason="Reviewed"):
        return self.client.post(reverse("refunds:decide", args=[refund.pk]), {"decision": decision, "reason": reason})


class AuthenticationTests(RefundsTestBase):
    def test_unauthenticated_reads_redirect_to_login(self):
        refund = self.pending_request()
        for url in [
            reverse("refunds:list"), reverse("refunds:payments"), reverse("kyc:list"),
            reverse("refunds:detail", args=[refund.pk]), reverse("refunds:request", args=[self.payment.pk]),
        ]:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302, url)
            self.assertTrue(resp.url.startswith(reverse("login")), url)

    def test_unauthenticated_writes_rejected_and_nothing_changes(self):
        refund = self.pending_request()
        resp = self.post_request(self.payment2, "10.00", "x")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith(reverse("login")))
        resp = self.post_decision(refund, "approve")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith(reverse("login")))
        self.assertEqual(RefundRequest.objects.count(), 1)
        refund.refresh_from_db()
        self.assertEqual(refund.status, RefundStatus.PENDING)
        self.assertEqual(RefundEvent.objects.count(), 1)

    def test_login_page_and_bad_password(self):
        resp = self.client.post(reverse("login"), {"username": "op", "password": "wrong"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Please enter a correct username and password")
        resp = self.client.post(reverse("login"), {"username": "op", "password": "pw-op"})
        self.assertEqual(resp.status_code, 302)


class RolePermissionTests(RefundsTestBase):
    def test_operator_cannot_decide_via_direct_post(self):
        refund = self.pending_request()
        self.login(self.operator)
        resp = self.post_decision(refund, "approve")
        self.assertEqual(resp.status_code, 403)
        refund.refresh_from_db()
        self.assertEqual(refund.status, RefundStatus.PENDING)
        self.assertEqual(refund.events.count(), 1)

    def test_operator_detail_page_has_no_decision_form(self):
        refund = self.pending_request()
        self.login(self.operator)
        resp = self.client.get(reverse("refunds:detail", args=[refund.pk]))
        self.assertNotContains(resp, reverse("refunds:decide", args=[refund.pk]))
        self.assertContains(resp, "Only a manager can approve or reject")

    def test_auditor_can_read_everything(self):
        refund = self.pending_request()
        self.login(self.auditor)
        for url in [reverse("refunds:list"), reverse("refunds:payments"), reverse("kyc:list"),
                    reverse("refunds:detail", args=[refund.pk])]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        resp = self.client.get(reverse("refunds:detail", args=[refund.pk]))
        self.assertContains(resp, "Customer asked")  # history is visible
        self.assertNotContains(resp, "Request a refund")

    def test_auditor_cannot_write(self):
        refund = self.pending_request()
        self.login(self.auditor)
        self.assertEqual(self.client.get(reverse("refunds:request", args=[self.payment2.pk])).status_code, 403)
        self.assertEqual(self.post_request(self.payment2, "10.00", "x").status_code, 403)
        self.assertEqual(self.post_decision(refund, "approve").status_code, 403)
        self.assertEqual(self.post_decision(refund, "reject").status_code, 403)
        self.assertEqual(RefundRequest.objects.count(), 1)
        refund.refresh_from_db()
        self.assertEqual(refund.status, RefundStatus.PENDING)

    def test_kyc_queue_rejects_post(self):
        self.login(self.manager)
        self.assertEqual(self.client.post(reverse("kyc:list"), {"status": "closed"}).status_code, 405)

    def test_manager_cannot_approve_own_request(self):
        refund = self.pending_request(by=self.manager)
        self.login(self.manager)
        resp = self.client.get(reverse("refunds:detail", args=[refund.pk]))
        self.assertContains(resp, "Managers cannot approve or reject their own requests")
        self.assertNotContains(resp, 'value="approve"')
        resp = self.post_decision(refund, "approve", "trying anyway")
        self.assertEqual(resp.status_code, 403)
        refund.refresh_from_db()
        self.assertEqual(refund.status, RefundStatus.PENDING)
        self.assertEqual(refund.events.count(), 1)

    def test_self_decision_blocked_by_database_constraint(self):
        refund = self.pending_request(by=self.manager)
        with self.assertRaises(IntegrityError):
            RefundRequest.objects.filter(pk=refund.pk).update(
                status=RefundStatus.APPROVED, decided_by=self.manager, decision_reason="x",
                decided_at=datetime(2026, 9, 1, tzinfo=dt_tz.utc),
            )

    def test_other_manager_can_decide_managers_request(self):
        refund = self.pending_request(by=self.manager)
        self.login(self.manager2)
        self.post_decision(refund, "approve", "Second manager reviewed")
        refund.refresh_from_db()
        self.assertEqual(refund.status, RefundStatus.APPROVED)
        self.assertEqual(refund.decided_by, self.manager2)

    def test_identity_comes_from_session_not_form(self):
        self.login(self.operator)
        resp = self.client.post(
            reverse("refunds:request", args=[self.payment.pk]),
            {"amount": "10.00", "reason": "spoof", "requested_by": self.manager.pk, "user": "mgr", "status": "approved"},
        )
        self.assertEqual(resp.status_code, 302)
        refund = RefundRequest.objects.get()
        self.assertEqual(refund.requested_by, self.operator)
        self.assertEqual(refund.status, RefundStatus.PENDING)


class DecisionTests(RefundsTestBase):
    def test_valid_approval_records_who_when_why_and_history(self):
        refund = self.pending_request()
        self.login(self.manager)
        resp = self.post_decision(refund, "approve", "Within policy")
        self.assertRedirects(resp, reverse("refunds:detail", args=[refund.pk]))
        refund.refresh_from_db()
        self.assertEqual(refund.status, RefundStatus.APPROVED)
        self.assertEqual(refund.decided_by, self.manager)
        self.assertIsNotNone(refund.decided_at)
        self.assertEqual(refund.decision_reason, "Within policy")
        events = list(refund.events.all())
        self.assertEqual([e.action for e in events], ["requested", "approved"])
        self.assertEqual(events[1].actor, self.manager)
        self.assertEqual(events[1].from_status, "pending")
        self.assertEqual(events[1].to_status, "approved")
        page = self.client.get(reverse("refunds:detail", args=[refund.pk]))
        self.assertContains(page, "Within policy")
        self.assertContains(page, "mgr")
        self.assertContains(page, "no money is moved")

    def test_valid_rejection(self):
        refund = self.pending_request()
        self.login(self.manager)
        self.post_decision(refund, "reject", "Outside window")
        refund.refresh_from_db()
        self.assertEqual(refund.status, RefundStatus.REJECTED)
        self.assertEqual(refund.decision_reason, "Outside window")
        self.assertEqual(refund.events.last().action, "rejected")

    def test_decision_requires_reason(self):
        refund = self.pending_request()
        self.login(self.manager)
        for reason in ["", "   "]:
            resp = self.post_decision(refund, "approve", reason)
            self.assertRedirects(resp, reverse("refunds:detail", args=[refund.pk]), fetch_redirect_response=False)
            refund.refresh_from_db()
            self.assertEqual(refund.status, RefundStatus.PENDING)
        page = self.client.get(reverse("refunds:detail", args=[refund.pk]))
        self.assertContains(page, "A decision reason is required.")
        self.assertEqual(refund.events.count(), 1)

    def test_decision_requires_valid_choice(self):
        refund = self.pending_request()
        self.login(self.manager)
        self.post_decision(refund, "maybe", "x")
        refund.refresh_from_db()
        self.assertEqual(refund.status, RefundStatus.PENDING)

    def test_repeated_decision_is_rejected_with_stale_message(self):
        refund = self.pending_request()
        self.login(self.manager)
        self.post_decision(refund, "approve", "First")
        resp = self.post_decision(refund, "reject", "Second click / stale tab")
        self.assertRedirects(resp, reverse("refunds:detail", args=[refund.pk]), fetch_redirect_response=False)
        refund.refresh_from_db()
        self.assertEqual(refund.status, RefundStatus.APPROVED)
        self.assertEqual(refund.decision_reason, "First")
        self.assertEqual(refund.events.count(), 2)
        page = self.client.get(reverse("refunds:detail", args=[refund.pk]))
        self.assertContains(page, "already approved by mgr")
        self.assertContains(page, "No further decision is possible")

    def test_second_manager_stale_decision(self):
        refund = self.pending_request()
        self.login(self.manager)
        self.post_decision(refund, "reject", "First")
        self.client.logout()
        self.login(self.manager2)
        self.post_decision(refund, "approve", "Stale page")
        refund.refresh_from_db()
        self.assertEqual(refund.status, RefundStatus.REJECTED)
        self.assertEqual(refund.decided_by, self.manager)

    def test_repeated_decision_service_level(self):
        refund = self.pending_request()
        services.decide_refund(refund_id=refund.pk, user=self.manager, approve=True, reason="ok")
        with self.assertRaises(services.StaleDecision):
            services.decide_refund(refund_id=refund.pk, user=self.manager2, approve=False, reason="again")

    def test_decided_request_cannot_be_reverted_in_db(self):
        refund = self.pending_request()
        services.decide_refund(refund_id=refund.pk, user=self.manager, approve=True, reason="ok")
        with self.assertRaises(IntegrityError):
            RefundRequest.objects.filter(pk=refund.pk).update(status=RefundStatus.PENDING)


class RequestValidationTests(RefundsTestBase):
    def setUp(self):
        self.login(self.operator)

    def assert_rejected(self, amount, reason, expected_msg):
        resp = self.post_request(self.payment, amount, reason)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, expected_msg)
        self.assertEqual(RefundRequest.objects.count(), 0)
        self.assertEqual(RefundEvent.objects.count(), 0)

    def test_zero_amount(self):
        self.assert_rejected("0", "reason", "Amount must be greater than zero.")
        self.assert_rejected("0.00", "reason", "Amount must be greater than zero.")

    def test_negative_amount(self):
        self.assert_rejected("-5.00", "reason", "Amount must be greater than zero.")

    def test_more_than_two_decimals(self):
        self.assert_rejected("10.005", "reason", "Amount cannot have more than two decimal places.")
        self.assert_rejected("0.001", "reason", "Amount cannot have more than two decimal places.")

    def test_above_payment_amount(self):
        self.assert_rejected("200.01", "reason", "Amount cannot exceed the original payment.")
        self.assert_rejected("1000", "reason", "Amount cannot exceed the original payment.")

    def test_non_numeric_amount(self):
        self.assert_rejected("abc", "reason", "Enter a valid amount.")
        self.assert_rejected("", "reason", "Enter a refund amount.")

    def test_missing_reason(self):
        self.assert_rejected("10.00", "", "A reason is required.")
        self.assert_rejected("10.00", "   ", "A reason is required.")

    def test_full_amount_and_exact_cents_accepted(self):
        resp = self.post_request(self.payment, "200.00", "Full refund")
        refund = RefundRequest.objects.get()
        self.assertRedirects(resp, reverse("refunds:detail", args=[refund.pk]))
        self.assertEqual(refund.amount_minor, 20_000)
        self.assertEqual(refund.currency, "USD")
        self.assertEqual(refund.requested_by, self.operator)
        self.assertEqual(refund.status, RefundStatus.PENDING)
        self.assertEqual(refund.events.count(), 1)

    def test_money_is_stored_exactly(self):
        self.post_request(self.payment2, "0.10", "Tiny")
        refund = RefundRequest.objects.get()
        self.assertEqual(refund.amount_minor, 10)
        self.assertEqual(str(refund.amount), "0.1")
        page = self.client.get(reverse("refunds:detail", args=[refund.pk]))
        self.assertContains(page, "€0.10")

    def test_service_rejects_bad_amounts_regardless_of_form(self):
        for bad in [0, -1, 20_001]:
            with self.assertRaises(services.RefundError):
                services.request_refund(payment=self.payment, user=self.operator, amount_minor=bad, reason="r")
        with self.assertRaises(services.RefundError):
            services.request_refund(payment=self.payment, user=self.operator, amount_minor=100, reason="  ")
        self.assertEqual(RefundRequest.objects.count(), 0)

    def test_parse_amount_helper(self):
        self.assertEqual(services.parse_amount_to_minor("120"), 12_000)
        self.assertEqual(services.parse_amount_to_minor("120.5"), 12_050)
        for bad in ["120.005", "0", "-1", "abc", "NaN"]:
            with self.assertRaises(services.RefundError):
                services.parse_amount_to_minor(bad)

    def test_db_rejects_non_positive_amount(self):
        with self.assertRaises(IntegrityError):
            RefundRequest.objects.create(
                payment=self.payment, amount_minor=0, currency="USD", reason="x",
                requested_by=self.operator, requested_at=datetime(2026, 9, 1, tzinfo=dt_tz.utc),
            )

    def test_db_rejects_unsupported_currency(self):
        with self.assertRaises(IntegrityError):
            Payment.objects.create(
                reference="PAY-GBP", customer_name="x", amount_minor=100, currency="GBP",
                paid_at=datetime(2026, 9, 1, tzinfo=dt_tz.utc),
            )


class DuplicateAndConsistencyTests(RefundsTestBase):
    def test_duplicate_request_via_repeated_post(self):
        self.login(self.operator)
        first = self.post_request(self.payment, "120.00", "Customer asked")
        second = self.post_request(self.payment, "120.00", "Customer asked")
        refund = RefundRequest.objects.get()  # exactly one row
        self.assertRedirects(first, reverse("refunds:detail", args=[refund.pk]), fetch_redirect_response=False)
        self.assertRedirects(second, reverse("refunds:detail", args=[refund.pk]), fetch_redirect_response=False)
        self.assertEqual(refund.events.count(), 1)
        page = self.client.get(reverse("refunds:detail", args=[refund.pk]))
        self.assertContains(page, "A refund request already exists for payment PAY-T1")

    def test_duplicate_request_from_other_user_blocked(self):
        self.pending_request()
        self.login(self.manager)
        resp = self.post_request(self.payment, "50.00", "Another attempt")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(RefundRequest.objects.count(), 1)

    def test_duplicate_request_blocked_by_database(self):
        self.pending_request()
        with self.assertRaises(IntegrityError):
            RefundRequest.objects.create(
                payment=self.payment, amount_minor=100, currency="USD", reason="dup",
                requested_by=self.operator, requested_at=datetime(2026, 9, 1, tzinfo=dt_tz.utc),
            )

    def test_duplicate_request_service_level_race(self):
        """Simulates two requests passing the pre-check before either inserts."""
        self.pending_request()
        with self.assertRaises(services.DuplicateRequest):
            services.request_refund(payment=self.payment, user=self.manager, amount_minor=100, reason="race")
        self.assertEqual(RefundRequest.objects.count(), 1)
        self.assertEqual(RefundEvent.objects.count(), 1)

    def test_request_rolled_back_when_history_write_fails(self):
        with mock.patch.object(RefundEvent.objects, "create", side_effect=IntegrityError("simulated")):
            with self.assertRaises(IntegrityError):
                services.request_refund(payment=self.payment, user=self.operator, amount_minor=100, reason="r")
        self.assertEqual(RefundRequest.objects.count(), 0)
        self.assertEqual(RefundEvent.objects.count(), 0)

    def test_decision_rolled_back_when_history_write_fails(self):
        refund = self.pending_request()
        with mock.patch.object(RefundEvent.objects, "create", side_effect=RuntimeError("disk full")):
            with self.assertRaises(RuntimeError):
                services.decide_refund(refund_id=refund.pk, user=self.manager, approve=True, reason="ok")
        refund.refresh_from_db()
        self.assertEqual(refund.status, RefundStatus.PENDING)
        self.assertIsNone(refund.decided_by)
        self.assertEqual(refund.decision_reason, "")
        self.assertEqual(refund.events.count(), 1)
        # And the request is still decidable afterwards.
        services.decide_refund(refund_id=refund.pk, user=self.manager, approve=True, reason="ok")
        refund.refresh_from_db()
        self.assertEqual(refund.status, RefundStatus.APPROVED)
        self.assertEqual(refund.events.count(), 2)

    def test_history_without_business_change_is_impossible_when_update_fails(self):
        refund = self.pending_request()
        with mock.patch.object(RefundRequest.objects, "filter", side_effect=RuntimeError("db gone")):
            with self.assertRaises(RuntimeError):
                services.decide_refund(refund_id=refund.pk, user=self.manager, approve=True, reason="ok")
        self.assertEqual(refund.events.count(), 1)
        refund.refresh_from_db()
        self.assertEqual(refund.status, RefundStatus.PENDING)

    def test_db_rejects_decided_row_without_reason_or_decider(self):
        refund = self.pending_request()
        with self.assertRaises(IntegrityError):
            RefundRequest.objects.filter(pk=refund.pk).update(status=RefundStatus.APPROVED)


class ListAndFilterTests(RefundsTestBase):
    def test_refund_search_and_status_filter(self):
        a = self.pending_request()
        b = self.pending_request(payment=self.payment2, amount_minor=1_000)
        services.decide_refund(refund_id=b.pk, user=self.manager, approve=False, reason="no")
        self.login(self.auditor)
        resp = self.client.get(reverse("refunds:list"), {"status": "pending"})
        self.assertContains(resp, f"RR-{a.pk}")
        self.assertNotContains(resp, f"RR-{b.pk}")
        resp = self.client.get(reverse("refunds:list"), {"q": "Sofia"})
        self.assertContains(resp, f"RR-{b.pk}")
        self.assertNotContains(resp, f"RR-{a.pk}")
        resp = self.client.get(reverse("refunds:list"), {"status": "bogus"})
        self.assertEqual(resp.status_code, 200)

    def test_kyc_search_and_filters(self):
        KycCase.objects.create(
            case_id="KYC-T2", customer_name="Noah B", risk_level="high", status="escalated",
            assigned_reviewer="k.osei", opened_at=datetime(2026, 8, 2, tzinfo=dt_tz.utc),
        )
        self.login(self.operator)
        resp = self.client.get(reverse("kyc:list"), {"risk": "high"})
        self.assertContains(resp, "KYC-T2")
        self.assertNotContains(resp, "KYC-T1")
        resp = self.client.get(reverse("kyc:list"), {"q": "mira"})
        self.assertContains(resp, "KYC-T1")
        self.assertNotContains(resp, "KYC-T2")
        resp = self.client.get(reverse("kyc:list"), {"status": "new"})
        self.assertContains(resp, "KYC-T1")
        self.assertNotContains(resp, "KYC-T2")
