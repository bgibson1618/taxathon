"""F2 — W-2 ingest (deterministic parse) tests.

Proves: parsing the supplied fake W-2 fixture yields the exact expected wages/withholding/
identity; ``masked_ssn`` masks correctly and the raw SSN never leaks (repr / dump / pydantic
serialization); and inconsistent input (withholding > wages, negatives, missing fields, bad
SSN) is rejected by validation before the numbers could reach the tax math.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from app.w2.build_fixture import (
    FIXTURE_DATA,
    build_fixture,
)
from app.w2.extract import (
    FIELD_EMPLOYEE_ADDRESS,
    FIELD_EMPLOYEE_NAME,
    FIELD_EMPLOYEE_SSN,
    FIELD_EMPLOYER_NAME,
    FIELD_FED_WITHHOLDING,
    FIELD_WAGES,
    W2,
    W2ValidationError,
    extract_w2,
    extract_w2_from_bytes,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / "fixtures" / "fake_w2.pdf"

RAW_SSN = "123-45-6789"
RAW_SSN_DIGITS = "123456789"


@pytest.fixture(scope="module")
def fixture_pdf(tmp_path_factory) -> Path:
    """Use the committed fixture if present; otherwise build a fresh one (builder is the source).

    Either way the fixture under test is the real authored W-2 PDF — not a mock.
    """
    if FIXTURE_PATH.exists():
        return FIXTURE_PATH
    out = tmp_path_factory.mktemp("fixtures") / "fake_w2.pdf"
    return build_fixture(out)


def test_committed_fixture_exists():
    """A realistic fake W-2 fixture exists in the repo (success criterion #4)."""
    assert FIXTURE_PATH.exists(), "fixtures/fake_w2.pdf must be committed in the repo"
    assert FIXTURE_PATH.stat().st_size > 0


def test_parse_yields_exact_expected_fields(fixture_pdf):
    """Parsing the fixture yields the exact wages, withholding, and identity (criterion #1)."""
    w2 = extract_w2(fixture_pdf)

    assert w2.wages == 40000.00
    assert w2.fed_withholding == 3000.00
    assert w2.employee_name == "Alex Taxpayer"
    assert w2.employee_address == "100 Example Ave, Springfield, IL 62704"
    assert w2.employer_name == "Acme Widgets LLC"


def test_parse_matches_authored_fixture_values(fixture_pdf):
    """The parsed values match exactly what the builder authored — no drift between the two."""
    w2 = extract_w2(fixture_pdf)
    assert w2.wages == float(FIXTURE_DATA[FIELD_WAGES])
    assert w2.fed_withholding == float(FIXTURE_DATA[FIELD_FED_WITHHOLDING])
    assert w2.employee_name == FIXTURE_DATA[FIELD_EMPLOYEE_NAME]
    assert w2.employee_address == FIXTURE_DATA[FIELD_EMPLOYEE_ADDRESS]
    assert w2.employer_name == FIXTURE_DATA[FIELD_EMPLOYER_NAME]


def test_extract_from_bytes_equivalent_to_path(fixture_pdf):
    data = Path(fixture_pdf).read_bytes()
    w2_path = extract_w2(fixture_pdf)
    w2_bytes = extract_w2_from_bytes(data)
    assert w2_bytes.model_dump() == w2_path.model_dump()


def test_masked_ssn_masks_correctly(fixture_pdf):
    """masked_ssn shows only the last four digits as ***-**-6789 (criterion #3)."""
    w2 = extract_w2(fixture_pdf)
    assert w2.masked_ssn == "***-**-6789"
    assert w2.ssn_last4 == "6789"


def test_raw_ssn_never_leaks_in_repr_or_dump(fixture_pdf):
    """The raw SSN must not appear in repr, str, model_dump, or JSON serialization."""
    w2 = extract_w2(fixture_pdf)

    for rendered in (repr(w2), str(w2), str(w2.model_dump()), w2.model_dump_json()):
        assert RAW_SSN not in rendered
        assert RAW_SSN_DIGITS not in rendered

    # The model's public field set must not expose a raw 'ssn'.
    assert "ssn" not in w2.model_dump()
    assert "_ssn" not in w2.model_dump()
    # masked_ssn IS exposed (and is the only SSN representation that leaves the module).
    assert w2.model_dump()["masked_ssn"] == "***-**-6789"


def test_various_ssn_formats_normalize_and_mask():
    """SSNs with or without separators normalize to 9 digits and mask identically."""
    base = dict(
        wages=40000.0,
        fed_withholding=3000.0,
        employee_name="Alex Taxpayer",
        employee_address="100 Example Ave",
        employer_name="Acme Widgets LLC",
    )
    for raw in ("123-45-6789", "123456789", "123 45 6789"):
        w2 = W2(ssn=raw, **base)
        assert w2.masked_ssn == "***-**-6789"
        assert RAW_SSN_DIGITS not in repr(w2)


def test_rejects_withholding_greater_than_wages():
    """withholding > wages is rejected before use (criterion #2)."""
    with pytest.raises(W2ValidationError):
        W2(
            wages=40000.0,
            fed_withholding=45000.0,  # > wages
            employee_name="Alex Taxpayer",
            employee_address="100 Example Ave",
            employer_name="Acme Widgets LLC",
            ssn="123-45-6789",
        )


def test_rejects_negative_wages():
    with pytest.raises(W2ValidationError):
        W2(
            wages=-1.0,
            fed_withholding=0.0,
            employee_name="Alex Taxpayer",
            employee_address="100 Example Ave",
            employer_name="Acme Widgets LLC",
            ssn="123-45-6789",
        )


def test_rejects_negative_withholding():
    with pytest.raises(W2ValidationError):
        W2(
            wages=40000.0,
            fed_withholding=-50.0,
            employee_name="Alex Taxpayer",
            employee_address="100 Example Ave",
            employer_name="Acme Widgets LLC",
            ssn="123-45-6789",
        )


def test_rejects_bad_ssn():
    with pytest.raises(W2ValidationError):
        W2(
            wages=40000.0,
            fed_withholding=3000.0,
            employee_name="Alex Taxpayer",
            employee_address="100 Example Ave",
            employer_name="Acme Widgets LLC",
            ssn="12-3456",  # not 9 digits
        )


def test_rejects_blank_identity_field():
    with pytest.raises(W2ValidationError):
        W2(
            wages=40000.0,
            fed_withholding=3000.0,
            employee_name="   ",  # blank after strip
            employee_address="100 Example Ave",
            employer_name="Acme Widgets LLC",
            ssn="123-45-6789",
        )


def _build_w2_pdf_bytes(overrides: dict[str, str]) -> bytes:
    """Build a one-off W-2 PDF with field overrides, return its bytes (in-memory, no disk)."""
    import tempfile

    data = dict(FIXTURE_DATA)
    data.update(overrides)

    # Reuse the builder by patching FIXTURE_DATA-equivalent values via a temp build.
    from app.w2 import build_fixture as bf

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "w2.pdf"
        original = bf.FIXTURE_DATA
        try:
            bf.FIXTURE_DATA = data
            bf.build_fixture(out)
        finally:
            bf.FIXTURE_DATA = original
        return out.read_bytes()


def test_withholding_over_wages_rejected_via_pdf_round_trip():
    """An out-of-range W-2 PDF (withholding > wages) is rejected at parse time, not just at model build."""
    pdf_bytes = _build_w2_pdf_bytes(
        {FIELD_WAGES: "40000.00", FIELD_FED_WITHHOLDING: "50000.00"}
    )
    with pytest.raises(W2ValidationError):
        extract_w2_from_bytes(pdf_bytes)


def test_missing_identity_field_rejected_via_pdf_round_trip():
    pdf_bytes = _build_w2_pdf_bytes({FIELD_EMPLOYEE_NAME: ""})
    with pytest.raises(W2ValidationError):
        extract_w2_from_bytes(pdf_bytes)


def test_non_acroform_pdf_rejected():
    """A PDF with no AcroForm fields is rejected with a clear error (not a silent empty parse)."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    with pytest.raises(W2ValidationError):
        extract_w2_from_bytes(buf.getvalue())
