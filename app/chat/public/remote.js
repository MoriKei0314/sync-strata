// 11/15 係 R: "Phone connection" in the start settings (setup.js calls Remote.addToSettings after drawing the sheet).
// - The choice: off / same Wi-Fi (lan) / Tailscale (the launcher's lan_remote; takes effect when dsh restarts).
// - On the PC itself (a page opened at 127.0.0.1) and only there: the QR code with a one-time link (3 min) the phone scans,
//   the address, and what to check when the phone cannot connect. A page opened from a phone gets no QR (the relay refuses it).
// - "Apply now": restarts dsh and the relay with the setting (the launcher; Strata keeps running).
// The QR code comes from the relay as rows of 0/1 (remote-qr.mjs); this file only draws it.
"use strict";

const Remote = (() => {
  const SVGNS = "http://www.w3.org/2000/svg";
  (() => {   // this part's styles (a file, as the page's CSP allows no inline styles)
    if (document.querySelector('link[data-remote-css]')) return;
    const l = document.createElement("link");
    l.rel = "stylesheet";
    l.href = "remote.css";
    l.setAttribute("data-remote-css", "1");
    document.head.append(l);
  })();

  async function call(path, post) {
    let r;
    try {
      r = await fetch(path, post ? { method: "POST", headers: { "x-dsh-mobile": "1" }, credentials: "same-origin", cache: "no-store" }
        : { credentials: "same-origin", cache: "no-store" });
    } catch {
      throw new Error(tr("Cannot reach the PC"));
    }
    let b = {};
    try { b = await r.json(); } catch { /* not JSON */ }
    if (!r.ok || !b.ok) throw new Error(b.error || tr("Failed (HTTP {0})", [r.status]));
    return b;
  }

  function qrSvg(q) {
    const n = q.size + 8;
    const svg = document.createElementNS(SVGNS, "svg");
    svg.setAttribute("viewBox", `0 0 ${n} ${n}`);
    svg.setAttribute("shape-rendering", "crispEdges");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", tr("QR code for the phone"));
    const bg = document.createElementNS(SVGNS, "rect");
    bg.setAttribute("width", n); bg.setAttribute("height", n); bg.setAttribute("fill", "#fff");
    let d = "";
    q.rows.forEach((row, y) => { for (let x = 0; x < row.length; x++) if (row[x] === "1") d += `M${x + 4} ${y + 4}h1v1h-1z`; });
    const p = document.createElementNS(SVGNS, "path");
    p.setAttribute("d", d); p.setAttribute("fill", "#000");
    svg.append(bg, p);
    return svg;
  }

  const PROBLEM = {
    no_lan: () => tr("Not connected to a network. Check the Wi-Fi or wired LAN."),
    not_installed: () => tr("Tailscale is not installed on this PC. Get it from tailscale.com."),
    not_running: () => tr("Log in to Tailscale on this PC."),
    relay_down: () => tr("Not running. Start it on the PC."),
  };

  let timer = null;

  // body: the settings sheet's body; cur: the settings (cur.settings.lan_remote); save({name: value}) saves and redraws
  function addToSettings(body, cur, save, opts) {
    clearInterval(timer);
    const set = (cur && cur.settings && cur.settings.lan_remote) || "auto";
    const now = set === "auto" ? "off" : set;
    const box = h("div", { class: "remote-box" }, h("div", { class: "set-note muted small" }, tr("Checking…")));
    const LABEL = { off: tr("Off"), lan: tr("Same Wi-Fi"), tailscale: tr("Tailscale") };
    // the choice is drawn only once the relay says this page is on the PC itself (a phone sees the state, not buttons;
    // the relay also refuses a change of lan_remote that does not come from the PC: Remote.settingsGuard in remote.mjs)
    const choices = h("div", { class: "set-choices" });
    const intro = h("div", { class: "set-note muted small hidden" }, tr("Scan the QR code to connect. Connecting from another network also needs Tailscale."));
    body.append(h("div", { class: "set-group remote" },
      ...(opts && opts.noLabel ? [] : [h("div", { class: "set-label muted small" }, tr("Phone connection"))]), choices, intro, box));
    const chips = (local) => choices.replaceChildren(...(local
      ? ["off", "lan", "tailscale"].map((v) => h("button", { class: `chip${now === v ? " on" : ""}`, type: "button", "aria-pressed": now === v ? "true" : "false",
        onclick: () => save({ lan_remote: v }).catch(() => {}) }, LABEL[v]))
      : [h("span", { class: "chip on remote-state" }, LABEL[now] || now)]));
    // 11/16: the phones logged in to this PC (the PC page only; the relay refuses a phone)
    const devGroup = h("div", { class: "set-group remote-devices hidden" });
    body.append(devGroup);
    fillDevices(devGroup).catch(() => {});
    fill(box, now, (local) => { chips(local); intro.classList.toggle("hidden", !local); })
      .catch((e) => { chips(false); box.replaceChildren(h("div", { class: "set-note fit-warn small" }, e.message)); });
  }

  async function fill(box, setting, drawChoice) {
    const st = await call("/m/remote/status?check=1");
    drawChoice(!!st.local);
    if (!st.local) {   // a phone: the state and where the QR code is; no choice, no QR, no "Apply now"
      box.replaceChildren(h("div", { class: "set-note muted small" }, tr("The QR code is shown on the PC's screen, in this setting.")));
      return;
    }
    const ck = st.check || {};
    const up = st.mode !== "off" && (st.listening || []).some((l) => l.up);
    const parts = [];
    const problem = ck.problem && PROBLEM[ck.problem] ? PROBLEM[ck.problem]() : null;
    if (problem) parts.push(h("div", { class: "set-note fit-warn small" }, problem));
    const needApply = ck.problem === "restart" || (ck.problem === "not_installed" || ck.problem === "not_running") || (!up && setting !== "off" && !ck.problem);
    if (ck.problem === "restart" || (!up && setting !== "off" && !ck.problem)) {
      parts.push(h("div", { class: "set-note muted small" }, setting === "off"
        ? tr("Still on until dsh restarts.") : tr("Available after dsh restarts.")));
    }
    if (needApply && st.launcher) {
      parts.push(h("div", { class: "remote-row" }, h("button", { class: "btn slim ghost", type: "button", onclick: () => apply() }, tr("Apply now (restart dsh)"))));
    }
    if (up && st.mode === setting) {
      const qrBox = h("div", { class: "remote-qr" });
      const left = h("div", { class: "set-note muted small remote-center" });
      const again = h("button", { class: "btn slim ghost", type: "button", onclick: () => show() }, tr("New QR code"));
      parts.push(h("div", { class: "set-note small remote-center" }, tr("Scan it with the phone's camera.")),
        qrBox, left, h("div", { class: "remote-row" }, again),
        h("div", { class: "remote-url" }, (st.urls || [])[0] || ""),
        h("div", { class: "set-note muted small" }, st.mode === "lan"
          ? tr("The connection is not encrypted. Use a Wi-Fi you trust.")
          : tr("Install Tailscale on the phone too and log in to the same account.")),
        h("div", { class: "set-note muted small" }, st.mode === "lan"
          ? tr("Can't connect? Check that both are on the same Wi-Fi and that Windows Firewall allows it.")
          : tr("Can't connect? Check that Tailscale is on on the phone.")));
      async function show() {
        clearInterval(timer);
        let q;
        try { q = await call("/m/remote/pair", true); } catch (e) { qrBox.replaceChildren(); left.textContent = e.message; return; }
        qrBox.replaceChildren(qrSvg(q.qr));
        qrBox.classList.remove("used");
        const until = Date.now() + q.expires_in * 1000;
        const since = Date.now();
        const tick = async () => {
          if (!box.isConnected) { clearInterval(timer); return; }
          const s = Math.max(0, Math.round((until - Date.now()) / 1000));
          if (s <= 0) {
            clearInterval(timer);
            qrBox.replaceChildren();
            left.textContent = tr("Expired. Tap \"New QR code\".");
            return;
          }
          left.textContent = tr("Works once, for {0}:{1}", [Math.floor(s / 60), String(s % 60).padStart(2, "0")]);
          if (s % 2 === 0) {
            try {
              const now2 = await call("/m/remote/status");
              if (now2.paired_at && now2.paired_at >= since) {
                clearInterval(timer);
                qrBox.classList.add("used");
                left.textContent = tr("The phone is connected.");
                left.classList.add("remote-ok");
              }
            } catch { /* try again */ }
          }
        };
        tick();
        timer = setInterval(tick, 1000);
      }
      box.replaceChildren(...parts);
      show();
      return;
    }
    box.replaceChildren(...parts);
  }

  // 11/16: "Connected devices": each phone's name, when it paired, when it was last used and the days left (30 days from the
  // pairing; to extend, scan a new QR code), with "take back this device's login" and "take back all". The PC page only.
  async function fillDevices(group) {
    let b;
    try { b = await call("/m/remote/devices"); } catch { group.classList.add("hidden"); return; }
    const day = (t) => new Date(t).toLocaleDateString();
    const rows = (b.devices || []).map((d) => h("div", { class: "device-item" },
      h("div", {},
        h("div", { class: "device-name" }, d.name || "?"),
        h("div", { class: "device-meta muted" }, tr("Paired {0} · Last used {1}", [day(d.created), day(d.last_used)])),
        h("div", { class: `device-meta device-left${d.expired ? " bad" : d.warn ? " warn" : ""}` },
          d.expired ? tr("Expired") : tr("{0} days left", [d.days_left]))),
      h("button", { class: "btn slim ghost", type: "button", onclick: () => revoke({ id: d.id }, tr("Take back this device's login?")) },
        tr("Take back this device's login"))));
    const parts = [h("div", { class: "set-label muted small" }, tr("Connected devices")),
      h("div", { class: "set-note muted small" }, tr("A phone's login lasts {0} days. To extend it, scan the QR code again.", [b.days || 30]))];
    if (!rows.length) parts.push(h("div", { class: "set-note muted small" }, tr("No devices are connected.")));
    else {
      parts.push(h("div", { class: "device-list" }, ...rows));
      parts.push(h("div", { class: "remote-row" }, h("button", { class: "btn slim ghost", type: "button",
        onclick: () => revoke({ all: true }, tr("Take back the login of all devices?")) }, tr("Take back all"))));
    }
    group.replaceChildren(...parts);
    group.classList.remove("hidden");
    async function revoke(what, title) {
      const ok = await confirmSheet({ title, message: tr("The device stops working right away. To use it again, scan the QR code on the PC again."),
        okLabel: tr("Take back"), danger: true });
      if (!ok) return;
      try {
        const r = await fetch("/m/remote/revoke", { method: "POST", headers: { "x-dsh-mobile": "1", "content-type": "application/json" },
          credentials: "same-origin", cache: "no-store", body: JSON.stringify(what) });
        const j = await r.json().catch(() => ({}));
        if (!r.ok || !j.ok) throw new Error(j.error || tr("Failed (HTTP {0})", [r.status]));
      } catch (e) { toast(e.message); return; }
      toast(tr("Taken back."));
      fillDevices(group).catch(() => {});
    }
  }

  async function apply() {
    const ok = await confirmSheet({
      title: tr("Restart dsh?"),
      message: tr("A reply in progress stops. Strata keeps running."),
      okLabel: tr("Restart"),
    });
    if (!ok) return;
    try { await call("/m/remote/apply", true); } catch (e) { toast(e.message); return; }
    toast(tr("Restarting dsh…"));
    // wait for the relay to go away and come back, then load the page again
    const t0 = Date.now();
    let gone = false;
    const wait = async () => {
      let alive = false;
      try { alive = (await fetch("/m/version", { cache: "no-store" })).ok; } catch { alive = false; }
      if (!alive) gone = true;
      if (alive && (gone || Date.now() - t0 > 20000)) { location.reload(); return; }
      if (Date.now() - t0 < 180000) setTimeout(wait, 1500);
    };
    setTimeout(wait, 1500);
  }

  // 11/16 本人: its own sheet, opened from the phone icon on the session list (it used to sit inside "Start settings")
  const isPcPage = () => ["127.0.0.1", "localhost", "[::1]", "::1"].includes(location.hostname);
  function openSheet2() {
    const body = h("div", { class: "set-body" }, h("div", { class: "sheet-note muted" }, tr("Reading the settings…")));
    let cur = null;
    async function save(change) {
      try { cur = await Setup.settingsCall(change); toast(tr("Saved. It takes effect at the next start")); } catch (e) { toast(e.message); throw e; }
      draw();
    }
    function draw() {
      if (!cur) return;
      body.replaceChildren();
      addToSettings(body, cur, save, { noLabel: true });
    }
    const sh = openSheet([h("div", { class: "sheet-title" }, tr("Phone connection")), body], { onClose: () => clearInterval(timer) });
    Setup.settingsCall(null).then((b) => { cur = b; draw(); },
      (e) => body.replaceChildren(h("div", { class: "sheet-note fit-warn" }, e.message)));
    return sh;
  }

  return { addToSettings, openSheet: openSheet2, isPcPage };
})();
