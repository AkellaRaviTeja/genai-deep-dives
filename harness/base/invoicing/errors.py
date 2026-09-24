class InvoiceError(Exception):
    """Every failure the package raises. `code` is a short upper-case string."""

    def __init__(self, code, message=""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
