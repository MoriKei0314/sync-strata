// 11/15 係 R: log this phone in with the one-time code of the QR code (pair.html#c=…), then open the chat.
// The code is taken from the address at once and sent once; it is never stored by this page.
// 11/16 係 G2（本人の画面写真: 取り消されたスマホが pair.html の背景だけで何も出ない）:
//  - 文は，この頁の中に 3 か国語で持つ（i18n.js・lang-*.json を取りに行かない）．取りに行く間（重い背景の描画と重なると数秒）文が空のままだった．
//  - 入り方（#expired があるか）に頼らない．コードも #expired も無い入り方は，GET /m/remote/me で見分ける: 401（cookie が無い・
//    取り消し・期限切れ）なら「期限が切れたか，取り消されました」を出し，ログインが生きている（または PC 自身）なら /m/ へ．
//    以前は #expired が付かない入り方（ブラウザーが 303 でフラグメントを落とした場合・再読み込み）で /m/ ↔ pair.html を行き来し続けた．
//  - 文は最初の 1 コマ目から見える（#msg の入りのアニメーションを止める）．
"use strict";
(async () => {
  const m = /(?:^#|&)c=([A-Za-z0-9_-]+)/.exec(location.hash);
  history.replaceState(null, "", location.pathname);
  const T = {
    connecting: ["Connecting to the PC…", "PC につないでいます…", "正在连接电脑…"],
    connected: ["Connected. Opening the chat…", "つながりました。会話の画面を開きます…", "已连接，正在打开对话页面…"],
    noreach: ["Cannot reach the PC", "PC に届きません", "无法连接 PC"],
    used: ["This QR code is used or expired. Show a new one on the PC.", "この QR は使用済みか期限切れです。PC で新しい QR を出してください。", "此二维码已使用或已过期，请在电脑上显示新的二维码。"],
    failed: ["Could not log in. Show a new QR code on the PC.", "ログインできませんでした。PC で新しい QR を出してください。", "无法登录，请在电脑上显示新的二维码。"],
    expired: ["This phone's login has ended or was taken back. Scan a new QR code on the PC.", "このスマホのログインは期限が切れたか、取り消されました。PC の QR を読み直してください。", "此手机的登录已过期或已被撤销。请重新扫描电脑上的二维码。"],
  };
  const pick = () => {   // the same order as i18n.js: ?lang=, the page's own choice, the browser's languages, English
    const norm = (c) => { c = String(c || "").toLowerCase().split(/[-_]/)[0]; return c === "ja" ? 1 : c === "zh" ? 2 : c === "en" ? 0 : -1; };
    let forced = null, saved = null;
    try { forced = new URLSearchParams(location.search).get("lang"); } catch { /* none */ }
    try { saved = localStorage.getItem("dsh-mobile-lang"); } catch { /* private mode */ }
    for (const c of [forced, saved, ...(navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language])]) {
      const i = norm(c);
      if (i >= 0) return i;
    }
    return 0;
  };
  const L = pick();
  document.documentElement.lang = ["en", "ja", "zh-CN"][L];
  const say = (k) => {
    const el = document.getElementById("msg");
    if (!el) return;
    el.textContent = T[k][L];
    el.style.animation = "none";   // visible at once (app.css fades it in 0.2 s late)
  };
  if (!m) {
    // no code: an expired / taken-back / never-paired phone gets the message; a live login (or the PC itself) goes on to the chat
    let st = 0;
    try { st = (await fetch("/m/remote/me", { credentials: "same-origin", cache: "no-store" })).status; } catch { /* below */ }
    if (st === 401) { say("expired"); return; }
    if (st === 0) { say("noreach"); return; }
    location.replace("/m/");
    return;
  }
  say("connecting");
  let r = null;
  try {
    r = await fetch("/m/remote/claim", { method: "POST", headers: { "content-type": "application/json" }, credentials: "same-origin",
      cache: "no-store", body: JSON.stringify({ c: m[1] }) });
  } catch { /* below */ }
  if (r && r.ok) {
    say("connected");
    location.replace("/m/");
    return;
  }
  say(!r ? "noreach" : r.status === 403 ? "used" : "failed");
})();
