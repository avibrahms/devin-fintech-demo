from io import StringIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.management import call_command
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods

from core.roles import can_reset_demo, require


def csrf_failure(request, reason="", template_name="403_csrf.html"):
    """CSRF rejection page that shows Django's reason, so proxy/cookie problems are diagnosable."""
    body = render_to_string(template_name, {"reason": reason}, request=request)
    return HttpResponseForbidden(body)


@login_required
@require_http_methods(["GET", "POST"])
def demo_reset(request):
    """Presenter-only, demo-mode-only. GET shows the confirmation; only a POST resets."""
    if not settings.DEMO_MODE:
        raise Http404
    return _demo_reset(request)


@require(can_reset_demo)
def _demo_reset(request):
    if request.method == "GET":
        return render(request, "demo_reset.html", {"nav": "reset"})
    out = StringIO()
    call_command("seed_demo", "--reset", stdout=out)
    messages.success(
        request,
        "Demo data reset: all synthetic refund requests, decisions, payments and KYC cases "
        "were restored to the starting examples (RR-1 to RR-7). Demo accounts were kept.",
    )
    return redirect("refunds:list")
