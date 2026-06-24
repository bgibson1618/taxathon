"""F7 — filing-status variation (test leg).

F7 does not own any app code: the *capability* already exists (F1 computes every
status, F4 carries the status in session state, F3 fills the PDF). This suite
**proves** the variation end-to-end at the test level:

1. For EACH of the four 2025 filing statuses (Single / MFJ / MFS / HoH), computing
   the return on the **same** wages + withholding yields the correct, status-specific
   standard deduction, tax, and refund — each asserted against a golden value that
   is computed BY HAND below (an independent literal, never a same-path recompute).
   This is what makes "changing status recomputes correctly" a real claim and not a
   tautology.

2. For EACH status, ``app.pdf.fill.fill_1040`` produces a PDF whose filing-status
   **checkbox** reflects the status (the right box is on, the other three are off)
   and whose **status-specific computed lines** (standard deduction, tax, refund)
   appear in the extracted page text. Single & HoH additionally fully fill — the
   taxpayer identity (name + masked SSN) is present in the text. MFJ & MFS produce
   the correct computed figures; spouse-identity PDF fields are out of v1 scope
   (ARCHITECTURE Key Decision 5 / DECISION_LOG D7), so they are not asserted.

Golden working (independent hand computation)
=============================================
Fixture profile, held constant across all four statuses so only the *status*
varies: wages = $40,000, federal withholding = $3,000 (the F2 fixture values).
2025 figures from Rev. Proc. 2024-40 (see app/tax/constants_2025.py).

  Single   : std 15,000 -> taxable 25,000
             tax = 0.10*11,925 + 0.12*(25,000-11,925)
                 = 1,192.50 + 0.12*13,075 = 1,192.50 + 1,569.00 = 2,761.50 -> 2,762
             refund = 3,000 - 2,762 = 238

  MFJ      : std 30,000 -> taxable 10,000  (entirely in the 10% MFJ slab, <=23,850)
             tax = 0.10*10,000 = 1,000
             refund = 3,000 - 1,000 = 2,000

  MFS      : std 15,000 -> taxable 25,000  (MFS shares the Single low-end breakpoints)
             tax = 0.10*11,925 + 0.12*13,075 = 2,761.50 -> 2,762
             refund = 3,000 - 2,762 = 238

  HoH      : std 22,500 -> taxable 17,500
             tax = 0.10*17,000 + 0.12*(17,500-17,000)
                 = 1,700.00 + 0.12*500 = 1,700.00 + 60.00 = 1,760.00 -> 1,760
             refund = 3,000 - 1,760 = 1,240

Note the variation is real: the deduction (15k/30k/15k/22.5k), the taxable income,
the tax, and the refund all move with the status even though wages/withholding are
identical. Single and MFS happen to share a deduction + low-end brackets, so their
numbers coincide — they are distinguished in the PDF by the filing-status checkbox.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from decimal import Decimal

import pytest
from pypdf import PdfReader

from app.pdf import field_map as fm
from app.pdf.fill import fill_1040
from app.tax.compute import compute_return
from app.tax.constants_2025 import FilingStatus
from app.w2.build_fixture import build_fixture
from app.w2.extract import extract_w2_from_bytes

D = Decimal

# The fixture profile, held CONSTANT across all four statuses so only the status varies.
WAGES = 40_000
WITHHOLDING = 3_000


@dataclass(frozen=True)
class Golden:
    """An independent, hand-computed golden for one filing status (see module docstring)."""

    status: FilingStatus
    standard_deduction: Decimal
    taxable_income: Decimal
    tax: Decimal
    refund: Decimal
    fully_fills: bool  # Single & HoH fully fill the PDF (identity asserted); MFJ/MFS compute-only.


# The four goldens. Every number is a literal hand computation, NOT a call to the
# function under test — so a transcription/bracket error cannot hide behind a
# self-consistent recompute.
GOLDENS: dict[FilingStatus, Golden] = {
    FilingStatus.SINGLE: Golden(
        FilingStatus.SINGLE, D("15000"), D("25000"), D("2762"), D("238"), fully_fills=True
    ),
    FilingStatus.MARRIED_FILING_JOINTLY: Golden(
        FilingStatus.MARRIED_FILING_JOINTLY,
        D("30000"),
        D("10000"),
        D("1000"),
        D("2000"),
        fully_fills=False,
    ),
    FilingStatus.MARRIED_FILING_SEPARATELY: Golden(
        FilingStatus.MARRIED_FILING_SEPARATELY,
        D("15000"),
        D("25000"),
        D("2762"),
        D("238"),
        fully_fills=False,
    ),
    FilingStatus.HEAD_OF_HOUSEHOLD: Golden(
        FilingStatus.HEAD_OF_HOUSEHOLD,
        D("22500"),
        D("17500"),
        D("1760"),
        D("1240"),
        fully_fills=True,
    ),
}

# Sanity: a golden exists for every supported status (catches a status added to the
# engine but not covered here).
assert set(GOLDENS) == set(FilingStatus)


@pytest.fixture(scope="module")
def w2_identity(tmp_path_factory):
    """Parse the F2 fake-W-2 fixture into a validated W2 (built to a temp path).

    Confirms the fixture really is the $40k / $3k profile the goldens assume, so the
    test stays honest if the fixture is ever re-authored.
    """
    tmp = tmp_path_factory.mktemp("w2") / "fake_w2.pdf"
    build_fixture(tmp)
    w2 = extract_w2_from_bytes(tmp.read_bytes())
    assert w2.wages == float(WAGES), "fixture wages drifted from the F7 golden profile"
    assert w2.fed_withholding == float(WITHHOLDING), "fixture withholding drifted from the F7 golden profile"
    return w2


def _all_pages_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() for page in reader.pages)


# ===========================================================================
# 1. Computation varies correctly per status (golden literals).
# ===========================================================================
@pytest.mark.parametrize("status", list(FilingStatus), ids=lambda s: s.value)
def test_computation_matches_status_golden(status):
    """Same wages, different status -> the correct status-specific deduction + tax + refund."""
    g = GOLDENS[status]
    r = compute_return(WAGES, WITHHOLDING, status)

    assert r.filing_status is status
    assert r.standard_deduction == g.standard_deduction, "standard deduction wrong for status"
    assert r.taxable_income == g.taxable_income, "taxable income wrong for status"
    assert r.tax == g.tax, "bracket tax wrong for status"
    assert r.total_tax == g.tax
    assert r.refund == g.refund, "refund wrong for status"
    assert r.amount_owed == D("0")


def test_standard_deduction_actually_varies_by_status():
    """The four statuses do not all share one deduction — variation is real, not cosmetic."""
    deductions = {s: compute_return(WAGES, WITHHOLDING, s).standard_deduction for s in FilingStatus}
    # MFJ (30k) and HoH (22.5k) are distinct from Single/MFS (15k) and from each other.
    assert deductions[FilingStatus.MARRIED_FILING_JOINTLY] == D("30000")
    assert deductions[FilingStatus.HEAD_OF_HOUSEHOLD] == D("22500")
    assert deductions[FilingStatus.SINGLE] == D("15000")
    # At least three distinct deduction values across the four statuses.
    assert len(set(deductions.values())) >= 3


def test_changing_status_recomputes_tax_and_refund():
    """Simulate the 'change status mid-conversation' move: single -> head_of_household.

    The same wages/withholding recompute to a DIFFERENT deduction, tax, and refund,
    which is exactly the F7 user-visible behavior (state carried; recomputed on change).
    """
    before = compute_return(WAGES, WITHHOLDING, FilingStatus.SINGLE)
    after = compute_return(WAGES, WITHHOLDING, FilingStatus.HEAD_OF_HOUSEHOLD)

    assert before.standard_deduction != after.standard_deduction
    assert before.tax != after.tax
    assert before.refund != after.refund
    # And each side still matches its independent golden.
    assert (before.standard_deduction, before.tax, before.refund) == (D("15000"), D("2762"), D("238"))
    assert (after.standard_deduction, after.tax, after.refund) == (D("22500"), D("1760"), D("1240"))


# ===========================================================================
# 2. The filled PDF reflects the status (checkbox + computed lines).
# ===========================================================================
@pytest.mark.parametrize("status", list(FilingStatus), ids=lambda s: s.value)
def test_filled_pdf_sets_the_right_filing_status_checkbox(w2_identity, status):
    """Exactly the status's checkbox is on (/1); the other three are off (/Off)."""
    r = compute_return(WAGES, WITHHOLDING, status)
    pdf = fill_1040(r, w2_identity, status)
    reader = PdfReader(io.BytesIO(pdf))
    fields = reader.get_fields() or {}

    on_box = fm.FILING_STATUS_CHECKBOX[status]
    assert fields.get(on_box, {}).get("/V") in (fm.CHECKBOX_ON_VALUE, "/1"), (
        f"{status.value}: its checkbox {on_box} is not set on"
    )
    # Every OTHER status checkbox must be off — so the form unambiguously shows one status.
    for other, box in fm.FILING_STATUS_CHECKBOX.items():
        if other is status:
            continue
        v = fields.get(box, {}).get("/V")
        assert v in (None, "/Off"), f"{status.value}: stray checkbox {other.value} is set ({v!r})"


@pytest.mark.parametrize("status", list(FilingStatus), ids=lambda s: s.value)
def test_filled_pdf_computed_lines_reflect_status(w2_identity, status):
    """The status-specific computed dollars (deduction, tax, refund) are real page text."""
    g = GOLDENS[status]
    r = compute_return(WAGES, WITHHOLDING, status)
    pdf = fill_1040(r, w2_identity, status)
    text = _all_pages_text(pdf)

    assert pdf[:5] == b"%PDF-"
    for label, value in (
        ("standard_deduction", g.standard_deduction),
        ("tax", g.tax),
        ("refund", g.refund),
    ):
        assert str(int(value)) in text, (
            f"{status.value}: {label} {int(value)} not found in filled PDF text"
        )


@pytest.mark.parametrize(
    "status",
    [FilingStatus.SINGLE, FilingStatus.HEAD_OF_HOUSEHOLD],
    ids=lambda s: s.value,
)
def test_single_and_hoh_fully_fill_identity(w2_identity, status):
    """Single & HoH fully fill: taxpayer name + masked SSN are present (raw SSN never is)."""
    r = compute_return(WAGES, WITHHOLDING, status)
    pdf = fill_1040(r, w2_identity, status)
    text = _all_pages_text(pdf)

    first, *rest = w2_identity.employee_name.split()
    last = rest[-1] if rest else ""
    assert first in text, f"{status.value}: first name missing from fully-filled PDF"
    assert last in text, f"{status.value}: last name missing from fully-filled PDF"
    # Masked SSN present; the raw 9-digit SSN must never appear.
    assert w2_identity.masked_ssn in text
    assert "123-45-6789" not in text
    assert "123456789" not in text


@pytest.mark.parametrize(
    "status",
    [FilingStatus.MARRIED_FILING_JOINTLY, FilingStatus.MARRIED_FILING_SEPARATELY],
    ids=lambda s: s.value,
)
def test_mfj_mfs_compute_only_but_produce_correct_figures(w2_identity, status):
    """MFJ/MFS are compute-focused: the correct status figures fill, even though spouse-

    identity PDF fields are out of v1 scope. We assert the computed lines, not spouse fields.
    """
    g = GOLDENS[status]
    r = compute_return(WAGES, WITHHOLDING, status)
    pdf = fill_1040(r, w2_identity, status)
    text = _all_pages_text(pdf)

    # The status-specific deduction + tax are present (the load-bearing claim for MFJ/MFS).
    assert str(int(g.standard_deduction)) in text
    assert str(int(g.tax)) in text
    # The right filing-status checkbox is still set (status is recorded on the form).
    reader = PdfReader(io.BytesIO(pdf))
    fields = reader.get_fields() or {}
    on_box = fm.FILING_STATUS_CHECKBOX[status]
    assert fields.get(on_box, {}).get("/V") in (fm.CHECKBOX_ON_VALUE, "/1")
