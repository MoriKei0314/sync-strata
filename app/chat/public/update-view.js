// 11/18 係 W9: the "Updates" sheet, opened from the start settings (setup.js). For a relay the launcher (sync.py) started.
// - "Check for updates" asks GET /m/update (sync.py update check --json): the version now, the new version, the parts that would be replaced and
//   how much would be downloaded, the release notes (when the list has them). Nothing is downloaded and nothing is replaced by a check.
//   Nothing is checked until the button is pressed (the sheet opens with only the version now).
// - "Close and update" (PC only) asks for a yes, then POST /m/update/apply: the updater starts apart from the app, closes everything the same
//   way as "stop everything", replaces the changed parts (models and settings stay) and starts the app again. A window shows the progress
//   (Windows: a console window; Linux: a terminal, or a log file when there is none). This page loses its connection a few seconds later.
// - A phone sees the check, but not the button: applying closes the app on the PC (the same rule as the phone connection setting).
// - A failure is told in words (no network, GitHub not reachable, the list is of another OS, an old update tool) with the by-hand way.
// The relay sends keys and numbers; the words are made here (tr). Loaded after ctx-settings.js. Uses h, tr, toast, openSheet, confirmSheet, I18n from the page.
"use strict";

const UpdateView = (() => {
  const MIB = 1024 ** 2;
  const size = (b) => (b >= 1024 ** 3 ? `${I18n.num(Math.round((b / 1024 ** 3) * 10) / 10)} GiB` : `${I18n.num(Math.max(1, Math.round(b / MIB)))} MiB`);
  // the parts, in words (python, node, dsh are names as they are)
  const partName = (id, name) => {
    const base = String(id).startsWith("engine") ? "engine" : id;
    const known = { shell: tr("App window"), launcher: tr("Launcher"), chat: tr("Chat screen"), engine: tr("Engine"), pack: tr("Install tools"), licenses: tr("Licenses"),
      python: "Python", node: "Node", dsh: "dsh" };
    return known[base] || name || id;
  };
  const notesText = (n) => {
    if (!n) return "";
    const s = typeof n === "string" ? n : n[I18n.lang] || n.en || Object.values(n)[0] || "";
    return String(s).trim().slice(0, 1500);
  };

  async function call(url, opts) {
    let r;
    try { r = await fetch(url, { cache: "no-store", credentials: "same-origin", ...opts }); } catch { throw new Error(tr("Cannot reach the PC")); }
    let b = {};
    try { b = await r.json(); } catch { /* not JSON */ }
    if (r.status === 401) throw new Error(tr("Failed (HTTP {0})", [401]));
    if (!r.ok && !b.kind) throw new Error(b.error || tr("Failed (HTTP {0})", [r.status]));
    return b;
  }

  function open() {
    const body = h("div", { class: "set-body" }, h("div", { class: "sheet-note muted" }, tr("Reading the settings…")));
    let now = null;        // the version now (from ?local=1)
    let res = null;        // the last check
    let busy = false;
    let started = null;    // the answer to "Close and update"

    function box(kind, ...kids) { return h("div", { class: `mem-alert ${kind}` }, ...kids); }

    function failure(r) {
      const lines = [];
      if (r.kind === "unreachable") {
        lines.push(box("warn", h("div", { class: "mem-alert-text" }, tr("Could not reach the place of new versions. Check that the PC is online.")),
          r.detail ? h("div", { class: "mem-alert-apps small" }, r.detail) : null));
        const how = [h("div", { class: "set-note muted small" }, tr("To install by hand: download the release zip (SyncStrata-<version>.zip, or -linux.zip) from the release page, put it in one of these folders, and check again."))];
        if (r.page) how.push(h("div", { class: "set-note small" }, r.page));
        for (const f of r.folders || []) how.push(h("div", { class: "set-note muted small upd-path" }, f));
        lines.push(h("div", { class: "set-group" }, ...how));
      } else if (r.kind === "old_tool") {
        lines.push(box("warn", h("div", { class: "mem-alert-text" }, tr("The update tool of this install cannot check yet. Run \"Sync-Strata update\" from the Start menu once.")),
          r.detail ? h("div", { class: "mem-alert-apps small" }, r.detail) : null));
      } else if (r.kind === "not_installed") {
        lines.push(box("warn", h("div", { class: "mem-alert-text" }, tr("The folder where Sync-Strata is installed was not found."))));
      } else if (r.kind === "bad_manifest") {
        lines.push(box("bad", h("div", { class: "mem-alert-text" }, tr("The list of versions could not be used. It is in the wrong format or for another OS.")),
          r.detail ? h("div", { class: "mem-alert-apps small" }, r.detail) : null));
      } else {
        lines.push(box("bad", h("div", { class: "mem-alert-text" }, tr("The check failed.")),
          r.detail || r.error ? h("div", { class: "mem-alert-apps small" }, r.detail || r.error) : null));
      }
      return lines;
    }

    async function apply() {
      const ok = await confirmSheet({
        title: tr("Close and update?"),
        message: tr("Sync-Strata will close and update. Chats and downloads will stop. When the update finishes, it restarts automatically. Models and settings do not change."),
        okLabel: tr("Close and update"), danger: true,
      });
      if (!ok) return;
      try {
        const r = await call(`/m/update/apply?lang=${encodeURIComponent(I18n.lang)}`, { method: "POST", headers: { "x-dsh-mobile": "1" } });
        if (!r.ok) {
          const why = r.kind === "pc_only" ? tr("Update from the PC's screen.") : r.kind === "busy" ? tr("Strata is starting or stopping. Try again in a moment.") : r.error || tr("The check failed.");
          toast(why);
          return;
        }
        started = r;
        render();
      } catch (e) { toast(e.message); }
    }

    async function check() {
      if (busy) return;
      busy = true;
      res = null;
      render();
      try { res = await call("/m/update"); } catch (e) { res = { ok: false, kind: "error", detail: e.message }; }
      busy = false;
      if (res && res.current) now = res.current;
      render();
    }

    function result() {
      const r = res;
      if (!r.ok) return failure(r);
      const out = [];
      const cur = r.current || now;
      if (!r.available) {
        out.push(box("ok", h("div", { class: "mem-alert-text" }, r.older ? tr("The uploaded version ({0}) is older than this one. Nothing to do.", [r.release]) : tr("Up to date ({0}).", [cur]))));
        return out;
      }
      if (r.kind === "zip") out.push(box("warn", h("div", { class: "mem-alert-text" }, tr("Found a release zip ({0}). You can update with it.", [r.release])),
        r.zip ? h("div", { class: "mem-alert-apps small upd-path" }, r.zip) : null));
      else out.push(box("warn", h("div", { class: "mem-alert-text" }, r.newer ? tr("A new version is available: {0} to {1}", [cur, r.release]) : tr("Same version ({0}), but some parts can be updated.", [cur]))));
      const parts = r.components || [];
      if (parts.length) {
        out.push(h("div", { class: "set-group" },
          h("div", { class: "set-label muted small" }, tr("Parts to replace")),
          ...parts.map((c) => h("div", { class: "upd-part" }, h("span", {}, partName(c.id, c.name)), h("span", { class: "muted small" }, `${c.from ? c.from + " → " : ""}${c.to} · ${size(c.download_bytes)}`))),
          h("div", { class: "set-note muted small" }, tr("To download: {0}", [size(r.download_bytes || 0)]))));
      }
      const notes = notesText(r.notes);
      if (notes) out.push(h("div", { class: "set-group" }, h("div", { class: "set-label muted small" }, tr("Release notes")), h("div", { class: "upd-notes small" }, notes)));
      return out;
    }

    function render() {
      if (started) {
        body.replaceChildren(box("ok", h("div", { class: "mem-alert-text" }, tr("The update has started. You can see the progress in the window. When it finishes, Sync-Strata restarts automatically."))),
          !started.window && started.log ? h("div", { class: "set-note muted small upd-path" }, tr("The progress is written to {0}.", [started.log])) : null);
        return;
      }
      const kids = [];
      kids.push(h("div", { class: "set-group" }, h("div", { class: "set-label muted small" }, now ? tr("Current version: {0}", [now]) : tr("Current version: {0}", ["?"]))));
      kids.push(h("button", { class: `btn wide-in ${res && res.ok && res.available ? "ghost" : "primary"}`, type: "button", disabled: busy, onclick: check },
        busy ? tr("Checking…") : tr("Check for updates")));
      if (res) kids.push(...result());
      if (res && res.ok && res.available) {
        if (res.pc) kids.push(h("button", { class: "btn wide-in primary", type: "button", onclick: apply }, tr("Close and update")));
        else kids.push(h("div", { class: "sheet-note muted" }, tr("Update from the PC's screen.")));
      }
      body.replaceChildren(...kids);
    }

    openSheet([h("div", { class: "sheet-title" }, tr("Updates")),
      h("div", { class: "sheet-note muted" }, tr("Nothing is downloaded or replaced until you press the button.")), body]);
    call("/m/update?local=1").then((b) => { if (b && b.current) now = b.current; render(); }, (e) => body.replaceChildren(h("div", { class: "sheet-note fit-warn" }, e.message)));
  }

  // for the start settings sheet: the button (small, at the end)
  function extras() {
    return [h("div", { class: "set-group ctx-open-row" }, h("button", { class: "btn slim ghost ctx-open", type: "button", onclick: () => open() }, tr("Updates")))];
  }

  return { open, extras };
})();
