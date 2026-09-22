from django.http import HttpResponseForbidden
from django.template.loader import render_to_string


def csrf_failure(request, reason="", template_name="403_csrf.html"):
    """CSRF rejection page that shows Django's reason, so proxy/cookie problems are diagnosable."""
    body = render_to_string(template_name, {"reason": reason}, request=request)
    return HttpResponseForbidden(body)
