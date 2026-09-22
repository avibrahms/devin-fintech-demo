from django.contrib import admin

from .models import Payment, RefundEvent, RefundRequest


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "customer_name", "amount_minor", "currency", "paid_at")
    search_fields = ("reference", "customer_name")


@admin.register(RefundRequest)
class RefundRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "payment", "amount_minor", "currency", "status", "requested_by", "decided_by")
    list_filter = ("status",)


@admin.register(RefundEvent)
class RefundEventAdmin(admin.ModelAdmin):
    list_display = ("id", "refund", "action", "actor", "occurred_at")
    readonly_fields = [f.name for f in RefundEvent._meta.fields]
