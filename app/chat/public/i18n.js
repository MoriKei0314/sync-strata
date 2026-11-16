// Words on this page in English, Japanese and Simplified Chinese (11/14).
// tr("English text", [args]) looks the English text up in lang-en.json (id -> English) and returns the same id from
// lang-<lang>.json, with {0}, {1}… filled in from args. English is the key, so a missing word falls back to English,
// and English itself needs no dictionary. Same rule as the desktop app's tr() (I18N.md).
// The language: ?lang=xx in the address (this load only) -> the one picked on the page (localStorage) -> the first of
// the browser's languages we have -> English. Numbers and dates go through Intl with the language's locale.
"use strict";

const I18n = (() => {
  const LANGS = {
    en: { name: "English", locale: "en-US", html: "en" },
    ja: { name: "日本語", locale: "ja-JP", html: "ja" },
    zh: { name: "简体中文", locale: "zh-CN", html: "zh-CN" },
  };
  const KEY = "dsh-mobile-lang";
  let lang = "en";
  let dict = null;   // id -> text in `lang`
  let index = null;  // English text -> id
  const missing = new Set();

  function norm(code) {
    const c = String(code || "").toLowerCase();
    if (LANGS[c]) return c;
    const base = c.split(/[-_]/)[0];
    return LANGS[base] ? base : null;
  }

  // saved: the page's own choice or null; prefs: navigator.languages; forced: ?lang=
  function pick(saved, prefs, forced) {
    return norm(forced) || norm(saved) || (prefs || []).map(norm).find(Boolean) || "en";
  }

  function fill(s, args) {
    if (!args || !args.length) return s;
    return s.replace(/\{(\d+)\}/g, (m, i) => (args[i] != null ? String(args[i]) : m));
  }

  function tr(en, args) {
    let s = en;
    if (dict && index) {
      const id = index.get(en);
      const v = id ? dict[id] : null;
      if (typeof v === "string" && v) s = v;
      else if (!missing.has(en)) missing.add(en);
    }
    return fill(s, args);
  }

  // one/other by n (English needs it; Japanese and Chinese carry the same text in both). args defaults to [n].
  function trp(one, other, n, args) {
    return tr(n === 1 ? one : other, args || [n]);
  }

  // Sets the dictionaries directly (the page after fetching them, and the Node tests).
  function load(code, enDict, langDict) {
    lang = norm(code) || "en";
    if (lang === "en" || !enDict || !langDict) { dict = null; index = null; return; }
    index = new Map(Object.entries(enDict).map(([id, text]) => [text, id]));
    dict = langDict;
  }

  const store = {
    get() { try { return localStorage.getItem(KEY); } catch { return null; } },
    set(v) { try { if (v) localStorage.setItem(KEY, v); else localStorage.removeItem(KEY); } catch { /* private mode */ } },
  };

  async function init() {
    let forced = null;
    try { forced = new URLSearchParams(location.search).get("lang"); } catch { /* no location */ }
    const prefs = typeof navigator !== "undefined" ? (navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language]) : [];
    const want = pick(store.get(), prefs, forced);
    if (typeof document !== "undefined") document.documentElement.lang = LANGS[want].html;
    if (want === "en") { load("en"); return want; }
    const meta = typeof document !== "undefined" && document.querySelector('meta[name="dsh-version"]');
    const v = meta && /^\d+$/.test(meta.content) ? `?v=${meta.content}` : "";
    try {
      const get = async (c) => { const r = await fetch(`lang-${c}.json${v}`, { cache: "no-store" }); if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); };
      const [en, other] = await Promise.all([get("en"), get(want)]);
      load(want, en, other);
    } catch (e) {
      console.warn(`dsh mobile: the ${want} words could not be read; English is shown`, e);
      load(want); // the language stays (dates and numbers), the words fall back to English
    }
    return want;
  }

  // Picking a language on the page: saved, then the page is drawn again from the start (every view reads tr()).
  // null goes back to the browser's language.
  function choose(code) {
    store.set(norm(code));
    location.reload();
  }

  const locale = () => LANGS[lang].locale;
  const cache = new Map();
  const fmt = (kind, opts) => {
    const k = `${lang}|${kind}`;
    if (!cache.has(k)) cache.set(k, kind === "num" ? new Intl.NumberFormat(locale(), opts) : new Intl.DateTimeFormat(locale(), opts));
    return cache.get(k);
  };
  const num = (n) => fmt("num").format(Number(n));
  const time = (ms) => fmt("time", { hour: "numeric", minute: "2-digit" }).format(new Date(ms));
  // month, day and weekday (with the year when asked): 11/3(月) · Mon, Nov 3 · 11/3周一
  const day = (ms, withYear) => fmt(withYear ? "dayY" : "day", { ...(withYear ? { year: "numeric" } : {}), month: lang === "en" ? "short" : "numeric", day: "numeric", weekday: "short" }).format(new Date(ms));

  return {
    LANGS, KEY, tr, trp, load, init, choose, pick, num, time, day, missing,
    get lang() { return lang; },
    get locale() { return locale(); },
    saved: () => norm(store.get()),
  };
})();

const tr = I18n.tr;
const trp = I18n.trp;
