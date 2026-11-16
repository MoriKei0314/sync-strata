// Images and files in a conversation (10/31): the pictures you sent and the ones the agent read (read_image) show as
// small images that open large when tapped; a file you sent shows as a card with its name and size.
// dsh keeps them as attachment refs ({attachmentId, mediaType, width, height, bytes, name}) in the session log, and its
// own session/attachment call returns an image's bytes only for an image that session's log refers to (the desktop UI
// reads them the same way). Files have no such call, so a file card shows the name and size only.
// An image is fetched when it scrolls into view, once per page load.
"use strict";

const Media = (() => {
  const urls = new Map(); // `${sessionId}|${attachmentId}` -> Promise<object URL>
  let observer = null;

  function load(sessionId, ref) {
    const key = `${sessionId}|${ref.attachmentId}`;
    if (!urls.has(key)) {
      urls.set(key, (async () => {
        const v = await Api.attachment(sessionId, ref.attachmentId);
        const bin = atob(v.data);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        return URL.createObjectURL(new Blob([bytes], { type: (v.attachment && v.attachment.mediaType) || ref.mediaType || "image/png" }));
      })());
      urls.get(key).catch(() => urls.delete(key)); // a failed read may be tried again on the next view
    }
    return urls.get(key);
  }

  function watch(el) {
    if (!("IntersectionObserver" in window)) return el._load();
    if (!observer) {
      observer = new IntersectionObserver((entries) => {
        for (const en of entries) {
          if (!en.isIntersecting) continue;
          observer.unobserve(en.target);
          en.target._load();
        }
      }, { rootMargin: "300px 0px" });
    }
    observer.observe(el);
  }

  function fmtBytes(n) {
    if (n == null) return "";
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(n < 10240 ? 1 : 0)} KB`;
    return `${(n / 1024 / 1024).toFixed(1)} MB`;
  }

  // The large view (11/2). While it is open it holds one history entry, so Android's back closes it instead of the
  // screen behind. Two fingers zoom (1x-6x, around the fingers), one finger moves a zoomed picture, a double tap zooms
  // in to 2.5x where tapped (or back out), a single tap or Esc closes it. On a PC the wheel zooms.
  let closeOpen = null;
  function openLarge(src, alt) {
    if (closeOpen) closeOpen(false);
    const img = h("img", { src, alt: alt || "", draggable: "false" });
    const box = h("div", { class: "img-large", role: "dialog", "aria-label": alt || tr("Image") }, img);
    const MAX = 6;
    let scale = 1, tx = 0, ty = 0;
    const pts = new Map();   // pointerId -> {x, y}
    let pinch = null;        // {d0, s0, fx, fy, tx0, ty0}: the start of a two-finger gesture
    let pan = null;          // {x, y, tx0, ty0}
    let multi = false;       // this touch had two fingers at some point (then it is not a tap)
    let moved = false;
    let downAt = 0;
    let lastTap = 0;
    let tapTimer = null;
    let closed = false;

    const show = (anim) => {
      img.style.transition = anim ? "transform .2s ease" : "none";
      img.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
    };
    // the picture's own centre on the screen when not moved (it sits in the middle of the box)
    const centre = () => {
      const r = box.getBoundingClientRect();
      return { x: r.left + img.offsetLeft + img.offsetWidth / 2, y: r.top + img.offsetTop + img.offsetHeight / 2 };
    };
    // keep a zoomed picture covering the screen where it can, and centred where it is smaller
    const clamp = () => {
      const r = box.getBoundingClientRect();
      const mx = Math.max(0, (img.offsetWidth * scale - r.width) / 2);
      const my = Math.max(0, (img.offsetHeight * scale - r.height) / 2);
      tx = Math.min(mx, Math.max(-mx, tx));
      ty = Math.min(my, Math.max(-my, ty));
    };
    // zoom to s keeping the screen point (px, py) on the same spot of the picture
    const zoomAt = (s, px, py, base = { s: scale, tx, ty, fx: px, fy: py }) => {
      const c = centre();
      const qx = (base.fx - c.x - base.tx) / base.s;
      const qy = (base.fy - c.y - base.ty) / base.s;
      scale = s;
      tx = px - c.x - s * qx;
      ty = py - c.y - s * qy;
    };
    const reset = () => { scale = 1; tx = 0; ty = 0; };

    function startPinch() {
      const [a, b] = [...pts.values()];
      pinch = { d0: Math.hypot(a.x - b.x, a.y - b.y) || 1, s: scale, tx, ty, fx: (a.x + b.x) / 2, fy: (a.y + b.y) / 2 };
      pan = null;
    }
    function startPan(p) { pan = { x: p.x, y: p.y, tx0: tx, ty0: ty }; }

    box.addEventListener("pointerdown", (e) => {
      try { box.setPointerCapture(e.pointerId); } catch { /* not supported */ }
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pts.size === 1) { multi = false; moved = false; downAt = Date.now(); startPan(pts.get(e.pointerId)); }
      if (pts.size === 2) { multi = true; startPinch(); }
    });
    box.addEventListener("pointermove", (e) => {
      const p = pts.get(e.pointerId);
      if (!p) return;
      p.x = e.clientX;
      p.y = e.clientY;
      if (pinch && pts.size >= 2) {
        const [a, b] = [...pts.values()];
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        const s = Math.min(MAX, Math.max(0.6, pinch.s * (d / pinch.d0)));
        zoomAt(s, (a.x + b.x) / 2, (a.y + b.y) / 2, pinch);
        moved = true;
        show(false);
      } else if (pan && pts.size === 1) {
        const dx = p.x - pan.x;
        const dy = p.y - pan.y;
        if (Math.hypot(dx, dy) > 8) moved = true;
        if (scale > 1) {
          tx = pan.tx0 + dx;
          ty = pan.ty0 + dy;
          clamp();
          show(false);
        }
      }
    });
    const up = (e) => {
      if (!pts.delete(e.pointerId)) return;
      if (pinch && pts.size < 2) {
        pinch = null;
        if (scale < 1.02) reset(); else clamp();
        show(true);
        if (pts.size === 1) startPan([...pts.values()][0]); // the finger left on the glass moves the picture on
        return;
      }
      if (pts.size) return;
      pan = null;
      if (multi || moved || e.type === "pointercancel" || Date.now() - downAt > 400) return;
      // a tap: a second one soon after zooms, otherwise it closes
      const now = Date.now();
      if (now - lastTap < 300) {
        clearTimeout(tapTimer);
        lastTap = 0;
        if (scale > 1) reset(); else { zoomAt(2.5, e.clientX, e.clientY); clamp(); }
        show(true);
      } else {
        lastTap = now;
        tapTimer = setTimeout(() => close(), 300);
      }
    };
    box.addEventListener("pointerup", up);
    box.addEventListener("pointercancel", up);
    box.addEventListener("wheel", (e) => {
      e.preventDefault();
      const s = Math.min(MAX, Math.max(1, scale * Math.exp(-e.deltaY / 300)));
      zoomAt(s, e.clientX, e.clientY);
      if (s === 1) reset(); else clamp();
      show(false);
    }, { passive: false });

    function close(back = true) {
      if (closed) return;
      closed = true;
      clearTimeout(tapTimer);
      closeOpen = null;
      box.remove();
      document.removeEventListener("keydown", onKey, true);
      window.removeEventListener("popstate", onPop);
      window.removeEventListener("hashchange", onPop);
      // closed by a tap or Esc: take back the history entry it added (the hash is the same, so no screen changes)
      if (back && history.state && history.state.dshLarge) history.back();
    }
    const onKey = (e) => { if (e.key === "Escape") { e.preventDefault(); close(); } };
    const onPop = () => close(false); // Android's back (or the screen changing under it)
    try { history.pushState({ dshLarge: true }, "", location.href); } catch { /* without it, back works as before */ }
    window.addEventListener("popstate", onPop);
    window.addEventListener("hashchange", onPop);
    document.addEventListener("keydown", onKey, true);
    closeOpen = close;
    document.body.append(box);
  }

  // A small image for one attachment ref. Its box keeps the picture's shape while it loads.
  function image(sessionId, ref) {
    const w = ref.width || 4;
    const hgt = ref.height || 3;
    const scale = Math.min(1, 220 / w, 220 / hgt);
    const btn = h("button", { class: "att-img loading", type: "button", "aria-label": ref.name ? tr("Image {0}", [ref.name]) : tr("Image") });
    btn.style.width = `${Math.max(48, Math.round(w * scale))}px`;
    btn.style.aspectRatio = `${w} / ${hgt}`;
    let src = null;
    btn._load = async () => {
      try {
        src = await load(sessionId, ref);
        btn.replaceChildren(h("img", { src, alt: ref.name || "" }));
        btn.classList.remove("loading");
      } catch {
        btn.classList.remove("loading");
        btn.classList.add("failed");
        btn.replaceChildren(h("span", {}, tr("Could not load")));
      }
    };
    btn.addEventListener("click", () => { if (src) openLarge(src, ref.name); });
    watch(btn);
    return btn;
  }

  function file(ref) {
    return h("div", { class: "att-file" }, icon("file"),
      h("div", { class: "att-file-text" }, h("div", { class: "att-file-name" }, ref.name || tr("File")), h("div", { class: "att-file-size muted" }, fmtBytes(ref.bytes))));
  }

  // The attachments among a message's content parts, or null when there are none. align: "end" for your messages.
  function strip(sessionId, parts, align) {
    const items = [];
    for (const p of parts || []) {
      const ref = p.attachment;
      if (!ref || !ref.attachmentId) continue;
      if (p.type === "image") items.push(image(sessionId, ref));
      else if (p.type === "file") items.push(file(ref));
    }
    return items.length ? h("div", { class: `att-media${align === "end" ? " end" : ""}` }, ...items) : null;
  }

  return { strip, fmtBytes };
})();
