/* SmearSight front end: core helpers, router, charts. No external libraries, works offline. */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const S = { state: null, cleanup: [] };

function reader() { try { return localStorage.getItem("ss_reader") || ""; } catch (e) { return ""; } }
function setReader(n) { try { localStorage.setItem("ss_reader", n); } catch (e) {} }

async function api(path, opt = {}) {
  const o = { method: opt.method || "GET", headers: { "X-Reader": reader() } };
  if (opt.json !== undefined) { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(opt.json); }
  if (opt.form) o.body = opt.form;
  const r = await fetch(path, o);
  if (r.status === 401) { location.href = "/login"; throw new Error("PIN required"); }
  let data = null;
  try { data = await r.json(); } catch (e) {}
  if (!r.ok) {
    let d = data && data.detail;
    if (Array.isArray(d)) d = d.map(x => x.msg).join("; ");
    throw new Error(d || ("Request failed (" + r.status + ")"));
  }
  return data;
}

function toast(msg, err) {
  const t = document.createElement("div");
  t.className = "toast" + (err ? " err" : "");
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), err ? 6000 : 2800);
}
async function guard(fn) { try { return await fn(); } catch (e) { toast(e.message, true); } }

function fmtDur(s) {
  if (s == null || isNaN(s)) return "n/a";
  s = Math.round(s);
  const m = Math.floor(s / 60), r = s % 60;
  return m + ":" + String(r).padStart(2, "0");
}
function fmtDate(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short" }) + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
const pct = (x, d = 1) => x == null ? "n/a" : (x * 100).toFixed(d) + "%";
const ci = c => c ? `(${(c[0] * 100).toFixed(0)} to ${(c[1] * 100).toFixed(0)}%)` : "";
const gradeLabel = g => g === "negative" ? "Negative" : g === "scanty" ? "Scanty" : (g || "n/a");
function gradeClass(g) { return g === "negative" ? "neg" : g === "scanty" ? "mid" : g ? "pos" : ""; }
function gradePill(g) { return g ? `<span class="pill ${g === "negative" ? "neg" : g === "scanty" ? "warn" : "pos"}">${esc(gradeLabel(g))}</span>` : `<span class="muted">n/a</span>`; }
function demoPill(d) { return d ? `<span class="pill demo">DEMO</span>` : ""; }

function modal(html, wide) {
  const bg = document.createElement("div");
  bg.className = "modal-bg";
  bg.innerHTML = `<div class="modal" ${wide ? 'style="max-width:1100px"' : ""}>${html}</div>`;
  bg.addEventListener("mousedown", e => { if (e.target === bg) bg.remove(); });
  document.body.appendChild(bg);
  bg.close = () => bg.remove();
  return bg;
}

/* ---------- tiny SVG charts ---------- */
function lineChart(series, { w = 560, h = 200, yfmt = v => v, ymin = null } = {}) {
  // series: [{name,color,points:[[x,y]...]}] x are numbers (epoch / index)
  const pad = { l: 44, r: 12, t: 10, b: 24 };
  const all = series.flatMap(s => s.points.filter(p => p[1] != null));
  if (!all.length) return `<div class="empty small">No data yet.</div>`;
  const xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs) || 1;
  let y0 = ymin != null ? ymin : Math.min(...ys), y1 = Math.max(...ys);
  if (y1 === y0) y1 = y0 + 1;
  const X = x => pad.l + (x1 === x0 ? 0.5 : (x - x0) / (x1 - x0)) * (w - pad.l - pad.r);
  const Y = y => h - pad.b - (y - y0) / (y1 - y0) * (h - pad.t - pad.b);
  let g = "";
  for (let i = 0; i <= 4; i++) {
    const v = y0 + (y1 - y0) * i / 4, y = Y(v);
    g += `<line x1="${pad.l}" x2="${w - pad.r}" y1="${y}" y2="${y}" stroke="#E6EEF0"/><text x="${pad.l - 6}" y="${y + 4}" text-anchor="end">${esc(yfmt(v))}</text>`;
  }
  const xt = (x0 === x1 ? [x0] : [x0, (x0 + x1) / 2, x1]).map((v, i) => `<text x="${X(v)}" y="${h - 6}" text-anchor="${x0 === x1 ? "middle" : i == 0 ? "start" : i == 2 ? "end" : "middle"}">${Math.round(v)}</text>`).join("");
  const lines = series.map(s => {
    const pts = s.points.filter(p => p[1] != null);
    const d = pts.map((p, i) => (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1)).join(" ");
    const dots = pts.length < 25 ? pts.map(p => `<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="3" fill="${s.color}"/>`).join("") : "";
    return `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="2.2" stroke-linejoin="round"/>${dots}`;
  }).join("");
  const leg = series.map(s => `<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join(" &nbsp; ");
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" role="img">${g}${xt}${lines}</svg><div class="legend tiny muted">${leg}</div>`;
}

function barChart(items, { w = 560, h = 190, color = "#0891A0" } = {}) {
  // items: [{label, value}]
  const pad = { l: 30, r: 8, t: 14, b: 40 };
  const max = Math.max(1, ...items.map(i => i.value));
  const bw = (w - pad.l - pad.r) / items.length;
  const bars = items.map((it, i) => {
    const bh = (it.value / max) * (h - pad.t - pad.b), x = pad.l + i * bw + 6, y = h - pad.b - bh;
    return `<rect x="${x}" y="${y}" width="${bw - 12}" height="${bh}" rx="4" fill="${color}"/>
      <text x="${x + (bw - 12) / 2}" y="${y - 4}" text-anchor="middle" style="fill:#0F2A33">${it.value}</text>
      <text x="${x + (bw - 12) / 2}" y="${h - 22}" text-anchor="middle">${esc(it.label.split(" to ")[0])}</text>
      <text x="${x + (bw - 12) / 2}" y="${h - 9}" text-anchor="middle">${it.label.includes(" to ") ? "to " + esc(it.label.split(" to ")[1]) : ""}</text>`;
  }).join("");
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" role="img"><line x1="${pad.l}" x2="${w - pad.r}" y1="${h - pad.b}" y2="${h - pad.b}" stroke="#C5D3D8"/>${bars}</svg>`;
}

/* ---------- router ---------- */
const ROUTES = {};
function route(name, fn) { ROUTES[name] = fn; }
function go(h) { location.hash = h; }

async function render() {
  S.cleanup.forEach(f => { try { f(); } catch (e) {} });
  S.cleanup = [];
  const parts = location.hash.replace(/^#\/?/, "").split("/");
  const name = parts[0] || "";
  $$("nav.side a[data-r]").forEach(a => a.classList.toggle("on", a.dataset.r === name));
  const view = $("#view");
  const fn = ROUTES[name] || ROUTES[""];
  try {
    await refreshState();
    view.innerHTML = `<div class="empty"><span class="spin"></span></div>`;
    await fn(view, parts.slice(1));
    window.scrollTo(0, 0);
  } catch (e) {
    view.innerHTML = `<div class="banner bad">Something went wrong: ${esc(e.message)}</div>`;
  }
}

async function refreshState() {
  S.state = await api("/api/state");
  const sel = $("#reader");
  const cur = reader() && S.state.readers.find(r => r.name === reader()) ? reader() : S.state.readers[0].name;
  setReader(cur);
  sel.innerHTML = S.state.readers.map(r => `<option ${r.name === cur ? "selected" : ""} value="${esc(r.name)}">${esc(r.name)} (${esc(r.role)})</option>`).join("");
  const b = $("#rv-badge");
  b.hidden = !S.state.open_review;
  b.textContent = S.state.open_review;
  $("#model-chip").innerHTML = ["zn", "fm"].map(k => {
    const m = S.state.active_models[k];
    return m ? `${MOD_SHORT[k]} <b style="color:#fff">${esc(m.name)}</b> ${m.demo ? '<span class="pill demo">DEMO</span>' : ""}`
      : `${MOD_SHORT[k]} <span style="color:#F7C98B">no model</span>`;
  }).join("<br>");
}

function boot() {
  $("#reader").addEventListener("change", e => { setReader(e.target.value); render(); });
  window.addEventListener("hashchange", render);
  render();
}

const MOD_SHORT = { zn: "Bright-field", fm: "Fluorescence" };
const modPill = m => `<span class="pill ${m === "fm" ? "fm" : "teal"}">${m === "fm" ? "Fluorescence" : "Bright-field"}</span>`;
function demoBanner(modality) {
  const am = S.state.active_models;
  const m = modality ? am[modality] : (am.zn && am.zn.demo ? am.zn : am.fm && am.fm.demo ? am.fm : am.zn || am.fm);
  return m && m.demo ? `<div class="banner"><b>Demo model active.</b> ${esc(S.state.demo_banner)} Results from this model are for testing the workflow only.</div>` : "";
}

function roleOf(name) { const r = S.state.readers.find(x => x.name === name); return r ? r.role : "technician"; }
