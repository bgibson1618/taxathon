"""2025 Form 1040 constants — standard deduction and federal income-tax brackets.

These are DATA, transcribed exactly from the official IRS inflation-adjustment
figures for tax year 2025. A single transcription error here silently corrupts
every return, so each figure is sourced and golden-tested in ``tests/test_tax.py``
against independent hand-computed cases.

SOURCE — IRS Revenue Procedure 2024-40 (inflation-adjusted amounts for tax year
2025), published 2024-10-22. Cross-checked against IRS Topic / news release
IR-2024-273 ("IRS releases tax inflation adjustments for tax year 2025").

  - Standard deduction, TY2025 (Rev. Proc. 2024-40 sec. 2.15):
        Single ............................. $15,000
        Married filing jointly ............. $30,000
        Married filing separately .......... $15,000
        Head of household .................. $22,500

  - Income-tax rate schedules, TY2025 (Rev. Proc. 2024-40 sec. 2.01, Table 3):
        seven brackets — 10/12/22/24/32/35/37% — with the breakpoints below.

SCOPE: this models the ordinary-income rate schedule for a standard-deduction
return only. No age-65/blind/dependent standard-deduction adjustments, no
capital-gains schedule, no AMT, no credits. That bounded scope is intentional
(see DECISION_LOG D6/D7 and ARCHITECTURE Key Decision 8).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class FilingStatus(str, Enum):
    """The four 2025 filing statuses the engine supports.

    ``str``-valued so the member value is a stable wire/enum token usable by the
    ``set_filing_status`` tool and the PDF filing-status checkbox map.
    """

    SINGLE = "single"
    MARRIED_FILING_JOINTLY = "married_filing_jointly"
    MARRIED_FILING_SEPARATELY = "married_filing_separately"
    HEAD_OF_HOUSEHOLD = "head_of_household"


# --- Standard deduction, tax year 2025 (Rev. Proc. 2024-40 sec. 2.15) ---------
# Whole dollars; Decimal so it composes with the rest of the money math.
STANDARD_DEDUCTION_2025: dict[FilingStatus, Decimal] = {
    FilingStatus.SINGLE: Decimal("15000"),
    FilingStatus.MARRIED_FILING_JOINTLY: Decimal("30000"),
    FilingStatus.MARRIED_FILING_SEPARATELY: Decimal("15000"),
    FilingStatus.HEAD_OF_HOUSEHOLD: Decimal("22500"),
}


@dataclass(frozen=True)
class Bracket:
    """One slab of a progressive rate schedule.

    ``lower`` is the inclusive lower bound of taxable income for this slab,
    ``upper`` is the exclusive upper bound (``None`` for the top, open-ended
    slab), and ``rate`` is the marginal rate applied to income within the slab.
    """

    lower: Decimal
    upper: Decimal | None
    rate: Decimal


# --- 2025 ordinary-income rate schedules (Rev. Proc. 2024-40 sec. 2.01) -------
# Each list is ordered low -> high. Breakpoints are the TAXABLE-INCOME edges of
# each marginal slab for the status, transcribed from the published TY2025
# schedule. ``upper=None`` marks the open-ended top (37%) slab.
#
# Single (unmarried individuals other than surviving spouses and HoH):
#   10% : $0          – $11,925
#   12% : $11,925     – $48,475
#   22% : $48,475     – $103,350
#   24% : $103,350    – $197,300
#   32% : $197,300    – $250,525
#   35% : $250,525    – $626,350
#   37% : $626,350    – and up
_SINGLE = [
    Bracket(Decimal("0"), Decimal("11925"), Decimal("0.10")),
    Bracket(Decimal("11925"), Decimal("48475"), Decimal("0.12")),
    Bracket(Decimal("48475"), Decimal("103350"), Decimal("0.22")),
    Bracket(Decimal("103350"), Decimal("197300"), Decimal("0.24")),
    Bracket(Decimal("197300"), Decimal("250525"), Decimal("0.32")),
    Bracket(Decimal("250525"), Decimal("626350"), Decimal("0.35")),
    Bracket(Decimal("626350"), None, Decimal("0.37")),
]

# Married filing jointly (and surviving spouses):
#   10% : $0          – $23,850
#   12% : $23,850     – $96,950
#   22% : $96,950     – $206,700
#   24% : $206,700    – $394,600
#   32% : $394,600    – $501,050
#   35% : $501,050    – $751,600
#   37% : $751,600    – and up
_MFJ = [
    Bracket(Decimal("0"), Decimal("23850"), Decimal("0.10")),
    Bracket(Decimal("23850"), Decimal("96950"), Decimal("0.12")),
    Bracket(Decimal("96950"), Decimal("206700"), Decimal("0.22")),
    Bracket(Decimal("206700"), Decimal("394600"), Decimal("0.24")),
    Bracket(Decimal("394600"), Decimal("501050"), Decimal("0.32")),
    Bracket(Decimal("501050"), Decimal("751600"), Decimal("0.35")),
    Bracket(Decimal("751600"), None, Decimal("0.37")),
]

# Married filing separately:
#   10% : $0          – $11,925
#   12% : $11,925     – $48,475
#   22% : $48,475     – $103,350
#   24% : $103,350    – $197,300
#   32% : $197,300    – $250,525
#   35% : $250,525    – $375,800
#   37% : $375,800    – and up
_MFS = [
    Bracket(Decimal("0"), Decimal("11925"), Decimal("0.10")),
    Bracket(Decimal("11925"), Decimal("48475"), Decimal("0.12")),
    Bracket(Decimal("48475"), Decimal("103350"), Decimal("0.22")),
    Bracket(Decimal("103350"), Decimal("197300"), Decimal("0.24")),
    Bracket(Decimal("197300"), Decimal("250525"), Decimal("0.32")),
    Bracket(Decimal("250525"), Decimal("375800"), Decimal("0.35")),
    Bracket(Decimal("375800"), None, Decimal("0.37")),
]

# Head of household:
#   10% : $0          – $17,000
#   12% : $17,000     – $64,850
#   22% : $64,850     – $103,350
#   24% : $103,350    – $197,300
#   32% : $197,300    – $250,500
#   35% : $250,500    – $626,350
#   37% : $626,350    – and up
_HOH = [
    Bracket(Decimal("0"), Decimal("17000"), Decimal("0.10")),
    Bracket(Decimal("17000"), Decimal("64850"), Decimal("0.12")),
    Bracket(Decimal("64850"), Decimal("103350"), Decimal("0.22")),
    Bracket(Decimal("103350"), Decimal("197300"), Decimal("0.24")),
    Bracket(Decimal("197300"), Decimal("250500"), Decimal("0.32")),
    Bracket(Decimal("250500"), Decimal("626350"), Decimal("0.35")),
    Bracket(Decimal("626350"), None, Decimal("0.37")),
]

BRACKETS_2025: dict[FilingStatus, list[Bracket]] = {
    FilingStatus.SINGLE: _SINGLE,
    FilingStatus.MARRIED_FILING_JOINTLY: _MFJ,
    FilingStatus.MARRIED_FILING_SEPARATELY: _MFS,
    FilingStatus.HEAD_OF_HOUSEHOLD: _HOH,
}
