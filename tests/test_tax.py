"""F1 — golden tests for the deterministic 2025 Form 1040 engine.

Every expected number below is computed BY HAND (the working is shown in each
test's comments) from the official 2025 IRS standard-deduction and bracket
figures (Rev. Proc. 2024-40). These are INDEPENDENT goldens — they are written
as literals, never derived by calling the function under test — so the suite
proves the constants and the bracket walk are correct, not merely self-consistent.

All 1040 amounts are whole-dollar ``Decimal``.
"""

from decimal import Decimal

import pytest

from app.tax.compute import ComputedReturn, compute_return
from app.tax.constants_2025 import (
    BRACKETS_2025,
    STANDARD_DEDUCTION_2025,
    FilingStatus,
)

D = Decimal


def _d(x: str) -> Decimal:
    return Decimal(x)


# ---------------------------------------------------------------------------
# Constants sanity — the 2025 standard deductions, transcribed from IRS figures
# (Rev. Proc. 2024-40 sec. 2.15). These are independent literals.
# ---------------------------------------------------------------------------
def test_standard_deduction_2025_official_figures():
    assert STANDARD_DEDUCTION_2025[FilingStatus.SINGLE] == _d("15000")
    assert STANDARD_DEDUCTION_2025[FilingStatus.MARRIED_FILING_JOINTLY] == _d("30000")
    assert STANDARD_DEDUCTION_2025[FilingStatus.MARRIED_FILING_SEPARATELY] == _d("15000")
    assert STANDARD_DEDUCTION_2025[FilingStatus.HEAD_OF_HOUSEHOLD] == _d("22500")


def test_brackets_are_well_formed():
    """Each schedule is contiguous, ascending, and open-ended at the top."""
    for status, brackets in BRACKETS_2025.items():
        assert brackets[0].lower == _d("0"), status
        assert brackets[-1].upper is None, status
        for prev, nxt in zip(brackets, brackets[1:]):
            # Contiguous: each slab starts where the previous ended.
            assert prev.upper == nxt.lower, status
            # Strictly ascending marginal rate.
            assert nxt.rate > prev.rate, status


# ---------------------------------------------------------------------------
# Golden case A — Single, the fixture profile (~$40k single W-2).
#   wages 40,000 ; withholding 4,200 ; std deduction 15,000
#   taxable = 40,000 - 15,000 = 25,000
#   tax = 0.10*11,925 + 0.12*(25,000-11,925)
#       = 1,192.50 + 0.12*13,075
#       = 1,192.50 + 1,569.00 = 2,761.50  -> round half up -> 2,762
#   refund = 4,200 - 2,762 = 1,438
# ---------------------------------------------------------------------------
def test_golden_single_fixture_profile():
    r = compute_return(40_000, 4_200, FilingStatus.SINGLE)
    assert r.standard_deduction == _d("15000")
    assert r.taxable_income == _d("25000")
    assert r.tax == _d("2762")
    assert r.total_tax == _d("2762")
    assert r.total_payments == _d("4200")
    assert r.refund == _d("1438")
    assert r.amount_owed == _d("0")


# ---------------------------------------------------------------------------
# Golden case B — Married filing jointly.
#   wages 40,000 ; withholding 4,200 ; std deduction 30,000
#   taxable = 40,000 - 30,000 = 10,000  (entirely in the 10% MFJ slab, <=23,850)
#   tax = 0.10*10,000 = 1,000
#   refund = 4,200 - 1,000 = 3,200
# ---------------------------------------------------------------------------
def test_golden_mfj():
    r = compute_return(40_000, 4_200, FilingStatus.MARRIED_FILING_JOINTLY)
    assert r.standard_deduction == _d("30000")
    assert r.taxable_income == _d("10000")
    assert r.tax == _d("1000")
    assert r.refund == _d("3200")
    assert r.amount_owed == _d("0")


# ---------------------------------------------------------------------------
# Golden case C — Married filing separately, reaching the 22% slab.
#   wages 90,000 ; withholding 12,000 ; std deduction 15,000
#   taxable = 90,000 - 15,000 = 75,000
#   tax = 0.10*11,925
#       + 0.12*(48,475-11,925)   = 0.12*36,550 = 4,386.00
#       + 0.22*(75,000-48,475)   = 0.22*26,525 = 5,835.50
#       = 1,192.50 + 4,386.00 + 5,835.50 = 11,414.00 -> 11,414
#   refund = 12,000 - 11,414 = 586
# ---------------------------------------------------------------------------
def test_golden_mfs():
    r = compute_return(90_000, 12_000, FilingStatus.MARRIED_FILING_SEPARATELY)
    assert r.standard_deduction == _d("15000")
    assert r.taxable_income == _d("75000")
    assert r.tax == _d("11414")
    assert r.refund == _d("586")
    assert r.amount_owed == _d("0")


# ---------------------------------------------------------------------------
# Golden case D — Head of household.
#   wages 60,000 ; withholding 5,000 ; std deduction 22,500
#   taxable = 60,000 - 22,500 = 37,500
#   tax = 0.10*17,000          = 1,700.00
#       + 0.12*(37,500-17,000) = 0.12*20,500 = 2,460.00
#       = 4,160.00 -> 4,160
#   refund = 5,000 - 4,160 = 840
# ---------------------------------------------------------------------------
def test_golden_hoh():
    r = compute_return(60_000, 5_000, FilingStatus.HEAD_OF_HOUSEHOLD)
    assert r.standard_deduction == _d("22500")
    assert r.taxable_income == _d("37500")
    assert r.tax == _d("4160")
    assert r.refund == _d("840")
    assert r.amount_owed == _d("0")


# ---------------------------------------------------------------------------
# Owed case — Single, withholding short of the tax.
#   wages 40,000 ; withholding 1,000 ; tax (from case A) = 2,762
#   owed = 2,762 - 1,000 = 1,762   (refund must be 0)
# ---------------------------------------------------------------------------
def test_amount_owed_when_underwithheld():
    r = compute_return(40_000, 1_000, FilingStatus.SINGLE)
    assert r.tax == _d("2762")
    assert r.refund == _d("0")
    assert r.amount_owed == _d("1762")


# ---------------------------------------------------------------------------
# Bracket-boundary case — Single, taxable income EXACTLY at the 12%/22% edge.
#   Choose wages so taxable = 48,475 (the lower edge of the 22% slab):
#       wages = 48,475 + 15,000 = 63,475
#   At the edge, NO income is taxed at 22% yet.
#   tax = 0.10*11,925              = 1,192.50
#       + 0.12*(48,475-11,925)     = 0.12*36,550 = 4,386.00
#       = 5,578.50 -> round half up -> 5,579
# ---------------------------------------------------------------------------
def test_bracket_boundary_exact_edge():
    r = compute_return(63_475, 0, FilingStatus.SINGLE)
    assert r.taxable_income == _d("48475")
    assert r.tax == _d("5579")
    # No payments -> the whole tax is owed.
    assert r.refund == _d("0")
    assert r.amount_owed == _d("5579")


# ---------------------------------------------------------------------------
# Just past the boundary — one full slab dollar over should add 22% of the
# overage, proving the 22% slab actually engages.
#   taxable = 48,575 (i.e. 100 over the edge); wages = 48,575 + 15,000 = 63,575
#   tax = 5,578.50 (edge) + 0.22*100 = 5,578.50 + 22.00 = 5,600.50 -> 5,601
# ---------------------------------------------------------------------------
def test_bracket_just_past_boundary_engages_next_rate():
    r = compute_return(63_575, 0, FilingStatus.SINGLE)
    assert r.taxable_income == _d("48575")
    assert r.tax == _d("5601")


# ---------------------------------------------------------------------------
# Zero-tax low-income case — Single, income below the standard deduction's
# taxable threshold but above 0.
#   wages 10,000 ; std deduction 15,000 -> taxable floored at 0 -> tax 0
#   withholding 500 -> full refund of 500
# ---------------------------------------------------------------------------
def test_zero_tax_low_income_refunds_all_withholding():
    r = compute_return(10_000, 500, FilingStatus.SINGLE)
    assert r.taxable_income == _d("0")
    assert r.tax == _d("0")
    assert r.total_tax == _d("0")
    assert r.refund == _d("500")
    assert r.amount_owed == _d("0")


# ---------------------------------------------------------------------------
# Taxable-income-floored-at-0 — deduction strictly exceeds AGI (MFJ, $5k wages
# vs $30k deduction). Taxable must clamp to 0, never go negative.
# ---------------------------------------------------------------------------
def test_taxable_income_floored_at_zero():
    r = compute_return(5_000, 0, FilingStatus.MARRIED_FILING_JOINTLY)
    assert r.taxable_income == _d("0")
    assert r.taxable_income >= _d("0")
    assert r.tax == _d("0")
    # No withholding, no tax -> a $0 return (both refund and owed are 0).
    assert r.refund == _d("0")
    assert r.amount_owed == _d("0")


# ---------------------------------------------------------------------------
# Structural invariants every return must satisfy (the no-fabrication gate
# relies on these holding for arbitrary inputs).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "wages,withholding,status",
    [
        (40_000, 4_200, FilingStatus.SINGLE),
        (90_000, 12_000, FilingStatus.MARRIED_FILING_SEPARATELY),
        (60_000, 5_000, FilingStatus.HEAD_OF_HOUSEHOLD),
        (10_000, 500, FilingStatus.SINGLE),
        (250_000, 0, FilingStatus.MARRIED_FILING_JOINTLY),
    ],
)
def test_return_invariants(wages, withholding, status):
    r = compute_return(wages, withholding, status)
    assert isinstance(r, ComputedReturn)
    # Line identities for v1 scope (no adjustments/credits/other taxes).
    assert r.wages == r.total_income == r.agi
    assert r.total_tax == r.tax
    assert r.total_payments == r.withholding
    # Taxable income never negative.
    assert r.taxable_income >= _d("0")
    # Refund XOR owed: at most one is non-zero.
    assert not (r.refund > _d("0") and r.amount_owed > _d("0"))
    # The balance identity: payments - total tax = refund - owed.
    assert r.total_payments - r.total_tax == r.refund - r.amount_owed
    # Everything is whole dollars.
    for amount in (r.tax, r.refund, r.amount_owed, r.taxable_income):
        assert amount == amount.to_integral_value()


def test_negative_inputs_rejected():
    with pytest.raises(ValueError):
        compute_return(-1, 0, FilingStatus.SINGLE)
    with pytest.raises(ValueError):
        compute_return(40_000, -5, FilingStatus.SINGLE)


def test_whole_dollar_rounding_half_up():
    # wages 40,000.50 -> rounds to 40,001 before any math.
    r = compute_return(Decimal("40000.50"), Decimal("4200.49"), FilingStatus.SINGLE)
    assert r.wages == _d("40001")
    assert r.withholding == _d("4200")  # .49 rounds down
