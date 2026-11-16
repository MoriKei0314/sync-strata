// Copy and partial copy of a message (10/31), after another app's menu: hold a message for 0.5 s (or right-click it
// on a PC) and two tiles appear above the finger, "コピー" and "部分コピー".
// - コピー writes the whole message: an AI reply as its Markdown source (code fences included, so pasted code keeps its
//   shape), a message of yours as you sent it.
// - 部分コピー makes only that message selectable, selects the word under the press (11/10; was all of it) and dims the rest. The phone's own handles adjust
//   the range; since a selection made by script may show no handles in a Chrome home-screen app, a bar at the bottom
//   copies what is selected ("選んだ所をコピー") or ends it ("やめる").
// Only finished messages and the thinking text (opened 思考, 10/31) take part: tool rows, subagent rows, the thinking
// line while it is written, the speed line and a reply still being written do not (they are never marked).
"use strict";

const Copy = (() => {
  const raw = new WeakMap(); // message element -> the text コピー writes
  const HOLD_MS = 500;
  const MOVE_PX = 10;
  let menu = null;    // {el, target, openedAt, downs: Map(pointerId -> {x, y, t}), lastTouch}
  let partial = null; // {el, row, screen, bar, startedAt, retried, lastText, timer}
  let toastEl = null;
  let toastTimer = null;

  const ICON_COPY = '<svg viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2.5"/><path d="M15 9V6.5A2.5 2.5 0 0 0 12.5 4h-6A2.5 2.5 0 0 0 4 6.5v6A2.5 2.5 0 0 0 6.5 15H9"/></svg>';
  const ICON_PART = '<svg viewBox="0 0 24 24"><path d="M4 6h9M4 11h6M4 16h9"/><path d="M18 5v14M16 5h4M16 19h4"/></svg>';

  // An element counts once marked; text: what コピー writes.
  function mark(el, text) {
    raw.set(el, String(text == null ? el.textContent : text));
    el.classList.add("copyable");
    return el;
  }

  // --- the small notice at the top (a toast: 2 s, a newer one replaces it) ---
  function notice(text) {
    if (toastEl) toastEl.remove();
    clearTimeout(toastTimer);
    toastEl = h("div", { class: "copy-toast", role: "status" }, text);
    document.body.append(toastEl);
    toastTimer = setTimeout(() => { if (toastEl) { toastEl.remove(); toastEl = null; } }, 2000);
  }

  // --- writing to the clipboard: the async API, else a hidden textarea and execCommand (the selection is put back) ---
  async function write(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch { /* fall back below */ }
    const sel = window.getSelection();
    const saved = [];
    for (let i = 0; i < sel.rangeCount; i++) saved.push(sel.getRangeAt(i));
    const ta = h("textarea", { readonly: "", "aria-hidden": "true" });
    ta.value = text;
    ta.style.cssText = "position:fixed;top:-1000px;left:0;width:1px;height:1px;opacity:0;font-size:16px";
    document.body.append(ta);
    ta.select();
    ta.setSelectionRange(0, text.length);
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { ok = false; }
    ta.remove();
    sel.removeAllRanges();
    for (const r of saved) sel.addRange(r);
    return ok;
  }

  async function copyText(text) {
    notice((await write(text)) ? tr("Copied") : tr("Could not copy"));
  }

  // --- the menu ---
  function closeMenu() {
    if (!menu) return;
    menu.el.remove();
    menu.target.classList.remove("copy-target");
    document.removeEventListener("pointerdown", onOutside, true);
    window.removeEventListener("wheel", closeMenu, true);
    window.removeEventListener("resize", closeMenu);
    document.removeEventListener("keydown", onKey, true);
    menu = null;
  }
  function onOutside(e) { if (menu && !menu.el.contains(e.target)) closeMenu(); }
  function onKey(e) { if (e.key === "Escape") closeMenu(); }

  function tile(svg, label, act) {
    const b = h("button", { class: "copy-tile", type: "button", html: svg + `<span>${Md.esc(label)}</span>` });
    // a finger acts on pointerup at once (no waiting for click); only fingers that went down after the menu opened count,
    // and not after moving 10 px; a click within 600 ms of a finger is the same press, dropped
    b.addEventListener("pointerdown", (e) => { if (menu) menu.downs.set(e.pointerId, { x: e.clientX, y: e.clientY, t: performance.now() }); });
    b.addEventListener("pointerup", (e) => {
      if (!menu || e.pointerType === "mouse") return;
      const d = menu.downs.get(e.pointerId);
      menu.downs.delete(e.pointerId);
      if (!d || d.t < menu.openedAt || Math.hypot(e.clientX - d.x, e.clientY - d.y) > MOVE_PX) return;
      menu.lastTouch = performance.now();
      e.preventDefault();
      act();
    });
    b.addEventListener("click", (e) => {
      e.preventDefault();
      if (menu && performance.now() - (menu.lastTouch || -1e9) < 600) return;
      act();
    });
    return b;
  }

  function openMenu(target, x, y) {
    closeMenu();
    const text = raw.get(target);
    if (text == null) return;
    const el = h("div", { class: "copy-menu", role: "menu" },
      tile(ICON_COPY, tr("Copy"), () => { closeMenu(); copyText(text.trim()); }),
      tile(ICON_PART, tr("Copy part"), () => { closeMenu(); startPartial(target, x, y); }));
    el.style.visibility = "hidden";
    document.body.append(el);
    const w = el.offsetWidth;
    const hgt = el.offsetHeight;
    const top0 = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--sat")) || 0;
    let top = y - hgt - 14;
    if (top < 8 + top0) top = y + 14;
    top = Math.min(top, window.innerHeight - hgt - 8);
    const left = Math.max(8, Math.min(x - w / 2, window.innerWidth - w - 8));
    el.style.left = `${left}px`;
    el.style.top = `${top}px`;
    el.style.visibility = "";
    target.classList.add("copy-target");
    menu = { el, target, openedAt: performance.now(), downs: new Map(), lastTouch: null };
    document.addEventListener("pointerdown", onOutside, true);
    window.addEventListener("wheel", closeMenu, true);
    window.addEventListener("resize", closeMenu);
    document.addEventListener("keydown", onKey, true);
    if (navigator.vibrate) navigator.vibrate(15);
  }

  // --- partial copy ---
  function selectAll(el) {
    const sel = window.getSelection();
    const r = document.createRange();
    r.selectNodeContents(el);
    sel.removeAllRanges();
    sel.addRange(r);
  }
  // 11/10: 部分コピーの初めの選択は，長押しした所の 1 語だけ（本人）．押した点の文字を探し，日本語の単語の区切り
  // （Intl.Segmenter）でその語を選ぶ．区切れないときはその 1 文字，文字が見つからないとき（押したあとに画面が動いたなど）は全文
  function caretAt(x, y) {
    if (document.caretRangeFromPoint) {
      const r = document.caretRangeFromPoint(x, y);
      return r ? { node: r.startContainer, offset: r.startOffset } : null;
    }
    if (document.caretPositionFromPoint) {
      const q = document.caretPositionFromPoint(x, y);
      return q ? { node: q.offsetNode, offset: q.offset } : null;
    }
    return null;
  }
  function selectNear(el, x, y) {
    const c = typeof x === "number" ? caretAt(x, y) : null;
    if (!c || !c.node || c.node.nodeType !== Node.TEXT_NODE || !el.contains(c.node) || !c.node.data.trim()) { selectAll(el); return; }
    const t = c.node.data;
    let i = Math.max(0, Math.min(c.offset, t.length - 1));
    if (!t[i].trim()) {   // a space or a line break: the nearest character that is not one
      let k = 1;
      while (i - k >= 0 || i + k < t.length) {
        if (i + k < t.length && t[i + k].trim()) { i += k; break; }
        if (i - k >= 0 && t[i - k].trim()) { i -= k; break; }
        k++;
      }
    }
    let a = i, b = i + 1;
    try {
      for (const sg of new Intl.Segmenter(I18n.lang, { granularity: "word" }).segment(t)) {
        if (sg.index <= i && i < sg.index + sg.segment.length) {
          if (sg.isWordLike) { a = sg.index; b = sg.index + sg.segment.length; }
          break;
        }
      }
    } catch { /* no Intl.Segmenter: the one character */ }
    const sel = window.getSelection();
    const r = document.createRange();
    r.setStart(c.node, a);
    r.setEnd(c.node, b);
    sel.removeAllRanges();
    sel.addRange(r);
  }
  function selectedInside(el) {
    const sel = window.getSelection();
    if (!sel.rangeCount || sel.isCollapsed) return "";
    const r = sel.getRangeAt(0);
    return el.contains(r.commonAncestorContainer) ? sel.toString() : "";
  }
  function onSelChange() {
    if (!partial) return;
    const t = selectedInside(partial.el);
    if (t) partial.lastText = t;
    clearTimeout(partial.timer);
    // wait 0.3 s: re-selecting by a long press passes through an empty selection for a moment
    partial.timer = setTimeout(() => {
      if (!partial || selectedInside(partial.el)) return;
      if (performance.now() - partial.startedAt < 1000 && !partial.retried) { partial.retried = true; selectNear(partial.el, partial.x, partial.y); return; }
      endPartial();
    }, 300);
  }
  function startPartial(target, x, y) {
    endPartial();
    const screen = target.closest(".screen") || document.body;
    const row = target.closest(".msg, .reasoning") || target; // the row left undimmed: a message, or the thinking block
    const keep = (e) => e.preventDefault(); // pressing the bar must not drop the selection
    const copyBtn = h("button", { class: "btn primary", type: "button" }, tr("Copy selection"));
    const stopBtn = h("button", { class: "btn ghost", type: "button" }, tr("Stop selecting"));
    const bar = h("div", { class: "copy-bar" }, h("div", { class: "copy-bar-note muted" }, tr("Tap the selected text again to change the range")), h("div", { class: "copy-bar-row" }, copyBtn, stopBtn));
    for (const b of [copyBtn, stopBtn]) { b.addEventListener("pointerdown", keep); b.addEventListener("mousedown", keep); }
    copyBtn.addEventListener("click", () => {
      const t = (partial && (selectedInside(partial.el) || partial.lastText)) || "";
      endPartial();
      if (t.trim()) copyText(t); else notice(tr("Nothing is selected"));
    });
    stopBtn.addEventListener("click", () => endPartial());
    partial = { el: target, row, screen, bar, startedAt: performance.now(), retried: false, lastText: "", timer: null, x, y };
    target.classList.add("partial-target");
    row.classList.add("partial-row");
    screen.classList.add("partial-copy");
    document.body.append(bar);
    selectNear(target, x, y);
    partial.lastText = selectedInside(target);
    document.addEventListener("selectionchange", onSelChange);
  }
  function endPartial() {
    if (!partial) return;
    const p = partial;
    partial = null;
    clearTimeout(p.timer);
    document.removeEventListener("selectionchange", onSelChange);
    p.el.classList.remove("partial-target");
    p.row.classList.remove("partial-row");
    p.screen.classList.remove("partial-copy");
    p.bar.remove();
    const sel = window.getSelection();
    if (sel.rangeCount && p.el.contains(sel.getRangeAt(0).commonAncestorContainer)) sel.removeAllRanges();
  }

  // --- listening on a transcript (delegated, so messages added later and older pages take part too) ---
  function attach(root) {
    let hold = null; // {target, x, y, id, timer}
    const targetOf = (e) => {
      const el = e.target.closest && e.target.closest(".copyable");
      if (!el || !root.contains(el)) return null;
      if (e.target.closest("a, button, summary, input, textarea")) return null; // links and buttons keep the phone's own menu
      return el;
    };
    const cancel = () => { if (hold) { clearTimeout(hold.timer); hold = null; } };
    const onDown = (e) => {
      if (e.pointerType === "mouse") return; // a mouse opens it with the right button (contextmenu)
      const t = targetOf(e);
      if (!t || (partial && partial.el === t)) return; // in partial copy, a hold on it goes back to the phone's selection
      cancel();
      hold = { target: t, x: e.clientX, y: e.clientY, id: e.pointerId, timer: setTimeout(() => {
        const hd = hold;
        hold = null;
        if (hd) openMenu(hd.target, hd.x, hd.y);
      }, HOLD_MS) };
    };
    const onMove = (e) => { if (hold && e.pointerId === hold.id && Math.hypot(e.clientX - hold.x, e.clientY - hold.y) > MOVE_PX) cancel(); };
    const onCtx = (e) => {
      const t = targetOf(e);
      if (!t || (partial && partial.el === t)) return;
      if (e.pointerType === "mouse" || !("pointerType" in e) || e.button === 2) {
        const sel = window.getSelection();
        if (sel && !sel.isCollapsed && t.contains(sel.anchorNode)) return; // a mouse selection keeps the browser's menu
      }
      e.preventDefault();
      if (menu && menu.target === t) return; // Android sends contextmenu as well as our own timer: same place
      cancel();
      openMenu(t, e.clientX, e.clientY);
    };
    // 11/14: with a mouse, a small button appears at the top right of the message under the pointer and opens the same
    // menu, so a right click is not the only way (PC, iPad with a trackpad)
    let hoverBtn = null;
    let hoverFor = null;
    const hideHover = () => { hoverFor = null; if (hoverBtn) hoverBtn.classList.add("hidden"); };
    const onOver = (e) => {
      if (e.pointerType !== "mouse") return;
      const t = targetOf(e);
      if (!t || (partial && partial.el === t)) { if (!(hoverBtn && e.relatedTarget === hoverBtn)) hideHover(); return; }
      if (!hoverBtn) {
        hoverBtn = h("button", { class: "copy-hover hidden", type: "button", "aria-label": tr("Copy options"), html: ICON_COPY });
        hoverBtn.addEventListener("click", (ev) => {
          ev.preventDefault();
          if (!hoverFor) return;
          const r = hoverBtn.getBoundingClientRect();
          openMenu(hoverFor, r.left + r.width / 2, r.top);
        });
        hoverBtn.addEventListener("pointerleave", (ev) => { if (!root.contains(ev.relatedTarget)) hideHover(); });
        document.body.append(hoverBtn);
      }
      hoverFor = t;
      const r = t.getBoundingClientRect();
      const box = root.getBoundingClientRect();
      hoverBtn.style.top = `${Math.max(box.top + 4, r.top + 2)}px`;
      hoverBtn.style.left = `${Math.min(r.right, box.right - 8) - 30}px`;
      hoverBtn.classList.remove("hidden");
    };
    const onLeave = (e) => { if (!(hoverBtn && e.relatedTarget === hoverBtn)) hideHover(); };
    root.addEventListener("pointerover", onOver);
    root.addEventListener("pointerleave", onLeave);
    root.addEventListener("scroll", hideHover, { passive: true });

    root.addEventListener("pointerdown", onDown);
    root.addEventListener("pointermove", onMove);
    root.addEventListener("pointerup", cancel);
    root.addEventListener("pointercancel", cancel); // a scroll that started
    root.addEventListener("contextmenu", onCtx);
    return {
      destroy() {
        cancel();
        if (hoverBtn) hoverBtn.remove();
        root.removeEventListener("pointerover", onOver);
        root.removeEventListener("pointerleave", onLeave);
        root.removeEventListener("scroll", hideHover);
        closeMenu();
        endPartial();
        root.removeEventListener("pointerdown", onDown);
        root.removeEventListener("pointermove", onMove);
        root.removeEventListener("pointerup", cancel);
        root.removeEventListener("pointercancel", cancel);
        root.removeEventListener("contextmenu", onCtx);
      },
    };
  }

  return { mark, attach, write, notice, closeMenu, endPartial, _state: () => ({ menu: !!menu, partial: !!partial }) };
})();
