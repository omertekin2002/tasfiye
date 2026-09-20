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
  fetch_allocation_reports.py   the crawler that produced everything below
portfolio allocation/
  INDEX.csv                     ← start here: one row per fund
  <CODE>_*.pdf                  47 allocation reports
  _manifest/                    provenance and crawler state
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

## Status

Groundwork is complete; the UI is not built yet. The liquidation values themselves are not
here — per the SPK decision, those come from the appointed custodians, not from KAP.
