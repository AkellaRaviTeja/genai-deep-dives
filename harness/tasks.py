"""24 tasks cut from the correct codebase in base/.

Each task edits base/ into a starting state (a stub, a planted bug, or a missing
feature), asks for a change in plain words, and is graded by a hidden test the
agent never sees, plus the original test suite, run from a pristine copy.

`rules` names the AGENTS.md rules the hidden test checks that the prompt does not
state. Those are the tasks where the instructions file can matter.
"""

STUB = '    raise NotImplementedError("TODO")\n'

TASKS = [
    # ---- implement a stubbed function -------------------------------------------------------
    dict(
        id="impl_format_inr",
        kind="implement",
        rules=[],
        prompt='Implement format_inr in invoicing/money.py. It formats paise as rupees with Indian digit grouping, for example 12345678 becomes "₹1,23,456.78" and -250 becomes "-₹2.50".',
        stub=("invoicing/money.py", "format_inr"),
        hidden="""
from invoicing.money import format_inr
def test_hidden():
    assert format_inr(12345678) == "₹1,23,456.78"
    assert format_inr(100) == "₹1.00"
    assert format_inr(99999999) == "₹9,99,999.99"
    assert format_inr(-250) == "-₹2.50"
    assert format_inr(123456789012) == "₹1,23,45,67,890.12"
""",
    ),
    dict(
        id="impl_to_paise",
        kind="implement",
        rules=["errors"],
        prompt='Implement to_paise in invoicing/money.py. It parses a rupee amount such as "1,234.50", "20" or "-3.5" into integer paise, and rejects anything with more than two decimals or that is not a number.',
        stub=("invoicing/money.py", "to_paise"),
        hidden="""
import pytest
from invoicing.money import to_paise
from invoicing.errors import InvoiceError
def test_hidden():
    assert to_paise("1,234.50") == 123450
    assert to_paise("-3.5") == -350
    assert to_paise(" 7 ") == 700
    for bad in ["1.234", "abc", "1.2.3", ""]:
        with pytest.raises(InvoiceError):
            to_paise(bad)
""",
    ),
    dict(
        id="impl_subtotal",
        kind="implement",
        rules=[],
        prompt="Implement Invoice.subtotal in invoicing/invoice.py: the sum of every line item's amount, in paise.",
        stub=("invoicing/invoice.py", "subtotal"),
        hidden="""
from invoicing.invoice import Invoice, LineItem
def test_hidden():
    assert Invoice("A", "c").subtotal() == 0
    assert Invoice("A", "c", [LineItem("x", 3, 333), LineItem("y", 1, 1)]).subtotal() == 1000
""",
    ),
    dict(
        id="impl_apply_discount",
        kind="implement",
        rules=["case", "cap", "errors"],
        prompt="Implement apply_discount in invoicing/discount.py. It returns the discount in paise for a code on a subtotal, using the DISCOUNTS table. No code means no discount.",
        stub=("invoicing/discount.py", "apply_discount"),
        hidden="""
import pytest
from invoicing.discount import apply_discount
from invoicing.errors import InvoiceError
def test_hidden():
    assert apply_discount(100000, None) == 0
    assert apply_discount(100000, "WELCOME10") == 10000
    assert apply_discount(100000, " welcome10 ") == 10000
    assert apply_discount(30000, "FLAT500") == 30000
    with pytest.raises(InvoiceError):
        apply_discount(100, "NOPE")
""",
    ),
    dict(
        id="impl_gst",
        kind="implement",
        rules=["rounding"],
        prompt="Implement gst in invoicing/tax.py: the GST on an amount in paise at a rate in basis points (1800 means 18%), returned in paise.",
        stub=("invoicing/tax.py", "gst"),
        hidden="""
from invoicing.tax import gst
def test_hidden():
    assert gst(10000, 1800) == 1800
    assert gst(25, 1800) == 4      # 4.5 -> 4
    assert gst(75, 1800) == 14     # 13.5 -> 14
    assert gst(1, 5000) == 0       # 0.5 -> 0
    assert gst(3, 5000) == 2       # 1.5 -> 2
""",
    ),
    dict(
        id="impl_total",
        kind="implement",
        rules=[],
        prompt="Implement InvoiceService.total in invoicing/service.py: the subtotal, minus the discount, plus GST at GST_BP on the discounted amount. Only the invoice's owner may see it.",
        stub=("invoicing/service.py", "total"),
        hidden="""
from datetime import date
import pytest
from invoicing.invoice import Invoice, LineItem
from invoicing.service import InvoiceService
from invoicing.store import InvoiceStore
from invoicing.errors import InvoiceError
def test_hidden():
    s = InvoiceService(InvoiceStore())
    s.create(Invoice("A", "asha", [LineItem("x", 1, 100000)], date(2026, 1, 1), "FLAT500"))
    assert s.total("A", "asha") == 59000
    with pytest.raises(InvoiceError):
        s.total("A", "ravi")
""",
    ),
    dict(
        id="impl_list_by_customer",
        kind="implement",
        rules=["order"],
        prompt="Implement InvoiceStore.list_by_customer in invoicing/store.py: every invoice for one customer.",
        stub=("invoicing/store.py", "list_by_customer"),
        hidden="""
from datetime import date
from invoicing.invoice import Invoice
from invoicing.store import InvoiceStore
def test_hidden():
    s = InvoiceStore()
    for i, d in [("A1", date(2026, 1, 1)), ("A3", date(2026, 3, 1)), ("A2", date(2026, 3, 1)), ("B1", date(2026, 5, 1))]:
        s.put(Invoice(i, "asha" if i[0] == "A" else "ravi", [], d))
    assert [r.id for r in s.list_by_customer("asha")] == ["A3", "A2", "A1"]
""",
    ),
    dict(
        id="impl_get_handler",
        kind="implement",
        rules=["layering", "iso", "errors"],
        prompt="Implement get_invoice_handler in invoicing/api.py. It returns (status, body) for GET /invoices/{id}: the id, customer, created date, total and a display total, with 404 for a missing invoice and 403 for someone else's.",
        stub=("invoicing/api.py", "get_invoice_handler"),
        hidden="""
from datetime import date
from invoicing.api import get_invoice_handler
from invoicing.invoice import Invoice, LineItem
from invoicing.service import InvoiceService
from invoicing.store import InvoiceStore
def test_hidden():
    s = InvoiceService(InvoiceStore())
    s.create(Invoice("A1", "asha", [LineItem("pen", 1, 10000)], date(2026, 9, 1)))
    st, body = get_invoice_handler(s, "A1", "asha")
    assert st == 200 and body["created"] == "2026-09-01" and body["total"] == 11800
    assert get_invoice_handler(s, "A1", "ravi")[0] == 403
    assert get_invoice_handler(s, "ZZ", "asha")[0] == 404
    import pathlib, invoicing.api as api
    src = pathlib.Path(api.__file__).read_text()
    assert ".store" not in src and "InvoiceStore" not in src
""",
    ),
    # ---- fix a planted bug -----------------------------------------------------------------------
    dict(
        id="bug_subtotal",
        kind="bugfix",
        rules=[],
        prompt="Invoice totals are too small: the last line item seems to be ignored. Find and fix the bug.",
        bug=(
            "invoicing/invoice.py",
            "return sum(item.amount() for item in self.items)",
            "return sum(item.amount() for item in self.items[:-1])",
        ),
        hidden="""
from invoicing.invoice import Invoice, LineItem
def test_hidden():
    assert Invoice("A", "c", [LineItem("x", 2, 50)]).subtotal() == 100
    assert Invoice("A", "c", [LineItem("x", 1, 1), LineItem("y", 1, 2)]).subtotal() == 3
""",
    ),
    dict(
        id="bug_grouping",
        kind="bugfix",
        rules=[],
        prompt='Amounts over a lakh display wrongly: 12345678 paise shows as "₹123,456.78" instead of "₹1,23,456.78". Fix format_inr.',
        bug=(
            "invoicing/money.py",
            "    while len(head) > 2:",
            "    while len(head) > 3:",
        ),
        hidden="""
from invoicing.money import format_inr
def test_hidden():
    assert format_inr(12345678) == "₹1,23,456.78"
    assert format_inr(1234567890) == "₹1,23,45,678.90"
    assert format_inr(99999) == "₹999.99"
""",
    ),
    dict(
        id="bug_flat_discount",
        kind="bugfix",
        rules=[],
        prompt="The FLAT500 code gives a huge discount instead of ₹500 off. Fix it.",
        bug=(
            "invoicing/discount.py",
            'off = subtotal * value // 100 if kind == "percent" else value',
            "off = subtotal * value // 100",
        ),
        hidden="""
from invoicing.discount import apply_discount
def test_hidden():
    assert apply_discount(200000, "FLAT500") == 50000
    assert apply_discount(200000, "WELCOME10") == 20000
""",
    ),
    dict(
        id="bug_gst_float",
        kind="bugfix",
        rules=["rounding", "float"],
        prompt="Customers report GST a paise off on some invoices. gst() looks wrong for odd amounts. Fix it.",
        bug=(
            "invoicing/tax.py",
            "    return round_half_even(amount_paise * rate_bp, 10000)",
            "    return int(amount_paise * rate_bp / 10000 + 0.5)",
        ),
        hidden="""
from invoicing.tax import gst
def test_hidden():
    assert gst(25, 1800) == 4
    assert gst(75, 1800) == 14
    assert gst(10**15 + 1, 1800) == 180000000000000
    import pathlib, invoicing.tax as t
    assert "float" not in pathlib.Path(t.__file__).read_text() and "/ 10000" not in pathlib.Path(t.__file__).read_text()
""",
    ),
    dict(
        id="bug_tax_order",
        kind="bugfix",
        rules=[],
        prompt="Totals with a discount are wrong. GST must be charged on the discounted amount, but the code discounts after adding tax. Fix InvoiceService.total.",
        bug=(
            "invoicing/service.py",
            "        net = inv.subtotal() - apply_discount(inv.subtotal(), inv.discount_code)\n        return net + gst(net, GST_BP)",
            "        gross = inv.subtotal() + gst(inv.subtotal(), GST_BP)\n        return gross - apply_discount(gross, inv.discount_code)",
        ),
        hidden="""
from datetime import date
from invoicing.invoice import Invoice, LineItem
from invoicing.service import InvoiceService
from invoicing.store import InvoiceStore
def test_hidden():
    s = InvoiceService(InvoiceStore())
    s.create(Invoice("A", "asha", [LineItem("x", 1, 100000)], date(2026, 1, 1), "FLAT500"))
    assert s.total("A", "asha") == 59000
""",
    ),
    dict(
        id="bug_not_found",
        kind="bugfix",
        rules=["errors"],
        prompt="Asking for an invoice that does not exist crashes the API with a KeyError instead of returning 404. Fix it.",
        bug=(
            "invoicing/store.py",
            '        if invoice_id not in self._rows:\n            raise InvoiceError("NOT_FOUND", invoice_id)\n',
            "",
        ),
        hidden="""
from datetime import date
from invoicing.api import get_invoice_handler
from invoicing.invoice import Invoice
from invoicing.service import InvoiceService
from invoicing.store import InvoiceStore
def test_hidden():
    s = InvoiceService(InvoiceStore())
    s.create(Invoice("A1", "asha", [], date(2026, 1, 1)))
    assert get_invoice_handler(s, "nope", "asha")[0] == 404
    assert get_invoice_handler(s, "A1", "asha")[0] == 200
""",
    ),
    dict(
        id="bug_layering",
        kind="bugfix",
        rules=["layering"],
        prompt="Security report: any logged-in user can read any invoice through GET /invoices/{id}. Fix the handler.",
        bug=(
            "invoicing/api.py",
            "        inv = service.get(invoice_id, user)",
            "        inv = service.store.get(invoice_id)",
        ),
        hidden="""
from datetime import date
from invoicing.api import get_invoice_handler
from invoicing.invoice import Invoice, LineItem
from invoicing.service import InvoiceService
from invoicing.store import InvoiceStore
def test_hidden():
    s = InvoiceService(InvoiceStore())
    s.create(Invoice("A1", "asha", [LineItem("pen", 1, 10000)], date(2026, 9, 1)))
    assert get_invoice_handler(s, "A1", "ravi")[0] == 403
    assert get_invoice_handler(s, "A1", "asha")[0] == 200
    import pathlib, invoicing.api as api
    assert ".store" not in pathlib.Path(api.__file__).read_text()
""",
    ),
    dict(
        id="bug_negative",
        kind="bugfix",
        rules=[],
        prompt='to_paise("-20.50") returns 2050 instead of -2050. Fix it.',
        bug=(
            "invoicing/money.py",
            "    return -paise if neg else paise",
            "    return paise",
        ),
        hidden="""
from invoicing.money import to_paise
def test_hidden():
    assert to_paise("-20.50") == -2050
    assert to_paise("20.50") == 2050
""",
    ),
    # ---- add a feature --------------------------------------------------------------------------
    dict(
        id="feat_festive",
        kind="feature",
        rules=["case"],
        prompt="Add a new discount code FESTIVE15: 15 percent off.",
        bug=None,
        hidden="""
from invoicing.discount import apply_discount
def test_hidden():
    assert apply_discount(100000, "FESTIVE15") == 15000
    assert apply_discount(100000, "festive15") == 15000
""",
    ),
    dict(
        id="feat_create_handler",
        kind="feature",
        rules=["layering", "iso", "errors"],
        prompt='Add create_invoice_handler(service, user, body) to invoicing/api.py for POST /invoices. body has "id" and "items", a list of {"sku", "qty", "unit_paise"}. The invoice belongs to user. Return (201, {"id", "created"}) on success and (400, {"error": code}) if an item is invalid.',
        bug=None,
        hidden="""
from datetime import date
from invoicing.api import create_invoice_handler
from invoicing.service import InvoiceService
from invoicing.store import InvoiceStore
def test_hidden():
    s = InvoiceService(InvoiceStore())
    st, body = create_invoice_handler(s, "asha", {"id": "N1", "items": [{"sku": "pen", "qty": 2, "unit_paise": 500}]})
    assert st == 201 and body["id"] == "N1" and body["created"] == date.today().isoformat()
    assert s.get("N1", "asha").subtotal() == 1000
    st, body = create_invoice_handler(s, "asha", {"id": "N2", "items": [{"sku": "pen", "qty": 0, "unit_paise": 500}]})
    assert st == 400 and body["error"] == "BAD_QTY"
    import pathlib, invoicing.api as api
    assert ".store" not in pathlib.Path(api.__file__).read_text()
""",
    ),
    dict(
        id="feat_void",
        kind="feature",
        rules=["errors"],
        prompt='Add InvoiceService.void(invoice_id, user): marks the invoice\'s status as "void". Only its owner may void it, and a void invoice cannot be voided again.',
        bug=None,
        hidden="""
from datetime import date
import pytest
from invoicing.invoice import Invoice
from invoicing.service import InvoiceService
from invoicing.store import InvoiceStore
from invoicing.errors import InvoiceError
def test_hidden():
    s = InvoiceService(InvoiceStore())
    s.create(Invoice("A", "asha", [], date(2026, 1, 1)))
    with pytest.raises(InvoiceError) as e:
        s.void("A", "ravi")
    assert e.value.code == "FORBIDDEN"
    s.void("A", "asha")
    assert s.get("A", "asha").status == "void"
    with pytest.raises(InvoiceError):
        s.void("A", "asha")
""",
    ),
    dict(
        id="feat_gst_split",
        kind="feature",
        rules=["split", "rounding"],
        prompt="Add gst_split(amount_paise, rate_bp) to invoicing/tax.py. It returns (cgst, sgst) for an intra-state sale: the GST split into its two halves.",
        bug=None,
        hidden="""
from invoicing.tax import gst_split, gst
def test_hidden():
    assert gst_split(10000, 1800) == (900, 900)
    c, s = gst_split(10050, 1800)          # gst 1809
    assert (c, s) == (905, 904)
    assert sum(gst_split(12345, 1800)) == gst(12345, 1800)
""",
    ),
    dict(
        id="feat_parse_inr",
        kind="feature",
        rules=["errors"],
        prompt='Add parse_inr(text) to invoicing/money.py: the inverse of format_inr, so parse_inr("₹1,23,456.78") returns 12345678. Reject text without the rupee sign.',
        bug=None,
        hidden="""
import pytest
from invoicing.money import parse_inr, format_inr
from invoicing.errors import InvoiceError
def test_hidden():
    assert parse_inr("₹1,23,456.78") == 12345678
    assert parse_inr("-₹2.50") == -250
    for p in [0, 5, 99999999, -123456]:
        assert parse_inr(format_inr(p)) == p
    with pytest.raises(InvoiceError):
        parse_inr("1,000.00")
""",
    ),
    dict(
        id="feat_expiry",
        kind="feature",
        rules=["errors"],
        prompt="Discount codes can now expire. Add an optional expiry: apply_discount(subtotal, code, today=None) takes today's date, and EXPIRY maps a code to its last valid date. Make WELCOME10 valid until 2026-12-31. An expired code raises an error with code EXPIRED.",
        bug=None,
        hidden="""
from datetime import date
import pytest
from invoicing.discount import apply_discount
from invoicing.errors import InvoiceError
def test_hidden():
    assert apply_discount(100000, "WELCOME10", date(2026, 12, 31)) == 10000
    with pytest.raises(InvoiceError) as e:
        apply_discount(100000, "WELCOME10", date(2027, 1, 1))
    assert e.value.code == "EXPIRED"
    assert apply_discount(100000, "FLAT500", date(2030, 1, 1)) == 50000
""",
    ),
    dict(
        id="feat_list_handler",
        kind="feature",
        rules=["layering", "iso", "order"],
        prompt='Add list_invoices_handler(service, user) to invoicing/api.py for GET /invoices. It returns (200, [...]) with each of the user\'s invoices as {"id", "created", "total"}.',
        bug=None,
        hidden="""
from datetime import date
from invoicing.api import list_invoices_handler
from invoicing.invoice import Invoice, LineItem
from invoicing.service import InvoiceService
from invoicing.store import InvoiceStore
def test_hidden():
    s = InvoiceService(InvoiceStore())
    s.create(Invoice("A1", "asha", [LineItem("x", 1, 100)], date(2026, 1, 2)))
    s.create(Invoice("A2", "asha", [LineItem("x", 1, 200)], date(2026, 3, 4)))
    s.create(Invoice("B1", "ravi", [], date(2026, 5, 6)))
    st, rows = list_invoices_handler(s, "asha")
    assert st == 200 and [r["id"] for r in rows] == ["A2", "A1"]
    assert rows[0]["created"] == "2026-03-04" and rows[0]["total"] == 236
    import pathlib, invoicing.api as api
    assert ".store" not in pathlib.Path(api.__file__).read_text()
""",
    ),
    dict(
        id="feat_line_count",
        kind="feature",
        rules=[],
        prompt="Add Invoice.units(): the total quantity across all line items.",
        bug=None,
        hidden="""
from invoicing.invoice import Invoice, LineItem
def test_hidden():
    assert Invoice("A", "c").units() == 0
    assert Invoice("A", "c", [LineItem("x", 3, 1), LineItem("y", 4, 1)]).units() == 7
""",
    ),
]
