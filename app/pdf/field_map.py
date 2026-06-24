"""F3 — semantic -> AcroForm field-name map for the official 2025 Form 1040.

The vendored ``assets/f1040_2025.pdf`` is a hybrid AcroForm + XFA form whose field
names are opaque XFA-style dotted paths (``topmostSubform[0].Page1[0].f1_47[0]``) with
**no tooltips** — every field's ``/TU`` is ``None`` (verified). So the names alone do
not say which field is "wages" vs "AGI"; the map below was built **by hand**, by:

1. Dumping all 229 fields with :func:`pypdf.PdfReader.get_fields`.
2. Reading each field's ``/Rect`` (position) from its page annotation and correlating
   the field's Y-coordinate with the line label's Y-coordinate from the page's
   extracted text (the form has no usable ``/TU`` tooltips, so position is the key).
3. For the filing-status checkboxes, reading ``/_States_`` for the on-value — it is
   the NameObject ``/1`` (NOT ``/Yes``); off is ``/Off`` (verified per field).

Each mapped value was confirmed to survive ``flatten=True`` into the PDF's extracted
page text (see ``tests/test_pdf.py``). Scope is the guaranteed-core lines + identity +
filing status — ~20 fields of 229, exactly what a single-W-2 standard-deduction return
needs (ARCHITECTURE / research/irs-1040-pdf-fill.md).

2025-form line-numbering note: on the *2025* Form 1040 the adjusted gross income line
is **11a/11b**, the standard deduction is **line 12e**, and taxable income is **line 15**.
The semantic keys below use the architecture's shorthand (``LINE_11_AGI``,
``LINE_12_STANDARD_DEDUCTION``, ``LINE_15_TAXABLE_INCOME``) and target those 2025 cells.
"""

from __future__ import annotations

from app.tax.constants_2025 import FilingStatus

# --- Identity / header fields (page 1) ---------------------------------------
# The name/SSN row sits at the top of page 1; address is the Address_ReadOrder group.
FIELD_FIRST_NAME = "topmostSubform[0].Page1[0].f1_01[0]"  # Your first name and middle initial
FIELD_LAST_NAME = "topmostSubform[0].Page1[0].f1_02[0]"  # Last name
FIELD_SSN = "topmostSubform[0].Page1[0].f1_03[0]"  # Your social security number
FIELD_ADDRESS_STREET = (
    "topmostSubform[0].Page1[0].Address_ReadOrder[0].f1_20[0]"  # Home address (number and street)
)
FIELD_ADDRESS_APT = (
    "topmostSubform[0].Page1[0].Address_ReadOrder[0].f1_21[0]"  # Apt. no.
)
FIELD_ADDRESS_CITY = (
    "topmostSubform[0].Page1[0].Address_ReadOrder[0].f1_22[0]"  # City, town, or post office
)
FIELD_ADDRESS_STATE = (
    "topmostSubform[0].Page1[0].Address_ReadOrder[0].f1_23[0]"  # State
)
FIELD_ADDRESS_ZIP = (
    "topmostSubform[0].Page1[0].Address_ReadOrder[0].f1_24[0]"  # ZIP code
)

# --- Filing-status checkboxes (page 1) ---------------------------------------
# Each checkbox's on-value is the NameObject "/1" (read from /_States_ == ['/1', '/Off']).
# Layout on the 2025 form: Single (c1_1), MFJ (c1_2), MFS (c1_3), HoH (c1_4).
FIELD_FILING_STATUS_SINGLE = "topmostSubform[0].Page1[0].c1_1[0]"
FIELD_FILING_STATUS_MFJ = "topmostSubform[0].Page1[0].c1_2[0]"
FIELD_FILING_STATUS_MFS = "topmostSubform[0].Page1[0].c1_3[0]"
FIELD_FILING_STATUS_HOH = "topmostSubform[0].Page1[0].c1_4[0]"

# The on-value every 1040 checkbox uses (NOT "/Yes"). Read from /_States_.
CHECKBOX_ON_VALUE = "/1"

# Semantic FilingStatus -> the checkbox field that must be set to CHECKBOX_ON_VALUE.
FILING_STATUS_CHECKBOX: dict[FilingStatus, str] = {
    FilingStatus.SINGLE: FIELD_FILING_STATUS_SINGLE,
    FilingStatus.MARRIED_FILING_JOINTLY: FIELD_FILING_STATUS_MFJ,
    FilingStatus.MARRIED_FILING_SEPARATELY: FIELD_FILING_STATUS_MFS,
    FilingStatus.HEAD_OF_HOUSEHOLD: FIELD_FILING_STATUS_HOH,
}

# --- Numeric line fields -----------------------------------------------------
# Page 1 income block:
FIELD_LINE_1A_WAGES = "topmostSubform[0].Page1[0].f1_47[0]"  # 1a  W-2 box 1 wages
FIELD_LINE_1Z_TOTAL_WAGES = "topmostSubform[0].Page1[0].f1_57[0]"  # 1z  add lines 1a-1h
FIELD_LINE_9_TOTAL_INCOME = "topmostSubform[0].Page1[0].f1_73[0]"  # 9   total income
FIELD_LINE_11A_AGI = "topmostSubform[0].Page1[0].f1_75[0]"  # 11a adjusted gross income (page 1)

# Page 2:
FIELD_LINE_11B_AGI = "topmostSubform[0].Page2[0].f2_02[0]"  # 11b AGI (carried to page 2)
FIELD_LINE_12_STANDARD_DEDUCTION = "topmostSubform[0].Page2[0].f2_05[0]"  # 12e standard deduction
FIELD_LINE_15_TAXABLE_INCOME = "topmostSubform[0].Page2[0].f2_08[0]"  # 15  taxable income
FIELD_LINE_16_TAX = "topmostSubform[0].Page2[0].f2_09[0]"  # 16  tax
FIELD_LINE_24_TOTAL_TAX = "topmostSubform[0].Page2[0].f2_16[0]"  # 24  total tax
FIELD_LINE_25A_WITHHOLDING = "topmostSubform[0].Page2[0].f2_17[0]"  # 25a W-2 withholding
FIELD_LINE_25D_TOTAL_WITHHOLDING = "topmostSubform[0].Page2[0].f2_20[0]"  # 25d total withholding
FIELD_LINE_33_TOTAL_PAYMENTS = "topmostSubform[0].Page2[0].f2_28[0]"  # 33  total payments
FIELD_LINE_34_REFUND = "topmostSubform[0].Page2[0].f2_29[0]"  # 34  overpayment / refund
FIELD_LINE_37_AMOUNT_OWED = "topmostSubform[0].Page2[0].f2_35[0]"  # 37  amount you owe

# Every text field this module maps (identity + numeric). The fill writes these as
# strings; the unit test asserts every name still exists in the vendored form.
TEXT_FIELD_NAMES: tuple[str, ...] = (
    FIELD_FIRST_NAME,
    FIELD_LAST_NAME,
    FIELD_SSN,
    FIELD_ADDRESS_STREET,
    FIELD_ADDRESS_APT,
    FIELD_ADDRESS_CITY,
    FIELD_ADDRESS_STATE,
    FIELD_ADDRESS_ZIP,
    FIELD_LINE_1A_WAGES,
    FIELD_LINE_1Z_TOTAL_WAGES,
    FIELD_LINE_9_TOTAL_INCOME,
    FIELD_LINE_11A_AGI,
    FIELD_LINE_11B_AGI,
    FIELD_LINE_12_STANDARD_DEDUCTION,
    FIELD_LINE_15_TAXABLE_INCOME,
    FIELD_LINE_16_TAX,
    FIELD_LINE_24_TOTAL_TAX,
    FIELD_LINE_25A_WITHHOLDING,
    FIELD_LINE_25D_TOTAL_WITHHOLDING,
    FIELD_LINE_33_TOTAL_PAYMENTS,
    FIELD_LINE_34_REFUND,
    FIELD_LINE_37_AMOUNT_OWED,
)

# Every checkbox field this module maps (the four filing-status boxes).
CHECKBOX_FIELD_NAMES: tuple[str, ...] = (
    FIELD_FILING_STATUS_SINGLE,
    FIELD_FILING_STATUS_MFJ,
    FIELD_FILING_STATUS_MFS,
    FIELD_FILING_STATUS_HOH,
)

# All mapped field names (text + checkbox) — what the existence test iterates.
ALL_FIELD_NAMES: tuple[str, ...] = TEXT_FIELD_NAMES + CHECKBOX_FIELD_NAMES
