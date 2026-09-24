from invoicing.tax import gst

def test_gst():
    assert gst(10000, 1800) == 1800
