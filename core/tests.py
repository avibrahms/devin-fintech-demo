"""
CSRF and reverse-proxy tests. Django's test client normally skips CSRF checks;
these tests turn them back on and simulate the headers a TLS-terminating proxy
(such as the Devin preview) sends, so a login through such a proxy is covered.
"""
import importlib
import os
from unittest import mock

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core.roles import OPERATOR

PUBLIC_ORIGIN = "https://8000--session.preview.devinapps.com"
PUBLIC_HOST = "8000--session.preview.devinapps.com"

PROXY_HEADERS = {
    "HTTP_HOST": PUBLIC_HOST,
    "HTTP_X_FORWARDED_HOST": PUBLIC_HOST,
    "HTTP_X_FORWARDED_PROTO": "https",
    "HTTP_ORIGIN": PUBLIC_ORIGIN,
    "HTTP_REFERER": PUBLIC_ORIGIN + "/login/",
}

proxy_settings = override_settings(
    ALLOWED_HOSTS=["*"],
    CSRF_TRUSTED_ORIGINS=[PUBLIC_ORIGIN],
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="None",
    CSRF_COOKIE_SAMESITE="None",
)


class CsrfEnforcedTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="op", password="pw-op")
        cls.user.groups.add(Group.objects.get_or_create(name=OPERATOR)[0])

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def login_post(self, token, **extra):
        return self.client.post(
            reverse("login"),
            {"username": "op", "password": "pw-op", "csrfmiddlewaretoken": token},
            **extra,
        )

    def fetch_login_token(self, **extra):
        response = self.client.get(reverse("login"), **extra)
        self.assertEqual(response.status_code, 200)
        return response.context["csrf_token"]


@proxy_settings
class ProxiedLoginCsrfTests(CsrfEnforcedTestBase):
    def test_login_through_https_proxy_succeeds_with_csrf_enforced(self):
        token = self.fetch_login_token(**PROXY_HEADERS)
        response = self.login_post(token, **PROXY_HEADERS)
        self.assertEqual(response.status_code, 302, response.content[:300])
        self.assertEqual(response.url, reverse("refunds:list"))
        self.assertTrue(self.client.session.get("_auth_user_id"))

    def test_cookies_are_secure_and_samesite_none_behind_proxy(self):
        self.client.get(reverse("login"), **PROXY_HEADERS)
        csrf_cookie = self.client.cookies["csrftoken"]
        self.assertTrue(csrf_cookie["secure"])
        self.assertEqual(csrf_cookie["samesite"], "None")

    def test_post_without_token_is_still_rejected(self):
        self.fetch_login_token(**PROXY_HEADERS)
        response = self.client.post(
            reverse("login"), {"username": "op", "password": "pw-op"}, **PROXY_HEADERS
        )
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Form could not be verified", status_code=403)
        self.assertFalse(self.client.session.get("_auth_user_id"))

    def test_post_from_untrusted_origin_is_rejected(self):
        token = self.fetch_login_token(**PROXY_HEADERS)
        headers = dict(PROXY_HEADERS, HTTP_ORIGIN="https://evil.example", HTTP_REFERER="https://evil.example/")
        response = self.login_post(token, **headers)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.client.session.get("_auth_user_id"))

    def test_write_after_login_through_proxy_succeeds(self):
        token = self.fetch_login_token(**PROXY_HEADERS)
        self.login_post(token, **PROXY_HEADERS)
        response = self.client.get(reverse("refunds:list"), **PROXY_HEADERS)
        self.assertEqual(response.status_code, 200)
        logout = self.client.post(
            reverse("logout"), {"csrfmiddlewaretoken": response.context["csrf_token"]}, **PROXY_HEADERS
        )
        self.assertEqual(logout.status_code, 302)
        self.assertFalse(self.client.session.get("_auth_user_id"))


class LocalLoginCsrfTests(CsrfEnforcedTestBase):
    def test_plain_http_login_succeeds_with_csrf_enforced(self):
        token = self.fetch_login_token()
        response = self.login_post(token)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.client.session.get("_auth_user_id"))


class PublicOriginSettingsTests(TestCase):
    def _load_settings(self, env):
        import portal.settings as portal_settings

        with mock.patch.dict(os.environ, env, clear=False):
            return importlib.reload(portal_settings)

    def test_public_origin_enables_trusted_origin_and_secure_cookies(self):
        s = self._load_settings({"PORTAL_PUBLIC_ORIGIN": PUBLIC_ORIGIN + "/", "PORTAL_CSRF_TRUSTED_ORIGINS": ""})
        try:
            self.assertIn(PUBLIC_ORIGIN, s.CSRF_TRUSTED_ORIGINS)
            self.assertTrue(s.SESSION_COOKIE_SECURE and s.CSRF_COOKIE_SECURE)
            self.assertEqual((s.SESSION_COOKIE_SAMESITE, s.CSRF_COOKIE_SAMESITE), ("None", "None"))
        finally:
            self._load_settings({"PORTAL_PUBLIC_ORIGIN": ""})

    def test_without_public_origin_cookies_stay_lax(self):
        s = self._load_settings({"PORTAL_PUBLIC_ORIGIN": "", "PORTAL_CSRF_TRUSTED_ORIGINS": ""})
        self.assertEqual(s.CSRF_TRUSTED_ORIGINS, [])
        self.assertFalse(s.SESSION_COOKIE_SECURE)
        self.assertEqual(s.SESSION_COOKIE_SAMESITE, "Lax")
