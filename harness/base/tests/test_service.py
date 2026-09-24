from datetime import date
import pytest
from invoicing.invoice import Invoice, LineItem
from invoicing.service import InvoiceService
from invoicing.store import InvoiceStore
from invoicing.errors import InvoiceError

def svc():
    s = InvoiceService(InvoiceStore())
    s.create(Invoice("A1", "asha", [LineItem("pen", 10, 10000)], date(2026, 9, 1), "WELCOME10"))
    return s

def test_total():
    assert svc().total("A1", "asha") == 106200

def test_forbidden():
    with pytest.raises(InvoiceError):
        svc().get("A1", "ravi")
