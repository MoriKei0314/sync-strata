// 試し用（11/16 係 T2）: 長い文を流す画面を模した重い描画．枠の窓へ cdp.mjs で注入する．
// 毎コマ 400 個の箱を動かし（レイアウト＋合成），blur で GPU も使う．
(() => {
  document.body.innerHTML = "";
  document.body.style.cssText = "margin:0;background:#111;overflow:hidden";
  const root = document.createElement("div");
  root.style.cssText = "position:relative;width:100vw;height:100vh";
  document.body.appendChild(root);
  const els = [];
  for (let i = 0; i < 400; i++) {
    const d = document.createElement("div");
    d.textContent = "長い文の流しを模した行 " + i + " the quick brown fox";
    d.style.cssText = "position:absolute;color:#ddd;font:14px sans-serif;background:rgba(80,120,255,.25);box-shadow:0 0 12px #4af;filter:blur(1px);padding:2px 6px";
    root.appendChild(d); els.push(d);
  }
  let n = 0, t0 = performance.now(), c = 0;
  window.__fps = 0;
  const loop = (t) => {
    n++;
    for (let i = 0; i < els.length; i++) {
      const e = els[i];
      e.style.left = (Math.sin(n / 30 + i) * 40 + 50) + "%";
      e.style.top = ((i * 7 + n) % 100) + "%";
      e.textContent = "長い文の流し " + i + " " + (n % 1000);
    }
    c++;
    if (t - t0 > 1000) { window.__fps = c * 1000 / (t - t0); c = 0; t0 = t; }
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
  return "started";
})()
