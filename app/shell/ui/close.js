// 閉じるときの 4 択．選んだ物を枠（Rust）の close_choice へ渡す．止める間は「止めています…」．
(() => {
  const T = window.__TAURI__;
  const buttons = [...document.querySelectorAll(".option")];
  const busy = document.getElementById("busy");
  const error = document.getElementById("error");
  for (const b of buttons) {
    b.addEventListener("click", async () => {
      const choice = b.dataset.choice;
      error.classList.add("hidden");
      if (choice === "dsh" || choice === "all") busy.classList.remove("hidden");
      buttons.forEach((x) => (x.disabled = true));
      try {
        await T.core.invoke("close_choice", { choice });
      } catch (e) {
        busy.classList.add("hidden");
        error.textContent = String(e);
        error.classList.remove("hidden");
        buttons.forEach((x) => (x.disabled = false));
      }
    });
  }
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") T.core.invoke("close_choice", { choice: "cancel" }); });
})();

// 隠れている間は CSS のアニメーションを止める．
document.addEventListener("visibilitychange", () => document.documentElement.classList.toggle("paused", document.hidden));
