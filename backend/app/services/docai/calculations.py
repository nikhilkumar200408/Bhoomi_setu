"""Deterministic financial calculations using only explicitly supplied inputs."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calculate_financial_value(
    calculation_type: str,
    principal: float,
    annual_rate_percent: float,
    duration_value: float,
    duration_unit: str = "years",
    compounding_frequency: int = 12,
) -> dict:
    """Calculate simple interest, compound interest, or EMI; never infer inputs from documents."""
    try:
        p = Decimal(str(principal))
        rate = Decimal(str(annual_rate_percent))
        duration = Decimal(str(duration_value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("All calculation inputs must be valid numbers.") from exc
    if p <= 0 or rate < 0 or duration <= 0:
        raise ValueError("Principal and duration must be positive; rate cannot be negative.")
    if duration_unit not in ("months", "years"):
        raise ValueError("duration_unit must be months or years.")
    years = duration / Decimal(12) if duration_unit == "months" else duration
    monthly_count = int((duration if duration_unit == "months" else duration * 12).to_integral_value())
    if monthly_count <= 0:
        raise ValueError("Duration must represent at least one month.")

    if calculation_type == "simple_interest":
        interest = p * rate * years / Decimal(100)
        total = p + interest
        formula = "SI = P × R × T / 100"
        working = f"SI = {p} × {rate} × {years} / 100 = ₹{_money(interest):,.2f}"
        result = {"interest": _money(interest), "total_amount": _money(total)}
    elif calculation_type == "compound_interest":
        if compounding_frequency not in (1, 2, 4, 12, 365):
            raise ValueError("Compounding frequency must be 1, 2, 4, 12, or 365.")
        n = Decimal(compounding_frequency)
        periodic_rate = rate / (Decimal(100) * n)
        periods = n * years
        amount = p * (Decimal(1) + periodic_rate) ** periods
        interest = amount - p
        formula = "A = P × (1 + R / (100 × n)) ** (n × T)"
        working = f"A = {p} × (1 + {rate} / (100 × {n})) ** ({n} × {years}) = ₹{_money(amount):,.2f}"
        result = {"interest": _money(interest), "total_amount": _money(amount)}
    elif calculation_type == "emi":
        monthly_rate = rate / Decimal(1200)
        if monthly_rate == 0:
            emi = p / Decimal(monthly_count)
        else:
            factor = (Decimal(1) + monthly_rate) ** monthly_count
            emi = p * monthly_rate * factor / (factor - Decimal(1))
        total = emi * Decimal(monthly_count)
        interest = total - p
        formula = "EMI = P × r × (1 + r) ** n / ((1 + r) ** n − 1)"
        working = f"Monthly rate = {rate} / 1200 = {monthly_rate}; n = {monthly_count}; EMI = ₹{_money(emi):,.2f}"
        result = {"monthly_emi": _money(emi), "total_interest": _money(interest), "total_payable": _money(total)}
    else:
        raise ValueError("Unsupported calculation type.")

    return {
        "calculation_type": calculation_type,
        "inputs": {
            "principal": _money(p),
            "annual_rate_percent": float(rate),
            "duration_value": float(duration),
            "duration_unit": duration_unit,
            "compounding_frequency": compounding_frequency if calculation_type == "compound_interest" else None,
        },
        "formula": formula,
        "working": working,
        "result": result,
        "input_source": "USER_PROVIDED",
        "notice": "Calculated only from the values you entered; these values have not been verified against uploaded documents.",
    }
