#!/usr/bin/env python3
"""
Extract every individual security held by the 47 funds into data/holdings.json.

Scope is deliberately narrow — only the four asset classes that represent a claim
on an issuer: equities, debt securities, lease certificates (sukuk) and units in
other funds. Derivatives, deposits, repo, FX and precious metals are dropped.
No amounts are carried: this answers "what is held", not "how much".

Two report layouts, neither of which is a real table:

  Infleks (39 funds)  wide column grid; issuer names wrap INSIDE a 39pt column and
                      the wrap can fall mid-word ("FAKTORİN" / "G")
  Excel   (8 funds)   lettered sections (A) HİSSE SENETLERİ …); names wrap on word
                      boundaries, so they come out clean

Both are read from pdftotext -bbox-layout word coordinates rather than -layout text,
because the column geometry is the only thing that separates ticker from issuer.
"""
import json, os, re, subprocess, sys, xml.etree.ElementTree as ET
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(ROOT, "portfolio allocation")
DATA = os.path.join(ROOT, "data")

ISIN_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{9}[0-9]$')
NUM_RE  = re.compile(r'^-?[\d.,]+%?$')
JUNK_RE = re.compile(r'^\d{2}/\d{2}/\d{2,4}$|^-?[\d.,]+$|^%|^/$')
SEC_RE  = re.compile(r'^[A-ZÇĞİÖŞÜ]\)$')


# ───────────────────────── pdf words ─────────────────────────
def words(path):
    xml = subprocess.run(["pdftotext", "-bbox-layout", "-enc", "UTF-8", path, "-"],
                         capture_output=True).stdout.decode("utf-8", "ignore")
    xml = xml.replace('xmlns="http://www.w3.org/1999/xhtml"', '')
    xml = re.sub(r'^.*?<body>', '<body>', xml, flags=re.S)
    xml = xml[:xml.rindex('</body>') + 7]
    out = []
    for pi, page in enumerate(ET.fromstring(xml).iter("page")):
        for w in page.iter("word"):
            t = (w.text or "").strip()
            if t:
                out.append((pi, float(w.get("xMin")), float(w.get("xMax")),
                            float(w.get("yMin")), t))
    return out


def lines(ws, ytol=3.0):
    """Group words into visual lines (same baseline), left to right."""
    out = []
    for pi in sorted({w[0] for w in ws}):
        cur = []
        for w in sorted([x for x in ws if x[0] == pi], key=lambda z: (z[3], z[1])):
            if cur and abs(w[3] - cur[0][3]) > ytol:
                out.append(sorted(cur, key=lambda z: z[1])); cur = []
            cur.append(w)
        if cur: out.append(sorted(cur, key=lambda z: z[1]))
    return out


def txt(l): return ' '.join(w[4] for w in l)


# ───────────────────── layout A: Infleks ─────────────────────
def parse_infleks(path):
    ls = lines(words(path))
    s = e = None
    for i, l in enumerate(ls):
        t = txt(l)
        if s is None and t.startswith("III-FON PORTFÖY"): s = i
        if s is not None and t.startswith("IV-FON TOPLAM"): e = i; break
    if s is None: return []
    ls = ls[s + 1:e]

    cols = None; section = sub = None; cur = None; mode = "head"; recs = []

    def cell(ws, x0, x1):
        sel = [w for w in ws if x0 <= w[1] < x1 and not JUNK_RE.match(w[4])]
        return ([w[4] for w in sel], sel[0][1], sel[-1][2]) if sel else None

    for ws in ls:
        t = txt(ws)
        # the column header block repeats on every page and defines the geometry
        if any(w[4] == "İHRAÇCI" for w in ws):
            dov = next((w[1] for w in ws if w[4] == "DÖVİZ"), None)
            iss = next(w[1] for w in ws if w[4] == "İHRAÇCI")
            vad = next((w[1] for w in ws if w[4] == "VADE"), None)
            cols = ((dov - 4) if dov else iss - 20, iss - 6, (vad - 4) if vad else iss + 45)
            continue
        if "MENKUL" in t and "KIYMET" in t: continue
        if re.match(r'^(VADEYE|CİNSİ|GÜN|KALAN|DÖVİZ)\b', t): continue
        if not cols: continue

        code_x1, iss_x0, iss_x1 = cols
        has_num = any(w[1] > 330 and NUM_RE.match(w[4]) for w in ws)
        if not has_num and ws[0][1] > 250: continue          # page running head

        if t.startswith("GRUP TOPLAMI") or t.startswith("FON PORTFÖY DEĞERİ"):
            cur = None; mode = "head"; continue

        code_cell = cell(ws, 0, code_x1)
        iss_cell  = cell(ws, iss_x0, iss_x1)
        isins     = [w[4] for w in ws if ISIN_RE.match(w[4])]

        if has_num and code_cell:                             # a holding
            cur = {"section": section, "sub": sub, "code": [code_cell],
                   "isin": list(isins), "iss": [iss_cell] if iss_cell else []}
            recs.append(cur); mode = "row"; continue

        # headings only ever follow a group total, never a holding
        if mode == "head" and not re.search(r'\d', t) and \
           all(w[2] < iss_x1 + 8 for w in ws) and len(t) <= 45:
            if t.isupper(): section, sub = t, None
            else: sub = t
            continue

        if cur is not None:                                   # wrapped continuation
            if iss_cell:  cur["iss"].append(iss_cell)
            if code_cell: cur["code"].append(code_cell)
            cur["isin"] += isins
    return recs


# ────────────────────── layout B: Excel ──────────────────────
def parse_excel(path):
    ls = lines(words(path))
    s = None
    for i, l in enumerate(ls):
        if "FON PORTFÖY DEĞERİ TABLOSU" in txt(l): s = i; break
    if s is None: return []
    cols = None; section = None; cur = None; recs = []
    for ws in ls[s + 1:]:
        t = txt(ws)
        if "İhraççı" in t and "Nominal" in t:
            cols = (next(w[1] for w in ws if w[4] == "İhraççı") - 6,
                    next(w[1] for w in ws if w[4] == "Nominal") - 6)
            continue
        if not cols: continue
        iss_x0, iss_x1 = cols
        if t.startswith("4-") or t.startswith("FON TOPLAM DEĞERİ"): break
        if SEC_RE.match(ws[0][4]):
            section = ' '.join(w[4] for w in ws[1:]); cur = None; continue
        if ws[0][4].startswith("TOPLAM"): cur = None; continue
        iw = [w[4] for w in ws if iss_x0 <= w[1] < iss_x1]
        cw = [w[4] for w in ws if w[1] < iss_x0]
        if cw and any(w[1] >= iss_x1 and NUM_RE.match(w[4]) for w in ws):
            cur = {"section": section, "sub": None, "code": cw, "iss": list(iw), "isin": []}
            recs.append(cur)
        elif cur is not None and iw:
            cur["iss"] += iw
    return recs


# ─────────────── rebuilding names broken by wrapping ───────────────
_TR = str.maketrans({"İ":"i","I":"i","ı":"i","Ş":"s","ş":"s","Ğ":"g","ğ":"g","Ü":"u",
                     "ü":"u","Ö":"o","ö":"o","Ç":"c","ç":"c","Â":"a","â":"a"})
def fold(t): return t.translate(_TR).lower().strip('.,')

SEED = '''A.Ş. A.Ş A.O. A.O T.A.Ş. T.A.S. AŞ VE İLE SANAYİ SANAYİİ SANAYI TİCARET TİC
TICARET HOLDİNG YATIRIM YATIRIMLARI MENKUL DEĞERLER FAKTORİNG FAKTORING VARLIK KİRALAMA
KIRALAMA YÖNETİM YÖNETİMİ YONETIM YÖNETIMI BANKASI BANKA BANK KATILIM GAYRİMENKUL
ORTAKLIĞI FİNANSMAN FİNANSMANI FINANSMANI FINANSMAN FİNANS FİNANSAL FINANSAL ENERJİ
ENERJİSİ ÜRETİM TEKNOLOJİ TEKNOLOJİLERİ GIDA TARIM TARİM İNŞAAT LOJİSTİK TURİZM ELEKTRİK
ELEKTRONİK ÇİMENTO OTOMOTİV DIŞ İÇ PAZARLAMA SİGORTA HAVA YOLLARI PORTFÖY FON FONU
BİRİNCİ İKİNCİ SÜT MAMÜLLERİ MAMULLERI ENTEGRE ÇELİK BORU BOYA FABRİKALARI ARAŞTIRMA
GELİŞTİRME HİZMETLERİ İŞLETMELERİ TAŞIMACILIK DENİZCİLİK MADENCİLİK TEKSTİL SERAMİK
FARMA İLAÇ PETROLCÜLÜK YAYINCILIK OTOKİRALAMA SERVİS ARAÇ SUKUK GERİ DÖNÜŞÜM EKOENERJİ
GÜNEŞ ENDÜSTRİ ATIK ÇEVRE AGRO KONUT ALFA ULUSAL İSTANBUL OSMANLI GELECEK DÜNYA EMİR
HAZİNE MALİYE BAKANLIĞI TREASURY TURKISH FİLO ET UN SERBEST VADELİ KISA PARA PİYASASI
İPOTEK ÖZEL SEKTÖR KİRA SERTİFİKALARI DEMİR ÇELIK YAPI BİLİŞİM İLETİŞİM MAĞAZALARI
PERAKENDE SATIŞ ALIM ANONİM ŞİRKETİ LİMİTED GRUP FAKTÖRİNG ELEKTROLİTİK KURUMSAL
KUYUMCULUK İŞLETMECİLİK KARABÜK BAKIR METAL GİYİM SAĞLIK FABRİKASI FABRİKALARI
OTOMOBİL TÜRK TÜRKİYE TURKIYE PETROL RAFİNERİLERİ RAFINERILERI TELEKOMÜNİKASYON
MAĞAZACILIK MAĞAZALAR MARKETLER SERMAYESİ GİRİŞİM YENİLENEBİLİR SAVUNMA TEKNOLOJİLERİ
BİRACILIK MALT PROJE TAAHHÜT BİYO BİO ŞİRKETLER ŞEKER ECZA DEPOSU ECZACIBAŞI İLAÇ
SINAİ FİNANSAL HAVALİMANLARI HAVA TAŞIMACILIĞI PETROKİMYA POLİMER PLASTİK KALIP
TEKNİK YAZILIM BİLGİSAYAR SİSTEMLERİ MÜHENDİSLİK KALKINMA VAKIFLAR BANKASı GAYRİMENKUL
GAYRIMENKUL ORTAKLIĞI AVRASYA AVRUPA ANADOLU DOĞU TASARRUF DANIŞMANLIK ORGANİZASYON
EĞİTİM OFİS KIRTASİYE PROMOSYON ÜRÜNLERİ İMALAT BANYO ÜRÜNLERİ URUNLERI BİRLEŞİK
MENSUCAT KOYUNLULULAR HEKİM ENGÜRÜSAĞ TURİZM HİZMETLER TEKSTİL METALURJİ ÇİMENTO
SABANCI HOLDİNG KORDSA NETCAD PASİFİK RÖNESANS KUZU EGEYAPI AĞAOĞLU BORUSAN
İŞLETMELERİ SİSTEMLERİ BİLGİSAYAR İNDEKS KOZA ALTIN MADENCİLİK'''

V = {fold(t) for t in SEED.split()}


def harvest(cells):
    """Tokens that provably cannot be a wrap fragment.

    A wrap leaves a truncated prefix at the END of a line and its tail at the START
    of the next — nowhere else. So a token is a whole word unless it is line-initial
    with a line above it, or line-final with a line below it."""
    for li, (toks, _, _) in enumerate(cells):
        for ti, t in enumerate(toks):
            if ti == 0 and li > 0: continue
            if ti == len(toks) - 1 and li < len(cells) - 1: continue
            V.add(fold(t))


def join_cell(cells):
    """Rebuild a wrapped cell. A mid-word break leaves a non-word on BOTH sides
    ("FAKTORİN"|"G"); an ordinary wrap leaves real words on both ("SANAYİ VE"|
    "TİCARET"). So glue the lines only when neither side is a word we know."""
    if not cells: return None
    out = []
    for i, (toks, _, _) in enumerate(cells):
        out.append(' '.join(toks))
        if i < len(cells) - 1:
            tail, head = fold(toks[-1]), fold(cells[i + 1][0][0])
            out.append('' if (tail not in V and head not in V) else ' ')
    joined = unglue(re.sub(r'\s+', ' ', ''.join(out)).strip())
    return re.sub(r'(?<=\w) (LERİ|LARI|RI|Rİ|NI|Nİ|SI|Sİ)\b',
                  lambda m: m.group(1), joined)


def unglue(name):
    """Undo a wrap we glued too eagerly. Peel known words off the right-hand end of
    an unknown token ("PARAFİNANSFAKTORİNG" -> "PARAFİNANS FAKTORİNG"), repeatedly,
    keeping whatever prefix is left over."""
    out = []
    for tok in name.split():
        parts = []
        while len(tok) >= 8 and fold(tok) not in V:
            for cut in range(len(tok) - 3, 2, -1):
                if fold(tok[cut:]) in V:
                    parts.insert(0, tok[cut:]); tok = tok[:cut]; break
            else:
                break
        out.append(tok); out += parts
    return ' '.join(out)


# ─────────────────────── classification ───────────────────────
BOND_XL = {'DEVLET TAHVİLİ VE BONOLAR':'government','BANKA BONOLARI':'bank bill',
           'FİNANSMAN BONOLARI':'finance bill','ÖZEL SEKTÖR TAHVİLLERİ':'corporate',
           'VARLIĞA DAYALI MENKUL KIYMETLER':'asset-backed',
           'YABANCI SABİT GETİRİLİ MENKUL KIYMETLER':'foreign','DÖVİZE ENDEKSLİ TAHVİLLER':'FX-indexed'}
SUB_INF = {'Bono':'bill','Özel Sektör':'corporate','Devlet Tahvili':'government',
           'Varlığa Dayalı Menkul Kıymet':'asset-backed'}


def classify_infleks(sec, sub, isin, blob):
    if sub == 'VIOP Nakit Teminatı': return None, None
    if sec == 'HİSSE SENETLERİ':  return 'stock', None
    if sec == 'ÖDÜNÇ ALMA':       return 'stock', 'securities lending'
    if sec == 'AÇIĞA SATIŞ':      return 'stock', 'short position'
    if sec == 'BORÇLANMA SENETLERİ':
        if sub and 'Kira Sertifika' in sub: return 'sukuk', 'corporate'
        return 'bond', SUB_INF.get(sub, sub)
    if sec == 'KİRA SERTİFİKALARI':
        return 'sukuk', 'public' if (sub or '').startswith('Kamu') else 'corporate'
    if sec == 'DİĞER' and (sub or '').startswith(('Y.Fonu', 'Borsa Y.Fonu')):
        return 'fund', 'ETF' if (sub or '').startswith('Borsa') else None
    # one report files a fund holding under a derivatives heading; a TRY… ISIN
    # carrying a fund name is a fund holding whatever the heading says
    if isin.startswith('TRY') and 'FON' in blob.upper(): return 'fund', None
    return None, None


def classify_excel(sec):
    if sec == 'HİSSE SENETLERİ':    return 'stock', None
    if sec in BOND_XL:              return 'bond', BOND_XL[sec]
    if sec == 'KİRA SERTİFİKALARI': return 'sukuk', 'corporate'
    if sec == 'KATILMA BELGELERİ':  return 'fund', None
    return None, None


# an issuer is spelled differently from one report to the next ("LİDER FAKTORİNG
# A.Ş." / "LIDER FAKTORING A.Ş"), so pick one spelling per issuer and keep the rest
GLUE_RE = re.compile(r'[A-ZÇĞİÖŞÜ]{13,}')
ALIAS = {"hazine": "Hazine ve Maliye Bakanlığı"}        # same issuer, two labels
# Two reports print an issuer the ISIN flatly contradicts. The ISIN wins and the
# label is dropped, rather than kept as an alternative spelling:
#   PRY calls TRFKYTRE2613 (Kayatur Filo Kiralama) a Treasury bill
#   PPT calls TRFPNSTA2630 (Pınar Süt) Pınar Et ve Un paper
# Sukuk are NOT misprints in the same way — a report naming the originator instead
# of the asset-leasing company is a legitimate reading, so both of those are kept.
MISPRINT = {"TRFKYTR": {"HAZİNE"},
            "TRFPNST": {"PINAR ENTEGRE ET VE UN SANAYI A.Ş"}}
# a handful of names the reports themselves render with no space at all
NAME_FIX = {"AKFAKTORİNG A.Ş.": "AK FAKTORİNG A.Ş.",
            "KUZUGRUPGAYRİ MENKUL YATIRIM ORTAKLIĞI A.Ş.": "KUZU GRUP GAYRİMENKUL YATIRIM ORTAKLIĞI A.Ş.",
            "RÖNESANSGAYRİ MENKUL YATIRIM A.Ş.": "RÖNESANS GAYRİMENKUL YATIRIM A.Ş.",
            "AURAPORT.YÖN. AŞ": "AURA PORT.YÖN. AŞ"}
# fund names run words together the same way; these are the words that get glued on
FUND_GLUE = re.compile(r'(?<=[A-ZÇĞİÖŞÜ])(HİSSE|BORSA|PORTFÖY|SERBEST|KATILIM|FONU|FON)\b')


def _best(counter):
    """Pick one spelling per issuer. Reports vary in whether they keep Turkish
    characters ("PINAR SUT MAMULLERI" vs "PINAR SÜT MAMÜLLERİ"), so prefer the
    accented rendering over the more frequent one, and never a run-together name."""
    def key(kv):
        n, uses = kv
        tr = sum(c in "İŞĞÜÖÇı" for c in n) + (2 if n.rstrip().endswith("A.Ş.") else 0)
        return (len(GLUE_RE.findall(n)), -tr, -uses, -len(n.split()), -len(n))
    return NAME_FIX.get(sorted(counter.items(), key=key)[0][0],
                        sorted(counter.items(), key=key)[0][0])


def canonicalise(rows):
    from collections import Counter
    # bonds and sukuk: the ISIN mnemonic (TRFLDFK…) identifies the issuer, not the text
    byiss = defaultdict(Counter)
    for r in rows:
        if r["assetClass"] in ("bond", "sukuk") and r["issuer"]:
            key = (r["isin"] or r["security"])[:7]
            if r["issuer"] in MISPRINT.get(key, ()):    # the ISIN says otherwise
                continue
            byiss[key][r["issuer"]] += 1
    pick = {k: _best(v) for k, v in byiss.items()}

    bytick = defaultdict(Counter)
    for r in rows:
        if r["assetClass"] == "stock" and r["issuer"]:
            bytick[r["security"]][r["issuer"]] += 1
    tick = {k: _best(v) for k, v in bytick.items()}

    for r in rows:
        if r["assetClass"] in ("bond", "sukuk"):
            key = (r["isin"] or r["security"])[:7]
            name = pick.get(key, r["issuer"])
            name = ALIAS.get(fold(name or ""), name)
            r["issuerCanonical"] = name
            others = sorted(n for n in byiss.get(key, {}) if n != name)
            r["issuerAsPrinted"] = r["issuer"]
            r["issuerAlt"] = others or None
        elif r["assetClass"] == "stock":
            r["issuerAsPrinted"] = r["issuer"]
            r["issuerCanonical"] = NAME_FIX.get(tick.get(r["security"], r["issuer"]),
                                                tick.get(r["security"], r["issuer"]))


def main():
    index = {r["fundCode"]: r for r in
             json.load(open(os.path.join(SRC, "_manifest", "results.json"), encoding="utf-8"))}
    manifest = {f["fundCode"]: (f.get("kapTitle") or f.get("bulletinName"))
                for f in json.load(open(os.path.join(SRC, "_manifest", "funds.json"), encoding="utf-8"))}

    parsed = {}
    for code, rec in index.items():
        path = os.path.join(SRC, rec["savedAs"])
        recs = parse_infleks(path)
        layout = "infleks"
        if not recs:
            recs, layout = parse_excel(path), "excel"
        if not recs:
            sys.exit(f"ERROR: no portfolio table parsed for {code} ({rec['savedAs']})")
        parsed[code] = (layout, recs)

    for layout, recs in parsed.values():                 # vocabulary first, then join
        if layout == "infleks":
            for r in recs:
                harvest(r["iss"]); harvest(r["code"])

    rows = []
    for code, (layout, recs) in sorted(parsed.items()):
        for r in recs:
            if layout == "infleks":
                name = join_cell(r["iss"]); sec_code = join_cell(r["code"]) or ""
                isin = (r["isin"] or [""])[0]
                cls, sub = classify_infleks(r["section"], r["sub"], isin,
                                            f"{sec_code} {name or ''}")
            else:
                sec_code = ' '.join(r["code"]); name = ' '.join(r["iss"])   # already clean
                isin = sec_code if ISIN_RE.match(sec_code) else ""
                cls, sub = classify_excel(r["section"])
            if not cls: continue

            ticker = re.sub(r'\s*_(VIOP|Rep\.).*$', '', sec_code).strip()
            rows.append({"fund": code, "assetClass": cls, "type": sub,
                         "security": ticker, "isin": isin,
                         "issuer": name or None,
                         "section": r["section"]})

    # fund units: recover the fund's own name where a report prints it
    for r in rows:
        if r["assetClass"] != "fund": continue
        s = r["security"]
        m = re.match(r'^([A-Z0-9]{3,6})\s*-\s*(.+)$', s) or re.match(r'^([A-Z0-9]{3,6})-([A-ZÇĞİÖŞÜ].+)$', s)
        if m:
            r["security"], r["fundName"] = m.group(1), m.group(2).strip()
        elif manifest.get(s):
            r["fundName"] = manifest[s]
        elif r["issuer"] and re.search(r'A\.Ş\.\s*[A-ZÇĞİÖŞÜ]', r["issuer"]):
            mgr, rest = re.split(r"(?<=A\.Ş\.)\s*(?=[A-ZÇĞİÖŞÜ])", r["issuer"], maxsplit=1)
            r["issuer"], r["fundName"] = mgr.strip(), rest.strip()
        else:
            r["fundName"] = None
        if r.get("fundName"):
            r["fundName"] = FUND_GLUE.sub(r' \1', r["fundName"]).strip()
        if r.get("issuer"):
            r["issuer"] = NAME_FIX.get(r["issuer"], r["issuer"])

    canonicalise(rows)

    os.makedirs(DATA, exist_ok=True)
    json.dump(rows, open(os.path.join(DATA, "holdings.json"), "w"),
              ensure_ascii=False, indent=1)

    import csv
    with open(os.path.join(DATA, "holdings.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ["fund", "assetClass", "type", "security", "isin",
                                "issuerCanonical", "issuerAsPrinted", "fundName",
                                "section"], extrasaction="ignore")
        w.writeheader()
        for r in rows: w.writerow(r)

    n = defaultdict(int)
    for r in rows: n[r["assetClass"]] += 1
    print(f"{len(rows)} holdings from {len(parsed)} funds -> data/holdings.json")
    for k in ("stock", "bond", "sukuk", "fund"):
        uniq = len({r.get("issuerCanonical") if k in ("bond", "sukuk") else r["security"]
                    for r in rows if r["assetClass"] == k})
        print(f"  {k:6} {n[k]:5} holdings   {uniq:4} distinct")


if __name__ == "__main__":
    main()
