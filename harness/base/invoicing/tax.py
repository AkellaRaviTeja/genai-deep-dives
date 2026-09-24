def round_half_even(numerator, denominator):
    """Integer division rounded to nearest, ties to even (banker's rounding)."""
    q, r = divmod(numerator, denominator)
    if 2 * r > denominator or (2 * r == denominator and q % 2 == 1):
        q += 1
    return q


def gst(amount_paise, rate_bp):
    """GST on `amount_paise` at `rate_bp` basis points (1800 = 18%), in paise."""
    return round_half_even(amount_paise * rate_bp, 10000)
