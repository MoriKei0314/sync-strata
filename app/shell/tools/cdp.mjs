// 試し用: 枠の WebView2 を DevTools の口（--devtools-port）から操る．
//   node cdp.mjs <port> list
//   node cdp.mjs <port> eval <url の一部> <式>
//   node cdp.mjs <port> shot <url の一部> <png の置き場>
// URL はトークンを含みうるので，list では場所（origin と path）だけを出す．
const [port, cmd, match, arg] = process.argv.slice(2);
const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const pages = targets.filter((t) => t.type === "page");
const safe = (u) => { try { const x = new URL(u); return x.origin + x.pathname; } catch { return u; } };
if (cmd === "list") {
  for (const t of pages) console.log(safe(t.url), "|", t.title);
  process.exit(0);
}
const t = pages.find((p) => p.url.includes(match));
if (!t) { console.error("見つからない:", match, pages.map((p) => safe(p.url))); process.exit(2); }
const ws = new WebSocket(t.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let id = 0;
const call = (method, params = {}) => new Promise((res) => {
  const my = ++id;
  const on = (ev) => { const m = JSON.parse(ev.data); if (m.id === my) { ws.removeEventListener("message", on); res(m); } };
  ws.addEventListener("message", on);
  ws.send(JSON.stringify({ id: my, method, params }));
});
if (cmd === "eval") {
  const r = await call("Runtime.evaluate", { expression: arg, awaitPromise: true, returnByValue: true });
  console.log(JSON.stringify(r.result?.result?.value ?? r.result));
} else if (cmd === "shot") {
  const r = await call("Page.captureScreenshot", { format: "png" });
  const fs = await import("node:fs");
  fs.writeFileSync(arg, Buffer.from(r.result.data, "base64"));
  console.log("saved", arg);
}
ws.close();
process.exit(0);
