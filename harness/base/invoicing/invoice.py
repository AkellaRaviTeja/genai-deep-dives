from dataclasses import dataclass, field
from datetime import date

from .errors import InvoiceError


@dataclass
class LineItem:
    sku: str
    qty: int
    unit_paise: int

    def __post_init__(self):
        if self.qty <= 0:
            raise InvoiceError("BAD_QTY", f"{self.sku}: {self.qty}")

    def amount(self):
        return self.qty * self.unit_paise


@dataclass
class Invoice:
    id: str
    customer: str
    items: list = field(default_factory=list)
    created: date = field(default_factory=date.today)
    discount_code: str | None = None
    status: str = "open"

    def subtotal(self):
        return sum(item.amount() for item in self.items)
