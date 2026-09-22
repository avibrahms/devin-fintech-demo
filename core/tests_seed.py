"""
Demo-data lifecycle tests.

Background (2026-09-22): changes made through the preview "disappeared". The server
log and the command timeline showed that an explicit `seed_demo --reset` had been run
while the demo was in use; the application's writes had succeeded. These tests pin
the contract: the seed command run on every normal startup must never touch existing
records, only `--reset` may, and the seeded accounts cover the two-manager scenario.
"""
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from core.roles import AUDITOR, MANAGER, OPERATOR, PRESENTER, role_of
from refunds import services
from refunds.models import Payment, RefundEvent, RefundRequest, RefundStatus


def seed(*args):
    out = StringIO()
    call_command("seed_demo", *args, stdout=out)
    return out.getvalue()


class SeedDemoStartupTests(TestCase):
    def setUp(self):
        seed()
        self.operator = User.objects.get(username="operator")
        self.manager = User.objects.get(username="manager")
        self.manager2 = User.objects.get(username="manager2")
        self.mira = Payment.objects.get(reference="PAY-1007")

    def make_changes(self):
        new = services.request_refund(payment=self.mira, user=self.operator, amount_minor=12_000, reason="Loom demo")
        rr6 = RefundRequest.objects.get(payment__reference="PAY-1008")
        services.decide_refund(refund_id=rr6.pk, user=self.manager2, approve=True, reason="Second manager")
        return new.pk, rr6.pk

    def test_startup_seed_preserves_user_changes(self):
        new_pk, decided_pk = self.make_changes()
        before = list(RefundRequest.objects.order_by("pk").values_list("pk", "status", "decided_by_id", "amount_minor"))
        events_before = RefundEvent.objects.count()

        output = seed()  # what `make run` / app/main.py execute on every start

        self.assertIn("nothing seeded", output)
        after = list(RefundRequest.objects.order_by("pk").values_list("pk", "status", "decided_by_id", "amount_minor"))
        self.assertEqual(before, after)
        self.assertEqual(RefundEvent.objects.count(), events_before)
        self.assertEqual(RefundRequest.objects.get(pk=new_pk).payment, self.mira)
        self.assertEqual(RefundRequest.objects.get(pk=decided_pk).status, RefundStatus.APPROVED)

    def test_startup_seed_is_idempotent_over_repeated_runs(self):
        seed()
        seed()
        self.assertEqual(Payment.objects.count(), 12)
        self.assertEqual(RefundRequest.objects.count(), 7)

    def test_only_explicit_reset_deletes_records(self):
        new_pk, _ = self.make_changes()
        self.assertEqual(RefundRequest.objects.count(), 8)

        output = seed("--reset")

        self.assertIn("RESET: deleting 8 refund requests", output)
        self.assertEqual(RefundRequest.objects.count(), 7)
        self.assertFalse(RefundRequest.objects.filter(payment__reference="PAY-1007").exists())
        self.assertFalse(RefundRequest.objects.filter(pk=new_pk).exists())
        self.assertEqual(RefundRequest.objects.get(payment__reference="PAY-1008").status, RefundStatus.PENDING)

    def test_seeded_accounts_and_roles(self):
        roles = {u.username: role_of(u) for u in User.objects.all()}
        self.assertEqual(
            roles, {"operator": OPERATOR, "manager": MANAGER, "manager2": MANAGER, "auditor": AUDITOR, "presenter": PRESENTER}
        )
        for username in roles:
            self.assertTrue(self.client.login(username=username, password=f"{username}-demo-2026"), username)


class TwoManagerScenarioTests(TestCase):
    """RR-6 (PAY-1008) is created by `manager`; only a *different* manager may decide it."""

    def setUp(self):
        seed()
        self.rr6 = RefundRequest.objects.get(payment__reference="PAY-1008")
        self.url = f"/refunds/{self.rr6.pk}/decide/"

    def decide_as(self, username):
        self.client.login(username=username, password=f"{username}-demo-2026")
        response = self.client.post(self.url, {"decision": "approve", "reason": "Reviewed"})
        self.client.logout()
        self.rr6.refresh_from_db()
        return response

    def test_manager_a_cannot_approve_own_request(self):
        self.assertEqual(self.decide_as("manager").status_code, 403)
        self.assertEqual(self.rr6.status, RefundStatus.PENDING)

    def test_operator_and_auditor_cannot_approve(self):
        self.assertEqual(self.decide_as("operator").status_code, 403)
        self.assertEqual(self.decide_as("auditor").status_code, 403)
        self.assertEqual(self.rr6.status, RefundStatus.PENDING)

    def test_manager_b_can_approve_and_decision_is_final(self):
        response = self.decide_as("manager2")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.rr6.status, RefundStatus.APPROVED)
        self.assertEqual(self.rr6.decided_by.username, "manager2")
        self.assertEqual(self.rr6.events.count(), 2)
        # Manager A trying afterwards is still refused and changes nothing.
        self.assertEqual(self.decide_as("manager").status_code, 403)
        self.assertEqual(self.rr6.decided_by.username, "manager2")


class DemoResetButtonTests(TestCase):
    """Presenter-only, demo-mode-only reset action; CSRF enforced; cancel/GET never resets."""

    URL = "/demo/reset/"

    def setUp(self):
        seed()
        self.client = Client(enforce_csrf_checks=True)
        self.operator = User.objects.get(username="operator")
        self.new_pk = services.request_refund(
            payment=Payment.objects.get(reference="PAY-1007"), user=self.operator,
            amount_minor=12_000, reason="Loom demo",
        ).pk
        self.snapshot = self._snapshot()

    def _snapshot(self):
        return (
            list(RefundRequest.objects.order_by("pk").values_list("pk", "status", "amount_minor")),
            RefundEvent.objects.count(),
        )

    def login(self, username):
        self.assertTrue(self.client.login(username=username, password=f"{username}-demo-2026"))

    def csrf_token(self, path):
        response = self.client.get(path)
        return response.cookies["csrftoken"].value if "csrftoken" in response.cookies else self.client.cookies["csrftoken"].value

    def post_reset(self, with_token=True):
        data = {}
        if with_token:
            data["csrfmiddlewaretoken"] = self.csrf_token(self.URL)
        return self.client.post(self.URL, data)

    @override_settings(DEMO_MODE=True)
    def test_presenter_sees_button_confirmation_and_cancel_leaves_data_untouched(self):
        self.login("presenter")
        response = self.client.get("/refunds/")
        self.assertContains(response, "Reset demo data")
        confirm = self.client.get(self.URL)
        self.assertContains(confirm, "Delete all demo changes and restore the starting data?")
        self.assertContains(confirm, "Cancel")
        self.client.get("/refunds/")  # "Cancel" is a plain link back to the list
        self.assertEqual(self._snapshot(), self.snapshot)

    @override_settings(DEMO_MODE=True)
    def test_presenter_confirm_resets_everything_and_keeps_accounts(self):
        rr4 = RefundRequest.objects.get(payment__reference="PAY-1004")
        services.decide_refund(refund_id=rr4.pk, user=User.objects.get(username="manager"), approve=True, reason="ok")
        self.login("presenter")
        response = self.post_reset()
        self.assertEqual(response.status_code, 302)
        listing = self.client.get(response.url)
        self.assertContains(listing, "Demo data reset")
        self.assertEqual(list(RefundRequest.objects.order_by("pk").values_list("pk", flat=True)), [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(RefundRequest.objects.get(pk=4).status, RefundStatus.PENDING)
        self.assertFalse(RefundRequest.objects.filter(payment__reference="PAY-1007").exists())
        self.assertEqual(Payment.objects.count(), 12)
        self.assertEqual(RefundEvent.objects.count(), 11)
        self.assertEqual(
            set(User.objects.values_list("username", flat=True)),
            {"operator", "manager", "manager2", "auditor", "presenter"},
        )
        self.assertTrue(self.client.session.get("_auth_user_id"), "presenter stays logged in after reset")

    @override_settings(DEMO_MODE=True)
    def test_other_roles_cannot_reset_even_with_direct_post(self):
        for username in ("operator", "manager", "manager2", "auditor"):
            self.login(username)
            self.assertNotContains(self.client.get("/refunds/"), "Reset demo data")
            self.assertEqual(self.client.get(self.URL).status_code, 403, username)
            self.assertEqual(self.post_reset().status_code, 403, username)
            self.client.logout()
        self.assertEqual(self._snapshot(), self.snapshot)

    @override_settings(DEMO_MODE=True)
    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/login/"))
        self.assertEqual(self._snapshot(), self.snapshot)

    @override_settings(DEMO_MODE=True)
    def test_post_without_csrf_token_is_rejected(self):
        self.login("presenter")
        response = self.post_reset(with_token=False)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self._snapshot(), self.snapshot)

    @override_settings(DEMO_MODE=False)
    def test_disabled_outside_demo_mode(self):
        self.login("presenter")
        self.assertNotContains(self.client.get("/refunds/"), "Reset demo data")
        self.assertEqual(self.client.get(self.URL).status_code, 404)
        self.assertEqual(self.post_reset().status_code, 404)
        self.assertEqual(self._snapshot(), self.snapshot)

    def test_presenter_cannot_write_business_records(self):
        self.login("presenter")
        token = self.csrf_token("/refunds/payments/")
        response = self.client.post(
            "/refunds/payments/9/request/", {"amount": "1.00", "reason": "x", "csrfmiddlewaretoken": token}
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.post(
            "/refunds/4/decide/", {"decision": "approve", "reason": "x", "csrfmiddlewaretoken": token}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self._snapshot(), self.snapshot)
