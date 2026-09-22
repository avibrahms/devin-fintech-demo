from decimal import Decimal

from django import template

register = template.Library()

SYMBOLS = {"USD": "$", "EUR": "€"}


def minor_to_decimal(amount_minor: int) -> Decimal:
    return (Decimal(amount_minor) / Decimal(100)).quantize(Decimal("0.01"))


@register.filter
def money(amount_minor, currency="USD"):
    """Format an integer minor-unit amount as e.g. $1,200.00 / €50.00."""
    if amount_minor is None:
        return ""
    symbol = SYMBOLS.get(currency, currency + " ")
    return f"{symbol}{minor_to_decimal(amount_minor):,.2f}"


@register.filter
def status_class(status):
    return {"pending": "badge-pending", "approved": "badge-approved", "rejected": "badge-rejected"}.get(
        status, "badge-neutral"
    )
