// 11/16 (本人の決定): a phone's login lasts 30 days from its pairing. On a phone (the LAN / Tailscale address), when 7 days or
// fewer are left, a band at the top says so and how to go on (scan a new QR code on the PC). Nothing on the PC itself.
// GET /m/remote/me answers {remote, days_left, warn}; a page on 127.0.0.1 gets remote:false. Uses h, tr from the page.
"use strict";

const DeviceBanner = (() => {
  let shown = null;
  async function check() {
    let b = null;
    try {
      const r = await fetch("/m/remote/me", { credentials: "same-origin", cache: "no-store" });
      if (r.status === 401) { location.replace("/m/pair.html#expired"); return; }
      b = r.ok ? await r.json() : null;
    } catch { return; }
    if (!b || !b.ok || !b.remote || !b.warn) { if (shown) { shown.remove(); shown = null; } return; }
    const text = b.days_left <= 0 ? tr("This phone's login ends today. Scan a new QR code on the PC to keep using it.")
      : tr("This phone's login ends in {0} days. Scan a new QR code on the PC to extend it by 30 days.", [b.days_left]);
    const el = h("div", { class: "device-warn", role: "status" }, text);
    if (shown) shown.replaceWith(el); else document.body.prepend(el);
    shown = el;
  }
  check();
  setInterval(check, 6 * 3600 * 1000);
  return { check };
})();
