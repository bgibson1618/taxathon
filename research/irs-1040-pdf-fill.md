# Research: Programmatically Filling the Official IRS Form 1040 (TY 2025) PDF in Python

> **Question:** Which Python approach most robustly fills the *official* IRS Form 1040 (tax year
> 2025) fillable PDF — library choice, field-name discovery/mapping, form availability, checkbox
> on-values, flattening, XFA/AcroForm gotchas — and what is the reportlab fallback? Optimize for a
> "must actually work" hackathon bar.
>
> **Date:** 2026-06-24. Verified empirically against the live IRS PDF with **pypdf 6.14.2 / Python 3.12.13**.

---

## Short Answer

**Use `pypdf` (>= 6.x) to fill the official IRS 2025 Form 1040 AcroForm, drop the embedded `/XFA`
entry, and FLATTEN the output.** This was verified end-to-end today against the real form:

- The **official 2025 Form 1040 is FINAL and downloadable right now** at
  `https://www.irs.gov/pub/irs-pdf/f1040.pdf` — page-1 text reads *"Form 1040 2025 U.S. Individual
  Income Tax Return … For the year Jan. 1–Dec. 31, 2025 … OMB No. 1545-0074"*, **no DRAFT
  watermark**. (Confidence: **high** — read the bytes.)
- It is a **hybrid AcroForm + XFA** form (229 fields: 126 text `/Tx`, 73 button `/Btn`). pypdf
  fills the **AcroForm** layer; the `/XFA` entry should be deleted so XFA-aware viewers don't
  override your values. (Confidence: **high** — inspected `/Root/AcroForm` keys.)
- Filling top-level line fields (`f1_NN[0]` on page 1, `f2_NN[0]` on page 2) and filing-status
  checkboxes works; with `flatten=True` the filled values are **burned into page content**
  (verified: filled strings appear in `page.extract_text()`), making the PDF render correctly in
  any viewer regardless of XFA/NeedAppearances support. (Confidence: **high** — round-tripped.)

**`pypdf` is the recommendation** because it is **pure-Python, zero system binaries**, which is the
deciding factor on Render free tier. `fillpdf`/`pypdftk` require the external **`pdftk` binary**
(not installable on the free tier without a custom buildpack) — confirmed `pdftk` is absent on this
machine. Keep a **reportlab "overlay or from-scratch 1040" generator** as a documented fallback in
case a specific field refuses to render, but it should not be the primary path.

---

## Sources

Primary / verified:

- Live form, inspected byte-for-byte today: `https://www.irs.gov/pub/irs-pdf/f1040.pdf`
- pypdf forms guide (stable): `https://pypdf.readthedocs.io/en/stable/user/forms.html`
- pypdf `PdfWriter` API: `https://pypdf.readthedocs.io/en/latest/modules/PdfWriter.html`
- pypdf appearance-generation limitations (autosize/center/unicode):
  `https://github.com/py-pdf/pypdf/issues/1919`, `.../issues/2731`, discussion `.../discussions/2770`
- pypdf CHANGELOG (6.3.0 flatten wrap/align, 6.4.2 flatten /Font fix, 6.5.0 FontDescriptor):
  `https://github.com/py-pdf/pypdf/blob/main/CHANGELOG.md`
- IRS draft-forms policy (don't rely on drafts): `https://www.irs.gov/draft-tax-forms`
- IRS About Form 1040: `https://www.irs.gov/forms-pubs/about-form-1040`

Secondary / context:

- OpenTaxForms (extracts XFA from IRS forms; evidence of XFA in 1040): `https://pypi.org/project/opentaxforms/`
- fillpdf / pypdftk require the pdftk binary: `https://github.com/Balonger/pdfformfields`,
  `https://gist.github.com/peteristhegreat/0bb67b74754f5cd3e31bf7ab7e8ad4c2`
- pdfrw checkbox `/Yes` vs `/Off` pattern (general AcroForm checkbox note):
  `https://blog.pythonlibrary.org/2018/05/22/filling-pdf-forms-with-python/`

---

## Findings

### 1. Form availability — RESOLVED, no caveat for 2025

The earlier worry ("2025 form may release late / as a draft") does **not** apply as of 2026-06-24.
`f1040.pdf` at the canonical IRS path is the **final TY2025** form. Verified:

| Check | Result |
| --- | --- |
| File | `PDF document, version 1.7`, 215 KB, 2 pages |
| Year on page 1 | `Form 1040 2025`, `For the year Jan. 1–Dec. 31, 2025` |
| OMB | `OMB No. 1545-0074` present |
| Draft watermark | **None** (text scan shows no "DRAFT") |

**Action:** vendor (commit) a pinned copy of `f1040.pdf` into the repo (e.g. `assets/f1040_2025.pdf`)
rather than fetching from irs.gov at runtime. The IRS occasionally re-posts a form (catalog/date
revision); pinning guarantees your field map stays valid and the demo never depends on irs.gov
being reachable from Render. (The form is a U.S. Government work / public domain — fine to vendor.)

> Note: companion forms also live & final at the same path style — `f1040s.pdf` (1040-SR). The
> instructions PDF (`i1040gi.pdf`) is dated Feb 25, 2026, consistent with a finalized 2025 cycle.

### 2. Form structure — hybrid AcroForm + XFA (the central gotcha)

`/Root/AcroForm` keys observed: `['/DA', '/DR', '/Fields', '/XFA', '/SigFlags']`.

- **`/XFA` is present.** XFA (XML Forms Architecture) is a parallel form definition. XFA-aware
  viewers (notably **Adobe Acrobat/Reader**) can render the XFA layer and **ignore the AcroForm
  values you set** — your numbers look filled in some viewers and blank in Acrobat. This is the #1
  way a "filled" IRS form silently appears empty.
- **Mitigations (use BOTH):**
  1. **Delete the `/XFA` key** from the writer's AcroForm before writing:
     `del writer._root_object["/AcroForm"][NameObject("/XFA")]` — verified the output then has no
     `/XFA`. This demotes the file to a plain AcroForm everywhere.
  2. **Flatten** (below) — removes the dependency on any interactive layer entirely.
- `NeedAppearances` was **not** set in the source.

### 3. Field naming — opaque, hierarchical, NO tooltips → you must build a map by hand

Field names are XFA-style dotted paths, e.g.:

```
topmostSubform[0].Page1[0].f1_01[0]     # page-1 text field #1
topmostSubform[0].Page2[0].f2_07[0]     # page-2 text field #7
topmostSubform[0].Page1[0].c1_1[0]      # page-1 checkbox #1
```

- `f1_NN` / `f2_NN` = **text** fields; `c1_NN` = **checkbox/button** fields.
- **Tooltips are absent** — every field's `/TU` (the human-readable description) is `None`. So the
  names alone do **not** tell you which field is "wages" vs "AGI" vs "withholding." You cannot infer
  the map; you must determine it once, by hand, and hard-code it.
- **Recommended mapping workflow (one-time):**
  1. Run `PdfReader("f1040_2025.pdf").get_fields()` to dump all 229 names (script provided below).
  2. Open the real PDF in a viewer, click each line you care about, and read its field name
     (Acrobat: hover/Prepare Form shows the name; or use pypdf to print the field's page + rect and
     correlate with `page.extract_text()` positions).
  3. Hard-code a dict mapping your **semantic** keys to field names, e.g.
     `LINE_1a_WAGES = "topmostSubform[0].Page1[0].f1_..."`. Pin it next to the vendored PDF and add
     a unit test that asserts every mapped name still exists in `get_fields()` (catches an IRS
     re-post that renumbers fields).
- **Scope guidance:** you only need to map the **guaranteed-core** lines + filing status:
  1a wages, 1z total wages, 9 total income, 11 AGI, 12 standard deduction, 15 taxable income,
  16 tax, 22, 24 total tax, 25a (W-2 withholding), 25d, 33 total payments, 34 overpayment/refund,
  37 amount owed, plus name/SSN/address and the 5 filing-status checkboxes. That's ~20 fields, not
  229.

### 4. Checkboxes — each has its OWN on-value (do NOT assume `/Yes`)

Every checkbox's "on" state is the **first** entry of its `/_States_` list; "off" is `/Off`.
Observed:

- Filing-status checkboxes `c1_1[0] … c1_7[0]` each have states `['/1', '/Off']` → set the value to
  the **NameObject `/1`** (not the string `"Yes"`, not `True`).
- Some grouped checkboxes use other on-values: `c1_8[*]` variants use `/1`, `/2`, `/3`, `/4`, `/5`;
  `c1_10[*]` uses `/1`, `/2`. **Always read `/_States_` per field** rather than hard-coding `/Yes`.
- Verified round-trip: setting `c1_1[0]` to `/1` and re-reading shows `/V == '/1'`. The common
  bug (writing the string `"Yes"`) leaves IRS checkboxes off because their on-state is `/1`.

pypdf usage for checkboxes is the same `update_page_form_field_values` call; pass the on-value
string (pypdf converts to a NameObject internally for `/Btn` fields):
`{"topmostSubform[0].Page1[0].c1_1[0]": "/1"}`.

### 5. Filling text + the page-iteration gotcha

Verified-working recipe (text + checkbox, both pages):

```python
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject

reader = PdfReader("assets/f1040_2025.pdf")
writer = PdfWriter()
writer.append(reader)

# 1) demote XFA so Acrobat doesn't override AcroForm values
acro = writer._root_object["/AcroForm"]
if "/XFA" in acro:
    del acro[NameObject("/XFA")]

values = {
    "topmostSubform[0].Page1[0].f1_01[0]": "Jane Q Public",   # text
    "topmostSubform[0].Page1[0].c1_1[0]": "/1",                # filing-status checkbox (on-value!)
    # ... your ~20 mapped core fields, page 1 and page 2 ...
}

# 2) apply across ALL pages — a page-1-only call misses page-2 fields
for page in writer.pages:
    writer.update_page_form_field_values(page, values, auto_regenerate=False, flatten=True)

with open("filled_1040.pdf", "wb") as fh:
    writer.write(fh)
```

Empirically confirmed:
- Top-level `f1_01` (page 1) and `f2_01` (page 2) fill and persist.
- You **must iterate `writer.pages`** — `update_page_form_field_values(writer.pages[0], …)` only
  touches widgets whose annotation is on the page object you pass.
- A handful of **deeply nested table subform** fields (e.g. `Table_Dependents[0].Row1[0].f1_32[0]`)
  did **not** take a value via the same call in this test. These are dependent-table cells —
  **outside the guaranteed core** and outside the recommended ~20-field map, so this does not affect
  the spine. If you later need them, fill them via the per-widget annotation directly. Flag: if you
  map a field and it won't fill, suspect it's a nested-subform/`/Kids` field.

### 6. Flattening — the robustness lever (verified)

`update_page_form_field_values(..., flatten=True)` makes pypdf **generate an appearance stream and
merge it into the page content**, then the values no longer depend on an interactive form layer.

Proof: after filling with `flatten=True`, the strings `FNAME`, `40000`, and a page-2 value all
appear in `PdfReader(out).pages[i].extract_text()` — i.e. they are now real page content, viewer
independent. Combined with dropping `/XFA`, this is the **most robust output for "must actually
work"**: it renders the same in Chrome's PDF viewer, Preview, Acrobat, and on print.

Tradeoff: a flattened PDF is **not editable** (fine — the user just downloads/prints it). If you
want it to remain editable, skip `flatten` but then you depend on `NeedAppearances` + viewer
behavior (riskier — see §7). For this project, **flatten**.

### 7. `NeedAppearances` ordering gotcha (only relevant if you DON'T flatten)

`auto_regenerate=False` (which you want, to avoid Acrobat's "save changes" prompt) **clears**
`/NeedAppearances`. Verified: calling `writer.set_need_appearances_writer(True)` **before**
`update_page_form_field_values(..., auto_regenerate=False)` results in `NeedAppearances=False` in
the output; calling it **after** the fill yields `NeedAppearances=True`. So in the non-flatten path
you must set NeedAppearances *last*. **Flattening avoids this entirely** — another reason to flatten.

### 8. Font / appearance-quality caveats (pypdf-generated appearances)

- The 1040's text widgets carry a fixed default appearance: `/HelveticaLTStd-Bold 8.00 Tf` — a
  **fixed 8 pt** font, **not** auto-size. This matters: pypdf's appearance generator has known
  trouble with **auto-size (font size 0)** fields (they can render blank until clicked). Because the
  1040 widgets specify 8 pt explicitly, the core line fields **avoid that failure mode**. (The
  AcroForm-level default `/DA` is `/Helv 0 Tf` but per-widget `/DA` overrides it.)
- pypdf may substitute base-14 **Helvetica** for the embedded `HelveticaLTStd-Bold` when it
  generates appearances. Visually near-identical at 8 pt; **exact** font fidelity is not guaranteed.
  Acceptable for a hackathon (numbers legible and correctly placed).
- Known pypdf appearance limitations to be aware of (mostly irrelevant to numeric money fields):
  text is rendered **left-aligned** even on center/right-aligned fields in some versions; some
  **Unicode** glyphs (accented chars) can mis-encode. 6.3.0+ added flatten wrap/align and 6.4.2/6.5.0
  fixed flatten `/Font` crashes — **use the latest 6.x** (6.14.2 tested). Your data is ASCII names +
  digits, so these limitations are low-risk. **Right-alignment of dollar amounts may not be perfect;
  values will still be correct and readable.**

### 9. Library comparison

| Library | Fills AcroForm | Checkboxes | Flatten | System deps | XFA-aware | Verdict for this project |
| --- | --- | --- | --- | --- | --- | --- |
| **pypdf** (6.x) | Yes (verified on 1040) | Yes (per-field on-value) | Yes (verified, burns to content) | **None (pure Python)** | No (you delete `/XFA`) | **RECOMMENDED** |
| fillpdf | Yes (wraps pdfrw + pdf2image) | Yes | Yes (via pdftk) | **pdftk + poppler** for some ops | No | Avoid — pdftk not on Render free tier |
| pypdftk / pdfformfields | Yes | Yes | Yes | **Requires `pdftk` binary** | No | Avoid — same deploy blocker |
| pdfrw | Yes (low-level) | Yes (`/Yes` pattern) | Manual/limited | None | No | Works but more manual than pypdf; pypdf is the maintained successor |
| reportlab | N/A (generates from scratch) | N/A | N/A | None | N/A | **Fallback generator** (see §10) |
| pdftk (CLI) | Yes (FDF) | Yes | Yes | **Binary install** | No | Robust but undeployable on free tier |

Empirical: `pdftk` is **not present** on this machine (`which pdftk` → not found). Render's free
tier runs a standard Python image; installing `pdftk` (a GCJ/Java-era binary) is painful. **pypdf's
pure-Python nature is the deciding factor.**

### 10. Fallback: generate a 1040-style PDF with reportlab

If a mapped field stubbornly won't render (e.g. an unexpected nested field, or a future IRS re-post
that breaks the map), the fallback is to **draw the values onto the form yourself**:

- **Overlay approach (best fallback):** render text at fixed (x, y) coordinates with `reportlab`
  onto a transparent canvas, then **merge that overlay over the original IRS PDF pages** with pypdf
  (`page.merge_page(overlay_page)`). This keeps the authentic IRS form background and sidesteps
  AcroForm/XFA entirely. Cost: you must measure ~20 (x, y) positions once (use the widget `/Rect`
  values from `get_fields()` to get exact coordinates — they're already in the PDF, so this is
  semi-automatable).
- **From-scratch approach:** build a 1040-*styled* document in reportlab. Faithfully reproducing the
  official layout is a lot of work and the result is **not the official form** — weaker against the
  PRD's "output the official IRS 2025 1040 PDF" requirement. Use only as a last resort.

**Tradeoff summary:** overlay-on-official > flatten-AcroForm only on rendering fidelity, but
flatten-AcroForm is less manual and uses real field semantics. Recommend **flatten-AcroForm as
primary, overlay-on-official as the documented fallback**; treat full from-scratch reportlab as the
break-glass option.

### 11. Reproducible verification scripts

All run with `pypdf 6.14.2` on Python 3.12. Inspect names/states:

```python
from pypdf import PdfReader
r = PdfReader("assets/f1040_2025.pdf")
for name, f in r.get_fields().items():
    if f.get("/FT") == "/Btn":
        print(name, f.get("/_States_"))   # checkbox on-values
    else:
        print(name, f.get("/FT"))         # text fields
```

Working artifacts produced during this research (in the session scratchpad, not committed):
`out_flat.pdf` (XFA-present + flatten, values in page text), `out_noxfa.pdf` (XFA-dropped),
`o2.pdf` (XFA-dropped + flatten — the recommended recipe, `FLATNAME` confirmed in page text).

---

## Risks and Unknowns

- **Acrobat rendering not visually confirmed.** I verified values persist and (when flattened)
  appear in extracted page text, which is strong evidence of correct rendering, but I could not open
  a GUI viewer in this environment. **Resolve before demo:** open the flattened output in
  Chrome's built-in PDF viewer AND Acrobat Reader and eyeball the dollar amounts. (Confidence the
  flatten path renders everywhere: **high**; confidence on exact glyph/alignment fidelity:
  **medium**.)
- **Field map is hand-built and unversioned by the IRS.** If the IRS re-posts `f1040.pdf` with
  renumbered fields, a map keyed to `f1_NN` could silently shift. **Mitigation:** vendor the PDF +
  add a test asserting each mapped name still exists. (Confidence the current map approach is
  correct: **high**; that names are stable across re-posts: **low** — hence vendor + test.)
- **Right-alignment of money fields** may render left/oddly via pypdf's appearance generator in some
  cases (documented limitation). Numbers will be correct and legible; placement may not be
  pixel-perfect. (Confidence: **medium**.)
- **Dependent-table / nested subform fields** did not fill via the standard call in testing. Out of
  guaranteed-core scope, but if "best-effort" lines later require them, budget extra time. (Confidence
  they're awkward: **high**; that you'll need them for v1: **low**.)
- **Exact semantic field map not produced here.** I confirmed the *mechanism*, naming scheme,
  checkbox on-values, and page split, but did not enumerate "f1_NN == wages". That click-through
  mapping is a ~30-minute task for the implementer (or use the `/Rect`-coordinate correlation).

---

## Recommendation (smallest decision set for the orchestrator)

1. **PDF-fill tooling = `pypdf` (latest 6.x, tested 6.14.2). No pdftk/system binaries.** Add `pypdf`
   to `pyproject.toml`. This unblocks the NFR/architecture "PDF-fill tooling = TBD" open item.
2. **Vendor the official `f1040.pdf` into the repo** (e.g. `assets/f1040_2025.pdf`) — it is final
   TY2025 and public domain. Do not fetch from irs.gov at runtime.
3. **Output recipe = drop `/XFA` + `update_page_form_field_values(..., auto_regenerate=False,
   flatten=True)` iterating all pages.** This is the verified "must actually work" path.
4. **Build a ~20-entry semantic→field-name map once, hard-code it, and unit-test that each name
   exists** in `get_fields()`. Read each checkbox's `/_States_` for its on-value; never hard-code
   `/Yes` (the 1040 uses `/1`).
5. **Keep reportlab overlay-on-official as the documented fallback;** do not build it preemptively.
6. **Before the demo:** open the flattened output in Chrome PDF viewer and Acrobat Reader to confirm
   visual rendering (the one thing not verifiable headless here).
