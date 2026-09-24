from invoicing.discount import apply_discount

def test_percent():
    assert apply_discount(100000, "WELCOME10") == 10000

def test_flat():
    assert apply_discount(100000, "FLAT500") == 50000
