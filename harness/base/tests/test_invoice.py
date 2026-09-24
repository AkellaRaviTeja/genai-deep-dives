from invoicing.invoice import Invoice, LineItem

def test_subtotal():
    inv = Invoice("A1", "asha", [LineItem("pen", 2, 1500), LineItem("pad", 1, 9900)])
    assert inv.subtotal() == 12900
