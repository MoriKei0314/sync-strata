// 11/15 app1115: the start settings, the first-run guide and "stop" choices, for a relay the launcher (sync.py) started.
// - The settings sheet: the model, quality or speed, the RAM limit and the VRAM kept free, each "automatic" by default. They are
//   the launcher's settings.json (GET/POST /m/settings) and take effect at the next start.
// - The first-run guide opens by itself when /m/models says first_run (no model, or a shared part missing): what to download,
//   how big, the free space, and the buttons. It downloads one item after another ("Download all").
// - "Stop": Strata only, or everything (this page then loses its connection too).
// strata.js (loaded before) gives Models, loadModels, modelsPost, fmtGiB, fmtSpeed, fmtLeft, startStrata, stopStrata.
"use strict";

const Setup = (() => {
  // --- settings ---
  async function settingsCall(body) {
    let r;
    try {
      r = await fetch("/m/settings", body
        ? { method: "POST", headers: { "x-dsh-mobile": "1", "content-type": "application/json" }, credentials: "same-origin", cache: "no-store", body: JSON.stringify(body) }
        : { cache: "no-store", credentials: "same-origin" });
    } catch {
      throw new Error(tr("Cannot reach the PC"));
    }
    let b = {};
    try { b = await r.json(); } catch { /* not JSON */ }
    if (!r.ok || !b.ok) throw new Error(b.error || tr("Failed (HTTP {0})", [r.status]));
    return b;
  }

  function openSettingsSheet() {
    const body = h("div", { class: "set-body" }, h("div", { class: "sheet-note muted" }, tr("Reading the settings…")));
    const note = h("div", { class: "sheet-note muted" }, tr("Takes effect from the next start."));
    let cur = null;
    const choice = (label, name, options, help) => h("div", { class: "set-group" },
      h("div", { class: "set-label muted small" }, label),
      h("div", { class: "set-choices" }, options.map(([v, text]) => h("button", {
        class: `chip${String(cur.settings[name]) === String(v) ? " on" : ""}`, type: "button",
        "aria-pressed": String(cur.settings[name]) === String(v) ? "true" : "false",
        onclick: () => save({ [name]: v }),
      }, text))),
      help ? h("div", { class: "set-note muted small" }, help) : null);
    // a number: "automatic" or the value (tap it to type another)
    const number = (label, name, unit, help, placeholder) => {
      const v = cur.settings[name];
      const custom = v !== "auto";
      const ask = () => openPrompt({
        title: label, value: custom ? String(v) : "", placeholder, okLabel: tr("Save"), note: help,
        onSubmit: async (text) => { await save({ [name]: text.replace(/[^\d.]/g, "") }); },
      });
      return h("div", { class: "set-group" },
        h("div", { class: "set-label muted small" }, label),
        h("div", { class: "set-choices" },
          h("button", { class: `chip${custom ? "" : " on"}`, type: "button", "aria-pressed": custom ? "false" : "true", onclick: () => save({ [name]: "auto" }) }, tr("Automatic")),
          h("button", { class: `chip${custom ? " on" : ""}`, type: "button", "aria-pressed": custom ? "true" : "false", onclick: ask },
            custom ? `${I18n.num(v)} ${unit}` : tr("Set a value…"))),
        h("div", { class: "set-note muted small" }, help));
    };
    function render() {
      if (!cur) return;
      if (cur.settings && cur.settings.ram_squeeze == null) cur.settings.ram_squeeze = "auto";   // 11/16: not set = the default, on
      // 11/16 本人: the phone connection moved out of here to its own icon on the session list (Remote.openSheet)
      const models = (cur.models || []).map((m) => (typeof m === "string" ? [m, (modelOf(m) || {}).name || m] : [m.id, m.name || m.id]));
      body.replaceChildren(
        choice(tr("Model"), "model", [["auto", tr("Automatic")], ...models], tr("Automatic: the model that suits this PC")),
        // 11/15 本人: 起動時の tail skip は R4・R7・R10（自動＝この PC に推奨の方）．API を別のソフトから使うときだけ効く
        choice(tr("Tail skip at start"), "tail_skip", [["auto", tr("Automatic")], ...[4, 7, 10].map((r) => [r, Spec.v && Spec.v.recommended_r === r ? `${rLabel(r)} · ${tr("Recommended for this PC")}` : rLabel(r)])],
          tr("Applies only when another program uses the API.")),
        number(tr("RAM limit"), "ram_max_gib", "GiB", tr("Automatic: follows the free RAM"), "20"),
        number(tr("VRAM kept free"), "vram_reserve_mib", "MiB", tr("Automatic"), "1024"),
        // 11/16 係 S4・G2 (本人の決めた文): ram_squeeze = auto（既定．「入」と見せる）か off（「切」）．起動・モデルの切り替えのとき 1 回だけ，
        // ほかのアプリのメモリを追い出して（アプリは閉じない）モデルに回す．
        choice(tr("Memory push-out"), "ram_squeeze", [["auto", tr("Push out")], ["off", tr("Leave alone")]],
          tr("When starting or switching models, other apps' memory is pushed out and given to the model. No apps are closed.")));
      if (typeof CtxSettings !== "undefined") body.append(...CtxSettings.extras());   // 11/15 係 C
    }
    async function save(change) {
      try {
        cur = await settingsCall(change);
        toast(tr("Saved. It takes effect at the next start"));
      } catch (e) {
        toast(e.message);
        throw e;
      }
      render();
    }
    openSheet([h("div", { class: "sheet-title" }, tr("Start settings")), note, body]);
    (Spec.v ? Promise.resolve() : Spec.load()).then(() => settingsCall(null)).then((b) => { cur = b; render(); }, (e) => body.replaceChildren(h("div", { class: "sheet-note fit-warn" }, e.message)));
  }

  // --- stop: Strata only, or everything ---
  function openStopSheet() {
    const sh = openSheet([h("div", { class: "sheet-title" }, tr("Stop")),
      sheetItem("power", tr("Stop Strata"), async () => { sh.close(true); try { await stopStrata(); } catch (e) { toast(e.message); } }),
      sheetItem("stop", tr("Stop everything (this page also disconnects)"), async () => {
        sh.close(true);
        const ok = await confirmSheet({
          title: tr("Stop everything?"),
          message: tr("To use it again, start it on the PC."),
          okLabel: tr("Stop everything"), danger: true,
        });
        if (!ok) return;
        try {
          const r = await fetch("/m/shutdown?what=all", { method: "POST", headers: { "x-dsh-mobile": "1" }, credentials: "same-origin", cache: "no-store" });
          const b = await r.json().catch(() => ({}));
          if (!r.ok || !b.ok) throw new Error(b.error || tr("Failed (HTTP {0})", [r.status]));
          toast(tr("Stopping everything"));
        } catch (e) { toast(e.message); }
      }, "bad"),
      h("button", { class: "btn wide-in ghost", type: "button", onclick: () => sh.close() }, tr("Cancel"))]);
  }

  // --- the first-run guide ---
  let guideOpen = false;
  function openGuide() {
    if (guideOpen) return;
    guideOpen = true;
    const list = h("div", { class: "msel-group" });
    const free = h("div", { class: "sheet-note muted" });
    const title = h("div", { class: "sheet-title" }, tr("Download a model"));
    const intro = h("div", { class: "sheet-note muted" }, tr("Once the download finishes, Strata can start."));
    const all = h("button", { class: "btn wide-in primary", type: "button" }, tr("Download all"));
    const later = h("button", { class: "btn wide-in ghost", type: "button" }, tr("Later"));
    // 11/15 係 C: the Hugging Face token field (after saving, the download that failed for a private model starts again)
    const hfBox = typeof HfToken !== "undefined" ? HfToken.box(() => { const x = items().find((i) => i.download && i.download.error_kind === "auth"); if (x) act(() => modelsPost("download", x.id)); }) : null;
    let auto = false;
    let closed = false;
    let timer = null;

    // what is missing: the recommended model (or the one being downloaded), then the shared parts
    function items() {
      const L = Models.list;
      if (!L) return [];
      const out = [];
      const ms = (L.models || []).filter((m) => !m.pending);   // 11/15: 準備中のモデルは案内に出さない
      const haveModel = ms.some((m) => m.local.complete);
      const rec = ms.find((m) => m.recommended) || ms[0];
      const busy = ms.find((m) => m.download && DL_ACTIVE.includes(m.download.state));
      const m = busy || (!haveModel ? rec : null);
      if (m && !m.local.complete) out.push({ ...m, kind: "model", downloadable: true });
      for (const x of L.shared || []) if (!x.local.complete) out.push({ ...x, kind: "shared" });
      return out;
    }
    function row(x) {
      const d = x.download;
      const active = d && DL_ACTIVE.includes(d.state);
      const left = x.local.total_bytes - x.local.have_bytes;
      const lines = [h("div", { class: "msel-note" }, x.kind === "model"
        ? tr("Model · {0} to download", [fmtGiB(left)]) + (x.recommended ? tr(" · recommended for this PC") : "")
        : (x.optional ? tr("Shared part (optional) · {0}", [fmtGiB(left)]) : tr("Shared part · {0}", [fmtGiB(left)])))];
      const acts = [];
      if (active) {
        const pct = d.state === "verifying" && d.verify && d.verify.total_bytes ? Math.floor((100 * d.verify.done_bytes) / d.verify.total_bytes)
          : d.total_bytes ? Math.floor((100 * (d.done_bytes || 0)) / d.total_bytes) : 0;
        const fill = h("div", { class: "ctx-fill" });
        fill.style.width = `${pct}%`;
        lines.push(h("div", { class: "ctx-bar dl-bar" }, fill),
          h("div", { class: "msel-note dl-text" }, d.state === "verifying" ? tr("Checking the files {0}%", [pct])
            : [`${pct}%`, fmtSpeed(d.speed_bps), fmtLeft(d.eta_s)].filter(Boolean).join(" · ")));
        acts.push(h("button", { class: "btn slim ghost", type: "button", onclick: () => act(() => { auto = false; return modelsPost("cancel", x.id); }) }, tr("Stop the download")));
      } else if (!x.downloadable) {
        lines.push(h("div", { class: "msel-note fit-warn" }, tr("The download source is not set.")));
      } else {
        if (d && d.state === "failed" && d.error) lines.push(h("div", { class: "msel-note fit-warn" }, d.error));
        const resume = x.local.have_bytes + x.local.partial_bytes > 0;
        acts.push(h("button", { class: "btn slim primary", type: "button", disabled: !!(Models.list && Models.list.active),
          onclick: () => act(() => modelsPost("download", x.id)) }, resume ? tr("Resume the download") : tr("Download ({0})", [fmtGiB(left)])));
      }
      return h("div", { class: "msel-item strata-model" }, h("div", { class: "msel-text" },
        h("div", { class: "msel-name" }, x.name), lines, acts.length ? h("div", { class: "model-acts" }, acts) : null));
    }
    async function act(fn) {
      try { await fn(); } catch (e) { toast(e.message); }
      await loadModels();
      render();
    }
    function render() {
      const L = Models.list;
      if (!L) return;
      const xs = items();
      if (!L.first_run && !xs.some((x) => !x.optional)) {
        // ready: offer the start
        title.textContent = tr("Ready");
        intro.textContent = tr("Strata can start now.");
        list.replaceChildren();
        free.textContent = "";
        all.textContent = tr("Start Strata");
        all.disabled = !!(Store.S.strata && Store.S.strata.online);
        if (typeof EnvCheck !== "undefined") EnvCheck.guide(list, all);   // 11/15 係 C env: not supported -> no start
        all.onclick = () => {
          const m = (L.models || []).find((x) => x.recommended && x.local.complete) || (L.models || []).find((x) => x.local.complete);
          const r = (Spec.v && Spec.v.recommended_r) || m.default_r || 7;   // 11/15: この PC に推奨の R（R4 か R7）
          if (m) startStrata(m.preset, { model: m.id, r, name: `${m.name} ${rLabel(r)}` }).catch((e) => toast(e.message));
          sh.close();
        };
        return;
      }
      list.replaceChildren(...xs.map(row));
      if (hfBox) { list.append(hfBox.el); hfBox.need(xs.some((x) => x.download && x.download.state === "failed" && x.download.error_kind === "auth")); }   // 11/15 係 C
      const need = xs.filter((x) => x.downloadable).reduce((a, x) => a + (x.local.total_bytes - x.local.have_bytes), 0);
      const fb = (xs[0] && xs[0].free_bytes) ?? L.free_bytes;
      free.textContent = fb != null ? tr("Free space: {0} (to download: {1})", [fmtGiB(fb), fmtGiB(need)]) : tr("To download: {0}", [fmtGiB(need)]);
      free.classList.toggle("fit-warn", fb != null && fb < need + 2 * GIB);
      all.textContent = auto ? tr("Downloading one after another…") : tr("Download all");
      all.disabled = auto || !xs.some((x) => x.downloadable);
      all.onclick = () => { auto = true; next(); render(); };
      if (typeof EnvCheck !== "undefined") EnvCheck.guide(list, all);   // 11/15 係 C env: not supported -> no download
    }
    async function next() {
      const L = Models.list;
      if (!auto || !L || L.active) return;
      const x = items().find((i) => i.downloadable && !(i.download && i.download.state === "failed"));
      if (!x) { auto = false; return; }
      try { await modelsPost("download", x.id); } catch (e) { toast(e.message); auto = false; }
    }
    async function poll() {
      if (!Spec.v) await Spec.load();   // 11/15: 「Strata を起動」は，この PC に推奨の R で
      await loadModels();
      if (closed) return;
      await next();
      render();
      timer = setTimeout(poll, Models.list && Models.list.active ? 1000 : 3000);
    }
    later.onclick = () => sh.close();
    const sh = openSheet([title, intro, list, free, all, later], {
      onClose: () => { closed = true; guideOpen = false; clearTimeout(timer); try { sessionStorage.setItem("dsh-setup-later", "1"); } catch { /* private */ } },
    });
    render();
    poll();
  }

  // opens the guide once per page load, when logged in and the relay says first_run (not again after "Later" in this tab)
  let asked = false;
  async function maybeGuide() {
    if (asked || Store.S.conn !== "online") return;
    asked = true;
    try { if (sessionStorage.getItem("dsh-setup-later")) return; } catch { /* private */ }
    await loadModels();
    if (Models.list && Models.list.first_run) openGuide();
  }
  Store.on((topic) => { if (topic === "conn") maybeGuide(); });
  setTimeout(maybeGuide, 1500);

  return { openSettingsSheet, openStopSheet, openGuide, settingsCall, launcher: () => !!(Models.list && Models.list.launcher) };
})();
