"""A bigger repository around the same package: `legacy/` gets 40 modules of old code,
generated deterministically. Most are unrelated domains; four are old versions of the
billing code that follow different, older conventions (case-sensitive discount codes,
tax rounded half up with floats, an API that reads the store directly, lists oldest
first). A real codebase is like this: the rules are not the only thing in it.

    uv run python harness/big.py    writes legacy/ into big/ and prints its size
"""

import pathlib
import random

ROOT = pathlib.Path(__file__).resolve().parent
LEGACY = ROOT / "big" / "legacy"

DOMAINS = [
    "inventory",
    "shipping",
    "payroll",
    "loyalty",
    "refunds",
    "vendors",
    "warehouse",
    "catalog",
    "pricing",
    "coupons",
    "returns",
    "ledger",
    "reports",
    "exports",
    "imports",
    "webhooks",
    "notifications",
    "audit",
    "sessions",
    "tenants",
    "currency",
    "addresses",
    "contacts",
    "subscriptions",
    "usage",
    "quotas",
    "schedules",
    "reminders",
    "templates",
    "attachments",
    "search",
    "tags",
    "comments",
    "approvals",
    "budgets",
    "forecasts",
]

OLD = {
    "billing_v1.py": '''"""Billing, version 1. Kept for the 2023 invoices; new code must not use it."""

DISCOUNTS = {"WELCOME10": 10.0, "FLAT500": 500.0}


def apply_discount(subtotal_rupees, code):
    """Discount in rupees. Codes are exact and case-sensitive."""
    if code not in DISCOUNTS:
        return 0.0
    value = DISCOUNTS[code]
    if value < 100:
        return subtotal_rupees * value / 100
    return value
''',
    "tax_old.py": '''"""Tax helpers from before the paise migration."""


def gst(amount_rupees, rate_percent=18.0):
    """GST in rupees, rounded half up to two decimals."""
    return float(int(amount_rupees * rate_percent / 100 * 100 + 0.5)) / 100


def split_gst(total):
    """CGST and SGST: the odd paisa goes to SGST."""
    half = round(total / 2, 2)
    return total - half, half
''',
    "api_v1.py": '''"""API handlers, version 1. Read straight from the store for speed."""

from invoicing.store import InvoiceStore

STORE = InvoiceStore()


def get_invoice(invoice_id):
    inv = STORE.get(invoice_id)
    return 200, {"id": inv.id, "customer": inv.customer, "created": str(inv.created)}


def list_invoices(customer):
    rows = STORE.list_by_customer(customer)
    return 200, [{"id": r.id} for r in sorted(rows, key=lambda r: r.created)]
''',
    "money_old.py": '''"""Money formatting from the first release."""


def format_rupees(amount):
    """Western grouping: 1234567.8 -> "Rs 1,234,567.80"."""
    return "Rs {:,.2f}".format(amount)


def parse_rupees(text):
    return float(text.replace("Rs", "").replace(",", "").strip())
''',
}


def module(domain, rng):
    lines = [
        f'"""{domain.capitalize()}: helpers used by the back office."""',
        "",
        "from dataclasses import dataclass",
        "",
    ]
    entity = domain.rstrip("s").capitalize() or domain.capitalize()
    fields = rng.sample(
        [
            "id",
            "name",
            "owner",
            "created",
            "status",
            "amount",
            "count",
            "region",
            "notes",
            "priority",
            "updated",
        ],
        5,
    )
    if "id" not in fields:
        fields[0] = "id"
    lines += (
        ["", "@dataclass", f"class {entity}:"]
        + [f"    {f}: object = None" for f in fields]
        + [""]
    )
    verbs = rng.sample(
        [
            "load",
            "save",
            "list",
            "find",
            "total",
            "summarise",
            "validate",
            "archive",
            "merge",
            "export",
            "count",
            "rank",
        ],
        12,
    )
    for v in verbs:
        arg = rng.choice(["rows", "items", "records", "entries"])
        key = rng.choice(fields)
        lines += [
            "",
            f"def {v}_{domain}({arg}, limit=100):",
            f'    """{v.capitalize()} {domain} by {key}. Returns at most `limit` results."""',
        ]
        body = rng.choice(
            [
                [
                    f"    out = [r for r in {arg} if getattr(r, '{key}', None) is not None]",
                    "    return out[:limit]",
                ],
                [
                    "    seen = {}",
                    f"    for r in {arg}:",
                    f"        seen[getattr(r, '{key}', None)] = r",
                    "    return list(seen.values())[:limit]",
                ],
                [
                    "    total = 0",
                    f"    for r in {arg}[:limit]:",
                    "        total += getattr(r, 'amount', 0) or 0",
                    "    return total",
                ],
                [
                    f"    return sorted({arg}, key=lambda r: str(getattr(r, '{key}', '')))[:limit]"
                ],
            ]
        )
        lines += body
    return "\n".join(lines) + "\n"


def build():
    rng = random.Random(2026)
    LEGACY.mkdir(parents=True, exist_ok=True)
    (LEGACY / "__init__.py").write_text("")
    for d in DOMAINS:
        (LEGACY / f"{d}.py").write_text(module(d, rng))
        (LEGACY / f"{d}_jobs.py").write_text(module(d, rng))
    for name, src in OLD.items():
        (LEGACY / name).write_text(src)
    files = sorted(LEGACY.glob("*.py"))
    n_lines = sum(len(p.read_text().splitlines()) for p in files)
    print(f"  legacy/: {len(files)} files, {n_lines:,} lines")
    return files


if __name__ == "__main__":
    build()
