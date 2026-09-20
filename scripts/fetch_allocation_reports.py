#!/usr/bin/env python3
"""
Fetch the last Portföy Dağılım Raporu (portfolio allocation report) for every fund in
portfolio allocation/_manifest/funds.json.

Scope: only funds that actually publish an allocation report are in scope. Performance
reports are not a substitute and are never collected here.

Pipeline per fund (all on kap.org.tr):
  1. POST /tr/api/disclosure/funds/byCriteria   -> that fund's disclosures for a window
  2. newest row whose subject contains "Portföy Dağılım"  -> disclosureIndex
  3. GET  /tr/api/notification/attachment-detail/<disclosureIndex> -> attachments[].objId
  4. GET  /tr/api/file/download/<objId>  -> Java-serialised byte[] wrapping the PDF;
     the PDF is the slice from b"%PDF" to the last b"%%EOF".
  A report filed inline rather than as an attachment is saved via
  GET /tr/api/BildirimPdf/<disclosureIndex>.

KAP rate-limits aggressively (HTTP 429), so this runs single-threaded with a delay
between every request and exponential backoff. It is resumable: completed funds are
recorded in crawl_state.json and skipped on re-run.
"""
import json, os, re, time, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "portfolio allocation")
MAN = os.path.join(OUT, "_manifest")
STATE = os.path.join(MAN, "crawl_state.json")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
HDRS = {"User-Agent": UA, "Accept-Language": "tr"}
BASE = "https://www.kap.org.tr/tr/api"

DELAY = 3.0
MAX_RETRY = 5


def _req(url, payload=None, timeout=60):
    for attempt in range(MAX_RETRY):
        try:
            if payload is None:
                r = urllib.request.Request(url, headers=HDRS)
            else:
                h = dict(HDRS); h["Content-Type"] = "application/json"
                r = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=h)
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                data = resp.read()
            time.sleep(DELAY)
            return data
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < MAX_RETRY - 1:
                back = DELAY * (2 ** (attempt + 1))
                print(f"      {e.code}; backing off {back:.0f}s", flush=True)
                time.sleep(back)
                continue
            raise
        except Exception:
            if attempt < MAX_RETRY - 1:
                time.sleep(DELAY * (2 ** (attempt + 1)))
                continue
            raise
    raise RuntimeError("retries exhausted")


def _key(row):
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2}):(\d{2})", row.get("publishDate", ""))
    return tuple(int(x) for x in (m.group(3), m.group(2), m.group(1),
                                  m.group(4), m.group(5), m.group(6))) if m else (0,) * 6


def disclosures(fund_oid):
    """All 2026 disclosures for a fund; falls back to 2025 if 2026 is empty."""
    for frm, to in (("2026-01-01", "2026-10-10"), ("2025-01-01", "2025-12-31")):
        rows = json.loads(_req(f"{BASE}/disclosure/funds/byCriteria",
                               {"fromDate": frm, "toDate": to, "fundTypeList": ["YF"],
                                "mkkMemberOidList": [], "fundOidList": [fund_oid],
                                "passiveFundOidList": [], "disclosureClass": "", "isLate": "",
                                "subjectList": [], "discIndex": [], "fromSrc": False,
                                "srcCategory": ""}))
        if rows:
            return rows
    return []


def attachments(disclosure_index):
    """[(objId, fileName)] for a disclosure, parsed from the detail payload."""
    raw = _req(f"{BASE}/notification/attachment-detail/{disclosure_index}").decode("utf-8", "ignore")
    try:
        found = []
        for node in json.loads(raw):
            for a in (node.get("attachments") or []):
                if a.get("objId"):
                    found.append((a["objId"], a.get("fileName") or f"{disclosure_index}.pdf"))
        return found
    except Exception:
        return [(m.group(1), m.group(2)) for m in
                re.finditer(r'"objId"\s*:\s*"([^"]+)"\s*,\s*"fileName"\s*:\s*"([^"]+)"', raw)]


def fetch_attachment_pdf(obj_id):
    raw = _req(f"{BASE}/file/download/{obj_id}")
    i, j = raw.find(b"%PDF"), raw.rfind(b"%%EOF")
    if i < 0 or j < 0:
        raise ValueError(f"no PDF payload (head={raw[:12]!r})")
    return raw[i:j + 5]


def save(name, blob):
    with open(os.path.join(OUT, name), "wb") as fh:
        fh.write(blob)
    return name, len(blob)


def handle(f, rec):
    rows = disclosures(f["fundOid"])
    hits = [r for r in rows if "Portföy Dağılım" in (r.get("subject") or "")]
    if not hits:
        rec.update(status="no_report", note="no Portföy Dağılım Raporu filed")
        return

    code = f["fundCode"]
    pdr = max(hits, key=_key)
    rec.update(pdrDate=pdr.get("publishDate"), pdrIndex=pdr["disclosureIndex"],
               pdrPeriod=f"{pdr.get('year')}/{pdr.get('period')}",
               sourceUrl=f"https://www.kap.org.tr/tr/Bildirim/{pdr['disclosureIndex']}")

    if (pdr.get("attachmentCount") or 0) > 0:
        atts = attachments(pdr["disclosureIndex"])
        if atts:
            obj_id, fname = atts[0]
            saved, n = save(f"{code}_{fname}", fetch_attachment_pdf(obj_id))
            rec.update(status="ok", reportType="Portföy Dağılım Raporu", savedAs=saved, bytes=n)
            return

    # filed inline rather than as an attachment
    saved, n = save(f"{code}_PDR_{pdr['disclosureIndex']}.pdf",
                    _req(f"{BASE}/BildirimPdf/{pdr['disclosureIndex']}"))
    rec.update(status="ok", reportType="Portföy Dağılım Raporu (inline)", savedAs=saved, bytes=n)


def main():
    funds = json.load(open(os.path.join(MAN, "funds.json"), encoding="utf-8"))
    state = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}
    state = {k: v for k, v in state.items() if v.get("status") == "ok"}
    os.makedirs(OUT, exist_ok=True)

    for n, f in enumerate(funds, 1):
        code = f["fundCode"]
        if code in state:
            continue
        print(f"[{n:3d}/{len(funds)}] {code} …", flush=True)
        rec = {"fundCode": code, "bulletinName": f["bulletinName"], "kapTitle": f["kapTitle"]}
        try:
            handle(f, rec)
        except Exception as e:
            rec.update(status="error", note=f"{type(e).__name__}: {e}")
        print(f"          {rec.get('status')}  {rec.get('savedAs') or rec.get('note','')}", flush=True)
        state[code] = rec
        with open(STATE, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=1)

    from collections import Counter
    print("\nDONE " + "  ".join(f"{k}={v}" for k, v in
                                Counter(v.get("status") for v in state.values()).most_common()), flush=True)


if __name__ == "__main__":
    main()
