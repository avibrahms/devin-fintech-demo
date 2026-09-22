from django.db import models


class KycCase(models.Model):
    class Risk(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_REVIEW = "in_review", "In review"
        WAITING_ON_CUSTOMER = "waiting_on_customer", "Waiting on customer"
        ESCALATED = "escalated", "Escalated"
        CLOSED = "closed", "Closed"

    case_id = models.CharField(max_length=20, unique=True)
    customer_name = models.CharField(max_length=120)
    risk_level = models.CharField(max_length=10, choices=Risk.choices)
    status = models.CharField(max_length=25, choices=Status.choices)
    assigned_reviewer = models.CharField(max_length=80, blank=True)
    opened_at = models.DateTimeField()

    class Meta:
        ordering = ["-opened_at", "case_id"]

    def __str__(self):
        return self.case_id
