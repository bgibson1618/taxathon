"""F1 — deterministic 2025 Form 1040 computation.

``compute_return`` maps W-2 wages + federal withholding + filing status onto the
2025 Form 1040 lines and a refund-or-owed result, entirely in code. This is the
"deterministic spine": the LLM never authors a number — it only calls this and
reports what it returns.

Money is ``Decimal`` throughout and rounded to whole dollars (the 1040 is filed
in whole dollars). Rounding is ROUND_HALF_UP, the convention the IRS instructs
("50 cents or more, round up").

The bounded scope (single W-2, standard deduction, ordinary-income brackets, no
credits / schedules / age adjustments) is intentional — see
``constants_2025`` and DECISION_LOG D6/D7.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.tax.constants_2025 import (
    BRACKETS_2025,
    STANDARD_DEDUCTION_2025,
    Bracket,
    FilingStatus,
)

_ZERO = Decimal("0")
_WHOLE_DOLLAR = Decimal("1")


def _to_dollars(value: Decimal | int | str) -> Decimal:
    """Coerce a money input to a whole-dollar ``Decimal`` (ROUND_HALF_UP)."""
    return Decimal(value).quantize(_WHOLE_DOLLAR, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ComputedReturn:
    """The computed 2025 Form 1040 result, by line number.

    Frozen so a computed return is an immutable fact once produced (the agent
    carries it in ``state.computed`` and the no-fabrication gate recomputes
    against it). All amounts are whole-dollar ``Decimal``.

    Exactly one of ``refund`` / ``amount_owed`` is non-zero (both zero only when
    payments exactly equal total tax).
    """

    filing_status: FilingStatus
    # Line 1a / 1z — wages (single-W-2 profile: 1a == 1z == total income source).
    wages: Decimal
    # Line 9 — total income.
    total_income: Decimal
    # Line 11 — adjusted gross income (no adjustments in v1 scope, so == line 9).
    agi: Decimal
    # Line 12 — standard deduction for the filing status.
    standard_deduction: Decimal
    # Line 15 — taxable income (AGI - deduction, floored at 0).
    taxable_income: Decimal
    # Line 16 — tax (bracket walk on taxable income).
    tax: Decimal
    # Line 24 — total tax (== line 16 in v1 scope: no other taxes/credits).
    total_tax: Decimal
    # Line 25 — federal income tax withheld (from the W-2).
    withholding: Decimal
    # Line 33 — total payments (== withholding in v1 scope).
    total_payments: Decimal
    # Line 34 — overpayment / refund (0 if a balance is owed).
    refund: Decimal
    # Line 37 — amount you owe (0 if a refund is due).
    amount_owed: Decimal


def compute_tax(taxable_income: Decimal, filing_status: FilingStatus) -> Decimal:
    """Line 16 — walk the 2025 brackets for ``filing_status``.

    Sums the marginal tax in each slab the income reaches. ``taxable_income`` is
    expected already floored at 0 and whole-dollar; the result is rounded to
    whole dollars.
    """
    if taxable_income <= _ZERO:
        return _ZERO

    brackets: list[Bracket] = BRACKETS_2025[filing_status]
    tax = _ZERO
    for b in brackets:
        if taxable_income <= b.lower:
            # Income never reaches this slab; nothing above it can either.
            break
        # Upper edge of the portion taxed at this slab's rate.
        slab_top = taxable_income if b.upper is None else min(taxable_income, b.upper)
        taxed_in_slab = slab_top - b.lower
        if taxed_in_slab > _ZERO:
            tax += taxed_in_slab * b.rate

    return _to_dollars(tax)


def compute_return(
    wages: Decimal | int | str,
    withholding: Decimal | int | str,
    filing_status: FilingStatus,
) -> ComputedReturn:
    """Compute the full 2025 Form 1040 result.

    Args:
        wages: W-2 box 1 wages (line 1a/1z). Whole or fractional dollars; rounded.
        withholding: W-2 box 2 federal income tax withheld (line 25).
        filing_status: one of the four supported 2025 statuses.

    Returns:
        A :class:`ComputedReturn` with every modeled 1040 line populated and
        exactly one of refund / amount_owed non-zero.

    Raises:
        ValueError: if ``wages`` or ``withholding`` is negative.
    """
    wages_d = _to_dollars(wages)
    withholding_d = _to_dollars(withholding)
    if wages_d < _ZERO:
        raise ValueError("wages must not be negative")
    if withholding_d < _ZERO:
        raise ValueError("withholding must not be negative")

    total_income = wages_d  # Single-W-2 profile: wages are the only income.
    agi = total_income  # No above-the-line adjustments in v1 scope.

    standard_deduction = STANDARD_DEDUCTION_2025[filing_status]

    # Line 15: taxable income, floored at 0 (deduction can exceed AGI).
    taxable_income = agi - standard_deduction
    if taxable_income < _ZERO:
        taxable_income = _ZERO

    tax = compute_tax(taxable_income, filing_status)
    total_tax = tax  # No additional taxes or nonrefundable credits in v1 scope.
    total_payments = withholding_d  # Withholding is the only payment in v1 scope.

    # Lines 34 / 37: a return is a refund XOR an amount owed.
    balance = total_payments - total_tax
    if balance >= _ZERO:
        refund = balance
        amount_owed = _ZERO
    else:
        refund = _ZERO
        amount_owed = -balance

    return ComputedReturn(
        filing_status=filing_status,
        wages=wages_d,
        total_income=total_income,
        agi=agi,
        standard_deduction=standard_deduction,
        taxable_income=taxable_income,
        tax=tax,
        total_tax=total_tax,
        withholding=withholding_d,
        total_payments=total_payments,
        refund=refund,
        amount_owed=amount_owed,
    )
