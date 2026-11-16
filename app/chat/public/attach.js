// 10/30 本人「スマホ版の UI で，＋ボタンで画像（と対応しているならファイルも）を送れるように」．
// 画像は dsh の送信の部品 {type:"image", mediaType, data(base64), name} で送る（png・jpeg・webp・gif．大きい写真は長い辺 2,048 px の
// JPEG に縮める）．ファイルは POST /api/session/uploadFileBinary?sessionId=…&name=…（中身そのまま）で dsh に預け，返ってきた控えを
// {type:"file", receiptId} で送る（dsh-client-file-upload と同じ道）．
// 画像を読めるのは dsh の設定の「画像あり」のモデル（strata-vision）だけで，ほかのモデルに送ると dsh が断る
// （session/attachment-invalid，MODEL_DOES_NOT_SUPPORT_IMAGES）ので，今のモデルが画像なしなら確かめてから切り替えて送る．
// Strata が画像なしで動いているときは送らずに知らせる（Strata が要求ごと断るため．付けた画像は入力欄に残る）．
"use strict";

const Attach = (() => {
  const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];
  const MAX_SIDE = 2048;
  const MAX_BYTES = 3 * 1024 * 1024;

  const isImage = (file) => /^image\//.test(file.type || "") || /\.(png|jpe?g|webp|gif|heic|heif|bmp)$/i.test(file.name || "");
  const fmtSize = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

  // 隠した <input type=file> で選ばせる．選ばずに閉じたときは [] を返す
  function pick({ accept = "", capture = null, multiple = true } = {}) {
    return new Promise((resolve) => {
      const input = h("input", { type: "file", accept: accept || null, capture, multiple: multiple || null, style: "display:none" });
      const done = (files) => { input.remove(); resolve(files); };
      input.addEventListener("change", () => done([...(input.files || [])]));
      input.addEventListener("cancel", () => done([]));
      document.body.append(input);
      input.click();
    });
  }

  function base64(blob) {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(String(r.result).replace(/^data:[^,]*,/, ""));
      r.onerror = () => reject(r.error || new Error(tr("Cannot read it")));
      r.readAsDataURL(blob);
    });
  }

  async function imagePart(file) {
    let blob = file;
    let type = (file.type || "").toLowerCase();
    let bmp = null;
    try { bmp = await createImageBitmap(file); } catch { /* この端末のブラウザーでは描けない形式 */ }
    const big = bmp && Math.max(bmp.width, bmp.height) > MAX_SIDE;
    if (!IMAGE_TYPES.includes(type) || file.size > MAX_BYTES || big) {
      if (!bmp) throw new Error(tr("{0}: this image format cannot be read", [file.name || tr("image")]));
      const s = Math.min(1, MAX_SIDE / Math.max(bmp.width, bmp.height));
      const c = document.createElement("canvas");
      c.width = Math.max(1, Math.round(bmp.width * s));
      c.height = Math.max(1, Math.round(bmp.height * s));
      c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
      blob = await new Promise((res) => c.toBlob(res, "image/jpeg", 0.85));
      if (!blob) throw new Error(tr("{0}: could not be made smaller", [file.name || tr("image")]));
      type = "image/jpeg";
    }
    if (bmp && bmp.close) bmp.close();
    const name = type === "image/jpeg" && !/\.jpe?g$/i.test(file.name || "") ? `${(file.name || "image").replace(/\.[^.]*$/, "")}.jpg` : (file.name || "image");
    return { type: "image", mediaType: type, data: await base64(blob), name };
  }

  function visionModel() {
    const cat = Store.S.catalog;
    const g = cat && cat.groups.find((x) => x.id === "strata");
    // 11/10: 画像を読めないモデルの会話に画像を付けたら，R7（いつもの精度）に切り替える（無ければ前からの strata-vision）
    return (g && (g.models.find((m) => m.id === "strata-r7") || g.models.find((m) => /vision/i.test(m.id)))) || null;
  }
  // 11/10: strata-r4 .. strata-r7 も画像あり（dsh の設定で input に image）．画像を付けても strata-vision に切り替えない（選んだ R が外れるので）
  const acceptsImages = (sel) => !!(sel && sel.provider === "strata" && (/vision/i.test(sel.model || "") || /^strata-r\d+$/.test(sel.model || "")));

  // atts: [{kind: "image" | "file", file}]．sel: その会話の今のモデル（新しい会話では選んだもの）
  async function send({ sessionId, text, atts, mode = "queue", sel }) {
    if (atts.some((a) => a.kind === "image")) {
      const st = Store.S.strata;
      if (st && st.online && !st.images) {
        throw new Error(tr("The running Strata cannot read images. Restart Strata, then send again (the images are still in the box)"));
      }
      if (!acceptsImages(sel)) {
        const vm = visionModel();
        if (!vm) throw new Error(tr("dsh has no model that reads images (strata-vision) in its settings"));
        const ok = await confirmSheet({
          title: tr("Switching to a model that reads images"),
          message: tr("Only “{0}” can read images. This conversation will switch to it before sending (you can switch back later).", [vm.name]),
          okLabel: tr("Switch and send"),
        });
        if (!ok) throw new Error(tr("Not sent (the images are still in the box)"));
        const eff = sel && sel.reasoningEffort;
        await Api.selectModel(sessionId, "strata", vm.id, eff).catch(() => Api.selectModel(sessionId, "strata", vm.id));
      }
    }
    return Api.prompt(sessionId, text, mode, await parts(sessionId, atts));
  }

  // 付けたものを送信の部品に（画像は縮めて base64，ファイルは預けて控え）．11/14: スラッシュ命令の submittedAttachments もこの形
  async function parts(sessionId, atts) {
    const out = [];
    for (const a of atts) {
      if (a.kind === "image") out.push(await imagePart(a.file));
      else out.push({ type: "file", receiptId: (await Api.uploadFile(sessionId, a.file)).receiptId });
    }
    return out;
  }

  // ＋ボタンのシート: 写真・カメラ・ファイル．選んだものを add(files, kind) に渡す
  function openSheetFor(add) {
    const row = (ic, title, note, fn) => h("button", { class: "sheet-item with-icon", type: "button", onclick: async () => { s.close(true); const f = await fn(); if (f.length) add(f); } },
      icon(ic),
      h("span", { class: "att-row" }, h("span", {}, title), h("span", { class: "muted small" }, note)));
    const s = openSheet([
      h("div", { class: "sheet-title" }, tr("Attach images or files")),
      // Attach.pick を通して呼ぶ（試験で選ぶ部分を差し替えられるように）
      row("image", tr("Choose photos or images"), tr("Sent as images. Strata (with images) looks at them and answers"), () => Attach.pick({ accept: "image/*" }).then((f) => f.map((x) => ({ file: x, kind: "image" })))),
      row("camera", tr("Take a photo"), tr("The photo is sent as an image"), () => Attach.pick({ accept: "image/*", capture: "environment", multiple: false }).then((f) => f.map((x) => ({ file: x, kind: "image" })))),
      row("file", tr("Choose files"), tr("Uploaded to dsh as files (images too). The agent reads them"), () => Attach.pick({}).then((f) => f.map((x) => ({ file: x, kind: "file" })))),
    ]);
  }

  return { pick, isImage, fmtSize, send, parts, visionModel, openSheetFor };
})();
