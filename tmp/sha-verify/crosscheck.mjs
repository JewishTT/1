// 1/tmp/sha-verify/crosscheck.ts
import { readFileSync } from "node:fs";

// 1/apps/webapp/src/lib/sha256.ts
var K = new Uint32Array([
  1116352408,
  1899447441,
  3049323471,
  3921009573,
  961987163,
  1508970993,
  2453635748,
  2870763221,
  3624381080,
  310598401,
  607225278,
  1426881987,
  1925078388,
  2162078206,
  2614888103,
  3248222580,
  3835390401,
  4022224774,
  264347078,
  604807628,
  770255983,
  1249150122,
  1555081692,
  1996064986,
  2554220882,
  2821834349,
  2952996808,
  3210313671,
  3336571891,
  3584528711,
  113926993,
  338241895,
  666307205,
  773529912,
  1294757372,
  1396182291,
  1695183700,
  1986661051,
  2177026350,
  2456956037,
  2730485921,
  2820302411,
  3259730800,
  3345764771,
  3516065817,
  3600352804,
  4094571909,
  275423344,
  430227734,
  506948616,
  659060556,
  883997877,
  958139571,
  1322822218,
  1537002063,
  1747873779,
  1955562222,
  2024104815,
  2227730452,
  2361852424,
  2428436474,
  2756734187,
  3204031479,
  3329325298
]);
var INITIAL_STATE = new Uint32Array([
  1779033703,
  3144134277,
  1013904242,
  2773480762,
  1359893119,
  2600822924,
  528734635,
  1541459225
]);
var HEX = "0123456789abcdef";
function rotr(word, bits) {
  return (word >>> bits | word << 32 - bits) >>> 0;
}
function hex8(word) {
  let out = "";
  for (let shift = 28; shift >= 0; shift -= 4) {
    out += HEX[word >>> shift & 15];
  }
  return out;
}
function sha256Hex(bytes) {
  const padded = new Uint8Array((Math.floor((bytes.length + 8) / 64) + 1) * 64);
  padded.set(bytes);
  padded[bytes.length] = 128;
  const bitLength = bytes.length * 8;
  const high = Math.floor(bitLength / 4294967296);
  const low = bitLength >>> 0;
  const tail = padded.length;
  padded[tail - 8] = high >>> 24 & 255;
  padded[tail - 7] = high >>> 16 & 255;
  padded[tail - 6] = high >>> 8 & 255;
  padded[tail - 5] = high & 255;
  padded[tail - 4] = low >>> 24 & 255;
  padded[tail - 3] = low >>> 16 & 255;
  padded[tail - 2] = low >>> 8 & 255;
  padded[tail - 1] = low & 255;
  const state = INITIAL_STATE.slice();
  const w = new Uint32Array(64);
  for (let offset = 0; offset < padded.length; offset += 64) {
    for (let t = 0; t < 16; t += 1) {
      const i = offset + t * 4;
      w[t] = (padded[i] << 24 | padded[i + 1] << 16 | padded[i + 2] << 8 | padded[i + 3]) >>> 0;
    }
    for (let t = 16; t < 64; t += 1) {
      const x = w[t - 15];
      const y = w[t - 2];
      const s0 = (rotr(x, 7) ^ rotr(x, 18) ^ x >>> 3) >>> 0;
      const s1 = (rotr(y, 17) ^ rotr(y, 19) ^ y >>> 10) >>> 0;
      w[t] = w[t - 16] + s0 + w[t - 7] + s1 >>> 0;
    }
    let a = state[0];
    let b = state[1];
    let c = state[2];
    let d = state[3];
    let e = state[4];
    let f = state[5];
    let g = state[6];
    let h = state[7];
    for (let t = 0; t < 64; t += 1) {
      const S1 = (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) >>> 0;
      const ch = (e & f ^ ~e & g) >>> 0;
      const temp1 = h + S1 + ch + K[t] + w[t] >>> 0;
      const S0 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) >>> 0;
      const maj = (a & b ^ a & c ^ b & c) >>> 0;
      const temp2 = S0 + maj >>> 0;
      h = g;
      g = f;
      f = e;
      e = d + temp1 >>> 0;
      d = c;
      c = b;
      b = a;
      a = temp1 + temp2 >>> 0;
    }
    state[0] = state[0] + a >>> 0;
    state[1] = state[1] + b >>> 0;
    state[2] = state[2] + c >>> 0;
    state[3] = state[3] + d >>> 0;
    state[4] = state[4] + e >>> 0;
    state[5] = state[5] + f >>> 0;
    state[6] = state[6] + g >>> 0;
    state[7] = state[7] + h >>> 0;
  }
  let hex = "";
  for (let i = 0; i < 8; i += 1) hex += hex8(state[i]);
  return hex;
}
function sha256HexOf(text) {
  return sha256Hex(new TextEncoder().encode(text));
}

// 1/apps/webapp/src/lib/edgeFormation.ts
var EDGE_ARITY = {
  assertion: "directed",
  evidence: "directed",
  possible_match: "directed",
  relationship: "directed",
  source_host: "directed",
  co_occurrence: "undirected"
};
function arityOf(kind) {
  return EDGE_ARITY[kind];
}
var EDGE_ID_PREFIX = "UI-";
var OBSERVATION_ID_PREFIX = "UO-";
var OBSERVATION_IDENTITY_SCHEMA = "ui-observation-identity/v1";
function compareCodePoints(left, right) {
  if (left === right) return 0;
  const a = Array.from(left);
  const b = Array.from(right);
  const shared = Math.min(a.length, b.length);
  for (let i = 0; i < shared; i += 1) {
    const x = a[i].codePointAt(0);
    const y = b[i].codePointAt(0);
    if (x !== y) return x < y ? -1 : 1;
  }
  if (a.length === b.length) return 0;
  return a.length < b.length ? -1 : 1;
}
function canonicalMaterial(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalMaterial(item)).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    const record = value;
    const keys = Object.keys(record).sort(compareCodePoints);
    return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalMaterial(record[key])}`).join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}
function digest128(material) {
  return sha256HexOf(material).slice(0, 32);
}
function edgeMaterial(a, b, kind, source) {
  const mode = arityOf(kind);
  if (mode === "undirected") {
    return { mode, type: kind, members: [.../* @__PURE__ */ new Set([a, b])].sort(compareCodePoints), source };
  }
  return { mode, type: kind, subject: a, object: b, source };
}
function makeEdgeId(nodeA, nodeB, kind, source) {
  return EDGE_ID_PREFIX + digest128(canonicalMaterial(edgeMaterial(nodeA, nodeB, kind, source)));
}
function makeObservationId(kind, participants, source) {
  return OBSERVATION_ID_PREFIX + digest128(
    canonicalMaterial({
      identity_schema: OBSERVATION_IDENTITY_SCHEMA,
      kind,
      members: [...new Set(participants)].sort(compareCodePoints),
      source
    })
  );
}

// 1/tmp/sha-verify/crosscheck.ts
var donor = JSON.parse(
  readFileSync(new URL("./donor_vectors.json", import.meta.url), "utf8")
);
var failures = 0;
for (const row of donor) {
  const mine = makeEdgeId(row.a, row.b, row.kind, row.source);
  const expected = `UI-${row.digest}`;
  const ok = mine === expected;
  if (!ok) failures += 1;
  console.log(`${ok ? "OK  " : "FAIL"} ${row.kind.padEnd(15)} ${row.a} -> ${row.b}  ${mine}`);
}
var obsId = makeObservationId("co_occurrence", ["ENT-1", "ENT-2", "ENT-3"], "OBS-1");
console.log(`OBS  ${obsId}`);
console.log(failures === 0 ? "ALL MATCH THE PYTHON DONOR" : `${failures} FAILURES`);
process.exit(failures === 0 ? 0 : 1);
