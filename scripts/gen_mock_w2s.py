"""Generate a set of mock W-2 PDFs in the app's AcroForm format for testing.

The app parses ONLY this fixture format (named AcroForm fields) — not arbitrary
W-2 PDFs/images. This produces several clearly-FAKE W-2s with varied wages,
withholding, and identities so you can exercise refund / owe / bracket cases on
the live app. Each is round-tripped through the real parser and its single-filer
result is printed.

Run: ``PYTHONPATH=. uv run python scripts/gen_mock_w2s.py``
"""
from __future__ import annotations

from pathlib import Path

import app.w2.build_fixture as bf
from app.tax.compute import FilingStatus, compute_return
from app.w2.extract import (
    FIELD_EMPLOYEE_ADDRESS,
    FIELD_EMPLOYEE_NAME,
    FIELD_EMPLOYEE_SSN,
    FIELD_EMPLOYER_NAME,
    FIELD_FED_WITHHOLDING,
    FIELD_WAGES,
    extract_w2,
)

OUT = Path("mock_w2s")
OUT.mkdir(exist_ok=True)


def w2(name, ssn, wages, wh, addr, employer):
    return {
        FIELD_EMPLOYEE_NAME: name,
        FIELD_EMPLOYEE_SSN: ssn,
        FIELD_EMPLOYEE_ADDRESS: addr,
        FIELD_EMPLOYER_NAME: employer,
        FIELD_WAGES: f"{wages:.2f}",
        FIELD_FED_WITHHOLDING: f"{wh:.2f}",
    }


SCENARIOS = [
    ("w2_alex_single_40k.pdf", "the demo profile — modest refund",
     w2("Alex Taxpayer", "123-45-6789", 40000, 3000, "100 Example Ave, Springfield, IL 62704", "Acme Widgets LLC")),
    ("w2_jordan_owes.pdf", "low withholding -> OWES money",
     w2("Jordan Rivera", "222-33-4444", 40000, 1500, "42 Maple St, Dayton, OH 45402", "Northwind Trading Co")),
    ("w2_sam_big_refund.pdf", "high withholding -> big refund",
     w2("Sam Lee", "333-22-1111", 40000, 5000, "9 Birch Ln, Boise, ID 83702", "Globex Foods Inc")),
    ("w2_priya_higher_bracket.pdf", "higher wages -> a different bracket",
     w2("Priya Nadeem", "444-55-6666", 52000, 5500, "7 Cedar Ct, Austin, TX 78701", "Initech Systems")),
]

print(f"Writing {len(SCENARIOS)} mock W-2s to {OUT.resolve()}/\n")
for filename, blurb, data in SCENARIOS:
    bf.FIXTURE_DATA = data  # override the module global the builder reads
    path = bf.build_fixture(OUT / filename)
    parsed = extract_w2(str(path))  # round-trip through the REAL parser
    c = compute_return(wages=parsed.wages, withholding=parsed.fed_withholding, filing_status=FilingStatus.SINGLE)
    result = f"refund ${c.refund}" if c.refund else f"OWES ${c.amount_owed}"
    print(f"  {filename:32s} {parsed.masked_ssn}  wages ${int(parsed.wages):>6,}  wh ${int(parsed.fed_withholding):>5,}  (single -> {result})  [{blurb}]")

print("\nAll generated W-2s parsed cleanly. Filing status is chosen in the chat, so any of these can")
print("also be tested as married/HoH to see the deduction + tax recompute.")
