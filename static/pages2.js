/* Review, Dataset, Training, Performance, Settings */

/* ---------------- Expert review ---------------- */
route("review", async (view, args) => {
  const R = { tab: "open" };
  async function load() {
    const d = await api("/api/review?status=" + (R.tab === "all" ? "all" : R.tab));
    const me = reader();
    const todo = d.items.filter(i => !i.my_vote && (i.status === "open" || (i.status === "disputed" && ["senior", "lead"].includes(d.role))));
    const cur = todo[0];
    view.innerHTML = `
      <div class="topbar"><div><h1>Expert review</h1>
        <div class="muted small">Low-confidence detections wait here. Two readers must agree before a box is counted or removed; disagreements go to a senior reader or the lab lead.</div></div></div>
      <div class="tabs"><a data-t="open" class="${R.tab === "open" ? "on" : ""}">Open (${d.counts.open})</a><a data-t="disputed" class="${R.tab === "disputed" ? "on" : ""}">Disputed (${d.counts.disputed})</a></div>
      <div class="banner ok" style="${d.counts.resolved ? "" : "display:none"}">${d.counts.resolved} item${d.counts.resolved === 1 ? "" : "s"} resolved so far.</div>
      ${cur ? `<div class="split"><div class="card" style="text-align:center">
          <img class="crop" id="rv-img" src="/api/review/${cur.id}/crop?t=${cur.id}" alt="Candidate">
          <div class="small muted" style="margin-top:6px">Model confidence <b>${Math.round(cur.conf * 100)}%</b> &middot; slide ${esc(cur.slide_code || "n/a")} &middot; ${cur.n_votes} vote${cur.n_votes === 1 ? "" : "s"} so far${cur.status === "disputed" ? ' &middot; <span class="pill warn">readers disagreed</span>' : ""}</div></div>
        <div class="card"><h2>Is this an acid-fast bacillus?</h2>
          <p class="small muted">The box is drawn on the picture. Look for a slender, slightly curved red rod on the blue background, and decide on the rod itself.</p>
          <div class="grid" style="gap:8px">
            <button class="primary" data-v="afb">Yes, AFB <span class="kbd">A</span></button>
            <button data-v="not_afb">No, not AFB <span class="kbd">N</span></button>
            <button data-v="unsure">Not sure <span class="kbd">U</span></button></div>
          <div class="tiny muted" style="margin-top:10px">${todo.length} waiting for you as ${esc(me)}. To get the second vote, switch the reader (left menu).</div></div></div>`
        : `<div class="card"><div class="empty">${d.items.length ? `Nothing left for ${esc(me)} to vote on. Items that already have your vote are waiting for another reader.` : "The queue is empty."}</div></div>`}
      ${d.items.length ? `<div class="card" style="margin-top:14px"><h3>In the queue</h3><table><thead><tr><th></th><th>Slide</th><th>Confidence</th><th>Status</th><th>Votes</th></tr></thead><tbody>
        ${d.items.slice(0, 30).map(i => `<tr><td><img src="/api/review/${i.id}/crop" width="46" height="46" style="border-radius:6px;object-fit:cover"></td><td>${esc(i.slide_code || "")}</td><td class="mono">${Math.round(i.conf * 100)}%</td><td>${i.status === "disputed" ? '<span class="pill warn">disputed</span>' : '<span class="pill">open</span>'}</td><td class="small muted">${i.voters.map(esc).join(", ") || "none"}</td></tr>`).join("")}</tbody></table></div>` : ""}`;
    $$(".tabs a").forEach(a => a.onclick = () => { R.tab = a.dataset.t; load(); });
    $$("[data-v]").forEach(b => b.onclick = () => vote(cur, b.dataset.v));
    R.cur = cur;
  }
  async function vote(cur, v) {
    if (!cur) return;
    await guard(async () => {
      const r = await api(`/api/review/${cur.id}/vote`, { method: "POST", json: { vote: v } });
      toast(r.resolution ? "Resolved: " + r.resolution.replace("_", " ") : "Vote recorded; waiting for a second reader");
      await refreshState(); await load();
    });
  }
  const key = e => {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;
    const m = { a: "afb", n: "not_afb", u: "unsure" }[e.key.toLowerCase()];
    if (m && R.cur) vote(R.cur, m);
  };
  document.addEventListener("keydown", key);
  S.cleanup.push(() => document.removeEventListener("keydown", key));
  await load();
});

/* ---------------- Dataset ---------------- */
route("dataset", async view => {
  const D = { filter: "", offset: 0, mod: (() => { try { return localStorage.getItem("ss_dmod") || "zn"; } catch (e) { return "zn"; } })() };
  const PAGE = 48;
  async function load() {
    const q = new URLSearchParams({ limit: PAGE, offset: D.offset, modality: D.mod });
    if (D.filter === "quality") q.set("quality", 1); else if (D.filter === "pos") q.set("positive", "yes"); else if (D.filter === "neg") q.set("positive", "no"); else if (D.filter) q.set("status", D.filter);
    const [st, imgs, vers] = await Promise.all([api("/api/dataset/stats?modality=" + D.mod), api("/api/images?" + q), api("/api/datasets")]);
    const p = st.preview;
    const flt = [["", "All"], ["unlabelled", "Unlabelled"], ["labelled", "Labelled"], ["verified", "Verified"], ["excluded", "Excluded"], ["pos", "With AFB"], ["neg", "No AFB"], ["quality", "Quality flagged"]];
    view.innerHTML = `
      <div class="topbar"><div><h1>Dataset</h1><div class="muted small">Images, labels and frozen versions used for training. Only consented, two-reader-verified images are used by default. Bright-field and fluorescence images are kept apart because each has its own model.</div></div><div class="sp"></div>
        <div class="tabs" style="margin:0"><a data-m="zn" class="${D.mod === "zn" ? "on" : ""}">Bright-field</a><a data-m="fm" class="${D.mod === "fm" ? "on" : ""}">Fluorescence</a></div></div>
      <div class="grid g4" style="margin-bottom:14px">
        <div class="card stat"><div class="n">${st.total}</div><div class="l">Images</div><div class="d">${st.synthetic} synthetic demo</div></div>
        <div class="card stat"><div class="n">${st.verified}</div><div class="l">Verified (2 readers)</div><div class="d">${st.labelled} waiting for a second reader</div></div>
        <div class="card stat"><div class="n">${st.unlabelled}</div><div class="l">Unlabelled</div><div class="d">${st.excluded} excluded</div></div>
        <div class="card stat"><div class="n">${st.quality_flagged}</div><div class="l">Quality flagged</div><div class="d">${st.consent_pending} without consent</div></div>
      </div>
      <div class="grid g3" style="margin-bottom:14px;align-items:start">
        <div class="card"><h2>Upload images</h2>
          <div class="drop small" id="up-drop">Drop smear field images here or click to choose</div>
          <input type="file" id="up-file" accept="image/*" multiple hidden>
          <label class="f" style="margin-top:8px">Site<input id="up-site" placeholder="e.g. NTRL Kampala"></label>
          <label class="chk" style="margin-top:8px"><input type="checkbox" id="up-consent"> Consent or ethics waiver covers training use; no patient identifiers are visible</label>
          <div class="tiny muted" style="margin-top:4px">Without this box ticked images are stored but cannot be used for training.</div></div>
        <div class="card"><h2>Import labelled data</h2>
          <p class="small muted">A .zip with <code>images/</code> and <code>labels/</code> folders in YOLO format (class 0 = AFB). A second reader still verifies them.</p>
          <input type="file" id="yz-file" accept=".zip"><label class="chk" style="margin-top:8px"><input type="checkbox" id="yz-consent"> Consent confirmed for this data</label>
          <button style="margin-top:8px" id="yz-go">Import zip</button></div>
        <div class="card"><h2>Demo images (${D.mod === "fm" ? "fluorescence" : "bright-field"})</h2>
          <p class="small muted">Generates synthetic smear-like pictures with known labels so you can try the full train and review workflow. Models trained on these are marked <span class="pill demo">DEMO</span> and must never be used clinically.</p>
          <div class="row"><input type="number" id="sy-n" value="120" min="8" max="400" style="width:90px"><button id="sy-go">Generate demo images</button></div></div>
      </div>
      <div class="card" style="margin-bottom:14px"><div class="row between"><h2 style="margin:0">Freeze a dataset version</h2></div>
        <p class="small muted" style="margin-top:4px">Freezing copies the eligible images into a fixed train, validation and test split. The split is made by slide, so pictures from one slide never appear in both training and test. The test set is only used to judge a finished model.</p>
        <div class="row" style="margin-bottom:8px"><label class="chk"><input type="checkbox" id="fz-single"> Also use single-reader labels (not recommended)</label>
          <label class="chk"><input type="checkbox" id="fz-syn" checked> Include synthetic demo images</label></div>
        <div id="fz-prev" class="small"></div>
        <div class="row" style="margin-top:8px"><input id="fz-name" placeholder="Version name (optional)" style="width:240px"><button class="primary" id="fz-go">Freeze version</button></div>
        ${vers.length ? `<table style="margin-top:12px"><thead><tr><th>Version</th><th>Created</th><th>Train / val / test</th><th></th></tr></thead><tbody>${vers.map(v => `<tr><td><b>v${v.id}</b> ${esc(v.name)} ${modPill(v.modality)} ${demoPill(v.includes_synthetic)}</td><td class="muted">${fmtDate(v.created_at)}</td><td class="mono">${v.n_train} / ${v.n_val} / ${v.n_test}</td><td><a class="btn sm" href="#/training/${v.id}">Train on this</a></td></tr>`).join("")}</tbody></table>` : ""}</div>
      <div class="card"><div class="row between"><h2 style="margin:0">Image library</h2><div class="tiny muted">${imgs.total} images</div></div>
        <div class="tabs" style="margin-top:8px">${flt.map(f => `<a data-f="${f[0]}" class="${D.filter === f[0] ? "on" : ""}">${f[1]}</a>`).join("")}</div>
        ${imgs.items.length ? `<div class="imggrid">${imgs.items.map(i => `<div class="imgcell" data-id="${i.id}"><img loading="lazy" src="/api/images/${i.id}/thumb?size=240"><div class="m"><span>${i.status === "verified" ? "verified" : i.status}${i.synthetic ? " (demo)" : ""}</span><span>${i.n_boxes} box${i.n_boxes == 1 ? "" : "es"}</span></div></div>`).join("")}</div>
        <div class="row between" style="margin-top:10px"><button class="sm" id="pg-prev" ${D.offset ? "" : "disabled"}>Previous</button><span class="tiny muted">${D.offset + 1} to ${Math.min(D.offset + PAGE, imgs.total)} of ${imgs.total}</span><button class="sm" id="pg-next" ${D.offset + PAGE < imgs.total ? "" : "disabled"}>Next</button></div>`
        : `<div class="empty small">No images match.</div>`}</div>`;

    const refreshPrev = async () => {
      const pv = await api(`/api/datasets/preview?modality=${D.mod}&include_single_read=${$("#fz-single").checked ? 1 : 0}&include_synthetic=${$("#fz-syn").checked ? 1 : 0}`);
      $("#fz-prev").innerHTML = `<b>${pv.images}</b> eligible images (${pv.positive_images} with AFB, ${pv.negative_images} without) from <b>${pv.groups}</b> slides.` + (pv.images < 12 ? ' <span class="pill warn">need at least 12</span>' : "");
    };
    $("#fz-single").onchange = refreshPrev; $("#fz-syn").onchange = refreshPrev; refreshPrev();
    $("#fz-go").onclick = () => guard(async () => {
      const r = await api("/api/datasets/freeze", { method: "POST", json: { modality: D.mod, name: $("#fz-name").value, include_single_read: $("#fz-single").checked, include_synthetic: $("#fz-syn").checked } });
      toast(`Version v${r.id} frozen: ${r.n_train} train, ${r.n_val} val, ${r.n_test} test`); load();
    });
    $("#sy-go").onclick = () => guard(async () => {
      $("#sy-go").disabled = true; $("#sy-go").textContent = "Generating...";
      const r = await api("/api/synthetic", { method: "POST", json: { modality: D.mod, count: +$("#sy-n").value, seed: Math.floor(Math.random() * 900) + 1 } });
      toast(r.made + " demo images created"); load();
    }).then(() => { const b = $("#sy-go"); if (b) { b.disabled = false; b.textContent = "Generate demo images"; } });
    const drop = $("#up-drop"), inp = $("#up-file");
    const up = files => guard(async () => {
      const fd = new FormData(); [...files].forEach(f => fd.append("files", f));
      fd.append("site", $("#up-site").value); fd.append("consent", $("#up-consent").checked ? 1 : 0); fd.append("modality", D.mod);
      drop.textContent = "Uploading...";
      const r = await api("/api/images/upload", { method: "POST", form: fd });
      toast(`${r.added} added, ${r.skipped} duplicates${r.errors.length ? ", " + r.errors.length + " rejected" : ""}`, r.errors.length > 0 && r.added == 0); load();
    });
    drop.onclick = () => inp.click(); inp.onchange = () => up(inp.files);
    ["dragover", "dragenter"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
    ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
    drop.addEventListener("drop", e => up(e.dataTransfer.files));
    $("#yz-go").onclick = () => guard(async () => {
      const f = $("#yz-file").files[0]; if (!f) throw new Error("Choose a .zip file first.");
      const fd = new FormData(); fd.append("file", f); fd.append("modality", D.mod); fd.append("consent", $("#yz-consent").checked ? 1 : 0); fd.append("site", $("#up-site").value);
      const r = await api("/api/import/yolo", { method: "POST", form: fd }); toast(`Imported ${r.added}, skipped ${r.skipped}`); load();
    });
    $$("[data-m]").forEach(a => a.onclick = () => { D.mod = a.dataset.m; D.filter = ""; D.offset = 0; try { localStorage.setItem("ss_dmod", D.mod); } catch (e) {} load(); });
    $$("[data-f]").forEach(a => a.onclick = () => { D.filter = a.dataset.f; D.offset = 0; load(); });
    const pp = $("#pg-prev"), pn = $("#pg-next");
    if (pp) pp.onclick = () => { D.offset = Math.max(0, D.offset - PAGE); load(); };
    if (pn) pn.onclick = () => { D.offset += PAGE; load(); };
    $$(".imgcell").forEach(c => c.onclick = () => editor(+c.dataset.id, load));
  }
  await load();
});

async function editor(iid, done) {
  const im = await api("/api/images/" + iid);
  let boxes = im.annotations.map(a => ({ cx: a.cx, cy: a.cy, w: a.w, h: a.h }));
  let drag = null, negative = im.status !== "unlabelled" && !boxes.length;
  const me = reader();
  const m = modal(`
    <div class="row between"><h2 style="margin:0">Image ${im.id} ${im.synthetic ? '<span class="pill demo">DEMO</span>' : ""}</h2><button class="sm" id="e-x">Close</button></div>
    <div class="small muted" style="margin:4px 0 10px">Status <b>${esc(im.status)}</b>${im.last_labelled_by ? " &middot; labelled by " + esc(im.last_labelled_by) : ""} &middot; ${im.width}x${im.height}${im.quality_flag ? ` &middot; <span class="pill warn">${esc(im.quality_flag)}</span>` : ""} &middot; consent ${im.consent ? "yes" : "<b>no</b>"}</div>
    <div class="split" style="grid-template-columns:minmax(0,1fr) 260px">
      <div><div class="viewer" id="e-view"><img id="e-img" src="/api/images/${im.id}/file"><canvas id="e-cv"></canvas></div>
        <div class="tiny muted" style="margin-top:4px">Drag to draw a box around each bacillus. Click a box to delete it.</div></div>
      <div class="grid" style="gap:10px;align-content:start">
        <div class="card" style="box-shadow:none"><div class="tiny muted">Boxes</div><div class="grade" id="e-n" style="font-size:30px">${boxes.length}</div>
          <label class="chk" style="margin-top:8px"><input type="checkbox" id="e-neg" ${negative ? "checked" : ""}> Checked: no AFB in this image</label>
          <button class="primary" id="e-save" style="margin-top:8px;width:100%">Save labels as ${esc(me)}</button>
          <button id="e-clear" style="margin-top:6px;width:100%">Clear boxes</button></div>
        <div class="card" style="box-shadow:none"><div class="tiny muted" style="margin-bottom:6px">Second reader</div>
          <button id="e-ver" style="width:100%" ${im.status === "labelled" ? "" : "disabled"}>Verify these labels as ${esc(me)}</button>
          <div class="tiny muted" style="margin-top:4px">A different reader from the one who labelled it.</div></div>
        <div class="row"><button class="sm" id="e-ex">Exclude</button>${im.consent ? "" : '<button class="sm" id="e-con">Confirm consent</button>'}<button class="sm danger" id="e-del">Delete</button></div>
      </div></div>`, true);
  const cv = $("#e-cv", m), img = $("#e-img", m);
  const paint = () => {
    const r = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    cv.width = r.width * dpr; cv.height = r.height * dpr;
    const c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0); c.lineWidth = 2;
    boxes.forEach(b => { c.strokeStyle = "#16A34A"; c.strokeRect((b.cx - b.w / 2) * r.width - 3, (b.cy - b.h / 2) * r.height - 3, b.w * r.width + 6, b.h * r.height + 6); });
    if (drag && drag.moved) { c.strokeStyle = "#F79009"; c.setLineDash([5, 3]); c.strokeRect(Math.min(drag.x0, drag.x1) * r.width, Math.min(drag.y0, drag.y1) * r.height, Math.abs(drag.x1 - drag.x0) * r.width, Math.abs(drag.y1 - drag.y0) * r.height); c.setLineDash([]); }
    $("#e-n", m).textContent = boxes.length;
  };
  img.onload = paint; if (img.complete) paint(); new ResizeObserver(paint).observe(cv);
  const pos = e => { const r = cv.getBoundingClientRect(); return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))]; };
  cv.onpointerdown = e => { cv.setPointerCapture(e.pointerId); const [x, y] = pos(e); drag = { x0: x, y0: y, x1: x, y1: y, moved: false }; };
  cv.onpointermove = e => { if (!drag) return; const [x, y] = pos(e); drag.x1 = x; drag.y1 = y; if (Math.hypot(x - drag.x0, y - drag.y0) > 0.01) drag.moved = true; paint(); };
  cv.onpointerup = () => {
    const a = drag; drag = null; if (!a) return;
    if (a.moved) boxes.push({ cx: (a.x0 + a.x1) / 2, cy: (a.y0 + a.y1) / 2, w: Math.abs(a.x1 - a.x0), h: Math.abs(a.y1 - a.y0) });
    else { const i = boxes.findIndex(b => Math.abs(a.x0 - b.cx) <= b.w / 2 + 0.012 && Math.abs(a.y0 - b.cy) <= b.h / 2 + 0.012); if (i >= 0) boxes.splice(i, 1); }
    paint();
  };
  const fin = () => { m.close(); done && done(); };
  $("#e-x", m).onclick = fin;
  $("#e-clear", m).onclick = () => { boxes = []; paint(); };
  $("#e-save", m).onclick = () => guard(async () => {
    const neg = $("#e-neg", m).checked;
    if (!boxes.length && !neg) throw new Error("Draw at least one box, or tick 'no AFB in this image'.");
    if (boxes.length && neg) throw new Error("You drew boxes, so untick 'no AFB'.");
    await api(`/api/images/${iid}/annotations`, { method: "PUT", json: { boxes, negative: neg } }); toast("Labels saved"); fin();
  });
  $("#e-ver", m).onclick = () => guard(async () => { await api(`/api/images/${iid}/verify`, { method: "POST" }); toast("Verified"); fin(); });
  $("#e-ex", m).onclick = () => guard(async () => { await api(`/api/images/${iid}/exclude`, { method: "POST" }); fin(); });
  const con = $("#e-con", m); if (con) con.onclick = () => guard(async () => { await api(`/api/images/${iid}/consent`, { method: "POST" }); toast("Consent recorded"); fin(); });
  $("#e-del", m).onclick = () => { if (confirm("Delete this image permanently?")) guard(async () => { await api("/api/images/" + iid, { method: "DELETE" }); fin(); }); };
}

/* ---------------- Training ---------------- */
route("training", async (view, args) => {
  let timer = null;
  S.cleanup.push(() => clearInterval(timer));
  async function load() {
    const [vers, runs, models] = await Promise.all([api("/api/datasets"), api("/api/training"), api("/api/models")]);
    const active = runs.find(r => r.status === "running" || r.status === "queued");
    const sel = args[0] ? +args[0] : (vers[0] && vers[0].id);
    const approvers = S.state.readers.filter(r => ["senior", "lead"].includes(r.role));
    
    const hist = active ? active.history : (runs[0] ? runs[0].history : []);
    view.innerHTML = `
      <div class="topbar"><div><h1>Model training</h1><div class="muted small">Trains a YOLOv8 nano detector on this computer. A new model is only a candidate until a senior reader approves it.</div></div></div>
      ${demoBanner()}
      <div class="grid g2" style="margin-bottom:14px;align-items:start">
        <div class="card"><h2>Start a run</h2>
          ${vers.length ? `<div class="grid" style="gap:10px">
            <label class="f">Dataset version<select id="t-ds">${vers.map(v => `<option value="${v.id}" ${v.id === sel ? "selected" : ""}>v${v.id} ${esc(v.name)} (${v.n_train}/${v.n_val}/${v.n_test}) ${v.modality === "fm" ? "FLUORESCENCE" : "bright-field"}${v.includes_synthetic ? " DEMO" : ""}</option>`).join("")}</select></label>
            <div class="row"><label class="f">Epochs<input id="t-ep" type="number" value="30" min="1" max="300" style="width:90px"></label>
              <label class="f">Image size<select id="t-sz"><option>512</option><option>640</option><option>416</option></select></label>
              <label class="f">Batch<input id="t-b" type="number" value="8" min="1" max="64" style="width:80px"></label>
              <label class="f">Start from<select id="t-base"><option value="auto">Pretrained if available</option><option value="scratch">Scratch</option></select></label></div>
            <button class="primary" id="t-go" ${active ? "disabled" : ""}>Start training</button>
            <div class="tiny muted">On a laptop CPU, about 30 to 40 seconds per epoch for 100 images. Training keeps running if you leave this page.</div></div>`
        : `<div class="empty small">Freeze a dataset version first (Dataset page).</div>`}</div>
        <div class="card"><h2>${active ? "Run " + active.id + " in progress" : "Latest run"}</h2>
          ${active ? `<div class="small">${esc(active.message || "")}</div><div class="bar" style="margin:8px 0"><i style="width:${active.epochs ? Math.round(100 * active.epoch / active.epochs) : 0}%"></i></div>
            <div class="row between"><span class="small mono">Epoch ${active.epoch} of ${active.epochs}</span><button class="sm danger" id="t-cancel">Cancel</button></div>`
        : runs[0] ? `<div class="small">${statusPill(runs[0].status)} ${esc(runs[0].message || "")}</div>${runs[0].error ? `<pre class="tiny" style="white-space:pre-wrap;color:var(--red);max-height:120px;overflow:auto">${esc(runs[0].error)}</pre>` : ""}` : `<div class="empty small">No runs yet.</div>`}
          ${hist.length ? `<div style="margin-top:10px">${lineChart([
            { name: "train box loss", color: "#0891A0", points: hist.map(h => [h.epoch, h.train_box]) },
            { name: "validation box loss", color: "#B54708", points: hist.map(h => [h.epoch, h.val_box]) }], { yfmt: v => v.toFixed(2), h: 170 })}</div>` : ""}</div>
      </div>
      <div class="card"><h2>Models</h2>
        ${models.length ? `<table><thead><tr><th>Model</th><th>Test images</th><th>Sens.</th><th>Spec.</th><th>PPV</th><th>NPV</th><th>mAP50</th><th>Time</th><th>Status</th><th></th></tr></thead><tbody>
          ${models.map(m => `<tr><td><b>${esc(m.name)}</b> ${modPill(m.modality)} ${demoPill(m.demo)}<div class="tiny muted">dataset v${m.dataset_version_id} &middot; ${fmtDate(m.created_at)}</div></td>
            <td class="mono">${m.metrics.test_images ?? "n/a"}</td><td class="mono">${pct(m.metrics.sensitivity)}</td><td class="mono">${pct(m.metrics.specificity)}</td><td class="mono">${pct(m.metrics.ppv)}</td><td class="mono">${pct(m.metrics.npv)}</td>
            <td class="mono">${m.metrics.map50 != null ? m.metrics.map50.toFixed(3) : "n/a"}</td><td class="mono">${m.metrics.median_inference_ms != null ? Math.round(m.metrics.median_inference_ms) + " ms" : "n/a"}</td>
            <td>${m.status === "active" ? '<span class="pill teal">active</span>' : `<span class="pill">${esc(m.status)}</span>`}</td>
            <td style="white-space:nowrap"><button class="sm" data-co="${m.id}">Cut-offs</button> ${m.status !== "active" ? `<button class="sm" data-p="${m.id}">${m.status === "archived" ? "Roll back to this" : "Approve and activate"}</button>` : ""}</td></tr>`).join("")}</tbody></table>
          <div class="tiny muted" style="margin-top:8px">Image-level figures are measured on test slides the model never saw, at the count cut-off in use (bright-field ${S.state.thresholds_by_modality.zn.positive}, fluorescence ${S.state.thresholds_by_modality.fm.positive}). With few test images they carry wide uncertainty; PPV and NPV also depend on how many test images contain AFB. Open <i>Cut-offs</i> to see every threshold. Approval is blocked if sensitivity is lower than the active model of the same microscopy type.</div>
          <div class="row" style="margin-top:10px"><label class="f">Approver<select id="p-by">${approvers.map(a => `<option ${a.name === reader() ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select></label></div>`
        : `<div class="empty small">No models yet.</div>`}</div>
      ${runs.length > 1 ? `<div class="card" style="margin-top:14px"><h3>Run history</h3><table><tbody>${runs.map(r => `<tr><td>Run ${r.id}</td><td>${statusPill(r.status)}</td><td class="muted small">dataset v${r.dataset_version_id}, ${r.params.epochs} epochs</td><td class="muted small">${fmtDate(r.started_at)} by ${esc(r.started_by || "")}</td></tr>`).join("")}</tbody></table></div>` : ""}`;
    const go = $("#t-go");
    if (go) go.onclick = () => guard(async () => {
      await api("/api/training/start", { method: "POST", json: { dataset_version_id: +$("#t-ds").value, epochs: +$("#t-ep").value, imgsz: +$("#t-sz").value, batch: +$("#t-b").value, base: $("#t-base").value } });
      toast("Training started"); load();
    });
    const ca = $("#t-cancel"); if (ca) ca.onclick = () => guard(async () => { await api(`/api/training/${active.id}/cancel`, { method: "POST" }); load(); });
    $$("[data-co]").forEach(b => b.onclick = () => guard(() => showCutoffs(+b.dataset.co)));
    $$("[data-p]").forEach(b => b.onclick = () => guard(async () => {
      await api(`/api/models/${b.dataset.p}/promote`, { method: "POST", json: { approved_by: $("#p-by").value } });
      toast("Model is now active"); await refreshState(); load();
    }));
    clearInterval(timer);
    if (active) timer = setInterval(() => { if (location.hash.startsWith("#/training")) load(); }, 4000);
  }
  await load();
});
const statusPill = s => `<span class="pill ${s === "completed" ? "neg" : s === "failed" ? "pos" : s === "running" ? "teal" : ""}">${esc(s)}</span>`;

/* ---------------- Performance ---------------- */
route("performance", async view => {
  const P = { days: 0, demo: 0, mod: "" };
  async function load() {
    const d = await api(`/api/performance?days=${P.days}&include_demo=${P.demo}&modality=${P.mod}`);
    const tp = (c, k) => { const t = c.targets && c.targets[k]; if (!t || t.status === "no_data") return ""; const cls = { met: "met", point: "point", not_met: "notmet" }[t.status], txt = { met: "meets target", point: "at target, interval too wide", not_met: "below target" }[t.status]; return `<span class="pill ${cls}" title="Target ${Math.round(t.target * 100)}%">${txt}</span>`; };
    const cm = (name, c) => `<div class="card"><h2>${name}</h2>
      ${c.n_with_reference ? `<table><tbody><tr><td>Slides with a reference result</td><td class="mono">${c.n_with_reference}</td></tr>
        <tr><td>Sensitivity</td><td class="mono"><b>${pct(c.sensitivity)}</b> ${ci(c.sens_ci)} ${tp(c, "sensitivity")}</td></tr>
        <tr><td>Specificity</td><td class="mono"><b>${pct(c.specificity)}</b> ${ci(c.spec_ci)} ${tp(c, "specificity")}</td></tr>
        <tr><td>Positive predictive value</td><td class="mono"><b>${pct(c.ppv)}</b> ${ci(c.ppv_ci)} ${tp(c, "ppv")}</td></tr>
        <tr><td>Negative predictive value</td><td class="mono"><b>${pct(c.npv)}</b> ${ci(c.npv_ci)} ${tp(c, "npv")}</td></tr>
        <tr><td>True pos / false pos</td><td class="mono">${c.tp} / ${c.fp}</td></tr><tr><td>False neg / true neg</td><td class="mono">${c.fn} / ${c.tn}</td></tr></tbody></table>
        ${c.adjusted && c.adjusted.ppv != null ? `<div class="tiny muted" style="margin-top:8px">At ${(c.adjusted.prevalence * 100).toFixed(1)}% positives among people tested (Settings), these would give PPV <b>${pct(c.adjusted.ppv, 0)}</b> (${pct(c.adjusted.ppv_range[0], 0)} to ${pct(c.adjusted.ppv_range[1], 0)}) and NPV <b>${pct(c.adjusted.npv, 1)}</b> (${pct(c.adjusted.npv_range[0], 1)} to ${pct(c.adjusted.npv_range[1], 1)}).</div>` : ""}
        <div class="tiny muted" style="margin-top:4px">"Meets target" needs the lower end of the 95% interval at or above the target. PPV and NPV depend on how common positives are in this sample.</div>`
        : `<div class="empty small">Add reference results (culture or Xpert) on confirmed slides to see this. Positive <i>and</i> negative slides need one, or NPV cannot be measured.</div>`}</div>`;
    view.innerHTML = `
      <div class="topbar"><div><h1>Performance</h1><div class="muted small">Time per slide and accuracy against reference results, with 95% confidence intervals.</div></div><div class="sp"></div>
        <select id="p-mod"><option value="">All microscopy</option><option value="zn">Bright-field</option><option value="fm">Fluorescence</option></select>
        <select id="p-days"><option value="0">All time</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option></select>
        <label class="chk"><input type="checkbox" id="p-demo" ${P.demo ? "checked" : ""}> Include demo data</label>
        <a class="btn" href="/api/export/slides.csv?include_demo=${P.demo}">Export CSV</a></div>
      <div class="grid g4" style="margin-bottom:14px">
        <div class="card stat"><div class="n">${d.slides}</div><div class="l">Confirmed slides</div></div>
        <div class="card stat"><div class="n">${fmtDur(d.median_seconds)}</div><div class="l">Median time (app)</div><div class="d">90th percentile ${fmtDur(d.p90_seconds)}</div></div>
        <div class="card stat"><div class="n">${fmtDur(d.manual_median_seconds)}</div><div class="l">Median time (manual)</div><div class="d">${d.manual_n} slides with a manual time</div></div>
        <div class="card stat"><div class="n">${d.with_ai ? Math.round(100 * d.overrides / d.with_ai) + "%" : "n/a"}</div><div class="l">Grades changed by reader</div><div class="d">${d.overrides} of ${d.with_ai}</div></div>
      </div>
      ${d.slides ? "" : `<div class="banner">No confirmed slides in this view yet. Analyse and confirm slides first${P.demo ? "" : " (demo data is hidden)"}.</div>`}
      <div class="grid g2" style="margin-bottom:14px">
        <div class="card"><h2>Time per slide</h2>${barChart(d.histogram.map(h => ({ label: h.label, value: h.count })))}</div>
        <div class="card"><h2>Median time by week (seconds)</h2>${lineChart([
          { name: "with app", color: "#0891A0", points: d.trend.map((t, i) => [i + 1, Math.round(t.app)]) },
          { name: "manual", color: "#B54708", points: d.trend.map((t, i) => [i + 1, t.manual != null ? Math.round(t.manual) : null]) }], { ymin: 0 })}
          <div class="tiny muted">${d.trend.map((t, i) => `${i + 1} = ${esc(t.week)} (n=${t.n})`).join(" &middot; ")}</div></div>
      </div>
      <div class="grid g2" style="margin-bottom:14px">${cm("Model alone vs reference", d.ai)}${cm("After reader confirmation vs reference", d.assisted)}</div>
      <div class="grid g2">
        <div class="card"><h2>Model speed</h2><table><tbody><tr><td>Median inference per field</td><td class="mono">${d.inference_median_ms != null ? Math.round(d.inference_median_ms) + " ms" : "n/a"}</td></tr>
          <tr><td>90th percentile</td><td class="mono">${d.inference_p90_ms != null ? Math.round(d.inference_p90_ms) + " ms" : "n/a"}</td></tr></tbody></table></div>
        <div class="card"><h2>By site</h2>${d.by_site.length ? `<table><thead><tr><th>Site</th><th>Slides</th><th>Median time</th><th>Changed</th><th>Sensitivity</th></tr></thead><tbody>${d.by_site.map(s => `<tr><td>${esc(s.site)}</td><td class="mono">${s.slides}</td><td class="mono">${fmtDur(s.median_seconds)}</td><td class="mono">${s.overrides}/${s.with_ai}</td><td class="mono">${s.sensitivity != null ? pct(s.sensitivity, 0) + ` (n=${s.positives_with_reference})` : "n/a"}</td></tr>`).join("")}</tbody></table>` : `<div class="empty small">No data.</div>`}</div>
      </div>`;
    $("#p-days").value = P.days; $("#p-mod").value = P.mod;
    $("#p-mod").onchange = e => { P.mod = e.target.value; load(); };
    $("#p-days").onchange = e => { P.days = +e.target.value; load(); };
    $("#p-demo").onchange = e => { P.demo = e.target.checked ? 1 : 0; load(); };
  }
  await load();
});

/* ---------------- Settings ---------------- */
route("settings", async view => {
  const [audit] = await Promise.all([api("/api/audit?limit=100")]);
  const s = S.state;
  view.innerHTML = `
    <div class="topbar"><div><h1>Settings, phones and audit</h1></div></div>
    <div id="v2-extras"></div>
    <div class="grid g2" style="margin-bottom:14px;align-items:start">
      <div class="card"><h2>Readers</h2>
        <table><tbody>${s.readers.map(r => `<tr><td>${esc(r.name)}</td><td><span class="pill">${esc(r.role)}</span></td></tr>`).join("")}</tbody></table>
        <div class="row" style="margin-top:10px"><input id="rd-name" placeholder="Name"><select id="rd-role"><option value="technician">technician</option><option value="reader">reader</option><option value="senior">senior</option><option value="lead">lead</option></select><button id="rd-add">Add or update</button></div>
        <div class="tiny muted" style="margin-top:6px">Senior readers and the lab lead resolve disputed review items and approve models. Pick who you are in the left menu.</div></div>
      <div class="card"><h2>Data and safety</h2>
        <table><tbody><tr><td>Access PIN</td><td>${s.pin_enabled ? "On" : '<span class="pill warn">Off</span> (start with <code>python run.py --lan --pin 1234</code> before sharing on Wi-Fi)'}</td></tr>
        <tr><td>Hide detections below</td><td class="mono">${s.thresholds.floor}</td></tr></tbody></table>
        <div style="margin-top:10px"><a class="btn" href="/api/backup.zip">Download full backup</a></div>
        <div class="tiny muted" style="margin-top:6px">Backup contains images, models and the database. Store it somewhere safe and follow your ethics approval for data handling.</div></div>
    </div>
    <div class="card"><h2>Important limits</h2>
      <p class="small">SmearSight assists a trained reader; it does not replace one, and it is not a validated diagnostic device. Before any use on real patient slides it needs a prospective evaluation against culture or Xpert at your own laboratory, ethics approval, and sign-off by the laboratory lead. Models trained on demo images say nothing about real smears.</p></div>
    <div class="card" style="margin-top:14px"><h2>Audit log</h2><div style="max-height:380px;overflow:auto"><table><thead><tr><th>When</th><th>Who</th><th>Action</th><th>Detail</th></tr></thead><tbody>
      ${audit.map(a => `<tr><td class="small muted" style="white-space:nowrap">${fmtDate(a.ts)}</td><td>${esc(a.reader)}</td><td><code>${esc(a.action)}</code></td><td class="small muted">${esc(a.detail)}</td></tr>`).join("")}</tbody></table></div></div>`;
  guard(() => settingsExtras($("#v2-extras")));
  $("#rd-add").onclick = () => guard(async () => { await api("/api/readers", { method: "POST", json: { name: $("#rd-name").value, role: $("#rd-role").value } }); toast("Saved"); await refreshState(); render(); });
});
