# tasfiye

Tracking the liquidation of investment funds that SPK ordered wound down in
**Bülteni 2026/60 (17.09.2026)**, and closed to buy/sell on TEFAS the same day.

The eventual UI shows one number per fund — its current liquidation value. No charts, no
historical performance. What lives here today is the groundwork: the fund list, the
identity mapping to KAP, and the last published portfolio allocation for each fund.

**Scope:** this repo covers the **47 funds that publish a portfolio allocation report**.
Funds that do not publish one are out of scope and are not tracked here. Performance
reports are not treated as a substitute — only the actual `Portföy Dağılım Raporu`
counts as an allocation source.

---

## Layout

```
DESIGN.md                       design system for the UI
README.md                       this file
scripts/
  fetch_allocation_reports.py   fetches the reports from KAP
  extract_fund_data.py          PDFs -> data/funds.json
portfolio allocation/
  INDEX.csv                     ← start here: one row per fund
  <CODE>_*.pdf                  47 allocation reports
  _manifest/                    provenance and crawler state
data/funds.json                 extracted figures, read by the UI
index.html, styles.css, app.js  the tracker page, served at the site root
ui/index.html                   redirect, keeps the old /ui/ link working
```

---

## `DESIGN.md`

The visual system for the tracker UI, adapted from Stripe's design language. Chosen for
its tabular-figure typography and hairline-table treatment — the product is a ledger, so
numbers had to come first.

The file is the upstream Stripe analysis verbatim, followed by a **Project Adaptation**
section that overrides it for this use case: no gradient mesh (a marketing-hero device),
heavier weight for the money tier, a semantic palette for liquidation status, a mandatory
"as of" date on every value, and a rule that unknown values render as an em-dash rather
than `0,00`. Where the two sections disagree, the adaptation section wins.

---

## `portfolio allocation/`

### `INDEX.csv`
The index of everything collected. One row per fund: `fundCode`, `fundName`,
`reportType`, `reportDate`, `pdrPeriod`, `file`, `sourceUrl`.

Every row is a real `Portföy Dağılım Raporu` pulled from that fund's own KAP filing, and
`sourceUrl` links back to the disclosure it came from.

**Recency.** All 47 reports were published in **September 2026**, between 02.09 and
17.09.2026 — the last of them on the day of the liquidation decision itself. They come in
two reporting cadences, which matters when comparing funds side by side:

| period filed | funds | covers |
|---|---|---|
| 2026 week 35–37 | 34 | weekly — late August to mid-September |
| 2026 month 8 | 11 | monthly — August |
| period not set by KAP | 2 | August 2026 per the filing itself |

The weekly filers are the freshest data in the set, some within days of liquidation. The
two undated rows are not missing data — KAP simply left the period fields unpopulated on
those filings; `pdrPeriod` reflects what the API returned rather than a value inferred
from the filename.

### `<CODE>_*.pdf`
The 47 reports, named `<fundCode>_<original KAP filename>`. All are validated,
non-truncated PDFs.

---

## `portfolio allocation/_manifest/`

Provenance for the run. Nothing here is needed at runtime; keep it so the numbers can be
traced back to KAP.

| file | what it is |
|---|---|
| `funds.json` | **The canonical fund list.** Each fund's bulletin name resolved to its KAP identity: `fundCode`, `kapTitle`, `permaLink`, `fundOid`, `fundId`. Everything else keys off this. |
| `results.json` | Same content as `INDEX.csv`, as JSON, in bulletin order. |
| `crawl_state.json` | The crawler's resume state — one record per fund. Delete a fund's entry to force a re-fetch. |

---

## `scripts/fetch_allocation_reports.py`

Rebuilds `portfolio allocation/` from scratch:

```bash
python3 scripts/fetch_allocation_reports.py
```

Single-threaded with a 3s delay between requests and exponential backoff — KAP rate-limits
aggressively and will start returning **429** under any real concurrency. It is
**resumable**: completed funds are skipped and anything unfinished is retried on the next
run, so it is safe to re-run after an interruption.

Per fund it takes the newest `Portföy Dağılım Raporu` and saves its attachment, falling
back to the rendered disclosure when the report is filed inline instead.

### KAP API notes

Undocumented endpoints, worked out by reading the site's JS bundles. Three traps cost real
time and are worth knowing before touching this code:

1. `POST /tr/api/disclosure/funds/byCriteria` — dates **must** be ISO `YYYY-MM-DD`.
   Passing `dd.MM.yyyy` returns an opaque upstream **500**, not a validation error.
   `fundTypeList` must also be non-empty (`["YF"]`), and the window can't exceed ~1 year.
2. `GET /tr/api/file/download/<objId>` — returns a **Java-serialised byte array**, not a
   PDF. The real file is the slice from `%PDF` to the last `%%EOF`.
3. `GET /tr/api/notification/attachment-detail/<disclosureIndex>` — `attachmentCount: 0`
   is meaningful, not an error: it means the report was filed inline.

Also useful: `GET /tr/api/BildirimPdf/<disclosureIndex>` renders any disclosure as a PDF,
and `GET /tr/api/batch-news/file-by-year/<fundOid>/<year>` returns a fund's entire year of
disclosures as one document.

**TEFAS is not a viable source** for these funds — it sits behind bot protection, and
`FonAnaliz.aspx` 404s for all of them now that they're delisted.

---

## The tracker

Live at **https://omertekin2002.github.io/tasfiye/**, served by GitHub Pages straight from
the repo root. Locally:

```bash
python3 scripts/extract_fund_data.py     # PDFs  -> data/funds.json
python3 -m http.server 8777              # then open http://localhost:8777/
```

`.nojekyll` is required, not cosmetic: Pages runs Jekyll by default, which skips any
directory beginning with an underscore — that would make `portfolio allocation/_manifest/`
unreachable on the live site.

A single static page built to `DESIGN.md`: a ledger of the 47 funds, sortable, filterable
by founder, with a per-row detail panel showing the portfolio breakdown as text and links
back to the KAP filing and the source PDF. No charts — the brief calls for values, not
performance history.

The **Tasfiye Değeri** column is an em-dash and a *Beklemede* pill for every fund, because
liquidation amounts are set by the custodian banks and are not published on KAP. The
headline figure is therefore labelled *son bildirilen toplam portföy değeri* — last
reported, not liquidation value — and carries the date range of the underlying reports.

## `scripts/extract_fund_data.py`

Reads the 47 PDFs and writes `data/funds.json`. Two things it handles that are easy to get
silently wrong:

- **Mixed decimal conventions.** The reports come in two layouts, one Turkish
  (`2.236.787.193,97`) and one US (`881,038.37`). The separator is decided per figure from
  whichever appears last, not assumed globally.
- **Turkish case folding.** Python lowercases `İ` into two code points and maps `I` to `i`
  rather than `ı`, so naive label regexes miss real filings. All matching runs against a
  folded copy of the text with a strict 1:1 character map, and figures are read from the
  original at the same offsets.

Every row is cross-checked with `NAV ≈ unitPrice × shares` (1% tolerance) and carries a
`verified` flag; all 47 currently pass.

---

## Status

The ledger is built and reads live from the extracted data. The liquidation values
themselves are still outstanding: per the SPK decision they are set by the appointed
custodian banks and are not published on KAP, so every fund shows *Beklemede* until
those figures are available. Wiring them in means adding a `liquidationValue` to each
row in `data/funds.json`; the UI already renders it the moment it is not null.
