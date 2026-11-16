// 「起動中」の画面．枠（Rust）の start を呼び，進み具合を 1 行ずつ出す．準備ができたら枠が会話の画面へ移す．
(async () => {
  const T = window.__TAURI__;
  const steps = document.getElementById("steps");
  const pill = document.getElementById("pill");
  const pillText = document.getElementById("pill-text");
  const error = document.getElementById("error");
  const actions = document.getElementById("actions");

  function add(line) {
    const li = document.createElement("li");
    li.textContent = line;
    li.title = line;
    steps.appendChild(li);
    while (steps.children.length > 40) steps.removeChild(steps.firstChild);
    steps.scrollTop = steps.scrollHeight;
  }
  function begin() {
    error.classList.add("hidden");
    actions.classList.add("hidden");
    pill.className = "pill";
    pillText.textContent = "起動中";
    T.core.invoke("start");
  }

  await T.event.listen("progress", (e) => {
    add(String(e.payload));
    if (e.payload === "準備ができました") { pill.className = "pill ok"; pillText.textContent = "準備ができました"; }
  });
  await T.event.listen("failed", (e) => {
    pill.className = "pill bad";
    pillText.textContent = "起動できませんでした";
    error.textContent = String(e.payload);
    error.classList.remove("hidden");
    actions.classList.remove("hidden");
  });
  document.getElementById("retry").addEventListener("click", () => { add("もう一度試します"); begin(); });
  begin();
})();

// 隠れている間は CSS のアニメーションを止める．
document.addEventListener("visibilitychange", () => document.documentElement.classList.toggle("paused", document.hidden));
