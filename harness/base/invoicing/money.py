from .errors import InvoiceError


def to_paise(text):
    """Parse a rupee amount such as "1,234.50" or "-20" into integer paise."""
    s = text.strip().replace(",", "")
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    whole, _, frac = s.partition(".")
    if not whole.isdigit() or (frac and not frac.isdigit()) or len(frac) > 2:
        raise InvoiceError("BAD_AMOUNT", text)
    paise = int(whole) * 100 + int(frac.ljust(2, "0") or 0)
    return -paise if neg else paise


def format_inr(paise):
    """Format paise as rupees with Indian digit grouping: 12345678 -> "₹1,23,456.78"."""
    neg = paise < 0
    rupees, p = divmod(abs(paise), 100)
    digits = str(rupees)
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    body = ",".join(groups + [tail]) if groups else tail
    return f"{'-' if neg else ''}₹{body}.{p:02d}"
