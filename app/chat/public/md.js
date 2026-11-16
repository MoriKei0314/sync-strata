// A small Markdown renderer for model replies: fenced code, headings, lists, tables, quotes, paragraphs,
// and inline code, bold and http(s) links. Everything is HTML-escaped first, so model text cannot inject markup.
"use strict";

const Md = (() => {
  const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function inline(text) {
    const parts = text.split(/(`[^`\n]+`)/g);
    return parts.map((p) => {
      if (p.length > 1 && p.startsWith("`") && p.endsWith("`")) return `<code>${esc(p.slice(1, -1))}</code>`;
      let h = esc(p);
      h = h.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
      h = h.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
      return h;
    }).join("");
  }

  const isTableRow = (l) => /^\s*\|.*\|\s*$/.test(l);
  const isRule = (l) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l);
  const cells = (l) => l.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => inline(c.trim()));
  const LI = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;   // 一覧の項目の行（字下げ・印・本文）

  // marks (11/15, optional): gets the line number where each top-level block starts (used by stream below; the output is the same)
  function render(src, marks) {
    const lines = String(src || "").replace(/\r\n?/g, "\n").split("\n");
    const out = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (marks && line.trim()) marks.push(i);
      const fence = line.match(/^\s*(```+|~~~+)\s*([\w+-]*)\s*$/);
      if (fence) {
        const body = [];
        i++;
        while (i < lines.length && !lines[i].trim().startsWith(fence[1])) body.push(lines[i++]);
        i++;
        out.push(`<pre><code>${esc(body.join("\n"))}</code></pre>`);
        continue;
      }
      const head = line.match(/^(#{1,6})\s+(.*)$/);
      if (head) {
        const level = Math.min(head[1].length + 2, 6);
        out.push(`<h${level}>${inline(head[2])}</h${level}>`);
        i++;
        continue;
      }
      if (isTableRow(line) && i + 1 < lines.length && isRule(lines[i + 1])) {
        const rows = [cells(line)];
        i += 2;
        while (i < lines.length && isTableRow(lines[i])) rows.push(cells(lines[i++]));
        const [th, ...tb] = rows;
        out.push(`<div class="table"><table><thead><tr>${th.map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>${
          tb.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
        continue;
      }
      const item = line.match(LI);
      if (item) {
        const ordered = /\d/.test(item[2]);
        const items = [];
        while (i < lines.length) {
          const m = lines[i].match(LI);
          if (m) {
            items.push({ depth: Math.floor(m[1].length / 2), mark: m[2], paras: [m[3]] });
            i++;
          } else if (lines[i].trim() && /^\s{2,}/.test(lines[i]) && items.length) {
            const ps = items[items.length - 1].paras;
            ps[ps.length - 1] += " " + lines[i++].trim();
          } else if (!lines[i].trim() && items.length) {
            // 11/16: 空行をはさんだ一覧（CommonMark の loose list）も 1 つの一覧に．前は空行で一覧を閉じ，次の項目が
            // 新しい <ol> になって番号が毎回 1 から振り直された（「1. 1. 1.」の表示）．次の空でない行が，同じ種類の項目か
            // 字下げした子の項目なら一覧を続け，字下げした続きの文（コードの囲みでない）なら最後の項目の次の段落にする
            let j = i;
            while (j < lines.length && !lines[j].trim()) j++;
            const n = j < lines.length ? lines[j].match(LI) : null;
            if (n && (Math.floor(n[1].length / 2) > 0 || /\d/.test(n[2]) === ordered)) { i = j; continue; }
            if (!n && j < lines.length && /^\s{2,}/.test(lines[j]) && !/^\s*(```|~~~)/.test(lines[j])) {
              items[items.length - 1].paras.push(lines[j].trim());
              i = j + 1;
              continue;
            }
            break;
          } else break;
        }
        const tag = ordered ? "ol" : "ul";
        // 11/16: 番号は書かれた数から数える（CommonMark と同じく，同じ深さの最初の項目の数から 1 ずつ）．<li value> で
        // 決めるので，<ol> の中に入れた子の項目（同じ <ol> の <li> として平らに並べている）で親の番号がずれることもない
        const cnt = [];
        out.push(`<${tag}>${items.map((it) => {
          cnt.length = it.depth + 1;
          let attr = "";
          let cls = `d${Math.min(it.depth, 3)}`;
          if (/\d/.test(it.mark)) {
            cnt[it.depth] = cnt[it.depth] === undefined ? parseInt(it.mark, 10) : cnt[it.depth] + 1;
            if (ordered) attr = ` value="${cnt[it.depth]}"`;
          } else if (ordered) cls += " b";
          return `<li class="${cls}"${attr}>${it.paras.map(inline).join("<br>")}</li>`;
        }).join("")}</${tag}>`);
        continue;
      }
      if (/^\s*>/.test(line)) {
        const body = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) body.push(lines[i++].replace(/^\s*>\s?/, ""));
        out.push(`<blockquote>${render(body.join("\n"))}</blockquote>`);
        continue;
      }
      if (/^\s*([-*_])\s*\1\s*\1[\s\1]*$/.test(line)) {
        out.push("<hr>");
        i++;
        continue;
      }
      if (!line.trim()) {
        i++;
        continue;
      }
      const para = [];
      while (i < lines.length && lines[i].trim() && !/^(\s*(```|~~~)|#{1,6}\s|\s*([-*+]|\d+[.)])\s|\s*>)/.test(lines[i])
        && !(isTableRow(lines[i]) && i + 1 < lines.length && isRule(lines[i + 1]))) para.push(lines[i++]);
      out.push(`<p>${para.map(inline).join("<br>")}</p>`);
    }
    return out.join("");
  }

  // 11/15: 生成中の返事の本文を描く係（view-chat.js の liveChunk）．毎回の全文の作り直しをやめ，確定した塊は一度だけ描いて残し，
  // 書き途中の最後の塊だけを描き直す．render は空行で必ず塊を閉じ（コードの囲みの中を除く），空行より先を読まないので，
  // render 自身が数えた「空行のすぐ後から始まる塊」の手前で切れば，分けて描いても全文を一度に描いたのと同じ HTML になる．
  // \r を含むとき・full のときは全文を一度に描く（生成の終わりは必ず full: できあがりは前と 1 字も変わらない）．
  function stream(el) {
    let cut = 0;    // text[0, cut) は描き終えて el に残してある
    let tailN = 0;  // el の末尾の，書き途中の部分の節の数
    const frag = (html) => { const t = document.createElement("template"); t.innerHTML = html; return t.content; };
    function update(text, full) {
      if (full || cut > text.length || /\r/.test(text)) {
        el.innerHTML = render(text);
        cut = 0;
        tailN = el.childNodes.length;   // 次に分けて描くときは頭から
        return;
      }
      const rest = text.slice(cut);
      const lines = rest.split("\n");
      const marks = [];
      let html = render(rest, marks);
      let k = 0;
      // 11/16: 書き途中の最後の行が一覧の印の書きかけ（「2」「2.」「-」）なら，そこでは切らない（前の一覧が空行の後も続く
      // ことがあるので，先に確定させると番号が分かれる．印が書き終わってから描き分ける）
      const partial = (j) => marks[j] === lines.length - 1 && /^\s*(\d{1,9}[.)]?|[-*+])\s*$/.test(lines[marks[j]]);
      for (let j = marks.length - 1; j > 0; j--) if (!lines[marks[j] - 1].trim() && !partial(j)) { k = marks[j]; break; }
      for (; tailN > 0 && el.lastChild; tailN--) el.lastChild.remove();
      tailN = 0;
      if (k) {
        const head = lines.slice(0, k).join("\n");
        el.append(frag(render(head)));
        cut += head.length + 1;
        html = render(lines.slice(k).join("\n"));
      }
      const f = frag(html);
      tailN = f.childNodes.length;
      el.append(f);
    }
    return { update };
  }

  return { render, esc, stream };
})();
