from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .models import KycCase


@login_required
@require_GET
def case_list(request):
    q = request.GET.get("q", "").strip()
    risk = request.GET.get("risk", "")
    status = request.GET.get("status", "")
    qs = KycCase.objects.all()
    if q:
        qs = qs.filter(Q(case_id__icontains=q) | Q(customer_name__icontains=q) | Q(assigned_reviewer__icontains=q))
    if risk in KycCase.Risk.values:
        qs = qs.filter(risk_level=risk)
    else:
        risk = ""
    if status in KycCase.Status.values:
        qs = qs.filter(status=status)
    else:
        status = ""
    return render(
        request,
        "kyc/list.html",
        {
            "nav": "kyc",
            "cases": qs,
            "q": q,
            "risk": risk,
            "status": status,
            "risks": KycCase.Risk.choices,
            "statuses": KycCase.Status.choices,
        },
    )
