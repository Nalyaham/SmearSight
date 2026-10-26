/* SmearSight phone camera page. Plain JavaScript, no libraries, works over http on the lab Wi-Fi.
   Camera access uses the phone's own camera app through <input type=file capture>, so the page never
   asks for camera permission and works without https. Photos are re-drawn on a canvas before upload,
   which drops EXIF data (including GPS), and the server re-encodes them again. */
(function () {
  "use strict";
  var KEY = "ss_phone_token";
  var memToken = null;                      // used when the browser blocks localStorage
  var state = { token: null, status: null, last: null, pending: null, busy: false, rating: 0, online: true, view: "" };
  var root = document.getElementById("root"), netEl = document.getElementById("net");

  function getToken() { try { return localStorage.getItem(KEY) || memToken; } catch (e) { return memToken; } }
  function setToken(t) { memToken = t; try { if (t) localStorage.setItem(KEY, t); else localStorage.removeItem(KEY); } catch (e) {} }
  function el(h) { var d = document.createElement("div"); d.innerHTML = h; return d.firstElementChild; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }

  function api(path, opts) {
    opts = opts || {};
    var h = opts.headers || {};
    if (state.token) h["Authorization"] = "Bearer " + state.token;
    opts.headers = h;
    return fetch(path, opts).then(function (r) {
      setNet(true);
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (r.status === 401 && state.token) { setToken(null); state.token = null; state.status = null; render(); }
        if (!r.ok) { var e = new Error(j.detail || ("Error " + r.status)); e.status = r.status; throw e; }
        return j;
      });
    }, function (err) { setNet(false); var e = new Error("No connection to the lab computer. Check that the phone is on the lab Wi-Fi."); e.offline = true; throw e; });
  }
  function setNet(ok) { state.online = ok; netEl.textContent = ok ? "" : "offline"; netEl.className = "net" + (ok ? "" : " bad"); }

  /* ---------- pairing screen */
  function pairView(msg) {
    var code = (new URLSearchParams(location.search).get("code") || "").replace(/\D/g, "").slice(0, 6);
    root.innerHTML = "";
    var v = el('<div><div class="card"><h1>Connect this phone</h1>' +
      '<p class="muted">On the lab computer open <b>Analyze slide</b>, choose <b>Pair a phone</b>, then type the 6-digit code here or scan its QR code.</p>' +
      (msg ? '<div class="msg bad">' + esc(msg) + '</div>' : '') +
      '<label class="f">6-digit code<input class="code" id="code" type="tel" inputmode="numeric" autocomplete="one-time-code" maxlength="6" value="' + code + '"></label>' +
      '<label class="f">Name for this phone (optional)<input id="pname" type="text" maxlength="40" placeholder="e.g. Ward 3 Samsung"></label>' +
      '<button class="btn big" id="go">Connect</button></div>' +
      '<p class="small muted">Your photos go only to the lab computer on this Wi-Fi. Nothing is sent over the internet.</p></div>');
    root.appendChild(v);
    var go = document.getElementById("go");
    go.onclick = function () {
      var c = document.getElementById("code").value.replace(/\D/g, "");
      if (c.length !== 6) { pairView("Type all 6 digits of the code."); return; }
      go.disabled = true; go.textContent = "Connecting…";
      api("/api/phone/pair", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: c, name: document.getElementById("pname").value }) })
        .then(function (r) { setToken(r.token); state.token = r.token; history.replaceState(null, "", "/phone"); poll(true); })
        .catch(function (e) { pairView(e.message); });
    };
  }

  /* ---------- main screen */
  function mainView() {
    var s = state.status, sl = s && s.slide, L = state.last;
    var h = '<div class="card"><h2>' + esc(s ? s.device.name : "Phone") + ' <span class="pill">connected</span></h2>';
    if (!sl) {
      h += '<p class="muted">Waiting for the computer. Open a slide on the lab computer and choose this phone under <b>Capture from</b>.</p></div>';
    } else {
      var pct = Math.min(100, Math.round(100 * sl.n_fields / Math.max(1, sl.target_fields)));
      h += '<p class="big" style="margin:4px 0"><b>Slide ' + esc(sl.code) + '</b></p>' +
        '<p class="small"><span class="pill ' + sl.modality + '">' + (sl.modality === "fm" ? "Fluorescence" : "Bright-field") + '</span> ' +
        esc(sl.stain) + ', ' + esc(sl.magnification) + '</p>' +
        '<p class="small" style="margin-bottom:0">' + sl.n_fields + ' field' + (sl.n_fields === 1 ? '' : 's') + ' taken (a full reading is ' + sl.target_fields + ')</p>' +
        '<div class="bar"><i style="width:' + pct + '%"></i></div></div>';
      if (state.pending) h += pendingBlock();
      else h += resultBlock(L) + captureButtons(sl);
      if (s.tips && s.tips.length) h += '<div class="card small"><b>Tips</b><ul class="tips">' + s.tips.map(function (t) { return "<li>" + esc(t) + "</li>"; }).join("") + '</ul></div>';
    }
    h += feedbackBlock() + '<button class="btn link" id="forget">Remove this phone from the lab computer</button>';
    root.innerHTML = h;
    wire();
  }
  function captureButtons(sl) {
    return '<label class="btn big" for="cam">Take photo of field ' + (sl.n_fields + 1) + '</label>' +
      '<input id="cam" class="vh" type="file" accept="image/*" capture="environment">' +
      '<label class="btn alt" for="gal">Choose from gallery</label>' +
      '<input id="gal" class="vh" type="file" accept="image/*">';
  }
  function resultBlock(L) {
    if (!L) return "";
    if (L.kind === "ok") return '<div class="msg ok">✓ Field ' + L.field_no + ' saved. ' + (L.message && L.message !== "Saved." ? esc(L.message) : "") + '</div>';
    if (L.kind === "err") return '<div class="msg bad">' + esc(L.message) + '</div>';
    return "";
  }
  function pendingBlock() {
    var p = state.pending, h = '<div class="card"><img class="preview" alt="Photo preview" src="' + p.url + '">';
    if (p.stage === "sending") h += '<p>Sending to the lab computer…</p>';
    else if (p.stage === "retake") h += '<div class="msg warn">' + esc(p.message) + '</div><button class="btn" id="retake">Retake</button><button class="btn warn" id="force">Use this photo anyway</button>';
    else if (p.stage === "failed") h += '<div class="msg bad">' + esc(p.message) + '</div><button class="btn" id="again">Try sending again</button><button class="btn link" id="drop">Discard this photo</button>';
    return h + '</div>';
  }
  function feedbackBlock() {
    var f = state.fbDone ? '<p class="msg ok">Thank you for the feedback.</p>' :
      '<div class="stars" id="stars">' + [1, 2, 3, 4, 5].map(function (i) { return '<button data-n="' + i + '" class="' + (state.rating >= i ? "on" : "") + '" aria-label="' + i + ' of 5">★</button>'; }).join("") + '</div>' +
      (state.rating ? '<textarea id="fbtext" placeholder="What was hard or easy? (optional)"></textarea><button class="btn alt" id="fbsend">Send feedback</button>' : "");
    return '<div class="card"><b>How easy was this?</b><div class="small muted">Helps us improve the app.</div>' + f + '</div>';
  }
  function wire() {
    ["cam", "gal"].forEach(function (id) {
      var i = document.getElementById(id); if (i) i.onchange = function () { if (i.files && i.files[0]) handle(i.files[0]); i.value = ""; };
    });
    var x;
    if ((x = document.getElementById("retake"))) x.onclick = function () { clearPending(); render(); };
    if ((x = document.getElementById("drop"))) x.onclick = function () { clearPending(); render(); };
    if ((x = document.getElementById("force"))) x.onclick = function () { send(state.pending, true); };
    if ((x = document.getElementById("again"))) x.onclick = function () { send(state.pending, state.pending.force); };
    if ((x = document.getElementById("forget"))) x.onclick = function () {
      if (!confirm("Remove this phone? It will stop sending photos until you pair it again.")) return;
      api("/api/phone/forget", { method: "POST" }).catch(function () {}).then(function () { setToken(null); state.token = null; state.status = null; render(); });
    };
    var st = document.getElementById("stars");
    if (st) st.onclick = function (e) { var n = +(e.target.getAttribute && e.target.getAttribute("data-n")); if (n) { state.rating = n; render(); } };
    if ((x = document.getElementById("fbsend"))) x.onclick = function () {
      api("/api/phone/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating: state.rating, comment: (document.getElementById("fbtext") || {}).value || "", context: "phone page" }) })
        .then(function () { state.fbDone = true; render(); }).catch(function (e) { alert(e.message); });
    };
  }
  function clearPending() { if (state.pending && state.pending.url) URL.revokeObjectURL(state.pending.url); state.pending = null; }

  /* ---------- photo handling */
  function shrink(file, maxSide) {
    return new Promise(function (resolve) {
      function draw(src, w, h) {
        var s = Math.min(1, maxSide / Math.max(w, h)), c = document.createElement("canvas");
        c.width = Math.round(w * s); c.height = Math.round(h * s);
        c.getContext("2d").drawImage(src, 0, 0, c.width, c.height);
        c.toBlob(function (b) { resolve(b || file); }, "image/jpeg", 0.9);
      }
      try {
        if (window.createImageBitmap) {
          createImageBitmap(file, { imageOrientation: "from-image" }).then(function (bm) { draw(bm, bm.width, bm.height); }, fallback);
        } else fallback();
      } catch (e) { fallback(); }
      function fallback() {
        var img = new Image(), u = URL.createObjectURL(file);
        img.onload = function () { draw(img, img.naturalWidth, img.naturalHeight); URL.revokeObjectURL(u); };
        img.onerror = function () { URL.revokeObjectURL(u); resolve(file); };
        img.src = u;
      }
    });
  }
  function handle(file) {
    clearPending();
    shrink(file, 1600).then(function (blob) {
      state.pending = { blob: blob, url: URL.createObjectURL(blob), stage: "sending", force: false };
      render();
      send(state.pending, false);
    });
  }
  function send(p, force) {
    p.stage = "sending"; p.force = !!force; render();
    var fd = new FormData();
    fd.append("file", p.blob, "field.jpg");
    if (force) fd.append("force", "1");
    api("/api/phone/upload", { method: "POST", body: fd }).then(function (r) {
      if (r.retake) { p.stage = "retake"; p.message = r.message; render(); return; }
      state.last = { kind: "ok", field_no: r.field_no, message: r.message };
      clearPending(); poll(true);
      if (navigator.vibrate) try { navigator.vibrate(40); } catch (e) {}
    }).catch(function (e) {
      if (e.offline) { p.stage = "failed"; p.message = e.message; render(); return; }
      state.last = { kind: "err", message: e.message }; clearPending(); render();
    });
  }

  /* ---------- status polling */
  var timer = null;
  function poll(now) {
    clearTimeout(timer);
    if (!state.token) return;
    api("/api/phone/status").then(function (s) { state.status = s; if (!state.pending || state.pending.stage !== "sending") render(); })
      .catch(function () { render(); });
    timer = setTimeout(poll, document.hidden ? 15000 : 4000);
  }
  function render() {
    if (!state.token) { if (state.view !== "pair") { pairView(); state.view = "pair"; } return; }
    state.view = "main";
    if (!state.status) { root.innerHTML = '<p class="muted">Connecting…</p>'; return; }
    mainView();
  }
  document.addEventListener("visibilitychange", function () { if (!document.hidden) poll(true); });
  state.token = getToken();
  if (state.token) poll(true); else render();
})();
