"""
Role model for the portal. Roles are Django auth Groups; every check here
reads the authenticated user from the session, never from request data.
"""
from functools import wraps

from django.conf import settings
from django.core.exceptions import PermissionDenied

OPERATOR = "operator"
MANAGER = "manager"
AUDITOR = "auditor"
PRESENTER = "presenter"  # demo-only: may reset the synthetic data; no business writes
ROLES = (OPERATOR, MANAGER, AUDITOR, PRESENTER)

ROLE_LABELS = {OPERATOR: "Operator", MANAGER: "Manager", AUDITOR: "Auditor", PRESENTER: "Presenter"}


def role_of(user):
    if not user.is_authenticated:
        return None
    names = set(user.groups.values_list("name", flat=True))
    for role in ROLES:
        if role in names:
            return role
    return None


def can_request_refund(user) -> bool:
    return role_of(user) in (OPERATOR, MANAGER)


def can_decide_refund(user) -> bool:
    return role_of(user) == MANAGER


def can_reset_demo(user) -> bool:
    return settings.DEMO_MODE and role_of(user) == PRESENTER


def role_context(request):
    user = getattr(request, "user", None)
    role = role_of(user) if user is not None else None
    return {
        "role": role,
        "role_label": ROLE_LABELS.get(role, "No role"),
        "can_request_refund": can_request_refund(user) if user is not None else False,
        "can_decide_refund": can_decide_refund(user) if user is not None else False,
        "can_reset_demo": can_reset_demo(user) if user is not None else False,
    }


def require(check):
    """View decorator: 403 unless check(request.user) is true. Assumes login_required ran first."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not check(request.user):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
