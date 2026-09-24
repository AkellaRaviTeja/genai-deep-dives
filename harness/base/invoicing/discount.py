from .errors import InvoiceError

# code -> (kind, value). "percent" values are whole percent; "flat" values are paise.
DISCOUNTS = {
    "WELCOME10": ("percent", 10),
    "FLAT500": ("flat", 50000),
}


def apply_discount(subtotal, code):
    """Return the discount in paise for `code` on `subtotal` paise. No code means 0."""
    if not code:
        return 0
    key = code.strip().upper()
    if key not in DISCOUNTS:
        raise InvoiceError("UNKNOWN_DISCOUNT", code)
    kind, value = DISCOUNTS[key]
    off = subtotal * value // 100 if kind == "percent" else value
    return min(off, subtotal)
