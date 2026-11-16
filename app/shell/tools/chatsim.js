// 計測用（11/16 係 T3）: 会話の画面を模した頁を，枠の窓の中に作る．文字が流れ，アニメーションが動く．
// 係 G の直し方に合わせる: 文字は 15ms ごとに数文字足す（setInterval），動きは 1 つの rAF の時計で約 60fps，transform・opacity だけ，
// できた返事は content-visibility:auto，書きかけの返事は contain．CSS の連続アニメーションは使わない．
// window.__sim.run(秒, {heavy}) が rAF の間隔（ms）の統計を返す．
(() => {
  document.head.innerHTML = '<meta charset="utf-8">';
  document.body.innerHTML = "";
  document.body.style.cssText = "margin:0;background:#14171d;color:#f1ede6;font:15px/1.7 'Yu Gothic UI',sans-serif;overflow:hidden;height:100vh";
  const st = document.createElement("style");
  st.textContent = `
    #feed{position:absolute;inset:0 0 56px 0;overflow-y:auto;padding:16px 24px}
    .msg{padding:10px 14px;margin:8px 0;border-radius:16px;background:#1e2128;content-visibility:auto;contain-intrinsic-size:auto 120px}
    .live{contain:layout paint style;background:#22262e}
    #fx{position:absolute;left:0;right:0;bottom:0;height:56px;overflow:hidden}
    .dot{position:absolute;top:20px;width:10px;height:10px;border-radius:50%;background:#ecd3a3;will-change:transform,opacity}
    #spin{position:absolute;right:20px;top:14px;width:22px;height:22px;border:3px solid #ecd3a3;border-top-color:transparent;border-radius:50%;will-change:transform}
    .layer{position:absolute;width:40px;height:40px;border-radius:10px;background:rgba(236,211,163,.35);will-change:transform,opacity}
  `;
  document.head.appendChild(st);
  const feed = document.createElement("div"); feed.id = "feed"; document.body.appendChild(feed);
  const fx = document.createElement("div"); fx.id = "fx"; document.body.appendChild(fx);
  const spin = document.createElement("div"); spin.id = "spin"; document.body.appendChild(spin);
  const text = "ローカルの言語モデルが返事を少しずつ書いています．この文は流れる文字の見た目を模したもので，意味はありません．the quick brown fox jumps over the lazy dog． ";
  for (let i = 0; i < 30; i++) { const m = document.createElement("div"); m.className = "msg"; m.textContent = text.repeat(6); feed.appendChild(m); }
  const live = document.createElement("div"); live.className = "msg live"; feed.appendChild(live);
  const node = document.createTextNode(""); live.appendChild(node);
  const dots = []; for (let i = 0; i < 12; i++) { const d = document.createElement("div"); d.className = "dot"; fx.appendChild(d); dots.push(d); }
  const layers = [];
  let ti = null, raf = 0, running = false;
  function setHeavy(n) { for (const l of layers) l.remove(); layers.length = 0; for (let i = 0; i < n; i++) { const l = document.createElement("div"); l.className = "layer"; l.style.left = (i * 37 % 900) + "px"; l.style.top = (i * 53 % 500) + "px"; document.body.appendChild(l); layers.push(l); } }
  let pos = 0;
  function tick() { node.data += text.slice(pos % text.length, pos % text.length + 3); pos += 3; if (node.data.length > 4000) { live.className = "msg"; node.data = node.data; } feed.scrollTop = feed.scrollHeight; }
  let n = 0, last = 0, t60 = 0;
  const dts = [];
  function frame(t) {
    if (!running) return;
    if (last) dts.push(t - last);
    last = t;
    if (t - t60 >= 16.0) { // 約 60fps の時計
      t60 = t; n++;
      for (let i = 0; i < dots.length; i++) { const d = dots[i]; d.style.transform = `translate(${(n * 3 + i * 70) % 1000}px,${Math.sin(n / 10 + i) * 8}px)`; d.style.opacity = 0.5 + 0.5 * Math.sin(n / 12 + i); }
      spin.style.transform = `rotate(${n * 12}deg)`;
      for (let i = 0; i < layers.length; i++) { layers[i].style.transform = `translate(${Math.sin(n / 20 + i) * 30}px,${Math.cos(n / 25 + i) * 30}px)`; layers[i].style.opacity = 0.4 + 0.4 * Math.sin(n / 15 + i); }
    }
    raf = requestAnimationFrame(frame);
  }
  const pct = (a, p) => a[Math.min(a.length - 1, Math.floor(a.length * p))];
  window.__sim = {
    run(sec, opt = {}) {
      return new Promise((res) => {
        setHeavy(opt.heavy || 0);
        dts.length = 0; last = 0; running = true; ti = setInterval(tick, 15); raf = requestAnimationFrame(frame);
        setTimeout(() => {
          running = false; clearInterval(ti); cancelAnimationFrame(raf);
          const a = dts.slice(2).sort((x, y) => x - y);
          const r = (v) => Math.round(v * 100) / 100;
          res({ frames: a.length, fps: r(a.length / sec), median: r(pct(a, 0.5)), p95: r(pct(a, 0.95)), p99: r(pct(a, 0.99)), max: r(a[a.length - 1]), over33: a.filter((x) => x > 33).length, over100: a.filter((x) => x > 100).length, hidden: document.hidden });
        }, sec * 1000);
      });
    },
  };
  return "ready";
})()
