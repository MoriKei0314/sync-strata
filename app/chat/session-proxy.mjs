// Pack copy (11/15 S2): made by s2/make_chat_pack.py from session-proxy.mjs; only the author's-PC default of SESSION_DIR is changed.
// Strata session proxy (2026-10-22): DeepSeek Harness -> 127.0.0.1:8081 (this) -> Strata 127.0.0.1:8080.
//
// Strata holds one conversation at a time. When dsh runs several sessions at once, every switch makes Strata read the
// other session's history again from its system prompt (10/22 17:42-17:58: 4 sessions, 24 switches, 324K of the 486K
// prompt tokens read again, about 400 s). Strata can save the conversation it holds to a file and restore one
// (POST /slots/0?action=save|restore, the config's "slot_save_path"), but dsh never asks it to. This proxy does:
//  - chat requests (POST .../chat/completions) go to Strata one at a time, in the order they came;
//  - before one that does not continue the conversation Strata holds, that conversation is saved to a file (when it is
//    long enough), and when a saved conversation is the start of the request, it is restored first, so Strata reads
//    only the request's new tail;
//  - anything else (models, health, metrics, Strata's own page) passes straight through.
// A conversation is recognised by its messages: the tool list and each message are hashed in order, and a saved file
// belongs to the requests whose hashes start with the ones it was saved after.
// Any failure (Strata started without slot_save_path, a refusal for lack of RAM, a file from another configuration)
// falls back to sending the request as it is, so it is never worse than talking to Strata directly.
//
// Log: session-proxy.log beside this file (one line per request and per save/restore). State: GET /proxy/status.
// Settings (env): PROXY_PORT 8081, STRATA_URL http://127.0.0.1:8080, SESSION_DIR <beside this file>\sessions (must be the
// config's slot_save_path), MIN_SAVE_TOKENS 3000, MAX_FILES 16, MAX_GIB 24, PROXY_LOG,
// PROXY_ALLOWED_HOSTS (11/14: Host names allowed besides loopback; empty by default, see refusal()).
//
// 11/13 (Linux): a request that continues what this proxy last saw Strata hold is sent as "continues" only when Strata's
// last request (/metrics) is still the one this proxy sent. Before, prepare() trusted it without asking, so after a
// Strata restart (stop-strata saves the conversation first) or a request sent to Strata directly, the next turn was read
// from token 0 (11/13 15:17: 80,015 tokens, 47 s) instead of restoring its file. Changed: the start of prepare() only.
import crypto from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PROXY_PORT || 8081);
const UPSTREAM = new URL(process.env.STRATA_URL || "http://127.0.0.1:8080");
const DIR = process.env.SESSION_DIR || path.join(HERE, "sessions"); // pack copy: the launcher passes SESSION_DIR
const LOG = process.env.PROXY_LOG || path.join(HERE, "session-proxy.log");
const MIN_SAVE_TOKENS = Number(process.env.MIN_SAVE_TOKENS || 3000);
const MAX_FILES = Number(process.env.MAX_FILES || 16);
const MAX_BYTES = Number(process.env.MAX_GIB || 24) * 2 ** 30;
const MAX_AGE_MS = 2 * 24 * 3600e3;
const ROOT_RESTORE = process.env.ROOT_RESTORE !== "0";   // 11/9: a new chat restores a file for its system prompt (prepare)
const INDEX = path.join(DIR, "index.json");

// --- log ---
const stamp = () => new Date().toLocaleString("sv-SE").replace("T", " ");
function log(line) {
  try {
    if (fs.existsSync(LOG) && fs.statSync(LOG).size > 4 * 2 ** 20) {        // keep the newest half
      const text = fs.readFileSync(LOG, "utf8");
      fs.writeFileSync(LOG, text.slice(text.indexOf("\n", text.length / 2) + 1));
    }
    fs.appendFileSync(LOG, `${stamp()} ${line}\n`);
  } catch { /* logging never stops the proxy */ }
}
const fmt = (n) => (n == null ? "?" : Number(n).toLocaleString("en-US"));
const gib = (b) => (b / 2 ** 30).toFixed(2);

// --- conversations as hash lists ---
// Keys are sorted so that the same message hashes the same whatever order its fields were written in.
function canon(v) {
  if (Array.isArray(v)) return `[${v.map(canon).join(",")}]`;
  if (v && typeof v === "object") return `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${canon(v[k])}`).join(",")}}`;
  return JSON.stringify(v ?? null);
}
const hash = (v) => crypto.createHash("sha1").update(canon(v)).digest("hex").slice(0, 16);
// The first element stands for what Strata puts before the messages and does not come from them: the tool list.
const seqOf = (j) => [hash({ tools: j.tools ?? null, kwargs: j.chat_template_kwargs ?? null }), ...(j.messages || []).map(hash)];
function lcp(a, b) {
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i++;
  return i;
}
const isPrefix = (a, b) => a.length <= b.length && lcp(a, b) === a.length;

// --- saved conversations (index.json in the session folder) ---
let entries = [];
function loadIndex() {
  try {
    const j = JSON.parse(fs.readFileSync(INDEX, "utf8"));
    entries = (j.entries || []).filter((e) => fs.existsSync(path.join(DIR, e.file)));
  } catch { entries = []; }
}
function writeIndex() {
  try {
    fs.mkdirSync(DIR, { recursive: true });
    fs.writeFileSync(INDEX + ".tmp", JSON.stringify({ entries }));
    fs.renameSync(INDEX + ".tmp", INDEX);
  } catch (e) { log(`index not written: ${e.message}`); }
}
function drop(e, why) {
  entries = entries.filter((x) => x !== e);
  try { fs.unlinkSync(path.join(DIR, e.file)); } catch { /* already gone */ }
  log(`dropped ${e.file} (${why})`);
}
function prune() {
  const now = Date.now();
  for (const e of [...entries]) if (now - e.usedAt > MAX_AGE_MS) drop(e, "unused for 2 days");
  const byUse = () => [...entries].sort((a, b) => a.usedAt - b.usedAt);
  while (entries.length > MAX_FILES) drop(byUse()[0], `more than ${MAX_FILES} files`);
  while (entries.length > 1 && entries.reduce((s, e) => s + (e.bytes || 0), 0) > MAX_BYTES) drop(byUse()[0], `more than ${gib(MAX_BYTES)} GiB`);
  writeIndex();
}

// --- what Strata holds, as far as this proxy knows ---
let live = null;      // {seq, tokens, fresh}: fresh = a file holds it exactly as it is (just saved or restored)
let lastId = null;    // Strata's id of the last request this proxy sent (/metrics "requests"[0].id)
let slotsOffUntil = 0; // Strata said 501 (started without slot_save_path): requests just pass, asking again later
const slotsOff = () => Date.now() < slotsOffUntil;
const stats = { requests: 0, continued: 0, saves: 0, restores: 0, refusals: 0, save_ms: 0, restore_ms: 0 };

function call(method, pathname, body, timeoutMs) {
  return new Promise((resolve) => {
    const data = body == null ? null : Buffer.from(JSON.stringify(body));
    const r = http.request({
      host: UPSTREAM.hostname, port: UPSTREAM.port, method, path: pathname, timeout: timeoutMs,
      headers: data ? { "content-type": "application/json", "content-length": data.length } : {},
    }, (res) => {
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => {
        let j = null;
        try { j = JSON.parse(Buffer.concat(chunks).toString("utf8")); } catch { /* not JSON */ }
        resolve({ status: res.statusCode, body: j });
      });
    });
    r.on("timeout", () => r.destroy(new Error("timeout")));
    r.on("error", (e) => resolve({ status: 0, body: { error: { message: e.message } } }));
    r.end(data);
  });
}

async function lastRequest() {
  const r = await call("GET", "/metrics", null, 5000);
  return r.status === 200 && r.body && Array.isArray(r.body.requests) ? r.body.requests[0] || null : undefined;
}

const why = (r) => `${r.status} ${(r.body && r.body.error && (r.body.error.kind ? r.body.error.kind + ": " : "") + r.body.error.message) || ""}`.trim();

// 11/6: while Strata is down or (re)starting, a request waits here (the stream keeps its pings) instead of failing.
// dsh retries a failed request for only about 30 s, and Strata takes a minute or two to load, so a restart used to
// end the turns of every agent waiting in the queue - the subagents included. HOLD_MIN (default 15) bounds the wait.
const HOLD_MS = Number(process.env.HOLD_MIN || 15) * 60000;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function strataUp() {
  const r = await call("GET", "/metrics", null, 5000);
  const state = r.status === 200 && r.body && r.body.live && r.body.live.state;
  return !!state && state !== "unloaded";
}
const canHold = (job) => !job.gone && Date.now() - (job.holdSince ??= Date.now()) < HOLD_MS;
async function holdUntilUp(job) {
  let said = false;
  const t0 = Date.now();
  while (!(await strataUp())) {
    if (!canHold(job)) return false;
    if (!said) { log(`#${job.n} held: Strata is not answering; waiting for it (up to ${HOLD_MS / 60000} min)`); said = true; }
    await sleep(2000);
  }
  if (said) log(`#${job.n} Strata answers again after ${((Date.now() - t0) / 1000).toFixed(0)} s`);
  return true;
}

async function slots(action, file) {
  const t0 = Date.now();
  const r = await call("POST", `/slots/0?action=${action}`, { filename: file }, 600000);
  if (r.status === 501) {
    if (!slotsOff()) log(`Strata cannot save sessions (${why(r)}): passing requests through, asking again in 5 minutes`);
    slotsOffUntil = Date.now() + 5 * 60000;
  }
  return { ...r, ms: Date.now() - t0 };
}

async function save() {
  // An older file of the same conversation is replaced (its messages are the start of what Strata holds now).
  const same = entries.filter((e) => e.seq.length >= 3 && isPrefix(e.seq, live.seq)).sort((a, b) => b.seq.length - a.seq.length);
  const e = same[0] || { file: `dsh-${crypto.randomBytes(4).toString("hex")}.bin` };
  const r = await slots("save", e.file);
  if (r.status !== 200) {
    stats.refusals++;
    log(`  save refused: ${why(r)} (${(r.ms / 1000).toFixed(1)} s)`);
    return;
  }
  Object.assign(e, { seq: live.seq, tokens: r.body.n_saved, bytes: r.body.n_written, usedAt: Date.now() });
  if (!same[0]) entries.push(e);
  for (const old of same.slice(1)) drop(old, "superseded");
  live.fresh = true;
  stats.saves++;
  stats.save_ms += r.ms;
  log(`  saved ${e.file}: ${fmt(e.tokens)} tokens, ${gib(e.bytes)} GiB, ${(r.ms / 1000).toFixed(1)} s`);
  prune();
}

async function restore(e) {
  const r = await slots("restore", e.file);
  if (r.status !== 200) {
    stats.refusals++;
    log(`  restore refused: ${why(r)} (${(r.ms / 1000).toFixed(1)} s)`);
    if (r.status === 404 || r.status === 400) drop(e, "Strata cannot use it");
    // A refusal for RAM leaves Strata's conversation as it was; anything else (not loaded, an engine that ended and is
    // started again) leaves it unknown.
    if (!(r.status === 503 && r.body && r.body.error && r.body.error.kind === "memory")) { live = null; lastId = null; }
    return;
  }
  live = { seq: e.seq, tokens: r.body.n_restored, fresh: true };
  e.usedAt = Date.now();
  writeIndex();
  stats.restores++;
  stats.restore_ms += r.ms;
  log(`  restored ${e.file}: ${fmt(r.body.n_restored)} tokens, ${(r.ms / 1000).toFixed(1)} s`);
}

// Before a request: keep it as it is when it continues what Strata holds; otherwise save that and restore the longest
// saved conversation the request continues, when that reaches further than what Strata would reuse anyway.
async function prepare(job) {
  if (live && isPrefix(live.seq, job.seq)) {
    // 11/13: only while Strata still holds it (an unanswered /metrics keeps the old belief, as a failed check did not drop it before)
    const top = await lastRequest();
    if (top === undefined || (top && top.id === lastId)) { job.note = "continues"; stats.continued++; return; }
    log(`  Strata answered someone else since (or restarted): what it holds is unknown`);
    live = null;
  }
  if (slotsOff()) { job.note = "pass"; return; }
  const top = await lastRequest();
  if (live && !(top && top.id === lastId)) {
    log(`  Strata answered someone else since (or restarted): what it holds is unknown`);
    live = null;
  }
  const common = live ? lcp(live.seq, job.seq) : 0;
  const best = entries.filter((e) => isPrefix(e.seq, job.seq) && e.seq.length > common)
    .sort((a, b) => b.seq.length - a.seq.length)[0];
  // 11/9: a new chat shares only the tool list and the system message with the saved ones. An engine started with
  // STRATA_QL_SESSION_ROOT=1 keeps the checkpoint at the end of that system prompt in its files, so restoring the
  // smallest file whose first two hashes match lets Strata read only what follows the system prompt (~8-11K tokens of
  // dsh's instructions and tools, 6-7 s, otherwise read again for every new chat and subagent). A file that gave
  // nothing back (an engine without it) is marked and not tried again. ROOT_RESTORE=0 turns this off.
  let partial = null;
  if (!best && ROOT_RESTORE && job.seq.length >= 3 && common < 2)
    partial = entries.filter((e) => !e.noRoot && e.seq.length > 2 && lcp(e.seq, job.seq) >= 2)
      .sort((a, b) => (a.bytes || 0) - (b.bytes || 0))[0] || null;
  job.note = best ? `switch to ${best.file}` : partial ? `new, system prompt from ${partial.file}` : "new";
  if (live && !live.fresh && live.tokens >= MIN_SAVE_TOKENS && !slotsOff()) await save();
  if (best && !slotsOff()) await restore(best);
  else if (partial && !slotsOff()) {
    await restore(partial);
    if (live && live.seq === partial.seq) job.partial = partial;
  }
}

// After a request: what Strata holds is now this request's conversation (its prompt and the answer it wrote).
async function after(job) {
  const top = await lastRequest();
  if (!top || top.id === lastId) {
    log(`#${job.n} ${job.note}, ${job.seq.length - 1} messages: Strata recorded no request (an error before the model)`);
    return;
  }
  lastId = top.id;
  live = { seq: job.seq, tokens: (top.prompt_tokens || 0) + (top.output_tokens || 0), fresh: false };
  if (job.partial && (top.reused || 0) < 1000) {   // the restored file held no checkpoint at the system prompt's end
    job.partial.noRoot = true;
    writeIndex();
    log(`  ${job.partial.file} gave back no system prompt (reused ${fmt(top.reused)}): not tried for new chats again`);
  }
  const read = top.prompt_read ?? (top.prompt_tokens || 0) - (top.reused || 0);
  log(`#${job.n} ${job.note}, ${job.seq.length - 1} messages: prompt ${fmt(top.prompt_tokens)} (reused ${fmt(top.reused)}, `
    + `read ${fmt(read)} in ${((top.prompt_ms || 0) / 1000).toFixed(1)} s), out ${fmt(top.output_tokens)}, ${top.finish}`
    + (job.waited > 1000 ? `, waited ${(job.waited / 1000).toFixed(1)} s` : ""));
}

// --- the HTTP side ---
function passThrough(req, res, body) {
  const headers = { ...req.headers, host: UPSTREAM.host };
  if (body) { delete headers["transfer-encoding"]; headers["content-length"] = body.length; }
  const up = http.request({ host: UPSTREAM.hostname, port: UPSTREAM.port, method: req.method, path: req.url, headers }, (ur) => {
    res.writeHead(ur.statusCode, ur.headers);
    ur.pipe(res);
  });
  up.on("error", (e) => {
    if (!res.headersSent) res.writeHead(502, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: { message: `Strata did not answer: ${e.message}` } }));
  });
  res.on("close", () => { if (!res.writableFinished) up.destroy(); });
  if (body) up.end(body);
  else req.pipe(up);
}

const SSE = { "content-type": "text/event-stream", "cache-control": "no-cache", "x-accel-buffering": "no" };
const sseError = (message, code) => `data: ${JSON.stringify({ error: { message, code, type: "server_error" } })}\n\n`;

function forward(job) {
  return new Promise((resolve) => {
    const { req, res } = job;
    const headers = { ...req.headers, host: UPSTREAM.host, "content-length": job.body.length };
    delete headers["transfer-encoding"];
    const up = http.request({ host: UPSTREAM.hostname, port: UPSTREAM.port, method: "POST", path: req.url, headers }, (ur) => {
      if (ur.statusCode === 503 && canHold(job)) {   // 11/6: Strata starting or not loaded: hold it, send it again
        const chunks = [];
        ur.on("data", (c) => chunks.push(c));
        ur.on("end", () => {
          let message = Buffer.concat(chunks).toString("utf8");
          try { message = JSON.parse(message).error.message || message; } catch { /* as it came */ }
          job.held = `503 ${String(message).slice(0, 120)}`;
          resolve("retry");
        });
        return;
      }
      job.started = true;
      if (!res.headersSent) {
        res.writeHead(ur.statusCode, ur.headers);
        ur.pipe(res);
      } else if (ur.statusCode === 200) {
        ur.pipe(res);                           // the client already has our 200 and pings: send only the events
      } else {                                  // ... and an error goes into the stream as an event
        const chunks = [];
        ur.on("data", (c) => chunks.push(c));
        ur.on("end", () => {
          let message = Buffer.concat(chunks).toString("utf8");
          try { message = JSON.parse(message).error.message || message; } catch { /* as it came */ }
          res.end(sseError(message, ur.statusCode));
        });
      }
      ur.on("close", () => resolve("done"));
    });
    up.on("error", (e) => {
      if (!job.started && canHold(job)) { job.held = e.message; return resolve("retry"); }   // 11/6: Strata is down
      job.started = true;
      if (!res.headersSent) {
        res.writeHead(502, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: { message: `Strata did not answer: ${e.message}` } }));
      } else res.end(sseError(`Strata did not answer: ${e.message}`, 502));
      resolve("done");
    });
    job.cancel = () => up.destroy();
    up.end(job.body);
  });
}

const queue = [];
let busy = false;
let counter = 0;

async function pump() {
  if (busy) return;
  busy = true;
  while (queue.length) {
    const job = queue.shift();
    if (job.gone) { log(`#${job.n} the client left while it waited`); continue; }
    job.waited = Date.now() - job.at;
    for (;;) {
      await holdUntilUp(job);     // gives up after HOLD_MIN: the request then fails as it did before
      if (job.gone) break;
      try { await prepare(job); } catch (e) { log(`  prepare failed: ${e.stack || e.message}`); }
      if (job.gone) break;
      const r = await forward(job);
      if (r === "retry") {        // Strata went away or is starting: what it holds is unknown, so prepare() again
        log(`#${job.n} held: Strata refused or did not answer (${job.held}); sending it again when Strata answers`);
        live = null;
        await sleep(2000);
        continue;
      }
      try { await after(job); } catch (e) { log(`  after failed: ${e.stack || e.message}`); }
      break;
    }
    if (job.gone && !job.started) log(`#${job.n} the client left before it was sent`);
  }
  busy = false;
}

function chat(req, res, body) {
  let j;
  try { j = JSON.parse(body.toString("utf8")); } catch { return passThrough(req, res, body); }
  if (!j || !Array.isArray(j.messages)) return passThrough(req, res, body);
  // 11/10: dsh's models strata-r4 .. strata-r7 are one Strata with the route tail skip rank R for that request
  // (strata_tune.tail_skip -> server.py -> the engine's tail_skip=R).  Other model names: the start-up rank.
  // 11/15 本人: strata-r10 は「省かない」．エンジンは tail_skip を 0〜9 に切るので，10 ではなく 0（切）を送る
  const tm = typeof j.model === "string" ? /^strata-r([0-9]+)$/.exec(j.model) : null;
  if (tm) {
    const tune = j.strata_tune && typeof j.strata_tune === "object" ? j.strata_tune : {};
    const r = Number(tm[1]);
    j.strata_tune = { ...tune, tail_skip: r >= 10 ? 0 : r };
    body = Buffer.from(JSON.stringify(j), "utf8");
  }
  const job = { n: ++counter, req, res, body, seq: seqOf(j), at: Date.now(), started: false, gone: false };
  stats.requests++;
  if (tm) log(`#${job.n} model ${j.model}: tail skip ${tm[1]}`);
  // A streaming client that waits its turn (or a save and a restore) gets the stream's headers and SSE comments, as
  // Strata itself sends while a request waits in its queue, so it does not give up on a silent connection.
  if (j.stream) {
    const pinger = setInterval(() => {
      if (job.started || job.gone) return clearInterval(pinger);
      if (!res.headersSent) res.writeHead(200, SSE);
      res.write(": ping\n\n");
    }, 2000);
  }
  res.on("close", () => {
    if (res.writableFinished) return;
    job.gone = true;
    if (job.cancel) job.cancel();
  });
  queue.push(job);
  pump();
}

// 11/9: POST /proxy/save-live - save the conversation Strata holds now, before Strata is stopped on purpose (stop-strata.ps1
// calls it), so the next request after the restart restores it instead of reading the whole history again.  A request in
// flight finishes first; requests that come meanwhile wait until the file is written.
async function saveLive(res) {
  const t0 = Date.now();
  while (busy && Date.now() - t0 < 120000) await sleep(200);
  let out;
  if (busy) out = { saved: false, why: "a request is still running" };
  else {
    busy = true;
    try {
      if (!live) out = { saved: false, why: "nothing known" };
      else if (live.fresh) out = { saved: true, why: "already saved", tokens: live.tokens };
      else if (live.tokens < MIN_SAVE_TOKENS) out = { saved: false, why: `short (${live.tokens} tokens)` };
      else if (slotsOff()) out = { saved: false, why: "Strata cannot save sessions now" };
      else {
        const top = await lastRequest();
        if (!(top && top.id === lastId)) { out = { saved: false, why: "Strata answered someone else since" }; live = null; }
        else { await save(); out = { saved: !!(live && live.fresh), tokens: live && live.tokens }; }
      }
    } catch (e) { out = { saved: false, why: e.message }; }
    busy = false;
    pump();
  }
  log(`save-live: ${JSON.stringify(out)} (${((Date.now() - t0) / 1000).toFixed(1)} s)`);
  res.writeHead(200, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  res.end(JSON.stringify(out));
}

function status(res) {
  const body = {
    upstream: UPSTREAM.href, dir: DIR, slots: !slotsOff(), queue: queue.length, busy,
    live: live && { messages: live.seq.length - 1, tokens: live.tokens, saved: live.fresh },
    files: entries.map((e) => ({ file: e.file, messages: e.seq.length - 1, tokens: e.tokens, gib: Number(gib(e.bytes || 0)), used: new Date(e.usedAt).toLocaleString("sv-SE") })),
    stats,
  };
  res.writeHead(200, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  res.end(JSON.stringify(body, null, 1));
}

// 11/14 (stage 2 of release/security/PLAN.md): the same fence Strata itself has, since passThrough()/forward() write
// Strata's own Host (127.0.0.1:8080) and so switch Strata's check off. A web page in a browser on this PC must not reach
// Strata through here by a DNS rebinding (another Host) or by sending from its own origin.
//  - Host: only the loopback names (127.0.0.1, localhost, [::1], any port) and those in PROXY_ALLOWED_HOSTS
//    ("name[:port],..."; empty by default); otherwise 421.
//  - Origin: when there is one (browsers send it; dsh, curl and PowerShell do not), it must be this same host;
//    Sec-Fetch-Site, when there is one, must be same-origin or none (typed in the address bar); otherwise 403.
const LOOPBACK = new Set(["127.0.0.1", "localhost", "[::1]"]);
const EXTRA_HOSTS = new Set((process.env.PROXY_ALLOWED_HOSTS || "").toLowerCase().split(/[\s,]+/).filter(Boolean));
function refusal(req) {
  const host = String(req.headers.host || "").toLowerCase();
  const m = host.match(/^(\[[0-9a-f:.]+\]|[^:[\]]+)(?::\d{1,5})?$/);
  if (!EXTRA_HOSTS.has(host) && !(m && LOOPBACK.has(m[1]))) return [421, "this Host is not served here"];
  const site = req.headers["sec-fetch-site"];
  if (site && site !== "same-origin" && site !== "none") return [403, `cross-site request refused (Sec-Fetch-Site: ${site})`];
  const origin = req.headers.origin;
  if (origin != null) {
    let o = null;
    try { o = new URL(origin); } catch { /* "null" and the like */ }
    if (!o || (o.protocol !== "http:" && o.protocol !== "https:") || o.host !== host) return [403, "cross-site request refused (Origin)"];
  }
  return null;
}

const server = http.createServer((req, res) => {
  const refused = refusal(req);
  if (refused) {
    log(`refused ${req.method} ${String(req.url).slice(0, 80)}: ${refused[1]}`);
    res.writeHead(refused[0], { "content-type": "application/json", "cache-control": "no-store", "x-content-type-options": "nosniff" });
    return res.end(JSON.stringify({ error: { message: refused[1] } }));
  }
  if (req.method === "GET" && req.url === "/proxy/status") return status(res);
  if (req.method === "POST" && req.url === "/proxy/save-live") { saveLive(res); return; }
  if (req.method === "POST" && /\/chat\/completions(\?|$)/.test(req.url)) {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => chat(req, res, Buffer.concat(chunks)));
    return;
  }
  passThrough(req, res);
});
server.requestTimeout = 0;   // a request may wait its turn for minutes
server.headersTimeout = 60000;
server.on("error", (e) => {
  log(`cannot listen on 127.0.0.1:${PORT}: ${e.message}`);
  console.error(e.message);
  process.exit(1);
});
server.listen(PORT, "127.0.0.1", () => {
  loadIndex();
  prune();
  log(`listening on 127.0.0.1:${PORT} -> ${UPSTREAM.href}, session files in ${DIR} (${entries.length} kept)`);
  console.log(`Strata session proxy: 127.0.0.1:${PORT} -> ${UPSTREAM.href} (log: ${LOG})`);
  console.log(`Strata session proxy: accepts Host loopback${EXTRA_HOSTS.size ? ` and ${[...EXTRA_HOSTS].join(", ")} (PROXY_ALLOWED_HOSTS)` : " only"}`);
});
