"""F1 — 2025 tax computation engine.

Deterministic 2025 Form 1040 math. The LLM never does arithmetic: every number
on the return is computed here in plain Python with ``Decimal`` and whole-dollar
rounding.

Public surface:
- :class:`app.tax.compute.ComputedReturn` — the typed 1040 line result.
- :func:`app.tax.compute.compute_return` — wages + withholding + filing status -> result.
- :class:`app.tax.constants_2025.FilingStatus` — the four supported statuses.
"""

from app.tax.compute import ComputedReturn, compute_return
from app.tax.constants_2025 import FilingStatus

__all__ = ["ComputedReturn", "compute_return", "FilingStatus"]
