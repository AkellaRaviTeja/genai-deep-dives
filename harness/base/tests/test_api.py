from datetime import date
from invoicing.api import get_invoice_handler
from invoicing.invoice import Invoice, LineItem
from invoicing.service import InvoiceService
from invoicing.store import InvoiceStore

def test_get():
    s = InvoiceService(InvoiceStore())
    s.create(Invoice("A1", "asha", [LineItem("pen", 1, 10000)], date(2026, 9, 1)))
    status, body = get_invoice_handler(s, "A1", "asha")
    assert status == 200 and body["created"] == "2026-09-01" and body["total"] == 11800
