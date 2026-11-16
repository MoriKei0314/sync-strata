// 11/15 夜 係 C: whether this PC can run Strata (the launcher's `sync env`), shown on the first-run guide and on the Strata
// sheet. GET /m/env gives only keys and values ({blockers:[{key, gpu|driver|vram_gib|ram_gib}], warnings:[…]}); the words are
// translated here. Blockers: "This PC is not supported." with the reasons, and the download / start buttons cannot be pressed.
// Warnings: one line each in the warning colour (nothing is stopped). Nothing at all when everything is fine, and nothing on a
// relay the launcher did not start (the everyday one answers 404).
// Loaded after setup.js. Uses h, tr from the page.
"use strict";

const EnvCheck = (() => {
  // key -> [English text (the tr key), the value that fills {0}]
  // 11/16: GTX 10・Radeon を試験的に通す改訂（launcher/sync_env.py の TEXTS と同じ）．[英語の文（tr の鍵）, 埋める値の欄…]
  const WORDS = {
    no_gpu: ["No supported GPU was found. An NVIDIA GTX 10 series or newer, or an AMD Radeon RX 6000 series or newer is needed.", []],
    gpu_too_old: ["This GPU ({0}) is not supported. An NVIDIA GTX 10 series or newer, or a Radeon RX 6000 series or newer is needed.", ["gpu"]],
    igpu_only: ["Built-in graphics ({0}) are not supported. A separate NVIDIA or Radeon graphics card is needed.", ["gpu"]],
    gpu_turing_pending: ["Support for the RTX 20 series ({0}) is still being checked.", ["gpu"]],
    driver_old: ["Please update the NVIDIA driver (now {0}; {1} or later is needed).", ["driver", "need"]],
    no_avx2: ["This CPU does not support AVX2, which is required.", []],
    gpu_untested: ["This GPU ({0}) should work, but it has not been tested yet.", ["gpu"]],
    gpu_experimental: ["Support for this GPU ({0}) is experimental. It has not been tested on a real PC.", ["gpu"]],
    vram_low: ["The GPU has only {0} GB of memory, so it may be slow (12 GB or more is recommended).", ["vram_gib"]],
    vram_unknown: ["The amount of GPU memory could not be read. Settings will be on the safe side.", []],
    ram_low: ["This PC has only {0} GB of memory, so it may be slow (32 GB or more is recommended).", ["ram_gib"]],
    no_nvidia_gpu: ["An NVIDIA GPU is required. Radeon and Intel GPUs are not supported.", []],
  };
  let state = null;      // {blockers, warnings} or null (not known / not a launcher relay)
  let asked = 0;
  let pending = null;

  function load() {
    if (pending || Date.now() - asked < 60000) return pending;
    asked = Date.now();
    pending = fetch("/m/env", { cache: "no-store", credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : null))
      .then((b) => { state = b && b.ok ? { blockers: b.blockers || [], warnings: b.warnings || [] } : null; })
      .catch(() => { /* keep what we had */ })
      .finally(() => { pending = null; });
    return pending;
  }

  function line(it) {
    const w = WORDS[it.key];
    if (!w) return null;
    const fields = Array.isArray(w[1]) ? w[1] : (w[1] ? [w[1]] : []);
    const vals = fields.map((f) => (it[f] != null ? it[f] : (f === "need" ? 580 : "?")));
    return tr(w[0], vals.map((v) => (typeof v === "number" ? I18n.num(v) : String(v))));
  }

  const blocked = () => !!(state && state.blockers.length);

  // the box: null when there is nothing to say
  function box() {
    if (!state || (!state.blockers.length && !state.warnings.length)) return null;
    const kids = [];
    if (state.blockers.length) {
      kids.push(h("div", { class: "msel-name bad" }, tr("This PC is not supported.")));
      for (const it of state.blockers) { const t = line(it); if (t) kids.push(h("div", { class: "msel-note bad" }, t)); }
    }
    for (const it of state.warnings) { const t = line(it); if (t) kids.push(h("div", { class: "msel-note fit-warn" }, t)); }
    return h("div", { class: "msel-item env-box" }, h("div", { class: "msel-text" }, kids));
  }

  // one box per place, kept just before `anchor` (redrawn on every render of that place)
  const placed = new WeakMap();
  function place(anchor, where) {
    const old = placed.get(anchor);
    const b = box();
    if (old) old.remove();
    if (b) { if (where === "prepend") anchor.prepend(b); else anchor.before(b); placed.set(anchor, b); } else placed.delete(anchor);
  }

  // the first-run guide: the box at the top of its list; when blocked, no download (or start) can be pressed
  function guide(list, all) {
    load();
    place(list, "prepend");
    if (!blocked()) return;
    all.disabled = true;
    for (const b of list.querySelectorAll(".model-acts .btn")) b.disabled = true;
  }

  // the Strata sheet: the box above the state line; when blocked, the start (or switch) button cannot be pressed.
  // Stopping a Strata that already runs stays possible.
  function strata(stateLine, btn, runningSame) {
    load();
    place(stateLine, "before");
    if (blocked() && !runningSame) btn.disabled = true;
  }

  load();
  return { load, guide, strata, blocked, state: () => state };
})();
