// Screens and navigation: #/ the session list, #/new a new session, #/s/<id> one session.
// When dsh refuses us (no login cookie, or an untrusted host) a help screen replaces them.
// 11/14: three layouts by the window's width (the desktop app's breakpoints, GUI.md 3.1):
//  - phone (< 768 px wide, or < 520 px tall: a phone turned sideways): one screen at a time, sliding (as before)
//  - tablet (768-1279 px): the list on the left, the session (or the new-session screen) on the right
//  - desktop (>= 1280 px): the list, the session, and a side panel (Strata, context, subagents, session details)
// The views are the same in all three; only where they are put changes. A view whose route is still shown is kept
// when the layout changes (turning an iPad), so a half-typed message stays.
"use strict";

function AuthView(kind) {
  const here = location.origin;
  const local = (typeof DSH_CONFIG !== "undefined" && DSH_CONFIG.dshLocalUrl) || "http://127.0.0.1:3080";
  const el = h("div", { class: "screen auth" },
    h("div", { class: "hero" }, h("div", { class: "hero-mark" }, icon("code")),
      h("div", { class: "hero-text" }, kind === "unauthorized" ? tr("You need to log in to dsh") : tr("dsh refused the connection"))),
    kind === "unauthorized"
      ? h("div", { class: "auth-body" },
        h("p", {}, tr("Open the URL shown in the PC's dsh window once, with its beginning replaced by this page's address.")),
        h("pre", {}, `dsh web: ${local}/?token=…\n↓\n${here}/?token=…`),
        h("p", { class: "muted" }, tr("dsh's own page opens. Then come back to this page (/m/) and it works. The login lasts 30 days.")))
      : h("div", { class: "auth-body" },
        h("p", {}, tr("dsh does not accept this address. Check that dsh was started with --trusted-host {0}.", [location.hostname]))),
    h("button", { class: "btn primary wide", type: "button", onclick: () => location.reload() }, tr("Reload")));
  return { el, destroy() {} };
}

(() => {
  const root = document.getElementById("app");
  let inApp = false;
  let authShown = false;
  let nextMove = null; // "swap" when a screen replaces another in place (new session -> its chat)
  let settling = null; // finishes the transition that is still running, if any
  let depth = 0;
  let layout = null;   // "phone" | "tablet" | "desktop"
  // what each place shows: {key, view}. Phone uses only main.
  const slots = { list: null, main: null, side: null };
  const panes = {};

  // the height too, so a phone turned sideways (about 390-430 px tall) keeps the phone layout it had before
  const mqTablet = window.matchMedia("(min-width: 768px) and (min-height: 520px)");
  const mqDesktop = window.matchMedia("(min-width: 1280px) and (min-height: 520px)");
  const layoutNow = () => (mqDesktop.matches ? "desktop" : mqTablet.matches ? "tablet" : "phone");
  const wide = () => layout !== "phone";

  // Screens are layered: the list is the bottom, the new/archive screens sit on it, a chat sits on those.
  const depthOf = (hash) => (/^#\/s\/[^/]+\/sub\//.test(hash) ? 3 : /^#\/s\//.test(hash) ? 2 : hash === "#/new" || hash === "#/archived" ? 1 : 0);

  function go(hash, mode) {
    if (mode === "back") {
      if (inApp) history.back();
      else location.replace(hash);
    } else if (mode === "replace") {
      nextMove = "swap";
      location.replace(hash);
    } else {
      inApp = true;
      location.hash = hash;
    }
  }

  // The session a route shows: {id, parentId} or null
  function routeSession(hash = location.hash) {
    const ms = hash.match(/^#\/s\/([^/]+)\/sub\/([^/]+)$/);
    if (ms) return { id: decodeURIComponent(ms[2]), parentId: decodeURIComponent(ms[1]) };
    const m = hash.match(/^#\/s\/(.+)$/);
    return m ? { id: decodeURIComponent(m[1]), parentId: null } : null;
  }
  window.dshRoute = { session: () => routeSession(), wide: () => wide(), layout: () => layout, go };

  // What the main place shows for a route ({key, make}); on wide layouts the list is in its own place.
  function mainSpec(hash) {
    const r = routeSession(hash);
    // 10/31: #/s/<parent>/sub/<child> is a subagent's conversation (read only), opened from its parent
    if (r && r.parentId) return { key: `chat:${hash}`, make: () => ChatView(go, r.id, { parentId: r.parentId }) };
    if (r) return { key: `chat:${hash}`, make: () => ChatView(go, r.id) };
    if (hash === "#/new") return { key: "new", make: () => NewView(go) };
    if (wide()) return { key: "empty", make: () => EmptyView(go) };
    if (hash === "#/archived") return { key: "archived", make: () => ArchivedView(go) };
    return { key: "list", make: () => ListView(go) };
  }
  const listSpec = (hash) => (hash === "#/archived" ? { key: "archived", make: () => ArchivedView(go) } : { key: "list", make: () => ListView(go) });
  function sideSpec(hash) {
    const r = routeSession(hash);
    return { key: r ? `side:${r.id}` : "side:", make: () => SidePanel(go, r ? r.id : null, r ? r.parentId : null) };
  }

  function finishNow() { if (settling) settling(); }

  function destroyAll() {
    finishNow();
    for (const k of Object.keys(slots)) { if (slots[k]) slots[k].view.destroy(); slots[k] = null; }
  }

  function setViewport() {
    // 11/14: a tablet or PC may zoom the page; the phone keeps maximum-scale=1 (as before) so the box never zooms in
    const vp = document.querySelector('meta[name="viewport"]');
    if (!vp) return;
    const base = vp.content.replace(/,\s*maximum-scale=1/, "");
    vp.content = wide() ? base : base.replace("initial-scale=1", "initial-scale=1, maximum-scale=1");
  }

  // Builds the places for the current layout, keeping every view whose key is still wanted.
  function relayout() {
    finishNow();
    const was = layout;
    layout = layoutNow();
    root.className = `layout-${layout}${wide() ? " wide" : ""}`;
    document.documentElement.dataset.layout = layout;
    setViewport();
    if (authShown) return;
    const hash = location.hash;
    const pool = new Map();
    for (const k of Object.keys(slots)) { if (slots[k]) pool.set(slots[k].key, slots[k].view); slots[k] = null; }
    const take = (spec) => {
      const v = pool.get(spec.key);
      if (v) { pool.delete(spec.key); return { key: spec.key, view: v }; }
      return { key: spec.key, view: spec.make() };
    };
    if (!wide()) {
      slots.main = take(mainSpec(hash));
      root.replaceChildren(slots.main.view.el);
    } else {
      slots.list = take(listSpec(hash));
      slots.main = take(mainSpec(hash));
      panes.list = h("div", { class: "pane pane-list" }, slots.list.view.el);
      panes.main = h("div", { class: "pane pane-main" }, slots.main.view.el);
      const kids = [panes.list, panes.main];
      if (layout === "desktop") {
        slots.side = take(sideSpec(hash));
        panes.side = h("div", { class: "pane pane-side" }, slots.side.view.el);
        kids.push(panes.side);
      }
      root.replaceChildren(...kids);
    }
    for (const v of pool.values()) v.destroy();
    depth = depthOf(hash);
    if (was && was !== layout) document.dispatchEvent(new CustomEvent("dsh:layout", { detail: layout }));
  }

  // Wide layouts: each place changes on its own, without the slide (a short rise for the session place).
  function placeWide() {
    const hash = location.hash;
    const put = (name, spec, animate) => {
      const cur = slots[name];
      if (cur && cur.key === spec.key) return;
      const view = spec.make();
      slots[name] = { key: spec.key, view };
      panes[name].replaceChildren(view.el);
      if (animate && cur && !reducedMotion()) {
        view.el.classList.add("enter-swap");
        view.el.addEventListener("animationend", () => view.el.classList.remove("enter-swap"), { once: true });
      }
      if (cur) cur.view.destroy();
    };
    put("list", listSpec(hash), false);
    put("main", mainSpec(hash), true);
    if (layout === "desktop") put("side", sideSpec(hash), false);
    nextMove = null;
    depth = depthOf(hash);
  }

  function route() {
    finishNow();
    const c = Store.S.conn;
    const wasAuth = authShown;
    authShown = c === "unauthorized" || c === "forbidden";
    if (authShown) {
      destroyAll();
      depth = 0;
      const v = AuthView(c);
      slots.main = { key: "auth", view: v };
      root.className = "layout-auth";
      layout = null;
      root.replaceChildren(v.el);
      return;
    }
    if (wasAuth || !layout || layoutNow() !== layout) { destroyAll(); relayout(); return; }
    if (wide()) { placeWide(); return; }

    const old = slots.main;
    const oldDepth = depth;
    const spec = mainSpec(location.hash);
    depth = depthOf(location.hash);
    if (old && old.key === spec.key) { nextMove = null; return; }
    const view = spec.make();
    slots.main = { key: spec.key, view };
    const move = nextMove || (depth > oldDepth ? "push" : depth < oldDepth ? "pop" : "swap");
    nextMove = null;
    if (!old || reducedMotion()) {
      root.replaceChildren(view.el);
      if (old) old.view.destroy();
      return;
    }
    // Both screens stay on stage while they slide; the old one is removed when the slide ends.
    const oldEl = old.view.el;
    const newEl = view.el;
    root.append(newEl);
    oldEl.classList.add(`leave-${move}`);
    newEl.classList.add(`enter-${move}`);
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      settling = null;
      oldEl.remove();
      oldEl.classList.remove(`leave-${move}`);
      newEl.classList.remove(`enter-${move}`);
      old.view.destroy();
    };
    settling = finish;
    newEl.addEventListener("animationend", (e) => { if (e.target === newEl) finish(); }, { once: false });
    setTimeout(finish, 520);
  }

  // A phone can keep an old copy of this page alive (an installed app is only resumed, not reloaded). The server
  // knows the current version; when it differs from the one this page was loaded with, reload, unless something is
  // being typed. A version is tried once per tab, so a stale copy kept by something in between cannot cause a loop.
  const meta = document.querySelector('meta[name="dsh-version"]');
  window.dshVersion = meta && /^\d+$/.test(meta.content) ? meta.content : null;
  async function checkVersion() {
    if (!window.dshVersion || document.hidden) return;
    try {
      const { v } = await (await fetch("/m/version", { cache: "no-store" })).json();
      if (!v || v === window.dshVersion) return;
      const typing = [...document.querySelectorAll("textarea, .text-input, .search-input")].some((e) => e.value);
      if (typing || document.querySelector(".scrim, .img-large")) return;
      let tried = null;
      try { tried = sessionStorage.getItem("dsh-mobile-reload"); } catch { /* private mode */ }
      if (tried === v) return;
      try { sessionStorage.setItem("dsh-mobile-reload", v); } catch { /* private mode */ }
      location.reload();
    } catch { /* offline: ask again next time */ }
  }
  document.addEventListener("visibilitychange", checkVersion);
  window.addEventListener("online", checkVersion);
  setInterval(checkVersion, 60000);

  // 11/2: the screen is as tall as the area actually shown. 100dvh sometimes stayed taller than it (the status and
  // navigation bars counted in, e.g. after the keyboard closed or the app came back), so the bottom (the box) was cut
  // off, or the whole page shifted up and the top was cut off. The page itself never scrolls.
  function fitHeight() {
    const vv = window.visualViewport;
    const hgt = Math.round(vv ? vv.height : window.innerHeight);
    if (hgt > 0) document.documentElement.style.setProperty("--app-h", `${hgt}px`);
    if (window.scrollY || document.documentElement.scrollTop || document.body.scrollTop) {
      window.scrollTo(0, 0);
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    }
  }
  const fitSoon = () => { fitHeight(); setTimeout(fitHeight, 350); }; // some phones settle their bars a moment later
  fitHeight();
  window.addEventListener("resize", fitHeight);
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", fitHeight);
    window.visualViewport.addEventListener("scroll", fitHeight);
  }
  window.addEventListener("orientationchange", fitSoon);
  window.addEventListener("pageshow", fitSoon);
  window.addEventListener("focusout", fitSoon); // the keyboard closing
  document.addEventListener("visibilitychange", () => { if (!document.hidden) fitSoon(); });
  window.addEventListener("scroll", () => { if (window.scrollY) window.scrollTo(0, 0); }, { passive: true });

  // 11/14: the words come first (the dictionaries are fetched), then the screens are drawn
  I18n.init().finally(() => {
    Prefs.applyText();
    const onWidth = () => { if (!authShown && layoutNow() !== layout) relayout(); };
    for (const mq of [mqTablet, mqDesktop]) {
      if (mq.addEventListener) mq.addEventListener("change", onWidth);
      else mq.addListener(onWidth); // older Safari
    }
    window.addEventListener("hashchange", route);
    Store.on((topic) => {
      if (topic !== "conn") return;
      const auth = Store.S.conn === "unauthorized" || Store.S.conn === "forbidden";
      if (auth !== authShown) route();
    });
    Keys.install(go);
    route();
    Store.start();
    Store.pollStrata();
    checkVersion();
  });
})();
