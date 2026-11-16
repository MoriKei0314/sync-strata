// A small QR code encoder for the phone link (11/15 係 R). Written here, not taken from a package: byte mode, error correction
// level M, versions 1-10 (up to 213 bytes; the link is about 70). It follows ISO/IEC 18004 the same way as Nayuki's public
// "QR Code generator" (MIT), re-written from the standard's steps; no code of it is copied.
//   qrMatrix(text) -> { size, rows: ["0101…", …] }   ("1" = dark; no quiet zone: the drawer adds 4 modules)

// level M, versions 1..10: total codewords, error-correction blocks, EC codewords per block
const TOTAL = [0, 26, 44, 70, 100, 134, 172, 196, 242, 292, 346];
const BLOCKS = [0, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5];
const ECC = [0, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26];
const ALIGN = [[], [], [6, 18], [6, 22], [6, 26], [6, 30], [6, 34], [6, 22, 38], [6, 24, 42], [6, 26, 46], [6, 28, 50]];

function gfMul(x, y) {
  let z = 0;
  for (let i = 7; i >= 0; i--) {
    z = (z << 1) ^ ((z >>> 7) * 0x11d);
    z ^= ((y >>> i) & 1) * x;
  }
  return z & 0xff;
}

function rsDivisor(degree) {
  const r = new Array(degree).fill(0);
  r[degree - 1] = 1;
  let root = 1;
  for (let i = 0; i < degree; i++) {
    for (let j = 0; j < r.length; j++) {
      r[j] = gfMul(r[j], root);
      if (j + 1 < r.length) r[j] ^= r[j + 1];
    }
    root = gfMul(root, 0x02);
  }
  return r;
}

function rsRemainder(data, divisor) {
  const r = new Array(divisor.length).fill(0);
  for (const b of data) {
    const f = b ^ r.shift();
    r.push(0);
    for (let i = 0; i < r.length; i++) r[i] ^= gfMul(divisor[i], f);
  }
  return r;
}

const bit = (x, i) => ((x >>> i) & 1) !== 0;

export function qrMatrix(text) {
  const bytes = [...Buffer.from(String(text), "utf8")];
  let ver = 0;
  for (let v = 1; v <= 10; v++) {
    const cap = (TOTAL[v] - BLOCKS[v] * ECC[v]) * 8;
    if (4 + (v < 10 ? 8 : 16) + bytes.length * 8 <= cap) { ver = v; break; }
  }
  if (!ver) throw new Error("text too long for the QR code");
  const dataLen = TOTAL[ver] - BLOCKS[ver] * ECC[ver];

  // the data bits: byte mode, the length, the bytes, a terminator, then the pad bytes
  const bits = [];
  const put = (val, n) => { for (let i = n - 1; i >= 0; i--) bits.push((val >>> i) & 1); };
  put(4, 4);
  put(bytes.length, ver < 10 ? 8 : 16);
  for (const b of bytes) put(b, 8);
  put(0, Math.min(4, dataLen * 8 - bits.length));
  while (bits.length % 8) bits.push(0);
  const data = [];
  for (let i = 0; i < bits.length; i += 8) data.push(bits.slice(i, i + 8).reduce((a, b) => (a << 1) | b, 0));
  for (let p = 0xec; data.length < dataLen; p ^= 0xec ^ 0x11) data.push(p);

  // split into blocks, add the error correction, interleave
  const nb = BLOCKS[ver];
  const ecLen = ECC[ver];
  const raw = TOTAL[ver];
  const nShort = nb - (raw % nb);
  const shortLen = Math.floor(raw / nb);
  const div = rsDivisor(ecLen);
  const blocks = [];
  for (let i = 0, k = 0; i < nb; i++) {
    const d = data.slice(k, k + shortLen - ecLen + (i < nShort ? 0 : 1));
    k += d.length;
    const blk = d.concat(rsRemainder(d, div));
    if (i < nShort) blk.splice(shortLen - ecLen, 0, 0);
    blocks.push(blk);
  }
  const words = [];
  for (let i = 0; i < blocks[0].length; i++) {
    for (let j = 0; j < blocks.length; j++) if (i !== shortLen - ecLen || j >= nShort) words.push(blocks[j][i]);
  }

  // the function patterns
  const size = ver * 4 + 17;
  const mod = Array.from({ length: size }, () => new Array(size).fill(false));
  const fn = Array.from({ length: size }, () => new Array(size).fill(false));
  const set = (x, y, dark) => { mod[y][x] = dark; fn[y][x] = true; };
  for (let i = 0; i < size; i++) { set(6, i, i % 2 === 0); set(i, 6, i % 2 === 0); }
  const finder = (cx, cy) => {
    for (let dy = -4; dy <= 4; dy++) for (let dx = -4; dx <= 4; dx++) {
      const x = cx + dx, y = cy + dy;
      if (x < 0 || y < 0 || x >= size || y >= size) continue;
      const d = Math.max(Math.abs(dx), Math.abs(dy));
      set(x, y, d !== 2 && d !== 4);
    }
  };
  finder(3, 3); finder(size - 4, 3); finder(3, size - 4);
  const al = ALIGN[ver];
  for (let i = 0; i < al.length; i++) for (let j = 0; j < al.length; j++) {
    if ((i === 0 && j === 0) || (i === 0 && j === al.length - 1) || (i === al.length - 1 && j === 0)) continue;
    for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) set(al[i] + dx, al[j] + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
  }
  const format = (mask) => {
    const d = (0 << 3) | mask;            // level M = 00
    let r = d;
    for (let i = 0; i < 10; i++) r = (r << 1) ^ ((r >>> 9) * 0x537);
    const b = ((d << 10) | r) ^ 0x5412;
    for (let i = 0; i <= 5; i++) set(8, i, bit(b, i));
    set(8, 7, bit(b, 6)); set(8, 8, bit(b, 7)); set(7, 8, bit(b, 8));
    for (let i = 9; i < 15; i++) set(14 - i, 8, bit(b, i));
    for (let i = 0; i < 8; i++) set(size - 1 - i, 8, bit(b, i));
    for (let i = 8; i < 15; i++) set(8, size - 15 + i, bit(b, i));
    set(8, size - 8, true);
  };
  format(0);
  if (ver >= 7) {
    let r = ver;
    for (let i = 0; i < 12; i++) r = (r << 1) ^ ((r >>> 11) * 0x1f25);
    const b = (ver << 12) | r;
    for (let i = 0; i < 18; i++) {
      const a = size - 11 + (i % 3), c = Math.floor(i / 3);
      set(a, c, bit(b, i)); set(c, a, bit(b, i));
    }
  }

  // the codewords, two columns at a time in a zigzag from the bottom right
  let k = 0;
  for (let right = size - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5;
    for (let v = 0; v < size; v++) for (let j = 0; j < 2; j++) {
      const x = right - j;
      const up = ((right + 1) & 2) === 0;
      const y = up ? size - 1 - v : v;
      if (!fn[y][x] && k < words.length * 8) { mod[y][x] = bit(words[k >>> 3], 7 - (k & 7)); k++; }
    }
  }

  const masked = (m) => {
    const out = mod.map((row) => row.slice());
    for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
      if (fn[y][x]) continue;
      let inv;
      switch (m) {
        case 0: inv = (x + y) % 2 === 0; break;
        case 1: inv = y % 2 === 0; break;
        case 2: inv = x % 3 === 0; break;
        case 3: inv = (x + y) % 3 === 0; break;
        case 4: inv = (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0; break;
        case 5: inv = ((x * y) % 2) + ((x * y) % 3) === 0; break;
        case 6: inv = (((x * y) % 2) + ((x * y) % 3)) % 2 === 0; break;
        default: inv = (((x + y) % 2) + ((x * y) % 3)) % 2 === 0;
      }
      if (inv) out[y][x] = !out[y][x];
    }
    return out;
  };
  // the penalty of ISO/IEC 18004 7.8.3 (runs, 2x2 blocks, finder-like patterns, balance); the lowest mask wins
  const penalty = (g) => {
    let p = 0;
    const lines = [];
    for (let i = 0; i < size; i++) { lines.push(g[i]); lines.push(g.map((row) => row[i])); }
    for (const line of lines) {
      let run = 1;
      for (let i = 1; i <= size; i++) {
        if (i < size && line[i] === line[i - 1]) run++;
        else { if (run >= 5) p += run - 2; run = 1; }
      }
      const s = "0000" + line.map((d) => (d ? "1" : "0")).join("") + "0000";
      for (const pat of ["10111010000", "00001011101"]) for (let i = s.indexOf(pat); i >= 0; i = s.indexOf(pat, i + 1)) p += 40;
    }
    let dark = 0;
    for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
      if (g[y][x]) dark++;
      if (x + 1 < size && y + 1 < size && g[y][x] === g[y][x + 1] && g[y][x] === g[y + 1][x] && g[y][x] === g[y + 1][x + 1]) p += 3;
    }
    p += Math.floor(Math.abs(dark * 20 - size * size * 10) / (size * size)) * 10;
    return p;
  };
  let best = null;
  for (let m = 0; m < 8; m++) {
    format(m);
    const g = masked(m);
    // format() wrote into mod; copy the format modules of this mask into g
    for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) if (fn[y][x]) g[y][x] = mod[y][x];
    const sc = penalty(g);
    if (!best || sc < best.sc) best = { sc, g };
  }
  return { size, version: ver, rows: best.g.map((row) => row.map((d) => (d ? "1" : "0")).join("")) };
}
