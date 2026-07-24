"""Direct tests of the rounding math -- the actual JPY caveat: minor_unit=0
means a WHOLE-yen amount, not yen-cents. Rounding to a hardcoded 2 decimals
would silently corrupt this."""

from decimal import Decimal

from mock_fx.convert import convert_amount


def test_convert_rounds_to_2_decimals_for_eur():
    result = convert_amount(Decimal("42000"), 0.1194, target_minor_unit=2)
    assert result == Decimal("5014.80")


def test_convert_rounds_to_0_decimals_for_jpy():
    """The caveat: JPY has NO subunit. 1000 USD at rate 150.4 -> whole yen,
    never "150400.00"."""
    result = convert_amount(Decimal("1000"), 150.4, target_minor_unit=0)
    assert result == Decimal("150400")
    assert "." not in str(result)


def test_convert_jpy_rounds_half_up_to_whole_yen():
    result = convert_amount(Decimal("10"), 150.455, target_minor_unit=0)
    assert result == Decimal("1505")  # 1504.55 rounds up to 1505, not 1504


def test_convert_preserves_precision_no_float_drift():
    """Decimal-based, not float -- avoids classic 0.1 + 0.2 style drift."""
    result = convert_amount(Decimal("100"), 1.005, target_minor_unit=2)
    assert result == Decimal("100.50")  # not 100.49999...
