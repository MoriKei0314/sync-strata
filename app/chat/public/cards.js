// Cards for what the agent is waiting on: a tool approval (allow once / reject) or questions with options.
// Both arrive as $events waterfalls and are answered through $events/result; the first client to answer
// wins, and the others get a cancel, which removes the card here.
"use strict";

function settle(eventId, value) {
  return Api.settle(Store.S.clientId, eventId, { kind: "result", value }).then(() => {
    Store.S.pending.delete(eventId);
  });
}

function approvalCard(p) {
  const r = p.request || {};
  const reason = (r.displayReason && (r.displayReason.ja || r.displayReason.en)) || r.reason || "";
  const buttons = h("div", { class: "card-actions" });
  const answer = async (value, btn) => {
    for (const b of buttons.children) b.disabled = true;
    btn.classList.add("busy");
    try {
      await settle(p.eventId, value);
      el.replaceWith(h("div", { class: "marker" }, value === "rejected" ? tr("Denied: {0}", [r.toolName]) : tr("Allowed: {0}", [r.toolName])));
    } catch (e) {
      toast(tr("Could not answer: {0}", [e.message || e.code]));
      for (const b of buttons.children) b.disabled = false;
    }
  };
  buttons.append(
    h("button", { class: "btn ghost", type: "button", onclick: (e) => answer("rejected", e.currentTarget) }, tr("Deny")),
    h("button", { class: "btn primary", type: "button", onclick: (e) => answer("allowed-once", e.currentTarget) }, tr("Allow once")));
  const el = h("div", { class: "ask" },
    h("div", { class: "ask-title" }, icon("tool", "small"), tr("Allow this tool to run?")),
    h("div", { class: "ask-tool" }, r.toolName || tr("Tool")),
    reason ? h("div", { class: "ask-detail" }, reason) : null,
    buttons);
  return el;
}

function questionCard(p) {
  const qs = (p.request && p.request.questions) || [];
  const state = qs.map(() => ({ selected: new Set(), custom: "" }));
  const send = h("button", { class: "btn primary", type: "button" }, tr("Answer"));
  const blocks = qs.map((q, i) => {
    const st = state[i];
    const opts = (q.options || []).map((o) => {
      const b = h("button", { class: "option", type: "button" },
        h("div", { class: "option-label" }, o.label), o.description ? h("div", { class: "option-desc" }, o.description) : null);
      b.addEventListener("click", () => {
        if (!q.multiSelect) {
          st.selected.clear();
          for (const x of b.parentElement.children) x.classList.remove("on");
        }
        if (st.selected.has(o.label)) { st.selected.delete(o.label); b.classList.remove("on"); }
        else { st.selected.add(o.label); b.classList.add("on"); }
      });
      return b;
    });
    const custom = h("input", { class: "custom", type: "text", placeholder: opts.length ? tr("Other (type your own)") : tr("Type your answer") });
    custom.addEventListener("input", () => { st.custom = custom.value; });
    return h("div", { class: "question" },
      q.header ? h("div", { class: "q-header" }, q.header) : null,
      h("div", { class: "q-text" }, q.question),
      q.detail ? h("div", { class: "ask-detail" }, q.detail) : null,
      opts.length ? h("div", { class: "options" }, opts) : null,
      custom);
  });
  send.addEventListener("click", async () => {
    const answers = qs.map((q, i) => ({
      id: q.id, selected: [...state[i].selected], ...(state[i].custom.trim() ? { custom: state[i].custom.trim() } : {}),
    }));
    send.disabled = true;
    try {
      await settle(p.eventId, { answers });
      el.replaceWith(h("div", { class: "marker" }, tr("Answered the questions")));
    } catch (e) {
      toast(tr("Could not answer: {0}", [e.message || e.code]));
      send.disabled = false;
    }
  });
  const el = h("div", { class: "ask" },
    h("div", { class: "ask-title" }, trp("{0} question", "{0} questions", qs.length)), blocks, h("div", { class: "card-actions" }, send));
  return el;
}

function pendingCards(sessionId) {
  return Store.pendingFor(sessionId).map((p) => (p.event === "approval/request" ? approvalCard(p) : questionCard(p)));
}
