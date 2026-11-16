// 11/16 本人の実機チェック「PC の画面のフレームレートが低すぎる（アニメーションも）」: 11/15 の PC の間引き（連続アニメーションを止め
// 1 秒 4 段だけ進める）をやめ，PC も約 60fps でなめらかに回す．ただし GPU を使わせない作りにする:
//  - 実測（この PC は 240Hz の画面）: CSS の連続アニメーションは画面の更新ごと（毎秒 240 回）に 1 コマずつ作らせ，
//    小さなスピナー 1 つで GPU 3D が約 24% 動いた．1 コマあたり約 0.1%．ので，CSS のアニメーションは PC では使わない
//    （html.fx-low で止める．app.css の既存の規則）．
//  - 代わりにここで 1 つの時計を回し，約 60fps（最短 15 ms 間隔）で，画面に出ている飾り（スピナー・状態の札の点・文脈の輪の弧・
//    画像の読み込み中）の transform・opacity だけを書き換える．同じ 60fps なら GPU 3D は約 7%（CSS の 3 分の 1）．
//    返事の文字（view-chat.js）も同じ 60fps なので，生成中は文字と飾りが同じコマに相乗りする（飾りの分は増えない）．
//  - 画面に出ている飾りが無い間と，窓が裏にある（document.hidden）間は時計を止める．スマホ（指で触る機器）は今までどおり CSS のまま．
// 裏にある間は，どの機器でも連続アニメーションを一時停止する（html.fx-hidden）．
// 11/16 係 G2（本人の実機チェック「会話の一覧のくるくると，考え中の横のくるくるが回らない」）: 原因は，時計が回っている間は
//  飾りの一覧（list）を作り直さず，回り始めたあとに出た飾り（一覧の走っている会話のくるくる，考え中のくるくる）を拾わなかったこと
//  （状態の札の点や文脈の輪が先に回っていると，あとから出たものは止まったまま）．時計の中でも WATCH_MS ごとに一覧を作り直す．
// 11/16 係 G2: フレームレートの測りのための切り替え（PC だけ）．localStorage の syncFps（JSON {"text":60|120|240|0, "fx":60|30|120|240|0}）か，
//  頁の ?textfps=&fxfps=（0 は毎コマ）．text は文字の流し（view-chat.js），fx はこの飾りの時計．無いときは今までどおり（text 15 ms・fx 約 60fps）．
"use strict";

// 毎秒の回数 -> 最短の間隔（ms）．60 -> 15（今の値），120 -> 6，240 -> 2，30 -> 31，0 -> 0（毎コマ）．数でなければ既定．
const SyncFps = (() => {
  let o = {};
  try { const j = JSON.parse(localStorage.getItem("syncFps") || "null"); if (j && typeof j === "object") o = { ...j }; } catch { /* none */ }
  try {
    const q = new URLSearchParams(location.search);
    if (q.has("textfps")) o.text = Number(q.get("textfps"));
    if (q.has("fxfps")) o.fx = Number(q.get("fxfps"));
  } catch { /* no location */ }
  const ms = (fps, def) => {
    if (fps === undefined || fps === null || fps === "") return def;
    const n = Number(fps);
    if (!Number.isFinite(n) || n < 0) return def;
    return n === 0 ? 0 : Math.max(0, Math.round(1000 / n - 2));
  };
  return { textMs: ms(o.text, 15), fxMs: ms(o.fx, 15), raw: o };
})();

(() => {
  const root = document.documentElement;
  const mq = window.matchMedia("(hover: hover) and (pointer: fine)");
  const SEL = ".spinner, .ctx-meter.busy .ctx-busy, .pill.busy .dot, .att-img.loading";
  const WATCH_MS = 250;   // 飾りが出たかを見る間隔（出ていない間はこれだけ）
  const FRAME_MS = SyncFps.fxMs;    // 時計の最短の間隔（既定 15 ms＝約 60fps．上の SyncFps で替えられる）
  let raf = 0;
  let watch = 0;
  let list = [];

  const kind = (e) => (e.classList.contains("spinner") || e.classList.contains("ctx-busy") ? "spin"
    : e.classList.contains("dot") ? "pulse" : "fade");
  const shown = () => {
    list = [...document.querySelectorAll(SEL)].filter((e) => e.getClientRects().length);
    return list.length > 0;
  };

  let last = 0;
  let scanned = 0;
  function frame(t) {
    raf = 0;
    if (document.hidden || !mq.matches) return;
    if (t - scanned >= WATCH_MS) {   // 回っている間も一覧を作り直す（あとから出た飾りを拾う．消えたものは外す）
      scanned = t;
      if (!shown()) return;
    }
    if (t - last >= FRAME_MS) {
      last = t;
      let live = false;
      for (const e of list) {
        if (!e.isConnected) continue;
        live = true;
        const k = kind(e);
        if (k === "spin") e.style.transform = `rotate(${((t % (e.classList.contains("spinner") ? 900 : 1100)) / (e.classList.contains("spinner") ? 900 : 1100)) * 360}deg)`;
        else if (k === "pulse") e.style.opacity = String(0.65 + 0.35 * Math.cos((t / 1200) * 2 * Math.PI));
        else e.style.opacity = String(0.775 + 0.225 * Math.cos((t / 1200) * 2 * Math.PI));
      }
      if (!live) return;   // みな消えた: 止める（次は watch が見つける）
    }
    raf = requestAnimationFrame(frame);
  }

  function tick() {
    if (document.hidden || raf) return;
    if (shown()) raf = requestAnimationFrame(frame);
  }

  function apply() {
    const low = mq.matches;
    root.classList.toggle("fx-low", low);
    if (watch) clearInterval(watch);
    watch = low ? setInterval(tick, WATCH_MS) : 0;
  }

  const hidden = () => root.classList.toggle("fx-hidden", document.hidden);
  document.addEventListener("visibilitychange", hidden);
  if (mq.addEventListener) mq.addEventListener("change", apply);
  else if (mq.addListener) mq.addListener(apply);
  hidden();
  apply();
})();
