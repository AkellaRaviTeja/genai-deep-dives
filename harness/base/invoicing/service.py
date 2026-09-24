from .discount import apply_discount
from .errors import InvoiceError
from .tax import gst

GST_BP = 1800


class InvoiceService:
    """All business rules and permission checks live here."""

    def __init__(self, store):
        self.store = store

    def _owned(self, invoice_id, user):
        inv = self.store.get(invoice_id)
        if inv.customer != user:
            raise InvoiceError("FORBIDDEN", invoice_id)
        return inv

    def get(self, invoice_id, user):
        return self._owned(invoice_id, user)

    def create(self, invoice):
        self.store.put(invoice)
        return invoice

    def list(self, user):
        return self.store.list_by_customer(user)

    def total(self, invoice_id, user):
        """Subtotal, minus the discount, plus GST on the discounted amount."""
        inv = self._owned(invoice_id, user)
        net = inv.subtotal() - apply_discount(inv.subtotal(), inv.discount_code)
        return net + gst(net, GST_BP)
