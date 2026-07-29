"""
currency.py — Currency validation and integer conversion utilities for Kenya Shillings (KES).

In Kenya, the standard unit of currency is the whole Kenya Shilling (KES).
Sub-unit cents are not used. All monetary amounts in the database and API boundaries
must be positive, whole integer KES amounts.
"""

def validate_kes_amount(amount: float | int, field_name: str = "Amount") -> int:
    """
    Validates that a monetary value is a positive whole integer KES amount.
    Returns the amount as an int. Raises ValueError if validation fails.
    """
    if amount is None:
        raise ValueError(f"{field_name} cannot be null.")

    try:
        val = float(amount)
    except (ValueError, TypeError):
        raise ValueError(f"{field_name} must be a valid numeric amount.")

    if val < 0:
        raise ValueError(f"{field_name} cannot be negative.")

    if not val.is_integer():
        raise ValueError(f"{field_name} must be a whole integer KES amount (no decimal places).")

    return int(val)
