"""Deterministic W-2 ingest (F2).

Reads the named AcroForm fields of a fake W-2 PDF (authored by ``build_fixture.py``) into a
validated :class:`W2` pydantic model. Everything is deterministic — no LLM, no OCR — so the
parse is ~100% reliable for the fixture we control (ARCHITECTURE "Deterministic Spine";
DECISION_LOG D5).

Privacy contract: the raw SSN is parsed code-side and is **never** rendered by ``repr``,
``str``, logging, the observation trace, or an LLM prompt. Callers read :attr:`W2.masked_ssn`
(e.g. ``***-**-6789``). The raw digits live only in the private ``_ssn`` attribute.

Validation contract (rejected *before* the numbers reach the tax math):
  * wages and withholding must be present and non-negative;
  * federal withholding may not exceed wages;
  * required identity fields (name, address, employer) must be non-empty;
  * the SSN must be 9 digits (after stripping separators).
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    computed_field,
    field_validator,
    model_validator,
)
from pypdf import PdfReader

# AcroForm field names authored by build_fixture.py. Kept here as the single source of truth
# so the fixture builder and the parser cannot drift apart.
FIELD_WAGES = "box1_wages"
FIELD_FED_WITHHOLDING = "box2_fed_withholding"
FIELD_EMPLOYEE_NAME = "employee_name"
FIELD_EMPLOYEE_SSN = "employee_ssn"
FIELD_EMPLOYEE_ADDRESS = "employee_address"
FIELD_EMPLOYER_NAME = "employer_name"

_SSN_DIGITS = re.compile(r"\D")


class W2ValidationError(ValueError):
    """Raised when a W-2 fails validation (missing fields, bad ranges, or inconsistency).

    A distinct type so callers / guardrails can catch W-2 problems specifically and surface a
    calm, guiding message instead of a raw stack trace.
    """


def _mask_ssn(raw: str) -> str:
    """Mask a 9-digit SSN as ``***-**-1234`` (last four shown). Never logs the raw value."""
    digits = _SSN_DIGITS.sub("", raw or "")
    if len(digits) != 9:
        # Should not happen post-validation, but never leak raw digits if it does.
        return "***-**-****"
    return f"***-**-{digits[-4:]}"


class W2(BaseModel):
    """A validated W-2.

    The raw SSN is stored in the private ``_ssn`` attribute (excluded from the model's public
    surface). Public access is only via :attr:`masked_ssn`. ``repr`` / serialization therefore
    cannot leak the raw SSN.
    """

    model_config = ConfigDict(frozen=True)

    wages: float = Field(..., ge=0, description="Box 1 — wages, tips, other comp (USD).")
    fed_withholding: float = Field(
        ..., ge=0, description="Box 2 — federal income tax withheld (USD)."
    )
    employee_name: str = Field(..., min_length=1, description="Employee full name.")
    employee_address: str = Field(..., min_length=1, description="Employee mailing address.")
    employer_name: str = Field(..., min_length=1, description="Employer name.")

    # Raw SSN held privately; never part of the model's public fields / dump.
    _ssn: str = ""

    def __init__(self, /, ssn: str = "", **data: Any) -> None:
        digits = _SSN_DIGITS.sub("", ssn or "")
        if len(digits) != 9:
            raise W2ValidationError(
                "SSN must contain exactly 9 digits (got a value that is not a 9-digit SSN)."
            )
        # Present a single, clean exception type to callers: any pydantic constraint failure
        # (range, blank field, consistency) surfaces as W2ValidationError, not the raw
        # pydantic ValidationError. The first error's message is preserved for the trace.
        try:
            super().__init__(**data)
        except ValidationError as exc:
            first = exc.errors()[0] if exc.errors() else {}
            msg = first.get("msg", "W-2 failed validation.")
            raise W2ValidationError(msg) from exc
        object.__setattr__(self, "_ssn", digits)

    @field_validator("employee_name", "employee_address", "employer_name")
    @classmethod
    def _strip_and_require(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise W2ValidationError("Required identity field is missing or blank.")
        return v

    @model_validator(mode="after")
    def _check_consistency(self) -> "W2":
        if self.fed_withholding > self.wages:
            raise W2ValidationError(
                "Federal withholding cannot exceed wages "
                f"(withholding {self.fed_withholding} > wages {self.wages})."
            )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def masked_ssn(self) -> str:
        """The SSN masked as ``***-**-1234`` — the only SSN representation that ever leaves here."""
        return _mask_ssn(self._ssn)

    @property
    def ssn_last4(self) -> str:
        """Last four digits of the SSN (for PDF identity fields). Not the full SSN."""
        return self._ssn[-4:] if len(self._ssn) == 9 else ""

    def __repr__(self) -> str:  # pragma: no cover - trivial, but proves no raw SSN leaks
        return (
            f"W2(employee_name={self.employee_name!r}, wages={self.wages!r}, "
            f"fed_withholding={self.fed_withholding!r}, masked_ssn={self.masked_ssn!r})"
        )


def _parse_money(raw: str | None, field: str) -> float:
    if raw is None or str(raw).strip() == "":
        raise W2ValidationError(f"W-2 is missing required numeric field '{field}'.")
    cleaned = str(raw).replace("$", "").replace(",", "").strip()
    try:
        value = float(cleaned)
    except ValueError as exc:
        raise W2ValidationError(
            f"W-2 field '{field}' is not a valid number: {raw!r}."
        ) from exc
    if value < 0:
        raise W2ValidationError(f"W-2 field '{field}' must be non-negative (got {value}).")
    return value


def _read_fields(pdf_bytes: bytes) -> dict[str, str]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    fields = reader.get_form_text_fields()
    if not fields:
        raise W2ValidationError(
            "Uploaded W-2 has no readable AcroForm fields — expected a fillable W-2 PDF."
        )
    return {k: ("" if v is None else str(v)) for k, v in fields.items()}


def extract_w2_from_bytes(pdf_bytes: bytes) -> W2:
    """Parse W-2 PDF bytes into a validated :class:`W2`. Raises :class:`W2ValidationError`."""
    fields = _read_fields(pdf_bytes)

    missing = [
        name
        for name in (FIELD_EMPLOYEE_NAME, FIELD_EMPLOYEE_SSN, FIELD_EMPLOYEE_ADDRESS, FIELD_EMPLOYER_NAME)
        if not str(fields.get(name, "")).strip()
    ]
    if missing:
        raise W2ValidationError(
            f"W-2 is missing required identity field(s): {', '.join(missing)}."
        )

    return W2(
        wages=_parse_money(fields.get(FIELD_WAGES), FIELD_WAGES),
        fed_withholding=_parse_money(fields.get(FIELD_FED_WITHHOLDING), FIELD_FED_WITHHOLDING),
        employee_name=fields[FIELD_EMPLOYEE_NAME],
        employee_address=fields[FIELD_EMPLOYEE_ADDRESS],
        employer_name=fields[FIELD_EMPLOYER_NAME],
        ssn=fields[FIELD_EMPLOYEE_SSN],
    )


def extract_w2(path: str | Path) -> W2:
    """Parse a W-2 PDF at ``path`` into a validated :class:`W2`."""
    data = Path(path).read_bytes()
    return extract_w2_from_bytes(data)
