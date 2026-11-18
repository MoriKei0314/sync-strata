// 11/17 係 W5: the "Memory" box in the Strata sheet — how much memory the other apps hold, at a glance.
// GET /m/sysmem (sync.py mem --json) gives numbers and keys only; the words are made here (tr), so the PC window and the phone read the same.
//   - three bars (RAM, Windows commit, VRAM): Sync-Strata's share | other apps | free
//   - on Windows, the part of Sync-Strata's RAM that is just file pages read through the file mapping is drawn lighter ("File reads (reclaimable)"):
//     Windows takes it back when another app asks, so it is not counted as taken (the launcher also counts it in the usable free RAM for its warnings)
//   - warnings (orange / red) that name the apps behind them: the model's RAM was cut by the commit, part of the model stays on the SSD,
//     VRAM is taken by other apps
//   - the other apps that hold the most (commit on Windows, RAM on Linux) and how much more of the model would fit in RAM if one were closed
// Nothing is closed from here; it only shows. Nothing is drawn on a relay the launcher did not start (the answer is 404) or when not logged in.
// While the box is on the screen it asks every 5 s (once the sheet is closed it stops). Loaded after env-check.js. Uses h, tr, I18n from the page.
"use strict";

const MemView = (() => {
  const num = (x) => I18n.num(Math.round(x * 10) / 10);
  const gib = (x) => num(x == null ? 0 : x);
  const list = (apps, k) => apps.map((a) => `${a.name} ${gib(a[k] != null ? a[k] : a.gib)} GiB`).join(", ");

  // one bar: Sync-Strata | other apps | free.  mine === null: the split is not known, so everything in use is "in use"
  function barRow(label, total, mine, others, free, recl) {
    const pct = (x) => `${Math.max(0, Math.min(100, (100 * x) / total))}%`;
    const bar = h("div", { class: "mem-bar" });
    const known = mine != null;
    const seg1 = h("div", { class: "mem-seg mine" });
    const seg2 = h("div", { class: "mem-seg others" });
    const hasRecl = known && recl != null && recl >= 0.1;      // the part of Sync-Strata's share that is file pages Windows can take back
    const segR = h("div", { class: "mem-seg recl" });
    seg1.style.width = pct(known ? (hasRecl ? Math.max(0, mine - recl) : mine) : 0);
    segR.style.width = pct(hasRecl ? Math.min(recl, mine) : 0);
    seg2.style.width = pct(others);
    bar.append(seg1, segR, seg2);
    const tight = (free + (hasRecl ? recl : 0)) / total < 0.12;
    const legend = h("div", { class: "mem-legend small" },
      known ? h("span", { class: "mem-key mine" }, tr("Sync-Strata {0} GiB", [gib(hasRecl ? Math.max(0, mine - recl) : mine)])) : null,
      hasRecl ? h("span", { class: "mem-key recl" }, tr("File reads (reclaimable) {0} GiB", [gib(Math.min(recl, mine))])) : null,
      h("span", { class: "mem-key others" }, known ? tr("Other apps {0} GiB", [gib(others)]) : tr("In use {0} GiB", [gib(others)])),
      h("span", { class: `mem-key free${tight ? " tight" : ""}` }, tr("Free {0} GiB", [gib(free)])));
    return h("div", { class: "mem-row" }, h("div", { class: "mem-row-head" }, h("span", { class: "mem-label" }, label),
      h("span", { class: "muted small" }, `${gib(total)} GiB`)), bar, legend);
  }

  function alertBox(a) {
    const apps = a.apps || [];
    let text;
    if (a.key === "commit_cut") text = tr("The model's RAM was cut from {0} GiB to {1} GiB. Other apps use up the Windows memory limit (commit).", [gib(a.from_gib), gib(a.to_gib)]);
    else if (a.key === "ssd_left") text = tr("{0} GiB of the model ({1}%) stays on the SSD. Chat can be slow.", [gib(a.gib), num(a.pct)]);
    else if (a.key === "commit_tight") text = tr("If you start now, about {0} GiB of the model will stay on the SSD. The Windows memory limit (commit) has {1} GiB left.", [gib(a.gib), gib(a.free_gib)]);
    else if (a.key === "ram_tight") text = tr("If you start now, about {0} GiB of the model will stay on the SSD. Free RAM is {1} GiB.", [gib(a.gib), gib(a.free_gib)]);
    else if (a.key === "vram_taken") text = tr("Other apps use {0} GiB of VRAM. Strata gets less.", [gib(a.gib)]);
    else return null;
    return h("div", { class: `mem-alert ${a.level === "bad" ? "bad" : "warn"}` }, h("div", { class: "mem-alert-text" }, text),
      apps.length ? h("div", { class: "mem-alert-apps small" }, tr("Biggest: {0}", [list(apps, "gib")])) : null);
  }

  function appRows(d) {
    const win = !!d.commit;
    const key = win ? "commit_gib" : "ram_gib";
    const apps = (d.apps || []).filter((a) => a[key] >= 0.1).slice(0, 6);
    if (!apps.length) return null;
    const max = Math.max(...apps.map((a) => a[key]));
    const rows = apps.map((a) => {
      const fill = h("div", { class: "mem-app-fill" });
      fill.style.width = `${Math.max(3, (100 * a[key]) / max)}%`;
      const sub = [win ? tr("RAM {0} GiB", [gib(a.ram_gib)]) : null].filter(Boolean).join(" · ");
      return h("div", { class: "mem-app" },
        h("div", { class: "mem-app-head" }, h("span", { class: "mem-app-name" }, a.n > 1 ? `${a.name} ×${a.n}` : a.name), h("span", { class: "mem-app-gib" }, `${gib(a[key])} GiB`)),
        h("div", { class: "mem-app-bar" }, fill),
        sub || a.gain_gib >= 0.25 ? h("div", { class: "mem-app-sub small muted" }, sub, a.gain_gib >= 0.25 ? h("span", { class: "mem-gain" }, `${sub ? " · " : ""}${tr("Closing it: {0} GiB more of the model fits in RAM", [gib(a.gain_gib)])}`) : null) : null);
    });
    return h("div", { class: "mem-apps" }, h("div", { class: "set-label muted small" }, win ? tr("Apps using the most commit") : tr("Apps using the most RAM")), ...rows);
  }

  function render(root, d) {
    const kids = [h("div", { class: "set-label muted small" }, tr("Memory"))];
    const al = [...(d.alerts || [])].sort((a, b) => (a.level === "bad" ? 0 : 1) - (b.level === "bad" ? 0 : 1)).map(alertBox).filter(Boolean);
    kids.push(...al);
    if (d.now && d.now.on_file_gib < 0.5 && !(d.alerts || []).length) kids.push(h("div", { class: "mem-alert ok" }, h("div", { class: "mem-alert-text" }, tr("Everything fits in RAM. Closing apps won't make it faster."))));
    const rows = [barRow(tr("RAM"), d.ram.total_gib, d.mine.ram_gib, d.others.ram_gib, d.ram.avail_gib, d.mine.reclaimable_gib)];
    if (d.commit) rows.push(barRow(tr("Commit (RAM + page file)"), d.commit.limit_gib, d.mine.commit_gib, d.others.commit_gib, d.commit.free_gib));
    if (d.vram) rows.push(barRow(tr("VRAM (GPU)"), d.vram.total_gib, d.mine.vram_gib, d.mine.vram_gib == null ? d.vram.used_gib : d.others.vram_gib, d.vram.free_gib));
    kids.push(...rows);
    if (d.vram && (d.gpu_apps || []).length) kids.push(h("div", { class: "muted small mem-vram-apps" }, tr("Most in VRAM: {0}", [list(d.gpu_apps, "vram_gib")])));
    const apps = appRows(d);
    if (apps) kids.push(apps);
    kids.push(h("div", { class: "muted small mem-foot" }, tr("Nothing is closed for you. Close apps yourself if you like.")));
    root.replaceChildren(...kids);
    root.classList.remove("hidden");
  }

  // the box for the Strata sheet: starts asking at once, stops when the box has left the screen
  function inline() {
    const root = h("div", { class: "mem-box hidden" });
    let attached = false;
    let stopped = false;
    let fails = 0;
    async function tick() {
      if (stopped) return;
      if (root.isConnected) attached = true;
      else if (attached) { stopped = true; return; }
      if (!document.hidden) {
        try {
          const r = await fetch("/m/sysmem", { cache: "no-store", credentials: "same-origin" });
          if (r.status === 404 || r.status === 401) { root.classList.add("hidden"); stopped = true; return; }   // not a launcher relay / not logged in
          const d = await r.json();
          if (d && d.ok && d.ram && d.mine && d.others) { fails = 0; render(root, d); }
          else if (++fails >= 2) root.replaceChildren(h("div", { class: "muted small" }, tr("Could not read the memory."))), root.classList.remove("hidden");
        } catch { /* the relay is away: ask again */ }
      }
      setTimeout(tick, 5000);
    }
    tick();
    return root;
  }

  return { inline };
})();
