"""Author the fake W-2 fixture (F2).

Generates ``fixtures/fake_w2.pdf`` — a realistic but clearly **FAKE** W-2 for a ~$40,000/year
single earner — using only pypdf (no system binaries, no reportlab). The page draws W-2-style
labels via a content stream *and* carries named AcroForm text fields holding the data, which
``extract.py`` parses deterministically.

The fixture is intentionally fake: SSN ``123-45-6789``, name "Alex Taxpayer", wages 40000.00,
federal withholding 3000.00 (see DECISION_LOG D5 — keeping a controlled fixture makes the parse
~100% reliable and keeps the SSN code-side).

Run directly to (re)generate the fixture::

    uv run python -m app.w2.build_fixture
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from app.w2.extract import (
    FIELD_EMPLOYEE_ADDRESS,
    FIELD_EMPLOYEE_NAME,
    FIELD_EMPLOYEE_SSN,
    FIELD_EMPLOYER_NAME,
    FIELD_FED_WITHHOLDING,
    FIELD_WAGES,
)

# Clearly-fake data for a ~$40k single earner. Centralized so tests can import the exact
# expected values (no magic numbers duplicated across files).
FIXTURE_DATA: dict[str, str] = {
    FIELD_WAGES: "40000.00",
    FIELD_FED_WITHHOLDING: "3000.00",
    FIELD_EMPLOYEE_NAME: "Alex Taxpayer",
    FIELD_EMPLOYEE_SSN: "123-45-6789",
    FIELD_EMPLOYEE_ADDRESS: "100 Example Ave, Springfield, IL 62704",
    FIELD_EMPLOYER_NAME: "Acme Widgets LLC",
}

# Default output location, resolved relative to the repo root (this file is app/w2/...).
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = _REPO_ROOT / "fixtures" / "fake_w2.pdf"

_PAGE_WIDTH = 612.0
_PAGE_HEIGHT = 792.0


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _draw_label(x: float, y: float, text: str, size: int = 10) -> bytes:
    # Standard Helvetica encodes Latin-1; map anything outside it (e.g. an em-dash) to '?'
    # so the drawn label can never crash the builder. Field *values* are stored separately.
    safe = _escape_pdf_text(text).encode("latin-1", "replace").decode("latin-1")
    return f"BT /F1 {size} Tf {x:.1f} {y:.1f} Td ({safe}) Tj ET\n".encode("latin-1")


def _build_content_stream() -> bytes:
    """Draw a W-2-looking layout (title + box labels) so the PDF reads as a real form."""
    parts: list[bytes] = [
        _draw_label(72, 752, "Form W-2  Wage and Tax Statement  2025", size=14),
        _draw_label(72, 736, "*** FAKE / SAMPLE - NOT A REAL W-2 - FOR DEMO USE ONLY ***", size=9),
        # Identity block
        _draw_label(72, 700, "Employee name:", size=10),
        _draw_label(72, 680, "Employee SSN (Box a):", size=10),
        _draw_label(72, 660, "Employee address:", size=10),
        _draw_label(72, 640, "Employer name (Box c):", size=10),
        # Wage / withholding boxes
        _draw_label(72, 600, "Box 1  Wages, tips, other compensation:", size=10),
        _draw_label(72, 580, "Box 2  Federal income tax withheld:", size=10),
    ]
    return b"".join(parts)


def _add_text_field(
    writer: PdfWriter,
    page: DictionaryObject,
    fields: list,
    name: str,
    value: str,
    rect: tuple[float, float, float, float],
) -> None:
    field = DictionaryObject()
    field[NameObject("/FT")] = NameObject("/Tx")
    field[NameObject("/T")] = TextStringObject(name)
    field[NameObject("/V")] = TextStringObject(value)
    field[NameObject("/Subtype")] = NameObject("/Widget")
    field[NameObject("/Rect")] = ArrayObject([FloatObject(c) for c in rect])
    field[NameObject("/F")] = NumberObject(4)  # Print flag
    field[NameObject("/DA")] = TextStringObject("/F1 10 Tf 0 g")
    field[NameObject("/P")] = page.indirect_reference
    ref = writer._add_object(field)
    fields.append(ref)
    if NameObject("/Annots") not in page:
        page[NameObject("/Annots")] = ArrayObject()
    page[NameObject("/Annots")].append(ref)


def build_fixture(output_path: str | Path = DEFAULT_OUTPUT) -> Path:
    """Build the fake W-2 PDF at ``output_path`` and return the path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    writer = PdfWriter()
    page = writer.add_blank_page(width=_PAGE_WIDTH, height=_PAGE_HEIGHT)

    # Content stream (drawn labels).
    content = DecodedStreamObject()
    content.set_data(_build_content_stream())
    page[NameObject("/Contents")] = writer._add_object(content)

    # Font resource for both the drawn text and the field appearances.
    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    font_ref = writer._add_object(font)
    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = font_ref
    resources = DictionaryObject()
    resources[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = resources

    # Named AcroForm fields placed next to their labels.
    fields: list = []
    _add_text_field(writer, page, fields, FIELD_EMPLOYEE_NAME, FIXTURE_DATA[FIELD_EMPLOYEE_NAME], (200, 696, 540, 712))
    _add_text_field(writer, page, fields, FIELD_EMPLOYEE_SSN, FIXTURE_DATA[FIELD_EMPLOYEE_SSN], (220, 676, 540, 692))
    _add_text_field(writer, page, fields, FIELD_EMPLOYEE_ADDRESS, FIXTURE_DATA[FIELD_EMPLOYEE_ADDRESS], (200, 656, 540, 672))
    _add_text_field(writer, page, fields, FIELD_EMPLOYER_NAME, FIXTURE_DATA[FIELD_EMPLOYER_NAME], (220, 636, 540, 652))
    _add_text_field(writer, page, fields, FIELD_WAGES, FIXTURE_DATA[FIELD_WAGES], (320, 596, 480, 612))
    _add_text_field(writer, page, fields, FIELD_FED_WITHHOLDING, FIXTURE_DATA[FIELD_FED_WITHHOLDING], (320, 576, 480, 592))

    # AcroForm dictionary tying the fields together, with a default resources/appearance config.
    acro = DictionaryObject()
    acro[NameObject("/Fields")] = ArrayObject(fields)
    acro[NameObject("/NeedAppearances")] = BooleanObject(True)
    acro[NameObject("/DA")] = TextStringObject("/F1 10 Tf 0 g")
    dr = DictionaryObject()
    dr_fonts = DictionaryObject()
    dr_fonts[NameObject("/F1")] = font_ref
    dr[NameObject("/Font")] = dr_fonts
    acro[NameObject("/DR")] = dr
    writer._root_object[NameObject("/AcroForm")] = writer._add_object(acro)

    with open(output_path, "wb") as fh:
        writer.write(fh)
    return output_path


if __name__ == "__main__":
    path = build_fixture()
    print(f"Wrote fake W-2 fixture: {path}")
