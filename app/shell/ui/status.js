// トレイの「状態」．起動の道具の status --json を短く見せる（番地のトークンは扱わない）．
(() => {
  const T = window.__TAURI__;
  const kv = document.getElementById("kv");
  const error = document.getElementById("error");
  function row(k, v, cls) {
    const dt = document.createElement("dt"); dt.textContent = k;
    const dd = document.createElement("dd"); dd.textContent = v; if (cls) dd.className = cls;
    kv.append(dt, dd);
  }
  const updown = (p) => (p && p.up ? ["動いています", "up"] : ["止まっています", "down"]);
  window.refresh = async () => {
    error.classList.add("hidden");
    try {
      const s = await T.core.invoke("status_summary");
      kv.replaceChildren();
      const e = s.engine || {}, d = s.dsh || {}, r = s.relay || {};
      let [t, c] = updown(e);
      row("エンジン", e.up ? `${t}（${e.model || "?"}${e.r ? "，R" + e.r : ""}，ポート ${e.port ?? "?"}）` : t, c);
      [t, c] = updown(d); row("dsh", d.up ? `${t}（ポート ${d.port ?? "?"}）` : t, c);
      [t, c] = updown(r); row("中継", r.up ? `${t}（ポート ${r.port ?? "?"}）` : t, c);
      const inst = (s.models && s.models.installed) || [];
      row("モデル", inst.length ? inst.join("，") : "まだありません");
      if (s.shell) row("画面の描画", { auto: "自動", on: "GPU", off: "CPU（--disable-gpu）" }[s.shell.gpu] + `（${s.shell.gpu_from}）`);
    } catch (e) {
      error.textContent = String(e);
      error.classList.remove("hidden");
    }
  };
  document.getElementById("reload").addEventListener("click", () => window.refresh());
  window.refresh();
})();

// 隠れている間は CSS のアニメーションを止める．
document.addEventListener("visibilitychange", () => document.documentElement.classList.toggle("paused", document.hidden));
