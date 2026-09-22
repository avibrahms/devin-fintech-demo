"""
Business operations for refunds. Every entry point takes the acting user
(from the session) and re-checks authorization, so the rules hold for
requests that bypass the HTML forms. Business row and history row are
written in one transaction.
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.roles import can_decide_refund, can_request_refund

from .models import Payment, RefundEvent, RefundRequest, RefundStatus


class RefundError(Exception):
    """Validation or state error safe to show to the user."""


class DuplicateRequest(RefundError):
    def __init__(self, existing: RefundRequest):
        super().__init__(f"A refund request already exists for payment {existing.payment.reference}.")
        self.existing = existing


class StaleDecision(RefundError):
    def __init__(self, refund: RefundRequest):
        decided_by = refund.decided_by.username if refund.decided_by else "another user"
        when = refund.decided_at.strftime("%Y-%m-%d %H:%M UTC") if refund.decided_at else "earlier"
        super().__init__(
            f"This request was already {refund.status} by {decided_by} at {when}. No further decision is possible."
        )
        self.refund = refund


def parse_amount_to_minor(value) -> int:
    """Accept a Decimal/str amount with at most two decimal places; return cents."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise RefundError("Enter a valid amount.")
    if not amount.is_finite():
        raise RefundError("Enter a valid amount.")
    if amount != amount.quantize(Decimal("0.01")):
        raise RefundError("Amount cannot have more than two decimal places.")
    if amount <= 0:
        raise RefundError("Amount must be greater than zero.")
    return int(amount * 100)


def request_refund(*, payment: Payment, user, amount_minor: int, reason: str) -> RefundRequest:
    if not can_request_refund(user):
        raise PermissionDenied("Your role cannot submit refund requests.")
    reason = (reason or "").strip()
    if not reason:
        raise RefundError("A reason is required.")
    if amount_minor <= 0:
        raise RefundError("Amount must be greater than zero.")
    if amount_minor > payment.amount_minor:
        raise RefundError("Amount cannot exceed the original payment.")

    now = timezone.now()
    try:
        with transaction.atomic():
            refund = RefundRequest.objects.create(
                payment=payment,
                amount_minor=amount_minor,
                currency=payment.currency,
                reason=reason,
                status=RefundStatus.PENDING,
                requested_by=user,
                requested_at=now,
            )
            RefundEvent.objects.create(
                refund=refund,
                action=RefundEvent.Action.REQUESTED,
                actor=user,
                occurred_at=now,
                from_status="",
                to_status=RefundStatus.PENDING,
                amount_minor=amount_minor,
                currency=payment.currency,
                reason=reason,
            )
    except IntegrityError:
        existing = RefundRequest.objects.filter(payment=payment).select_related("payment").first()
        if existing is not None:
            raise DuplicateRequest(existing)
        raise
    return refund


def decide_refund(*, refund_id: int, user, approve: bool, reason: str) -> RefundRequest:
    if not can_decide_refund(user):
        raise PermissionDenied("Only managers can approve or reject refund requests.")
    reason = (reason or "").strip()
    if not reason:
        raise RefundError("A decision reason is required.")

    new_status = RefundStatus.APPROVED if approve else RefundStatus.REJECTED
    now = timezone.now()
    with transaction.atomic():
        refund = RefundRequest.objects.select_for_update().select_related("payment", "decided_by").get(pk=refund_id)
        if refund.requested_by_id == user.pk:
            raise PermissionDenied("Managers cannot decide their own refund requests.")
        # Compare-and-set: only a still-pending row is updated, so a second
        # click or a decision from a stale page cannot overwrite the first.
        updated = RefundRequest.objects.filter(pk=refund.pk, status=RefundStatus.PENDING).update(
            status=new_status, decided_by=user, decided_at=now, decision_reason=reason
        )
        if updated != 1:
            refund.refresh_from_db()
            raise StaleDecision(refund)
        RefundEvent.objects.create(
            refund=refund,
            action=RefundEvent.Action.APPROVED if approve else RefundEvent.Action.REJECTED,
            actor=user,
            occurred_at=now,
            from_status=RefundStatus.PENDING,
            to_status=new_status,
            amount_minor=refund.amount_minor,
            currency=refund.currency,
            reason=reason,
        )
    refund.refresh_from_db()
    return refund
