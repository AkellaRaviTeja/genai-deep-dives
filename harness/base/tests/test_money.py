import pytest
from invoicing.money import to_paise, format_inr
from invoicing.errors import InvoiceError

def test_to_paise():
    assert to_paise("1,234.50") == 123450
    assert to_paise("20") == 2000

def test_to_paise_rejects_three_decimals():
    with pytest.raises(InvoiceError):
        to_paise("1.234")

def test_format_inr():
    assert format_inr(12345678) == "₹1,23,456.78"
    assert format_inr(5) == "₹0.05"
