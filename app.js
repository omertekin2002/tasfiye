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
})();
