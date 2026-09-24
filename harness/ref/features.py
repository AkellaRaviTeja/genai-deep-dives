"""Reference solutions for the feature tasks: appended or substituted into a copy of base/.
Used only by check_tasks() to prove every hidden test is passable."""

FEATURES = {
    "feat_festive": [("invoicing/discount.py", '    "FLAT500": ("flat", 50000),\n', '    "FLAT500": ("flat", 50000),\n    "FESTIVE15": ("percent", 15),\n')],
    "feat_create_handler": [("invoicing/api.py", None, '''

def create_invoice_handler(service, user, body):
    from .invoice import Invoice, LineItem
    try:
        items = [LineItem(i["sku"], i["qty"], i["unit_paise"]) for i in body["items"]]
        inv = service.create(Invoice(body["id"], user, items))
    except InvoiceError as e:
        return _status(e), {"error": e.code}
    return 201, {"id": inv.id, "created": inv.created.isoformat()}
''')],
    "feat_void": [("invoicing/service.py", None, '''
    def void(self, invoice_id, user):
        inv = self._owned(invoice_id, user)
        if inv.status == "void":
            raise InvoiceError("ALREADY_VOID", invoice_id)
        inv.status = "void"
        return inv
''')],
    "feat_gst_split": [("invoicing/tax.py", None, '''

def gst_split(amount_paise, rate_bp):
    total = gst(amount_paise, rate_bp)
    sgst = total // 2
    return total - sgst, sgst
''')],
    "feat_parse_inr": [("invoicing/money.py", None, '''

def parse_inr(text):
    s = text.strip()
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    if not s.startswith("₹"):
        raise InvoiceError("BAD_AMOUNT", text)
    p = to_paise(s[1:])
    return -p if neg else p
''')],
    "feat_expiry": [("invoicing/discount.py", "def apply_discount(subtotal, code):", '''from datetime import date

EXPIRY = {"WELCOME10": date(2026, 12, 31)}


def apply_discount(subtotal, code, today=None):'''),
                    ("invoicing/discount.py", "    kind, value = DISCOUNTS[key]\n", '''    if today and key in EXPIRY and today > EXPIRY[key]:
        raise InvoiceError("EXPIRED", code)
    kind, value = DISCOUNTS[key]
''')],
    "feat_list_handler": [("invoicing/api.py", None, '''

def list_invoices_handler(service, user):
    rows = service.list(user)
    return 200, [{"id": r.id, "created": r.created.isoformat(), "total": service.total(r.id, user)} for r in rows]
''')],
    "feat_line_count": [("invoicing/invoice.py", None, '''
    def units(self):
        return sum(item.qty for item in self.items)
''')],
}
