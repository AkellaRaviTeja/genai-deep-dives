# invoicing

Billing code for an Indian invoicing service.

## Rules that the code will not tell you

- Money is integer paise everywhere. Never use float for money, not even in between.
- Tax rounds half to even (banker's rounding): use `round_half_even` in `tax.py`.
- Every failure raises `InvoiceError(code)` from `errors.py`, never ValueError or KeyError.
  Codes are short and upper case, e.g. `NOT_FOUND`, `FORBIDDEN`, `BAD_AMOUNT`.
- Layering: `api.py` talks only to `InvoiceService`. It must never import or call
  `InvoiceStore`. Permission checks live in the service, so skipping it skips them.
- Discount codes are matched case-insensitively, after trimming spaces.
- A discount never makes a total negative: cap it at the subtotal.
- Dates in API responses are ISO 8601 strings (`date.isoformat()`).
- Lists of invoices are newest first, ties broken by id, newest id first.
- When GST is split into CGST and SGST, each is half; an odd paise goes to CGST.

## Checking your work

Run the tests with the `run_tests` tool. Do not edit anything under `tests/`.
