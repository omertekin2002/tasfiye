(() => {
  "use strict";

  const TL = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const UNIT = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 4, maximumFractionDigits: 6 });
  const PCT = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const ASSET_TR = {
    equity: "Hisse Senedi", tbill: "Hazine Bonosu", govbond: "Devlet Tahvili",
    corpbond: "Özel Sektör Tahvili", sukuk: "Kira Sertifikaları", finbill: "Finansman Bonosu",
    reverserepo: "Ters Repo", repo: "Repo", deposit: "Mevduat",
    participation: "Katılma Hesabı", fund: "Yatırım Fonu", moneymarket: "Borsa Para Piyasası",
  };

  const $ = (s) => document.querySelector(s);
  const rowsEl = $("#rows"), emptyEl = $("#empty"), qEl = $("#q"),
        founderEl = $("#founder"), countEl = $("#count");

  let funds = [];
  let sort = { key: "nav", dir: -1 };
  let expanded = null;

  // An unknown figure is an em-dash, never 0,00 — the design system is explicit about this.
  const money = (v) => v == null ? '<span class="dash">—</span>'
    : `${TL.format(v)}<span class="cur">TL</span>`;

  function render() {
    const q = qEl.value.trim().toLocaleLowerCase("tr-TR");
    const f = founderEl.value;
    let view = funds.filter((x) =>
      (!f || x.founder === f) &&
      (!q || x.fundCode.toLocaleLowerCase("tr-TR").includes(q) ||
             x.name.toLocaleLowerCase("tr-TR").includes(q)));

    view.sort((a, b) => {
      const A = a[sort.key], B = b[sort.key];
      if (A == null && B == null) return 0;
      if (A == null) return 1;            // unknowns always sink
      if (B == null) return -1;
      return (typeof A === "number" ? A - B : String(A).localeCompare(String(B), "tr")) * sort.dir;
    });

    rowsEl.innerHTML = view.map((x) => {
      const open = expanded === x.fundCode;
      const alloc = Object.entries(x.allocation || {})
        .filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
      return `
      <tr class="row" data-code="${x.fundCode}">
        <td>
          <span class="code">${x.fundCode}</span>
          <span class="fname">${x.name}</span>
        </td>
        <td class="col-founder founder" data-label="Kurucu">${x.founder}</td>
        <td class="num val" data-label="Son portföy değeri">${money(x.nav)}</td>
        <td class="num unit col-unit" data-label="Birim pay">${x.unitPrice == null ? '<span class="dash">—</span>' : UNIT.format(x.unitPrice)}</td>
        <td class="date" data-label="Rapor tarihi">${x.reportDate || '<span class="dash">—</span>'}</td>
        <td class="num val" data-label="Tasfiye değeri">
          ${x.liquidationValue == null
            ? '<span class="pill pill-pending">Beklemede</span>'
            : money(x.liquidationValue)}
        </td>
      </tr>` + (!open ? "" : `
      <tr class="detail">
        <td colspan="6">
          <div class="detail-inner">
            <div class="alloc">
              <div class="eyebrow">Portföy Dağılımı</div>
              ${alloc.length ? `<dl>${alloc.map(([k, v]) =>
                `<dt>${ASSET_TR[k] || k}</dt><dd>%${PCT.format(v)}</dd>`).join("")}</dl>`
                : '<p class="meta">Dağılım verisi okunamadı.</p>'}
            </div>
            <div class="meta">
              <div class="eyebrow">Kaynak</div>
              <div>Katılma payı sayısı:
                <span class="num">${x.shares == null ? "—" : TL.format(x.shares)}</span></div>
              <div>Rapor dönemi: ${x.reportPeriod || "—"}</div>
              <div><a href="${x.sourceUrl}" target="_blank" rel="noopener">KAP bildirimi</a>
                &middot;
                <a href="portfolio%20allocation/${encodeURIComponent(x.file)}" target="_blank" rel="noopener">PDF</a></div>
            </div>
          </div>
        </td>
      </tr>`);
    }).join("");

    emptyEl.hidden = view.length > 0;
    countEl.textContent = `${view.length} / ${funds.length} fon`;

    document.querySelectorAll("thead th[data-sort]").forEach((th) => {
      const k = th.dataset.sort;
      th.querySelector(".arrow")?.remove();
      if (k === sort.key) {
        const s = document.createElement("span");
        s.className = "arrow";
        s.textContent = sort.dir === 1 ? " ▲" : " ▼";
        th.appendChild(s);
      }
    });
  }

  function totals() {
    const withNav = funds.filter((x) => x.nav != null);
    $("#totalNav").innerHTML = money(withNav.reduce((s, x) => s + x.nav, 0));
    $("#totalCount").textContent = funds.length;
    // Every value carries an as-of stamp; these reports span a date range, so state it.
    const dates = funds.map((x) => x.reportDate).filter(Boolean).sort((a, b) => {
      const p = (d) => d.slice(6) + d.slice(3, 5) + d.slice(0, 2);
      return p(a).localeCompare(p(b));
    });
    if (dates.length) {
      $("#totalAsof").textContent = dates[0] === dates[dates.length - 1]
        ? `${dates[0]} itibarıyla`
        : `${dates[0]} – ${dates[dates.length - 1]} tarihli raporlar`;
    }
    const seen = [...new Set(funds.map((x) => x.founder))].sort((a, b) => a.localeCompare(b, "tr"));
    founderEl.insertAdjacentHTML("beforeend",
      seen.map((f) => `<option value="${f}">${f}</option>`).join(""));
  }

  rowsEl.addEventListener("click", (e) => {
    const tr = e.target.closest("tr.row");
    if (!tr || e.target.closest("a")) return;
    expanded = expanded === tr.dataset.code ? null : tr.dataset.code;
    render();
  });

  document.querySelectorAll("thead th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const k = th.dataset.sort;
      if (sort.key === k) sort.dir *= -1;
      else sort = { key: k, dir: typeof funds[0]?.[k] === "number" ? -1 : 1 };
      render();
    });
  });

  qEl.addEventListener("input", () => { expanded = null; render(); });
  founderEl.addEventListener("change", () => { expanded = null; render(); });

  fetch("data/funds.json")
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((d) => { funds = d; totals(); render(); })
    .catch((err) => {
      emptyEl.hidden = false;
      emptyEl.textContent = "Fon verisi yüklenemedi (" + err.message + ").";
    });

  /* ════════════════ Portföy Bileşenleri ════════════════
     What the 47 funds hold, rather than what they are worth. Rows carry no
     amounts by design — only which issuer, and which funds are exposed to it. */

  const CLASSES = [
    { id: "stock", title: "Hisse Senetleri", unit: "ayrı hisse",
      gloss: "Raporlarda basıldığı hâliyle BIST kodu ve şirket unvanı.",
      cols: ["Kod", "Şirket", "Fon", "Tutan fonlar"] },
    { id: "bond", title: "Borçlanma Senetleri", unit: "ayrı ihraççı",
      gloss: "Tahvil, bono, finansman bonosu ve varlığa dayalı menkul kıymet ihraççıları.",
      cols: ["İhraççı", "Tür", "İhraç", "Fon", "Tutan fonlar"] },
    { id: "sukuk", title: "Kira Sertifikaları", unit: "ayrı ihraççı",
      gloss: "Sukuk ihraççıları. Bir rapor varlık kiralama şirketini, bir diğeri kaynak kuruluşu yazabilir.",
      cols: ["İhraççı", "Tür", "İhraç", "Fon", "Tutan fonlar"] },
    { id: "fund", title: "Fon Katılma Payları", unit: "ayrı fon",
      gloss: "Diğer yatırım fonlarındaki paylar.",
      cols: ["Kod", "Fon adı", "Kurucu", "Fon", "Tutan fonlar"] },
  ];

  const TYPE_TR = {
    bill: "Bono", corporate: "Özel sektör tahvili", government: "Devlet tahvili",
    "finance bill": "Finansman bonosu", "bank bill": "Banka bonosu",
    "asset-backed": "Varlığa dayalı", foreign: "Yabancı", "FX-indexed": "Dövize endeksli",
    public: "Kamu kesimi", "securities lending": "Ödünç alma",
    "short position": "Açığa satış", ETF: "Borsa yatırım fonu",
  };

  const esc = (v) => String(v ?? "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const DASH = '<span class="dash">—</span>';

  let groups = null;            // { stock: [...], bond: [...], … }
  let hFilter = "all";
  const hqEl = $("#hq"), hCountEl = $("#hCount"), hSecEl = $("#hSections");

  // One row per security, 47 reports deep — collapse to one entry per issuer.
  function group(rows) {
    const by = new Map();
    for (const r of rows) {
      const key = r.assetClass === "stock" || r.assetClass === "fund"
        ? r.security : r.issuerCanonical;
      if (!key) continue;
      const id = r.assetClass + "\u0000" + key;
      let e = by.get(id);
      if (!e) by.set(id, e = { cls: r.assetClass, key, funds: new Set(),
                               isins: new Set(), types: new Set(), alt: new Set() });
      e.funds.add(r.fund);
      if (r.isin) e.isins.add(r.isin);
      if (r.type) e.types.add(r.type);
      for (const a of r.issuerAlt || []) e.alt.add(a);
      if (r.assetClass === "fund") { e.name = e.name || r.fundName; e.mgr = e.mgr || r.issuer; }
      else if (r.assetClass === "stock") e.name = e.name || r.issuerCanonical;
    }
    const out = {};
    for (const c of CLASSES) out[c.id] = [];
    for (const e of by.values()) {
      e.haystack = [e.key, e.name, e.mgr, ...e.alt, ...e.funds,
                    ...[...e.types].map((t) => TYPE_TR[t] || t)]
        .filter(Boolean).join(" ").toLocaleLowerCase("tr-TR");
      out[e.cls].push(e);
    }
    // most widely held first — that is the exposure story
    for (const k of Object.keys(out)) {
      out[k].sort((a, b) => b.funds.size - a.funds.size || a.key.localeCompare(b.key, "tr"));
    }
    return out;
  }

  const holders = (f) =>
    `<div class="holders">${[...f].sort().map((x) => `<span>${esc(x)}</span>`).join("")}</div>`;
  const kinds = (t) => [...t].map((x) =>
    `<span class="kind">${esc(TYPE_TR[x] || x)}</span>`).join("") || DASH;

  function cells(cls, e) {
    if (cls === "stock") return `
      <td class="code" data-label="Kod">${esc(e.key)}</td>
      <td class="name" data-label="Şirket">${e.name ? esc(e.name) : DASH}</td>
      <td class="num" data-label="Fon">${e.funds.size}</td>
      <td data-label="Tutan fonlar">${holders(e.funds)}</td>`;
    if (cls === "fund") return `
      <td class="code" data-label="Kod">${esc(e.key)}</td>
      <td class="name" data-label="Fon adı">${e.name ? esc(e.name)
        : `${DASH}<span class="alt">adı raporda basılmamış</span>`}</td>
      <td class="founder" data-label="Kurucu">${e.mgr ? esc(e.mgr) : DASH}</td>
      <td class="num" data-label="Fon">${e.funds.size}</td>
      <td data-label="Tutan fonlar">${holders(e.funds)}</td>`;
    return `
      <td class="name" data-label="İhraççı">${esc(e.key)}${e.alt.size
        ? `<span class="alt">raporlarda ayrıca: ${[...e.alt].sort().map(esc).join("; ")}</span>` : ""}</td>
      <td data-label="Tür">${kinds(e.types)}</td>
      <td class="num" data-label="İhraç">${e.isins.size || DASH}</td>
      <td class="num" data-label="Fon">${e.funds.size}</td>
      <td data-label="Tutan fonlar">${holders(e.funds)}</td>`;
  }

  function buildHoldings() {
    $("#hTally").innerHTML = CLASSES.map((c) => `
      <div class="total-block">
        <div class="eyebrow">${c.title}</div>
        <div class="total-value">${groups[c.id].length}</div>
        <div class="asof">${c.unit}</div>
      </div>`).join("");

    $("#hChips").innerHTML = [["all", "Tümü"], ...CLASSES.map((c) => [c.id, c.title])]
      .map(([v, t], i) =>
        `<button type="button" class="chip" data-f="${v}" aria-pressed="${i === 0}">${t}</button>`)
      .join("");

    hSecEl.innerHTML = CLASSES.map((c) => `
      <section class="hsec" data-cls="${c.id}">
        <div class="hhead">
          <h2>${c.title}</h2><span class="n"></span>
          <span class="gloss">${c.gloss}</span>
        </div>
        <table>
          <thead><tr>${c.cols.map((h) =>
            `<th${h === "Fon" || h === "İhraç" ? ' class="r"' : ""}>${h}</th>`).join("")}</tr></thead>
          <tbody>${groups[c.id].map((e) =>
            `<tr data-h="${esc(e.haystack)}">${cells(c.id, e)}</tr>`).join("")}</tbody>
        </table>
        <div class="empty" hidden>Eşleşen kayıt yok.</div>
      </section>`).join("");

    hqEl.addEventListener("input", filterHoldings);
    $("#hChips").addEventListener("click", (ev) => {
      const b = ev.target.closest(".chip");
      if (!b) return;
      hFilter = b.dataset.f;
      $("#hChips").querySelectorAll(".chip").forEach((c) =>
        c.setAttribute("aria-pressed", String(c === b)));
      filterHoldings();
    });
    filterHoldings();
  }

  function filterHoldings() {
    const q = hqEl.value.trim().toLocaleLowerCase("tr-TR");
    let shown = 0, all = 0;
    hSecEl.querySelectorAll("section.hsec").forEach((sec) => {
      const on = hFilter === "all" || hFilter === sec.dataset.cls;
      sec.hidden = !on;
      let n = 0;
      sec.querySelectorAll("tbody tr").forEach((tr) => {
        all++;
        const hit = on && (!q || tr.dataset.h.includes(q));
        tr.hidden = !hit;
        if (hit) n++;
      });
      sec.querySelector(".n").textContent = n;
      sec.querySelector("table").hidden = n === 0;   // no column headers over nothing
      sec.querySelector(".empty").hidden = n > 0;
      shown += n;
    });
    hCountEl.textContent = `${shown} / ${all} bileşen`;
  }

  /* ---------- tabs ---------- */
  const tabs = [...document.querySelectorAll(".tab")];
  function showTab(btn) {
    tabs.forEach((t) => {
      const on = t === btn;
      t.setAttribute("aria-selected", String(on));
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
    });
    $("#notes-funds").hidden = btn.id !== "tab-funds";
    $("#notes-holdings").hidden = btn.id !== "tab-holdings";
    if (btn.id === "tab-holdings" && !groups) loadHoldings();
  }
  tabs.forEach((t) => t.addEventListener("click", () => showTab(t)));
  tabs.forEach((t, i) => t.addEventListener("keydown", (e) => {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const next = tabs[(i + d + tabs.length) % tabs.length];
    next.focus(); showTab(next);
  }));

  function loadHoldings() {
    hSecEl.innerHTML = '<div class="empty">Yükleniyor…</div>';
    fetch("data/holdings.json")
      .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then((d) => { groups = group(d); buildHoldings(); })
      .catch((err) => {
        hSecEl.innerHTML =
          '<div class="empty">Bileşen verisi yüklenemedi (' + esc(err.message) + ").</div>";
      });
  }
})();
