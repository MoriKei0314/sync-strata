// 11/15 係 C: two small additions to the start settings, for a relay the launcher (sync.py) started.
// - CtxSettings: a "Context settings" button in the start settings; it opens its own sheet with the max context length and
//   the conversation memory (K/V) quantization, each "automatic" by default. GET /m/ctx (sync.py ctx --json) gives the
//   values, what "automatic" picks on this PC (marked "Recommended") and, when Strata runs, how far it fits; saving goes
//   through POST /m/settings like the other start settings. Takes effect from the next start.
// - HfToken: the Hugging Face read token for a private model. GET /m/hf-token says only whether one is saved (never the
//   token); POST /m/hf-token?action=set|clear saves it in this app's own place or removes it. The field is a password
//   field, cleared after saving. Shown in the first-run guide, under a download that failed for a private model, and as a
//   one-line "saved / remove" row in the start settings.
// Loaded after setup.js. Uses h, tr, toast, openSheet, I18n from the page.
"use strict";

const CtxSettings = (() => {
  const label = (n) => `${Math.round(n / 1024)}K`;

  async function call(url, body) {
    let r;
    try {
      r = await fetch(url, body
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

  function open() {
    const body = h("div", { class: "set-body" }, h("div", { class: "sheet-note muted" }, tr("Reading the settings…")));
    let cur = null;
    // 11/15 夜: each choice shows what pair it would give with the other side as set now (cur.preview, from sync ctx):
    // "ok" plain, "warn" marked tight, "block" not pressable. "Recommended" = what automatic picks with the other side as set.
    const chips = (name, list, setting) => h("div", { class: "set-choices" }, list.map(([v, text]) => {
      const p = (cur.preview && cur.preview[name] && cur.preview[name][String(v)]) || { status: "ok" };
      const autoPick = cur.preview && cur.preview[name] && cur.preview[name].auto;
      const on = String(setting) === String(v);
      const rec = v !== "auto" && autoPick && String(v) === String(autoPick[name]);
      const block = p.status === "block" && !on;
      const b = h("button", { class: `chip${on ? " on" : ""}`, type: "button", "aria-pressed": on ? "true" : "false", disabled: block,
        "aria-disabled": block ? "true" : "false", onclick: () => { if (!block) save({ [name]: v }); } },
        rec ? `${text} · ${tr("Recommended")}` : p.status === "warn" && v !== "auto" ? `${text} · ${tr("Tight")}` : text);
      if (block) { b.style.opacity = "0.35"; b.style.cursor = "not-allowed"; }
      else if (p.status === "warn" && v !== "auto" && !on) b.style.borderColor = "var(--warn)";
      return b;
    }));
    function render() {
      if (!cur) return;
      const c = cur.context;
      const k = cur.kv_format;
      const kids = [
        h("div", { class: "set-group" },
          h("div", { class: "set-label muted small" }, tr("Max context length")),
          chips("context", [["auto", tr("Automatic")], ...c.choices.map((n) => [n, label(n)])], c.setting),
          h("div", { class: "set-note muted small" }, tr("Longer takes more VRAM."))),
        h("div", { class: "set-group" },
          h("div", { class: "set-label muted small" }, tr("Quantization")),
          chips("kv_format", [["auto", tr("Automatic")], ...k.choices.map((x) => [x.value, x.label])], k.setting),
          h("div", { class: "set-note muted small" }, tr("Accuracy and VRAM use both go k8 > k8v4 > k4."))),
      ];
      // only while the settings are the ones Strata runs with (after a change, the number belongs to the old start).
      // The engine's own number, when it gave one, comes before the estimate below.
      const same = cur.running && cur.running.context === c.effective && cur.running.kv_format === k.effective;
      if (cur.kv_limit && same) kids.push(h("div", { class: "sheet-note fit-warn ctx-limit" }, tr("On this PC: up to about {0} tokens.", [I18n.num(cur.kv_limit)])));
      else if (cur.status === "warn") kids.push(h("div", { class: "sheet-note fit-warn ctx-limit" }, tr("Tight on VRAM. It can slow down as the chat gets long.")));
      const anyBlock = Object.values(cur.preview || {}).some((g) => Object.values(g).some((p) => p.status === "block"));
      if (anyBlock) kids.push(h("div", { class: "sheet-note muted small" }, tr("Grayed-out choices don't fit this PC's VRAM.")));
      body.replaceChildren(...kids);
    }
    async function load() {
      cur = await call("/m/ctx");
      render();
    }
    async function save(change) {
      try {
        await call("/m/settings", change);
        toast(tr("Saved. It takes effect at the next start"));
        await load();
      } catch (e) { toast(e.message); }
    }
    openSheet([h("div", { class: "sheet-title" }, tr("Context settings")),
      h("div", { class: "sheet-note muted" }, tr("Takes effect from the next start.")), body]);
    load().catch((e) => body.replaceChildren(h("div", { class: "sheet-note fit-warn" }, e.message)));
  }

  // for the start settings sheet: the button (small, at the end), then the token row
  function extras() {
    const btn = h("button", { class: "btn slim ghost ctx-open", type: "button", onclick: () => open() }, tr("Context settings"));
    return [h("div", { class: "set-group ctx-open-row" }, btn), HfToken.settingsRow()];
  }

  return { open, extras };
})();

const HfToken = (() => {
  let state = null;          // {available, set} or null while unknown
  const listeners = new Set();
  const changed = () => { for (const f of listeners) f(); };

  async function load() {
    try {
      const r = await fetch("/m/hf-token", { cache: "no-store", credentials: "same-origin" });
      const b = await r.json().catch(() => ({}));
      state = r.ok && b.ok ? { available: !!b.available, set: !!b.set } : { available: false, set: false };
    } catch { state = state || { available: false, set: false }; }
    changed();
    return state;
  }

  async function post(action, token) {
    let r;
    try {
      r = await fetch(`/m/hf-token?action=${action}`, { method: "POST", headers: { "x-dsh-mobile": "1", "content-type": "application/json" },
        credentials: "same-origin", cache: "no-store", body: JSON.stringify(token ? { token } : {}) });
    } catch {
      throw new Error(tr("Cannot reach the PC"));
    }
    const b = await r.json().catch(() => ({}));
    if (!r.ok || !b.ok) throw new Error(b.error || tr("Failed (HTTP {0})", [r.status]));
    state = { available: true, set: !!b.set };
    changed();
    return b;
  }

  // the field: a password box and Save; once saved, "Token saved" and Remove. onSaved runs after a save (to retry a download).
  function box(onSaved) {
    const input = h("input", { class: "text-input mono", type: "password", placeholder: "hf_…", maxlength: 200, autocomplete: "off",
      autocapitalize: "off", spellcheck: "false", enterkeyhint: "done", "aria-label": tr("Hugging Face token") });
    const ok = h("button", { class: "btn slim primary", type: "button" }, tr("Save"));
    const err = h("div", { class: "msel-note fit-warn hidden" });
    const editRow = h("div", { class: "hf-row" }, input, ok);
    const savedRow = h("div", { class: "hf-row" }, h("span", { class: "msel-note ok-note" }, tr("Token saved")),
      h("button", { class: "btn slim ghost", type: "button", onclick: () => remove() }, tr("Delete")));
    const el = h("div", { class: "msel-item hf-box hidden" }, h("div", { class: "msel-text" },
      h("div", { class: "msel-name" }, tr("Hugging Face token")),
      h("div", { class: "msel-note" }, tr("Needed for a private model. A read-only token is enough.")),
      editRow, savedRow, err));
    let needed = false;
    function paint() {
      const s = state;
      el.classList.toggle("hidden", !s || !s.available);
      if (!s) return;
      editRow.classList.toggle("hidden", s.set && !needed);
      savedRow.classList.toggle("hidden", !s.set);
      el.classList.toggle("need", needed);   // the failure itself is the download's own message just above
    }
    async function submit() {
      const v = input.value.trim();
      if (!v || ok.disabled) return;
      ok.disabled = true;
      err.classList.add("hidden");
      try {
        await post("set", v);
        input.value = "";
        needed = false;
        toast(tr("The token was saved"));
        paint();
        if (onSaved) onSaved();
      } catch (e) {
        err.textContent = e.message;
        err.classList.remove("hidden");
      }
      ok.disabled = false;
    }
    async function remove() {
      try { await post("clear"); toast(tr("The token was removed")); } catch (e) { toast(e.message); }
      paint();
    }
    ok.addEventListener("click", submit);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); submit(); } });
    listeners.add(paint);
    if (!state) load(); else paint();
    // need(true): a download failed because the model is private (mark the box, and show the field even when a token is saved)
    return { el, need: (v) => { if (needed !== !!v) { needed = !!v; paint(); } } };
  }

  // one box per model id in the Strata sheet (the same node every render, so typing is kept)
  const inl = new Map();
  function inline(id, onSaved) {
    if (!inl.has(id)) inl.set(id, box(onSaved));
    const b = inl.get(id);
    b.need(true);
    return b.el;
  }

  // the start settings: one line, whether a token is saved, and Remove (the value is never shown)
  function settingsRow() {
    const text = h("span", { class: "muted small" });
    const rm = h("button", { class: "btn slim ghost", type: "button", onclick: async () => {
      try { await post("clear"); toast(tr("The token was removed")); } catch (e) { toast(e.message); }
    } }, tr("Delete"));
    const el = h("div", { class: "set-group hf-set hidden" }, h("div", { class: "set-label muted small" }, tr("Hugging Face token")),
      h("div", { class: "hf-row" }, text, rm));
    const paint = () => {
      const s = state;
      el.classList.toggle("hidden", !s || !s.available);
      if (!s) return;
      text.textContent = s.set ? tr("Token saved") : tr("No token");
      rm.classList.toggle("hidden", !s.set);
    };
    listeners.add(paint);
    load();
    return el;
  }

  return { load, box, inline, settingsRow, state: () => state };
})();
