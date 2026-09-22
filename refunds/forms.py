from decimal import Decimal

from django import forms


class RefundRequestForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Refund amount",
        error_messages={
            "max_decimal_places": "Amount cannot have more than two decimal places.",
            "min_value": "Amount must be greater than zero.",
            "invalid": "Enter a valid amount.",
            "required": "Enter a refund amount.",
        },
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        max_length=1000,
        label="Reason",
        error_messages={"required": "A reason is required."},
    )

    def __init__(self, *args, payment, **kwargs):
        super().__init__(*args, **kwargs)
        self.payment = payment

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if int(amount * 100) > self.payment.amount_minor:
            raise forms.ValidationError("Amount cannot exceed the original payment.")
        return amount

    def clean_reason(self):
        reason = self.cleaned_data["reason"].strip()
        if not reason:
            raise forms.ValidationError("A reason is required.")
        return reason

    @property
    def amount_minor(self) -> int:
        return int(self.cleaned_data["amount"] * 100)


class DecisionForm(forms.Form):
    decision = forms.ChoiceField(choices=[("approve", "Approve"), ("reject", "Reject")])
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        max_length=1000,
        label="Decision reason",
        error_messages={"required": "A decision reason is required."},
    )

    def clean_reason(self):
        reason = self.cleaned_data["reason"].strip()
        if not reason:
            raise forms.ValidationError("A decision reason is required.")
        return reason
