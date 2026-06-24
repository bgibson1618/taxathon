"""W-2 ingest (F2) — deterministic AcroForm parse of the authored fake W-2 fixture.

The user uploads a (fake) W-2 PDF; ``extract.py`` reads its named AcroForm fields into a
validated :class:`~app.w2.extract.W2` model. The SSN is parsed code-side and only ever
exposed through ``masked_ssn`` — the raw SSN never lands in a log, trace, or LLM prompt.

``build_fixture.py`` authors ``fixtures/fake_w2.pdf`` (a realistic FAKE W-2 for a ~$40k
single earner) so the deterministic parse is ~100% reliable. Vision/OCR extraction is a
documented stretch (see DECISION_LOG D5), deliberately out of v1.
"""

from app.w2.extract import W2, W2ValidationError, extract_w2, extract_w2_from_bytes

__all__ = [
    "W2",
    "W2ValidationError",
    "extract_w2",
    "extract_w2_from_bytes",
]
