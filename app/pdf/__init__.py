"""Filled official 2025 Form 1040 PDF (F3).

Maps the F1 computed return + F2 taxpayer identity onto the **vendored** official IRS
2025 Form 1040 (``assets/f1040_2025.pdf``), drops the ``/XFA`` layer, sets the
filing-status checkbox on-value, and flattens — producing a viewer-independent,
genuinely completed 1040 as ``bytes`` for download.

Public surface:
- :func:`app.pdf.fill.fill_1040` — ``(computed, identity, filing_status) -> bytes``.
- :mod:`app.pdf.field_map` — the hand-built semantic -> AcroForm field-name map.
"""

from app.pdf.fill import fill_1040

__all__ = ["fill_1040"]
