from .errors import InvoiceError
from .money import format_inr


def _status(err):
    return {"NOT_FOUND": 404, "FORBIDDEN": 403}.get(err.code, 400)


def get_invoice_handler(service, invoice_id, user):
    """GET /invoices/{id}: returns (status, body)."""
    try:
        inv = service.get(invoice_id, user)
        total = service.total(invoice_id, user)
    except InvoiceError as e:
        return _status(e), {"error": e.code}
    return 200, {
        "id": inv.id,
        "customer": inv.customer,
        "created": inv.created.isoformat(),
        "total": total,
        "total_display": format_inr(total),
    }
