from .errors import InvoiceError


class InvoiceStore:
    """The storage layer. Only InvoiceService may use it."""

    def __init__(self):
        self._rows = {}

    def put(self, invoice):
        self._rows[invoice.id] = invoice

    def get(self, invoice_id):
        if invoice_id not in self._rows:
            raise InvoiceError("NOT_FOUND", invoice_id)
        return self._rows[invoice_id]

    def list_by_customer(self, customer):
        rows = [r for r in self._rows.values() if r.customer == customer]
        return sorted(rows, key=lambda r: (r.created, r.id), reverse=True)
