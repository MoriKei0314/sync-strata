// 11/15 app1115: log in to dsh with the token the launcher read from dsh's own output (sync gui-url), then open the page.
// The token comes after "#" (not sent to any server by the browser); it is removed from the address at once, given to dsh
// once through the relay (GET /?token=…: dsh answers with its login cookie), and never stored by this page.
"use strict";
(async () => {
  const m = /(?:^#|&)token=([^&]+)/.exec(location.hash);
  history.replaceState(null, "", location.pathname);
  const say = (t) => { const el = document.getElementById("msg"); if (el) el.textContent = t; };
  if (!m) { location.replace("/m/"); return; }
  say("ログインしています… / Logging in…");
  try {
    await fetch(`/?token=${encodeURIComponent(decodeURIComponent(m[1]))}`, { credentials: "same-origin", cache: "no-store", redirect: "follow" });
  } catch { /* the page shows the login help if it did not work */ }
  location.replace("/m/");
})();
