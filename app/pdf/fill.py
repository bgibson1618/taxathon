"""F3 — fill the official 2025 Form 1040 PDF from a computed return + identity.

``fill_1040`` takes the F1 :class:`~app.tax.compute.ComputedReturn` (the deterministic
math) plus the F2 :class:`~app.w2.extract.W2` (taxpayer identity) and a filing status,
maps them onto the **vendored** official IRS 2025 Form 1040 via the field map, and
returns the flattened PDF as ``bytes`` for download.

The verified "must actually work" recipe (research/irs-1040-pdf-fill.md, DECISION_LOG D2):

1. Load the vendored ``assets/f1040_2025.pdf`` (never fetched at runtime).
2. Delete ``/XFA`` from ``writer.root_object['/AcroForm']`` (the PUBLIC ``root_object``)
   so XFA-aware viewers (Acrobat) cannot override the AcroForm values we set.
3. Set the mapped text fields and the single filing-status checkbox to its on-value ``/1``.
4. ``update_page_form_field_values`` across **all** pages with
   ``auto_regenerate=False, flatten=True`` — flattening burns the values into page
   content so they render in any viewer regardless of XFA/NeedAppearances support.

Privacy: the raw SSN never leaves the W-2 module, so the SSN field is filled with the
**masked** SSN (``***-**-1234``) — never the raw digits.

Money is rendered in whole dollars (the 1040 is filed in whole dollars; the engine
already rounds). Zero-valued refund/amount-owed cells are left blank — a real 1040
shows only the one that applies, not "0" in both.
"""

from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject

from app.pdf import field_map as fm
from app.tax.compute import ComputedReturn
from app.tax.constants_2025 import FilingStatus
from app.w2.extract import W2

# The vendored official 2025 Form 1040 (committed; never fetched at runtime).
_REPO_ROOT = Path(__file__).resolve().parents[2]
VENDORED_FORM_PATH = _REPO_ROOT / "assets" / "f1040_2025.pdf"


def _whole_dollars(amount: Decimal) -> str:
    """Render a whole-dollar amount as a plain integer string (e.g. ``Decimal('1234')`` -> ``'1234'``).

    The engine already rounds to whole dollars, so this just drops any fractional part
    defensively and formats without a thousands separator (the form's narrow money cells
    read most cleanly without commas).
    """
    return str(int(amount.to_integral_value()))


def _split_name(full_name: str) -> tuple[str, str]:
    """Split a full name into (first + middle initial, last name).

    Best-effort: everything before the final whitespace-separated token is the
    first/middle portion, the final token is the last name. A single-token name fills
    the first-name field and leaves last name blank.
    """
    parts = full_name.strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return " ".join(parts[:-1]), parts[-1]


def _split_address(address: str) -> dict[str, str]:
    """Best-effort split of a one-line address into street / city / state / zip cells.

    Expects the fixture form ``"100 Example Ave, Springfield, IL 62704"``. Falls back to
    putting the whole string in the street field if the shape is unexpected — the form
    still carries the address, just less granular.
    """
    out = {"street": address.strip(), "city": "", "state": "", "zip": ""}
    parts = [p.strip() for p in address.split(",")]
    if len(parts) >= 3:
        out["street"] = parts[0]
        out["city"] = parts[1]
        # Last comma-part is "STATE ZIP" (e.g. "IL 62704").
        state_zip = parts[-1].split()
        if len(state_zip) >= 2:
            out["state"] = state_zip[0]
            out["zip"] = state_zip[-1]
        elif len(state_zip) == 1:
            out["state"] = state_zip[0]
    return out


def _build_field_values(
    computed: ComputedReturn,
    identity: W2,
    filing_status: FilingStatus,
) -> dict[str, str]:
    """Build the ``{field_name: value}`` dict applied to the form.

    Identity comes from the W-2 (SSN masked); numeric cells come from the computed
    return. Zero refund / zero amount-owed cells are omitted (left blank) so only the
    applicable one is shown.
    """
    first, last = _split_name(identity.employee_name)
    addr = _split_address(identity.employee_address)

    values: dict[str, str] = {
        # Identity / header.
        fm.FIELD_FIRST_NAME: first,
        fm.FIELD_LAST_NAME: last,
        fm.FIELD_SSN: identity.masked_ssn,  # masked — raw SSN never leaves the W-2 module
        fm.FIELD_ADDRESS_STREET: addr["street"],
        fm.FIELD_ADDRESS_CITY: addr["city"],
        fm.FIELD_ADDRESS_STATE: addr["state"],
        fm.FIELD_ADDRESS_ZIP: addr["zip"],
        # Numeric lines.
        fm.FIELD_LINE_1A_WAGES: _whole_dollars(computed.wages),
        fm.FIELD_LINE_1Z_TOTAL_WAGES: _whole_dollars(computed.wages),
        fm.FIELD_LINE_9_TOTAL_INCOME: _whole_dollars(computed.total_income),
        fm.FIELD_LINE_11A_AGI: _whole_dollars(computed.agi),
        fm.FIELD_LINE_11B_AGI: _whole_dollars(computed.agi),
        fm.FIELD_LINE_12_STANDARD_DEDUCTION: _whole_dollars(computed.standard_deduction),
        fm.FIELD_LINE_15_TAXABLE_INCOME: _whole_dollars(computed.taxable_income),
        fm.FIELD_LINE_16_TAX: _whole_dollars(computed.tax),
        fm.FIELD_LINE_24_TOTAL_TAX: _whole_dollars(computed.total_tax),
        fm.FIELD_LINE_25A_WITHHOLDING: _whole_dollars(computed.withholding),
        fm.FIELD_LINE_25D_TOTAL_WITHHOLDING: _whole_dollars(computed.withholding),
        fm.FIELD_LINE_33_TOTAL_PAYMENTS: _whole_dollars(computed.total_payments),
    }

    # Optional apartment field (the fixture has none); only fill if present-ish — here
    # always blank, but keeping the mapping explicit documents the field exists.

    # Refund XOR amount-owed: show only the applicable one.
    if computed.refund > Decimal("0"):
        values[fm.FIELD_LINE_34_REFUND] = _whole_dollars(computed.refund)
    if computed.amount_owed > Decimal("0"):
        values[fm.FIELD_LINE_37_AMOUNT_OWED] = _whole_dollars(computed.amount_owed)

    # Filing-status checkbox: set exactly the one for this status to its on-value.
    checkbox = fm.FILING_STATUS_CHECKBOX[filing_status]
    values[checkbox] = fm.CHECKBOX_ON_VALUE

    return values


def fill_1040(
    computed: ComputedReturn,
    identity: W2,
    filing_status: FilingStatus,
) -> bytes:
    """Fill the vendored official 2025 Form 1040 and return the flattened PDF bytes.

    Args:
        computed: the F1 computed 2025 return (every line already rounded to whole dollars).
        identity: the F2 parsed W-2 supplying taxpayer name / address / masked SSN.
        filing_status: the status whose checkbox is set (must match ``computed.filing_status``;
            the caller is responsible for keeping them consistent — the value used for the
            checkbox is this argument).

    Returns:
        ``bytes`` of a flattened, XFA-free official 2025 Form 1040 with identity + the
        computed numeric lines populated. Renders identically in any PDF viewer.
    """
    reader = PdfReader(str(VENDORED_FORM_PATH))
    writer = PdfWriter()
    writer.append(reader)

    # Demote the XFA layer so XFA-aware viewers (Acrobat) honor our AcroForm values.
    acro = writer.root_object["/AcroForm"]
    if "/XFA" in acro:
        del acro[NameObject("/XFA")]

    values = _build_field_values(computed, identity, filing_status)

    # Apply across ALL pages: update_page_form_field_values only touches widgets on the
    # page object passed in, and our fields span page 1 (identity/header) and page 2.
    for page in writer.pages:
        writer.update_page_form_field_values(
            page, values, auto_regenerate=False, flatten=True
        )

    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
