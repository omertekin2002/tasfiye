#!/usr/bin/env python3
"""
Extract the headline figures from each allocation report PDF into data/funds.json,
which is what the UI reads.

The reports come in two layouts with DIFFERENT decimal conventions, so the separator
must be decided per file or every figure silently lands orders of magnitude off:

  layout A (Turkish)  D-)Toplam Değer/Net Varlık Değeri : 2.236.787.193,97
  layout B (US)       E. TOPLAM DEĞER/NET VARLIK DEĞERİ : 881,038.37

Every parse is cross-checked with  NAV ≈ unitPrice × shareCount  (1% tolerance).
A row that fails the check is emitted with "verified": false rather than dropped or
quietly trusted — the UI renders those as unavailable.
"""
import json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "portfolio allocation")
DATA = os.path.join(ROOT, "data")

FOUNDERS = ["BULLS", "TERA", "PUSULA", "ATLAS", "HEDEF", "A1 CAPİTAL", "PARDUS"]


def text_of(path):
    return subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", path, "-"],
                          capture_output=True, timeout=90).stdout.decode("utf-8", "ignore")


# Turkish case folding, strictly 1 char -> 1 char so offsets stay aligned with the
# original text. Python's own .lower() expands 'İ' (U+0130) into two code points and
# maps 'I' to 'i' rather than 'ı', so label regexes silently fail on real filings.
_TR = str.maketrans({
    "İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s", "Ğ": "g", "ğ": "g",
    "Ü": "u", "ü": "u", "Ö": "o", "ö": "o", "Ç": "c", "ç": "c", "Â": "a", "â": "a",
})


def fold(s):
    """Lowercase + de-diacritic, preserving length so spans map back 1:1."""
    return s.translate(_TR).lower()


def num(raw):
    """Parse a figure, deciding the decimal separator from the token itself."""
    s = raw.strip().replace("%", "").replace(" ", "")
    if not s or not re.search(r"\d", s):
        return None
    # whichever separator appears LAST is the decimal one
    last_dot, last_comma = s.rfind("."), s.rfind(",")
    if last_dot == -1 and last_comma == -1:
        return float(s)
    if last_comma > last_dot:          # Turkish: 1.234.567,89
        s = s.replace(".", "").replace(",", ".")
    else:                               # US: 1,234,567.89
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def grab(txt, *patterns):
    """Search the folded text; read the number out of the ORIGINAL at the same span."""
    f = fold(txt)
    for p in patterns:
        m = re.search(p, f, re.M)
        if m:
            v = num(txt[m.start(1):m.end(1)])
            if v is not None:
                return v
    return None


# The two layouts label the same asset class differently, so both spellings are listed:
# the Turkish reports print "Yatırım Fonu" and misspell "Finansman Bonosu" as "Bonusu",
# the Excel ones print "Katılma Belgesi" and spell the finance bill correctly.
ALLOC_LABELS = {
    "Hisse Senedi": "equity", "Hazine Bonosu": "tbill", "Devlet Tahvili": "govbond",
    "Özel Sektör Tahvili": "corpbond", "Kira Sertifikaları": "sukuk",
    "Finansman Bonusu": "finbill", "Finansman Bonosu": "finbill",
    "Ters Repo": "reverserepo", "Repo": "repo",
    "Vadeli Mevduat": "deposit", "Mevduat": "deposit", "Katılma Hesabı": "participation",
    "Yatırım Fonu": "fund", "Katılma Belgesi": "fund",
    "Borsa Para Piyasası": "moneymarket",
}

# Section II lists the same securities twice: once as the percentage of the portfolio
# they make up, and again a few lines below as how fast they were traded. Both blocks
# name "Hisse Senedi", "Hazine Bonosu" and "Devlet Tahvili", so a scan of the whole
# document reads turnover as allocation. Bound the scan to the percentage block, which
# runs from its own heading to the turnover heading. The two layouts letter those
# headings differently (F-)/G-) in the Turkish reports, F./H. in the Excel ones), so
# match the heading text rather than the letter.
ALLOC_BLOCK_START = r"ortalama\s+portfoydeki\s+menkul\s+kiymetler\s+yuzdesi"
ALLOC_BLOCK_END = r"ortalama\s+portfoy\s+devir\s+hizi"


def alloc_block(txt):
    """Section II's percentage block, without its heading or the turnover heading."""
    lines = txt.splitlines()
    start = next((i for i, l in enumerate(lines)
                  if re.search(ALLOC_BLOCK_START, fold(l))), None)
    if start is None:
        return []
    end = next((i for i in range(start + 1, len(lines))
                if re.search(ALLOC_BLOCK_END, fold(lines[i]))), len(lines))
    return lines[start + 1:end]


def allocation(txt):
    out = {}
    folded = {fold(k): v for k, v in ALLOC_LABELS.items()}
    for line in alloc_block(txt):
        fl = fold(line)
        m = re.match(r"\s*(?:[a-z]\d?-\)|[a-z]\.|[a-z]\))?\s*([a-z /\-]+?)\s*:\s*([\d.,]+)\s*%?\s*$", fl)
        if not m:
            continue
        val = num(line[m.start(2):m.end(2)])
        # A fund that borrows to buy equity reports MORE than 100% in that line and
        # offsets it with a negative "TPP-TPP Borçlanma" (BRT 103,82 / -9,70;
        # PMP 117,82 / -19,52 — each set sums back to 100). The bound is only here to
        # reject a figure captured from the wrong column, so leave room for leverage.
        if val is None or not (0 <= val <= 200):
            continue
        label = m.group(1).strip()
        for k, slug in folded.items():
            if label.startswith(k):
                # a slug can still be written twice by label variants that share a
                # prefix ("Vadeli Mevduat TL" / "Vadeli Mevduat Döviz"); keep the larger
                out[slug] = max(out.get(slug, 0.0), round(val, 2))
                break
    return out


def founder_of(name):
    u = name.upper()
    for f in FOUNDERS:
        if u.startswith(f):
            return f.title().replace("A1 Capi̇tal", "A1 Capital")
    return "—"


def main():
    res = json.load(open(os.path.join(SRC, "_manifest", "results.json"), encoding="utf-8"))
    os.makedirs(DATA, exist_ok=True)
    rows, unverified = [], []

    for r in res:
        path = os.path.join(SRC, r["savedAs"])
        txt = text_of(path)
        # patterns are written against the FOLDED text: lowercase, no Turkish diacritics
        nav = grab(txt,
                   r"toplam\s+deger\s*/\s*net\s+varlik\s+degeri\s*:?\s*([\d.,]+)",
                   r"fon\s+toplam\s+degeri\s+([\d.,]+)")
        shares = grab(txt, r"katilma\s+payi\s+sayisi\s*:?\s*([\d.,]+)")
        unit = grab(txt,
                    r"(?:ay\s+sonu|haftalik|hafta\s+sonu)\s+(?:katilma\s+)?pay[i]?\s+fiyati\s*(?:\(tl\))?\s*:?\s*([\d.,]+)",
                    r"birim\s+pay\s+degeri\s*\(tr[ly]\)\s*:?\s*([\d.,]+)",
                    r"pay[i]?\s+fiyati\s*(?:\(tl\))?\s*:?\s*([\d.,]+)")

        verified = False
        if nav and shares and unit and shares > 0:
            verified = abs(nav - unit * shares) / nav < 0.01

        row = {
            "fundCode": r["fundCode"],
            "name": r["bulletinName"],
            "founder": founder_of(r["bulletinName"]),
            "nav": nav, "shares": shares, "unitPrice": unit,
            "verified": verified,
            "reportPeriod": r.get("pdrPeriod"),
            "reportDate": (r.get("pdrDate") or "")[:10] or None,
            "sourceUrl": r.get("sourceUrl"),
            "file": r["savedAs"],
            "allocation": allocation(txt),
            # the liquidation payout itself is not published on KAP
            "liquidationValue": None,
        }
        rows.append(row)
        if not verified:
            unverified.append(r["fundCode"])

    # Guard against manifest schema drift. Two records once carried publishDate /
    # reportPeriod instead of pdrDate / pdrPeriod, and every consumer silently rendered
    # them as unknown. A missing date must fail the build, not slip through as an em-dash.
    undated = [r["fundCode"] for r in rows if not r["reportDate"]]
    if undated:
        sys.exit(f"ERROR: no reportDate for {', '.join(undated)} — check the key names "
                 f"in _manifest/results.json (expected pdrDate)")

    rows.sort(key=lambda x: (-(x["nav"] or 0), x["fundCode"]))
    json.dump(rows, open(os.path.join(DATA, "funds.json"), "w"), ensure_ascii=False, indent=1)

    print(f"extracted {len(rows)} funds -> data/funds.json")
    print(f"  NAV parsed            : {sum(1 for r in rows if r['nav'])}")
    print(f"  unit price parsed     : {sum(1 for r in rows if r['unitPrice'])}")
    print(f"  allocation parsed     : {sum(1 for r in rows if r['allocation'])}")
    print(f"  cross-check verified  : {sum(1 for r in rows if r['verified'])}")
    if unverified:
        print(f"  NOT verified          : {', '.join(unverified)}")
    # an empty allocation means the percentage block's heading was not found, i.e. a
    # third layout has appeared; say so rather than shipping a row with no asset mix
    noalloc = [r["fundCode"] for r in rows if not r["allocation"]]
    if noalloc:
        print(f"  NO allocation block   : {', '.join(noalloc)}")


if __name__ == "__main__":
    main()
