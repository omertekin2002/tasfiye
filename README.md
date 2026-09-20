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
  extract_holdings.py           PDFs -> data/holdings.json (every security held)
portfolio allocation/
  INDEX.csv                     ← start here: one row per fund
  <CODE>_*.pdf                  47 allocation reports
  _manifest/                    provenance and crawler state
data/funds.json                 extracted figures, read by the UI
data/holdings.json              every individual security held, by fund
data/holdings.csv               same, flat
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
| 2026 week 35–37 | 35 | weekly — late August to mid-September |
| 2026 month 8 | 12 | monthly — August |

The weekly filers are the freshest data in the set, some within days of liquidation.
Every row carries a report date; `extract_fund_data.py` fails loudly if one does not.

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

A single static page built to `DESIGN.md`, in two tabs. No charts — the brief calls for
values, not performance history.

**Fonlar** — a ledger of the 47 funds, sortable, filterable by founder, with a per-row
detail panel showing the portfolio breakdown as text and links back to the KAP filing and
the source PDF.

**Portföy Bileşenleri** — what those funds actually hold, from `data/holdings.json`: one
hairline table per asset class, searchable across issuer, ticker, fund code and fund name,
with a class filter. Entries are collapsed to one row per issuer and carry **no amounts** —
only the instrument types, how many separate issues there are, and which of the 47 funds
hold it. `holdings.json` is fetched lazily the first time the tab is opened, so the fund
ledger costs nothing extra.

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
`verified` flag; all 47 currently pass. The asset mix has its own traps — see
*Reading the allocation block* under `extract_holdings.py`, which is where the cross-check
that found them lives.

---

## `scripts/extract_holdings.py`

Reads the same 47 PDFs and writes `data/holdings.json` — **1,061 individual holdings**,
one row per security per fund. Scope is the four asset classes that are a claim on an
issuer; repo, derivatives, deposits, participation accounts, precious metals, FX and
VİOP collateral are dropped. **No amounts**: this answers what is held, not how much.

| class | holdings | distinct |
|---|---|---|
| equities | 630 | 169 tickers |
| debt securities | 311 | 62 issuers |
| lease certificates (sukuk) | 82 | 14 issuers |
| units in other funds | 38 | 26 funds |

Unlike `extract_fund_data.py`, which only needs labelled figures from the summary block,
this one has to read the portfolio table itself — and that table is not a table. It is
read from `pdftotext -bbox-layout` word coordinates, because column geometry is the only
thing separating a ticker from an issuer name.

Three problems worth knowing about before touching this code:

1. **Issuer names wrap mid-word.** The Infleks reports give the issuer a 39pt column and
   break inside words: `FAKTORİN` / `G`, `GAYRİMEN` / `KUL`. Geometry cannot tell that
   apart from an ordinary wrap (`SANAYİ VE` / `TİCARET`) — both lines fill the column.
   The fix is lexical: a mid-word break leaves a non-word on *both* sides, so the two
   lines are glued only when neither side is a known word. The vocabulary is harvested
   from the reports themselves, using the one thing wrapping guarantees — a break can
   only split the *last* token of a line, so every other token is a whole word.
2. **Headings and continuation lines look alike.** Both are short, left-aligned and
   carry no figures. They are told apart by position: a heading only ever follows a
   `GRUP TOPLAMI`, a continuation only ever follows a holding.
3. **Two layouts, and the second is not a variant.** 8 funds file an Excel-generated
   report with lettered sections (`A) HİSSE SENETLERİ` … `N) KATILMA BELGELERİ`) and
   clean word-wrapped names. It gets its own parser; the layout is auto-detected.

Issuers are spelled differently from one report to the next (`LIDER FAKTORING A.Ş` /
`LİDER FAKTORİNG A.Ş.`), so rows are merged on the ISIN mnemonic rather than on the text,
and the other spellings are kept in `issuerAlt`. Two cases go further than spelling:

- **A misprint the ISIN contradicts** is dropped, not recorded as a variant. `MISPRINT`
  holds the two known ones: PRY files `TRFKYTRE2613` — a Kayatur Filo Kiralama bill —
  under `HAZİNE`, and PPT files `TRFPNSTA2630` — Pınar Süt paper — under
  `PINAR ENTEGRE ET VE UN SANAYI A.Ş`. The ISIN wins in both.
- **A sukuk naming the originator is not a misprint.** Some reports name the asset-leasing
  company (`HEDEF VARLIK KİRALAMA A.Ş.`) and others the company the certificates are
  raised for (`HAVER FARMA İLAÇ A.Ş`). Both are legitimate readings, so both are kept.

**Verification.** Extracted holdings are cross-checked against the allocation percentages
in `data/funds.json`: for each fund and class, a non-zero percentage must coincide with at
least one holding. 186 of 188 checks agree, and both exceptions are real rather than parse
errors: BMU reports 1.25% `Yatırım Fonu` because section II is a weekly *average* and its
portfolio table holds no fund units on the snapshot date, and TLV files its single fund
unit (TPKGY, `TRYTALP00036`) under a `TÜREV İŞLEMLER` heading. Row counts were also checked
directly against the PDFs for both layouts (BTJ 5 equities + 1 fund unit; TLY 54 equity lots).

**Not resolved.** 12 of the 26 held funds are identified only by code and founder
(`T3B`, `THF`, `TMV`, `HMV`, `MTL`, `ABG`, `BAC`, `GCD`, `KHD`, `KVR`, `LAI`, `PFS`).
Most reports print a fund unit as a bare code; those 12 are not among the 47 in
`_manifest/funds.json`, and KAP exposes no code→name endpoint (its fund directory is an
SPA, and TEFAS is bot-protected).

### Reading the allocation block

`extract_fund_data.py` takes the asset mix from section II. Two things about that section
are easy to get wrong, and the cross-check above caught both:

- **Bound the scan to the percentage block.** Section II names the same securities twice:
  once as the share of the portfolio they make up (`…Ortalama Portföydeki Menkul Kıymetler
  Yüzdesi`) and again as how fast they were traded (`…Ortalama Portföy Devir Hızı`). Both
  blocks list `Hisse Senedi`, `Hazine Bonosu` and `Devlet Tahvili`, so a scan of the whole
  document reads turnover as allocation — HPH's percentage block says `Hazine Bonosu : 0,00`
  while its turnover block says `0,03`. `alloc_block()` cuts the text at those two headings
  and reads only what lies between. The layouts letter them differently (`F-)` / `G-)` in
  the Turkish reports, `F.` / `H.` in the Excel ones), so the bound matches the heading
  *text*, not the letter. An empty allocation now means the heading was not found — i.e. a
  third layout has appeared — and the run says so.
- **A percentage may exceed 100.** A fund that borrows to buy equity reports over 100% on
  that line and offsets it with a negative `TPP-TPP Borçlanma`: BRT `103,82` / `-9,70` and
  PMP `117,82` / `-19,52`, each set summing back to 100. Bounding the accepted range at
  100% silently dropped those two figures.

Both layouts also have to be listed in `ALLOC_LABELS`: the Excel reports say
`Katılma Belgesi` where the Turkish ones say `Yatırım Fonu`, and spell `Finansman Bonosu`
correctly where the Turkish ones misspell it `Bonusu`.

---

## Status

The ledger is built and reads live from the extracted data. The liquidation values
themselves are still outstanding: per the SPK decision they are set by the appointed
custodian banks and are not published on KAP, so every fund shows *Beklemede* until
those figures are available. Wiring them in means adding a `liquidationValue` to each
row in `data/funds.json`; the UI already renders it the moment it is not null.
