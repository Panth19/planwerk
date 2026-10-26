/*
 * Planwerk importer, browser edition: reads a client's employee list in the
 * visitor's browser, so the file never leaves the machine.
 *
 * Mirrors the import rules of planwerk/excel.py (header synonyms, German and
 * English number formats, two-digit years). tests/test_js_import.py feeds the
 * same files to both and compares the result.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.PlanwerkImport = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const SYNONYMS = {
    id: ["personalnummer", "personalnr", "persnr", "pnr", "id", "employeeid", "staffno", "nr"],
    name: ["name", "mitarbeiter", "mitarbeiterin", "vornamename", "employee", "fullname", "nachnamevorname"],
    birth_date: ["geburtsdatum", "gebdatum", "geboren", "birthdate", "dateofbirth", "dob", "gebam"],
    entry_date: ["eintritt", "eintrittsdatum", "beschaeftigtseit", "betriebszugehoerigkeitab",
      "entrydate", "startdate", "hiredate", "seit"],
    monthly_gross: ["brutto", "bruttomonatsgehalt", "monatsbrutto", "gehalt", "bruttogehalt",
      "monthlygross", "salary", "grosssalary", "bruttomonat"],
    children: ["kinder", "unterhaltspflichtigekinder", "anzahlkinder", "children", "kids"],
    married: ["verheiratet", "familienstand", "verh", "married", "ehe"],
    disabled: ["schwerbehindert", "sb", "schwerbehinderung", "gdb50", "disabled", "disability"],
  };
  const REQUIRED = ["birth_date", "entry_date", "monthly_gross"];

  function normHeader(s) {
    return String(s).replace(/\(.*?\)/g, "").trim().toLowerCase()
      .replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue").replace(/ß/g, "ss")
      .normalize("NFKD").replace(/[^a-z0-9]/g, "");
  }

  function truthy(v) {
    if (typeof v === "boolean") return v;
    if (typeof v === "number") return v !== 0;
    return ["1", "true", "ja", "yes", "x", "j", "y", "wahr"].includes(String(v).trim().toLowerCase());
  }

  const pad = (n) => String(n).padStart(2, "0");

  // Builds the ISO date only if it exists in the calendar (no 31 February).
  function iso(y, m, d) {
    const t = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d)));
    if (t.getUTCFullYear() !== Number(y) || t.getUTCMonth() !== Number(m) - 1 || t.getUTCDate() !== Number(d)) {
      throw new Error(`Datum nicht lesbar: '${d}.${m}.${y}'`);
    }
    return `${String(y).padStart(4, "0")}-${pad(m)}-${pad(d)}`;
  }

  function toIsoDate(v, latestYear) {
    if (v instanceof Date) return v.toISOString().slice(0, 10);
    if (typeof v === "number") { // Excel serial date (1900 system)
      return new Date(Date.UTC(1899, 11, 30) + Math.round(v) * 86400000).toISOString().slice(0, 10);
    }
    const s = String(v ?? "").trim();
    let m = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/) || s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (m) return iso(m[3], m[2], m[1]);
    m = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T].*)?$/);
    if (m) return iso(m[1], m[2], m[3]);
    m = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{2})$/);
    if (m) {
      let y = 2000 + Number(m[3]);
      if (y > (latestYear || new Date().getFullYear())) y -= 100;
      return iso(y, m[2], m[1]);
    }
    throw new Error(`Datum nicht lesbar: '${s}'`);
  }

  function toMoney(v) {
    if (typeof v === "number") return v;
    let s = String(v ?? "").replace(/\s|€|EUR/g, "");
    if (s.includes(",") && s.includes(".")) {
      const dec = s.lastIndexOf(",") > s.lastIndexOf(".") ? "," : ".";
      s = s.split(dec === "," ? "." : ",").join("").replace(",", ".");
    } else if (s.includes(",")) {
      s = /^\d{1,3}(,\d{3})+$/.test(s) ? s.replace(/,/g, "") : s.replace(",", ".");
    } else if (/^\d{1,3}(\.\d{3})+$/.test(s)) {
      s = s.replace(/\./g, "");
    }
    const n = Number(s);
    if (s === "" || !isFinite(n)) throw new Error(`Betrag nicht lesbar: '${v}'`);
    return n;
  }

  function sniffDelimiter(text) {
    const first = text.split(/\r?\n/)[0] || "";
    let best = ";", count = -1;
    for (const d of [";", "\t", ","]) {
      const c = first.split(d).length - 1;
      if (c > count) { best = d; count = c; }
    }
    return best;
  }

  function parseCsv(text) {
    text = text.replace(/^﻿/, "");
    const delim = sniffDelimiter(text);
    const rows = [];
    let row = [], cur = "", quoted = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (quoted) {
        if (c === '"' && text[i + 1] === '"') { cur += '"'; i++; }
        else if (c === '"') quoted = false;
        else cur += c;
      } else if (c === '"') quoted = true;
      else if (c === delim) { row.push(cur); cur = ""; }
      else if (c === "\n" || c === "\r") {
        if (c === "\r" && text[i + 1] === "\n") i++;
        row.push(cur); rows.push(row); row = []; cur = "";
      } else cur += c;
    }
    if (cur !== "" || row.length) { row.push(cur); rows.push(row); }
    return rows;
  }

  const blank = (v) => v === null || v === undefined || String(v).trim() === "";

  function readRows(rows, latestYear) {
    const hi = rows.findIndex((r) => r.filter((v) => !blank(v)).length >= 3);
    if (hi < 0) throw new Error("Keine Tabelle mit Kopfzeile gefunden (mindestens drei Spalten erwartet).");
    const header = rows[hi].map((v) => (blank(v) ? "" : String(v).trim()));
    const idx = {}, unmapped = [];
    header.forEach((h, i) => {
      if (!h) return;
      const k = normHeader(h);
      const f = Object.keys(SYNONYMS).find((f) => SYNONYMS[f].includes(k) && !(f in idx));
      if (f) idx[f] = i; else unmapped.push(h);
    });
    const missing = REQUIRED.filter((f) => !(f in idx));
    const report = { employees: [], missing, unmapped, warnings: [] };
    if (missing.length) return report;

    const cell = (r, f, d) => (f in idx && idx[f] < r.length && !blank(r[idx[f]]) ? r[idx[f]] : d);
    const seen = new Set();
    rows.slice(hi + 1).forEach((r, k) => {
      const n = hi + k + 2;
      if (!r || r.every(blank)) return;
      if (["summe", "total", "gesamt"].includes(String(cell(r, "name", "")).trim().toLowerCase())) return;
      try {
        const id = String(cell(r, "id", "MA-" + String(n - 1).padStart(3, "0"))).trim();
        const birth = toIsoDate(cell(r, "birth_date"), latestYear);
        const entry = toIsoDate(cell(r, "entry_date"), latestYear);
        const salary = toMoney(cell(r, "monthly_gross"));
        if (!(salary > 0)) throw new Error(`Bruttogehalt ${salary} ist nicht positiv`);
        if (seen.has(id)) report.warnings.push(`Zeile ${n}: Personal-Nr. ${id} doppelt`);
        seen.add(id);
        if (Number(entry.slice(0, 4)) - Number(birth.slice(0, 4)) < 14) {
          report.warnings.push(`Zeile ${n}: Eintritt vor dem 14. Lebensjahr, bitte prüfen`);
        }
        const children = Math.trunc(Number(String(cell(r, "children", 0)).replace(",", ".")));
        if (!isFinite(children)) throw new Error(`Kinder nicht lesbar: '${cell(r, "children")}'`);
        report.employees.push({
          id, name: String(cell(r, "name", id)).trim(), birth_date: birth, entry_date: entry,
          monthly_gross: salary, children,
          married: truthy(cell(r, "married", false)), disabled: truthy(cell(r, "disabled", false)),
        });
      } catch (e) {
        report.warnings.push(`Zeile ${n}: ${e.message}`);
      }
    });
    return report;
  }

  return { SYNONYMS, normHeader, truthy, toIsoDate, toMoney, parseCsv, readRows };
});
