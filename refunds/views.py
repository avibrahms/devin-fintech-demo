from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from core.roles import can_decide_refund, can_request_refund, require

from . import services
from .forms import DecisionForm, RefundRequestForm
from .models import Payment, RefundRequest, RefundStatus


@login_required
def refund_list(request):
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    qs = RefundRequest.objects.select_related("payment", "requested_by", "decided_by")
    if q:
        qs = qs.filter(
            Q(payment__reference__icontains=q)
            | Q(payment__customer_name__icontains=q)
            | Q(reason__icontains=q)
            | Q(requested_by__username__icontains=q)
        )
    if status in RefundStatus.values:
        qs = qs.filter(status=status)
    else:
        status = ""
    return render(
        request,
        "refunds/list.html",
        {"nav": "refunds", "refunds": qs, "q": q, "status": status, "statuses": RefundStatus.choices},
    )


@login_required
def refund_detail(request, pk):
    refund = get_object_or_404(
        RefundRequest.objects.select_related("payment", "requested_by", "decided_by"), pk=pk
    )
    events = refund.events.select_related("actor")
    user = request.user
    may_decide = refund.is_pending and can_decide_refund(user) and refund.requested_by_id != user.pk
    is_own = refund.requested_by_id == user.pk
    form = DecisionForm() if may_decide else None
    return render(
        request,
        "refunds/detail.html",
        {"nav": "refunds", "refund": refund, "events": events, "may_decide": may_decide, "is_own": is_own, "form": form},
    )


@login_required
def payment_list(request):
    q = request.GET.get("q", "").strip()
    qs = Payment.objects.select_related("refund_request")
    if q:
        qs = qs.filter(Q(reference__icontains=q) | Q(customer_name__icontains=q) | Q(description__icontains=q))
    return render(request, "refunds/payments.html", {"nav": "payments", "payments": qs, "q": q})


@login_required
@require(can_request_refund)
@require_http_methods(["GET", "POST"])
def request_refund(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    existing = RefundRequest.objects.filter(payment=payment).first()
    if existing is not None:
        messages.info(request, f"A refund request already exists for payment {payment.reference}.")
        return redirect("refunds:detail", pk=existing.pk)

    if request.method == "POST":
        form = RefundRequestForm(request.POST, payment=payment)
        if form.is_valid():
            try:
                refund = services.request_refund(
                    payment=payment,
                    user=request.user,
                    amount_minor=form.amount_minor,
                    reason=form.cleaned_data["reason"],
                )
            except services.DuplicateRequest as exc:
                messages.info(request, str(exc))
                return redirect("refunds:detail", pk=exc.existing.pk)
            except services.RefundError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, f"Refund request RR-{refund.pk} submitted for {payment.reference}.")
                return redirect("refunds:detail", pk=refund.pk)
    else:
        form = RefundRequestForm(payment=payment)
    return render(request, "refunds/request_form.html", {"nav": "payments", "payment": payment, "form": form})


@login_required
@require_POST
def decide_refund(request, pk):
    if not can_decide_refund(request.user):
        raise PermissionDenied("Only managers can approve or reject refund requests.")
    refund = get_object_or_404(RefundRequest, pk=pk)
    form = DecisionForm(request.POST)
    if not form.is_valid():
        for errors in form.errors.values():
            for err in errors:
                messages.error(request, err)
        return redirect("refunds:detail", pk=pk)
    try:
        refund = services.decide_refund(
            refund_id=refund.pk,
            user=request.user,
            approve=form.cleaned_data["decision"] == "approve",
            reason=form.cleaned_data["reason"],
        )
    except services.StaleDecision as exc:
        messages.warning(request, str(exc))
    except services.RefundError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Refund request RR-{refund.pk} {refund.status}. Decision recorded; no money moved.")
    return redirect("refunds:detail", pk=pk)
