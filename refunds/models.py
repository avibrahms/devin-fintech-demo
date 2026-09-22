"""
Refund domain. Money is stored as integer minor units (cents) with an ISO
currency code, so there is no floating-point or SQLite NUMERIC rounding.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Currency(models.TextChoices):
    USD = "USD", "USD"
    EUR = "EUR", "EUR"


class Payment(models.Model):
    reference = models.CharField(max_length=20, unique=True)
    customer_name = models.CharField(max_length=120)
    amount_minor = models.BigIntegerField()
    currency = models.CharField(max_length=3, choices=Currency.choices)
    paid_at = models.DateTimeField()
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-paid_at", "reference"]
        constraints = [
            models.CheckConstraint(condition=Q(amount_minor__gt=0), name="payment_amount_positive"),
            models.CheckConstraint(condition=Q(currency__in=["USD", "EUR"]), name="payment_currency_supported"),
        ]

    def __str__(self):
        return self.reference

    @property
    def amount(self) -> Decimal:
        return Decimal(self.amount_minor) / 100


class RefundStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class RefundRequest(models.Model):
    # OneToOne => at most one refund request per payment, enforced by a
    # UNIQUE index in the database (documented demo limitation).
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name="refund_request")
    amount_minor = models.BigIntegerField()
    currency = models.CharField(max_length=3, choices=Currency.choices)
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=RefundStatus.choices, default=RefundStatus.PENDING)

    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="refunds_requested")
    requested_at = models.DateTimeField()

    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="refunds_decided"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-requested_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(amount_minor__gt=0), name="refund_amount_positive"),
            models.CheckConstraint(condition=Q(currency__in=["USD", "EUR"]), name="refund_currency_supported"),
            models.CheckConstraint(
                condition=Q(status__in=["pending", "approved", "rejected"]), name="refund_status_valid"
            ),
            # A decided request must carry decider, time and reason; a pending one must not.
            models.CheckConstraint(
                condition=(
                    Q(status="pending", decided_by__isnull=True, decided_at__isnull=True, decision_reason="")
                    | (
                        Q(status__in=["approved", "rejected"], decided_by__isnull=False, decided_at__isnull=False)
                        & ~Q(decision_reason="")
                    )
                ),
                name="refund_decision_fields_consistent",
            ),
            # Managers never decide their own requests.
            models.CheckConstraint(
                condition=Q(decided_by__isnull=True) | ~Q(decided_by=F("requested_by")),
                name="refund_no_self_decision",
            ),
        ]

    def __str__(self):
        return f"RR-{self.pk} ({self.payment.reference})"

    @property
    def is_pending(self) -> bool:
        return self.status == RefundStatus.PENDING

    @property
    def amount(self) -> Decimal:
        return Decimal(self.amount_minor) / 100


class RefundEvent(models.Model):
    """Append-only history row written in the same transaction as the change."""

    class Action(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    refund = models.ForeignKey(RefundRequest, on_delete=models.CASCADE, related_name="events")
    action = models.CharField(max_length=10, choices=Action.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="refund_events")
    occurred_at = models.DateTimeField()
    from_status = models.CharField(max_length=10, blank=True)
    to_status = models.CharField(max_length=10)
    amount_minor = models.BigIntegerField()
    currency = models.CharField(max_length=3)
    reason = models.TextField()

    class Meta:
        ordering = ["occurred_at", "id"]
