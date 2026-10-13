/* Dashboard and Analyze pages */

route("", async view => {
  const [sum, slides] = await Promise.all([api("/api/summary"), api("/api/slides?limit=12")]);
  const open = slides.filter(s => s.status === "open");
  const m = sum.active_model;
  const faster = sum.median_seconds != null && sum.manual_median_seconds != null
    ? `Manual reading median ${fmtDur(sum.manual_median_seconds)}` : "Enter your manual time when confirming to compare";
  view.innerHTML = `
    <div class="topbar"><div><h1>Dashboard</h1><div class="muted small">Last 30 days</div></div><div class="sp"></div>
      <a class="btn primary" href="#/analyze">Start a new slide</a></div>
    ${demoBanner()}
    ${m ? "" : `<div class="card" style="margin-bottom:14px">
      <h2>Getting started: no model is active yet</h2>
      <p class="muted">The app needs a trained model before it can suggest anything. The steps, in order:</p>
      <ol style="margin:0 0 10px 18px;padding:0;line-height:1.9">
        <li><b>Add images.</b> Upload labelled smear fields in <a href="#/dataset">Dataset</a>, or press <i>Generate demo images</i> to try the whole workflow with synthetic pictures.</li>
        <li><b>Freeze a dataset version</b> (the app splits train, validation and test by slide).</li>
        <li><b>Train</b> in <a href="#/training">Model training</a>. It runs on this computer and shows progress.</li>
        <li><b>Approve</b> the candidate model (senior reader or lab lead), then analyse slides.</li>
      </ol></div>`}
    <div class="grid g4" style="margin-bottom:14px">
      <div class="card stat"><div class="n">${sum.slides_30d}</div><div class="l">Slides confirmed</div><div class="d">${sum.open_slides} open now</div></div>
      <div class="card stat"><div class="n">${fmtDur(sum.median_seconds)}</div><div class="l">Median time per slide</div><div class="d">${esc(faster)}</div></div>
      <div class="card stat"><div class="n">${sum.flagged_positive}</div><div class="l">AI flagged positive</div><div class="d">Each one confirmed by a person</div></div>
      <div class="card stat"><div class="n">${sum.awaiting_review}</div><div class="l">Awaiting expert review</div><div class="d"><a href="#/review">Open the queue</a></div></div>
    </div>
    <div class="grid g2">
      <div class="card"><h2>Open slides</h2>
        ${open.length ? `<table><tbody>${open.map(s => `<tr class="click" onclick="go('#/analyze/${s.id}')"><td><b>${esc(s.code)}</b> ${demoPill(s.demo)}</td><td class="muted">${esc(s.site || "")}</td><td class="muted">${s.n_fields} fields</td><td><button class="sm primary">Resume</button></td></tr>`).join("")}</tbody></table>`
      : `<div class="empty small">No open slides.</div>`}</div>
      <div class="card"><h2>Model</h2>
        ${m ? `<div class="row between"><div><b>${esc(m.name)}</b> ${demoPill(m.demo)}<div class="small muted">approved by ${esc(m.approved_by || "n/a")} on ${fmtDate(m.approved_at)}</div></div></div>
        <table style="margin-top:8px"><tbody>
          <tr><td>Held-out test images</td><td class="mono">${m.metrics.test_images ?? "n/a"}</td></tr>
          <tr><td>Image-level sensitivity</td><td class="mono">${pct(m.metrics.sensitivity)}</td></tr>
          <tr><td>Image-level specificity</td><td class="mono">${pct(m.metrics.specificity)}</td></tr>
          <tr><td>Median inference time</td><td class="mono">${m.metrics.median_inference_ms != null ? Math.round(m.metrics.median_inference_ms) + " ms" : "n/a"}</td></tr></tbody></table>`
        : `<div class="empty small">No active model.</div>`}</div>
    </div>
    <div class="card" style="margin-top:14px"><h2>Recent slides</h2>
      ${slides.filter(s => s.status === "confirmed").length ? `<table><thead><tr><th>Slide</th><th>Site</th><th>AI only</th><th>Final</th><th>Time</th><th>Confirmed by</th></tr></thead><tbody>
      ${slides.filter(s => s.status === "confirmed").map(s => `<tr class="click" onclick="go('#/analyze/${s.id}')"><td><b>${esc(s.code)}</b> ${demoPill(s.demo)}</td><td>${esc(s.site || "")}</td><td>${gradePill(s.ai_grade)}</td><td>${gradePill(s.final_grade)}</td><td class="mono">${fmtDur(s.session_seconds)}</td><td class="muted">${esc(s.confirmed_by || "")}</td></tr>`).join("")}</tbody></table>`
      : `<div class="empty small">Nothing confirmed yet.</div>`}</div>`;
});

/* ---------------- Analyze ---------------- */
route("analyze", async (view, args) => {
  if (!args[0]) return analyzeStart(view);
  return analyzeSlide(view, parseInt(args[0]));
});

async function analyzeStart(view) {
  const open = await api("/api/slides?status=open&limit=20");
  const lastSite = (() => { try { return localStorage.getItem("ss_site") || ""; } catch (e) { return ""; } })();
  view.innerHTML = `
    <div class="topbar"><div><h1>Analyze a slide</h1><div class="muted small">Photograph fields at 1000x, let the model count, check its work, confirm the grade.</div></div></div>
    ${demoBanner()}
    ${S.state.active_model ? "" : `<div class="banner bad">No model is active, so nothing will be suggested yet. You can still photograph and grade by eye, or train a model first (see Dashboard).</div>`}
    <div class="grid g2">
      <div class="card"><h2>New slide</h2>
        <div class="grid" style="gap:10px">
          <label class="f">Slide ID (anonymous lab code, never a patient name)<input id="n-code" placeholder="e.g. NTRL-26-0412" autofocus></label>
          <label class="f">Site or laboratory<input id="n-site" value="${esc(lastSite)}" placeholder="e.g. NTRL Kampala"></label>
          <div class="row"><label class="f" style="flex:1">Stain<select id="n-stain"><option>Ziehl-Neelsen</option><option>Auramine</option><option>Kinyoun</option></select></label>
          <label class="f" style="flex:1">Magnification<select id="n-mag"><option>1000x</option><option>400x</option><option>630x</option></select></label></div>
          <button class="primary" id="n-go">Start slide and open camera</button>
        </div></div>
      <div class="card"><h2>Open slides</h2>
        ${open.length ? `<table><tbody>${open.map(s => `<tr class="click" onclick="go('#/analyze/${s.id}')"><td><b>${esc(s.code)}</b> ${demoPill(s.demo)}</td><td class="muted">${esc(s.site || "")}</td><td class="muted">${s.n_fields} fields</td><td><button class="sm">Resume</button></td></tr>`).join("")}</tbody></table>` : `<div class="empty small">None.</div>`}
      </div></div>`;
  $("#n-go").onclick = () => guard(async () => {
    const site = $("#n-site").value;
    try { localStorage.setItem("ss_site", site); } catch (e) {}
    const s = await api("/api/slides", { method: "POST", json: { code: $("#n-code").value, site, stain: $("#n-stain").value, magnification: $("#n-mag").value } });
    go("#/analyze/" + s.id);
  });
  $("#n-code").addEventListener("keydown", e => { if (e.key === "Enter") $("#n-go").click(); });
}

function analyzeSlide(view, sid) {
  const W = { sl: null, cur: 0, fetchedAt: 0, busy: null, drag: null };

  async function load() {
    W.sl = await api("/api/slides/" + sid);
    W.fetchedAt = performance.now();
    if (W.cur >= W.sl.fields.length) W.cur = Math.max(0, W.sl.fields.length - 1);
    draw();
  }
  const isOpen = () => W.sl.status === "open";
  const counted = d => d.status === "kept" || d.status === "added" || (d.status === "pending" && d.conf >= S.state.thresholds.positive);
  const field = () => W.sl.fields[W.cur];

  function elapsed() { return W.sl.elapsed_seconds + (isOpen() ? (performance.now() - W.fetchedAt) / 1000 : 0); }
  const tick = setInterval(() => { const e = $("#timer"); if (e && W.sl) e.textContent = fmtDur(elapsed()); }, 1000);
  S.cleanup.push(() => clearInterval(tick));

  function draw() {
    const sl = W.sl, sg = sl.suggested, f = field();
    const nb = sl.fields.map(x => x.detections.filter(counted).length);
    view.innerHTML = `
      <div class="topbar">
        <div><h1>${esc(sl.code)} ${demoPill(sl.demo)} ${sl.status === "confirmed" ? '<span class="pill teal">Confirmed</span>' : ""}</h1>
          <div class="muted small">${esc(sl.site || "No site")} &middot; ${esc(sl.stain)} &middot; ${esc(sl.magnification)} &middot; started by ${esc(sl.started_by || "")}</div></div>
        <div class="sp"></div>
        <div class="card" style="padding:8px 16px;text-align:center"><div class="tiny muted">Time on this slide</div><div class="mono" style="font-size:24px;font-weight:700" id="timer">${fmtDur(elapsed())}</div></div>
      </div>
      ${demoBanner()}
      ${W.busy ? `<div class="banner"><span class="spin"></span> ${esc(W.busy)}</div>` : ""}
      <div class="split">
        <div>
          <div class="card">
            ${f ? `<div class="viewer" id="viewer"><img id="vimg" src="/api/images/${f.id}/file" alt="Field ${f.field_no}"><canvas id="cv"></canvas></div>
              <div class="row between" style="margin-top:8px">
                <div class="small">Field ${f.field_no} of ${sl.fields.length}
                  ${f.quality_flag ? `<span class="pill warn">${esc(f.quality_flag)}</span>` : ""}
                  ${f.analysis ? `<span class="muted">&middot; model ${Math.round(f.analysis.inference_ms)} ms</span>` : `<span class="pill warn">not analysed</span>`}</div>
                <div class="tiny muted legend"><span><i style="background:#0891A0"></i>counted</span> <span><i style="background:#F79009"></i>needs a look</span> <span><i style="background:#16A34A"></i>added by you</span> <span><i style="background:#D92D20"></i>removed</span></div>
              </div>
              ${isOpen() && f.analysis ? `<div class="tiny muted" style="margin-top:4px">Tap a box to count or uncount it. Drag on the picture to add a bacillus the model missed.</div>` : ""}`
        : `<div class="empty">No fields yet. Photograph the first field below.</div>`}
          </div>
          <div class="card" style="margin-top:12px">
            <div class="row between"><h3 style="margin:0">Fields</h3>
              ${isOpen() ? `<div class="row">
                <button class="primary" id="b-cam">Take photo</button>
                <button id="b-add">Add images</button>
                <input type="file" id="in-cam" accept="image/*" capture="environment" hidden>
                <input type="file" id="in-add" accept="image/*" multiple hidden></div>` : ""}</div>
            <div class="strip" style="margin-top:8px">${sl.fields.map((x, i) => `<div class="thumb ${i === W.cur ? "on" : ""}" data-i="${i}"><img loading="lazy" src="/api/images/${x.id}/thumb?size=160"><span class="c">${nb[i]}</span>${x.quality_flag ? `<span class="q">!</span>` : ""}</div>`).join("") || `<span class="muted small">None yet</span>`}</div>
            ${isOpen() ? `<div class="drop small" id="drop" style="margin-top:8px;padding:12px">Drop field images here</div>` : ""}
          </div>
        </div>
        <div class="grid" style="gap:12px">
          <div class="card">
            <div class="tiny muted">${sl.status === "confirmed" ? "Suggestion at time of confirming" : "Suggested grade"}</div>
            ${sg.grade ? `<div class="grade ${gradeClass(sg.grade)}">${esc(gradeLabel(sg.grade))}</div>
              <div class="small" style="margin-top:6px"><b>${sg.total}</b> bacilli counted in <b>${sg.fields}</b> field${sg.fields === 1 ? "" : "s"}${sg.provisional ? ' <span class="pill warn">provisional</span>' : ""}</div>
              <div class="tiny muted" style="margin-top:4px">${esc(sg.explanation)}</div>
              ${sl.ai_only.grade !== sg.grade ? `<div class="tiny" style="margin-top:6px">Model alone would give <b>${esc(gradeLabel(sl.ai_only.grade))}</b>. Your edits changed the count.</div>` : ""}`
        : `<div class="muted" style="margin:6px 0">${W.sl.model_id || S.state.active_model ? "Add field images to get a suggestion." : "No model active."}</div>`}
          </div>
          ${isOpen() ? confirmCard(sl, sg) : doneCard(sl)}
        </div>
      </div>`;
    wire();
    paint();
  }

  function confirmCard(sl, sg) {
    const grades = ["negative", "scanty", "1+", "2+", "3+"];
    const sel = sg.grade || "negative";
    return `<div class="card"><h2>Confirm result</h2>
      <div class="grid" style="gap:10px">
        <label class="f">Final grade (your decision)
          <select id="c-grade">${grades.map(g => `<option value="${g}" ${g === sel ? "selected" : ""}>${gradeLabel(g)}</option>`).join("")}</select></label>
        <label class="f" id="c-why-wrap" hidden>Why does it differ from the suggestion?
          <textarea id="c-why" rows="2" placeholder="e.g. clumped bacilli counted as one"></textarea></label>
        <label class="f">Your usual manual time for this slide, m:ss (optional, for the time comparison)
          <input id="c-manual" placeholder="e.g. 7:30" style="width:120px"></label>
        <label class="chk"><input type="checkbox" id="c-ds"> Add these fields and my corrected boxes to the training dataset</label>
        <label class="chk" id="c-consent-wrap" hidden><input type="checkbox" id="c-consent"> I confirm that consent or an ethics waiver covers use of these images for model training, and that no patient identifiers are visible.</label>
        <button class="primary" id="c-ok" ${sl.fields.length ? "" : "disabled"}>Confirm and save</button>
        <div class="tiny muted">The app suggests, a person decides. This tool is not a validated diagnostic device.</div>
      </div></div>`;
  }

  function doneCard(sl) {
    const r = sl.reference_result;
    return `<div class="card"><h2>Result</h2>
      <div class="row"><div><div class="tiny muted">Final grade</div><div class="grade ${gradeClass(sl.final_grade)}">${esc(gradeLabel(sl.final_grade))}</div></div>
      <div><div class="tiny muted">AI alone</div><div style="font-size:18px;font-weight:700">${esc(gradeLabel(sl.ai_grade))}</div></div></div>
      <div class="small" style="margin-top:8px">Confirmed by ${esc(sl.confirmed_by)} in <b>${fmtDur(sl.session_seconds)}</b>${sl.manual_seconds ? ` (manual: ${fmtDur(sl.manual_seconds)})` : ""}</div>
      ${sl.override_reason ? `<div class="small muted">Override reason: ${esc(sl.override_reason)}</div>` : ""}
      <hr style="border:0;border-top:1px solid var(--line);margin:12px 0">
      <h3>Reference result (optional)</h3>
      <div class="tiny muted" style="margin-bottom:6px">Culture or Xpert result, so sensitivity and specificity can be measured on the Performance page.</div>
      <div class="row"><select id="r-res"><option value="">Not available</option><option value="pos" ${r === "pos" ? "selected" : ""}>Positive</option><option value="neg" ${r === "neg" ? "selected" : ""}>Negative</option></select>
      <input id="r-method" placeholder="Method (Xpert, culture)" value="${esc(sl.reference_method || "")}" style="width:150px">
      <button id="r-save">Save</button></div>
      <div style="margin-top:14px"><a class="btn primary" href="#/analyze">Next slide</a></div></div>`;
  }

  /* ----- canvas ----- */
  function paint() {
    const cv = $("#cv"), img = $("#vimg");
    if (!cv || !img) return;
    const fit = () => {
      const r = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
      cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr);
      const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, r.width, r.height);
      const f = field(); if (!f) return;
      f.detections.forEach(d => {
        const x = (d.cx - d.w / 2) * r.width, y = (d.cy - d.h / 2) * r.height, w = d.w * r.width, h = d.h * r.height;
        let col, dash = [];
        if (d.status === "removed") { col = "#D92D20"; dash = [4, 3]; }
        else if (d.status === "added") col = "#16A34A";
        else if (d.status === "kept") col = "#0891A0";
        else if (d.conf < S.state.thresholds.positive) { col = "#F79009"; dash = [4, 3]; }
        else if (d.conf < S.state.thresholds.review) col = "#F79009";
        else col = "#0891A0";
        ctx.lineWidth = 2; ctx.strokeStyle = col; ctx.setLineDash(dash);
        const pad = 3; ctx.strokeRect(x - pad, y - pad, w + 2 * pad, h + 2 * pad);
        ctx.setLineDash([]); ctx.font = "11px system-ui"; ctx.fillStyle = col;
        const label = d.status === "added" ? "added" : Math.round(d.conf * 100) + "%";
        ctx.fillText(label, x - pad, Math.max(10, y - pad - 3));
      });
      if (W.drag && W.drag.moved) {
        const a = W.drag; ctx.strokeStyle = "#16A34A"; ctx.setLineDash([5, 3]); ctx.lineWidth = 2;
        ctx.strokeRect(Math.min(a.x0, a.x1) * r.width, Math.min(a.y0, a.y1) * r.height, Math.abs(a.x1 - a.x0) * r.width, Math.abs(a.y1 - a.y0) * r.height);
      }
    };
    W.fit = fit;
    if (img.complete) fit(); else img.onload = fit;
    if (!W.ro) { W.ro = new ResizeObserver(() => W.fit && W.fit()); }
    W.ro.disconnect(); W.ro.observe(cv);
  }
  S.cleanup.push(() => W.ro && W.ro.disconnect());

  function pos(e) { const r = $("#cv").getBoundingClientRect(); return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))]; }
  function hit(x, y) {
    const f = field(); let best = null, area = 9;
    f.detections.forEach(d => {
      const m = 0.012;
      if (x >= d.cx - d.w / 2 - m && x <= d.cx + d.w / 2 + m && y >= d.cy - d.h / 2 - m && y <= d.cy + d.h / 2 + m && d.w * d.h < area) { best = d; area = d.w * d.h; }
    });
    return best;
  }

  function wire() {
    $$(".thumb").forEach(t => t.onclick = () => { W.cur = +t.dataset.i; draw(); });
    const cv = $("#cv");
    if (cv && isOpen() && field() && field().analysis) {
      cv.onpointerdown = e => { cv.setPointerCapture(e.pointerId); const [x, y] = pos(e); W.drag = { x0: x, y0: y, x1: x, y1: y, moved: false }; };
      cv.onpointermove = e => { if (!W.drag) return; const [x, y] = pos(e); W.drag.x1 = x; W.drag.y1 = y; if (Math.hypot(x - W.drag.x0, y - W.drag.y0) > 0.012) W.drag.moved = true; W.fit(); };
      cv.onpointerup = e => guard(async () => {
        const a = W.drag; W.drag = null; if (!a) return;
        if (!a.moved) {
          const d = hit(a.x0, a.y0);
          if (d) { await api("/api/detections/" + d.id, { method: "PATCH", json: { status: counted(d) ? "removed" : "kept" } }); await load(); }
          else W.fit();
        } else {
          const w = Math.abs(a.x1 - a.x0), h = Math.abs(a.y1 - a.y0);
          await api(`/api/images/${field().id}/detections`, { method: "POST", json: { cx: (a.x0 + a.x1) / 2, cy: (a.y0 + a.y1) / 2, w, h } });
          await load();
        }
      });
    }
    if (!isOpen()) {
      const sv = $("#r-save");
      if (sv) sv.onclick = () => guard(async () => { W.sl = await api(`/api/slides/${sid}/reference`, { method: "PATCH", json: { reference_result: $("#r-res").value || null, reference_method: $("#r-method").value } }); toast("Saved"); });
      return;
    }
    const upload = async files => {
      files = [...files].filter(f => f.type.startsWith("image/") || /\.(jpe?g|png|bmp|tiff?)$/i.test(f.name));
      if (!files.length) return;
      let n = 0, errs = [];
      for (const f of files) {
        n++; W.busy = `Analysing ${n} of ${files.length}...`; const b = $(".banner:not(.bad)"); if (b && b.querySelector(".spin")) b.lastChild.textContent = " " + W.busy; else draw();
        const fd = new FormData(); fd.append("files", f);
        try {
          const d = await api(`/api/slides/${sid}/fields`, { method: "POST", form: fd });
          W.sl = d; W.fetchedAt = performance.now();
          (d.upload_results || []).forEach(r => { if (r.error) errs.push(`${r.file}: ${r.error}`); });
          if (d.model_missing) errs.push("No active model: image saved but not analysed.");
        } catch (e) { errs.push(f.name + ": " + e.message); }
      }
      W.busy = null; W.cur = Math.max(0, W.sl.fields.length - 1); draw();
      if (errs.length) toast(errs[0], true);
    };
    $("#b-cam").onclick = () => $("#in-cam").click();
    $("#b-add").onclick = () => $("#in-add").click();
    $("#in-cam").onchange = e => upload(e.target.files);
    $("#in-add").onchange = e => upload(e.target.files);
    const drop = $("#drop");
    ["dragover", "dragenter"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
    ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
    drop.addEventListener("drop", e => upload(e.dataTransfer.files));

    const sg = $("#c-grade"), why = $("#c-why-wrap"), sug = W.sl.suggested.grade;
    const chk = () => { why.hidden = !(W.sl.model_id || S.state.active_model) || !sug || sg.value === sug; };
    sg.onchange = chk; chk();
    $("#c-ds").onchange = e => { $("#c-consent-wrap").hidden = !e.target.checked; };
    $("#c-ok").onclick = () => guard(async () => {
      let manual = null; const mv = $("#c-manual").value.trim();
      if (mv) { const m = mv.match(/^(\d+):(\d{1,2})$/); manual = m ? (+m[1]) * 60 + (+m[2]) : parseFloat(mv) * 60; if (isNaN(manual)) throw new Error("Enter the manual time as m:ss, e.g. 7:30"); }
      W.sl = await api(`/api/slides/${sid}/confirm`, { method: "POST", json: {
        final_grade: sg.value, override_reason: $("#c-why").value, manual_seconds: manual,
        add_to_dataset: $("#c-ds").checked, consent_confirmed: $("#c-consent") ? $("#c-consent").checked : false } });
      W.fetchedAt = performance.now(); toast("Slide confirmed in " + fmtDur(W.sl.session_seconds)); refreshState(); draw();
    });
  }
  load().catch(e => { view.innerHTML = `<div class="banner bad">${esc(e.message)}</div>`; });
}
