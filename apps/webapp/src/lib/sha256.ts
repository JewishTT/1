/**
 * Synchronous SHA-256 (FIPS 180-4) over UTF-8 bytes.
 *
 * Exists because ADR-0023 requires a collision-resistant digest and the only
 * platform primitive available in this runtime is `crypto.subtle.digest`, which
 * is async. `makeEdgeId` is called from synchronous graph builders
 * (`entityGraph.ts`, `intelGraph.ts`) inside React render paths, so promoting
 * the whole edge-formation API to `Promise` would make the graph async for a
 * property of the *platform*, not of the identity rules. This module keeps the
 * API sync without weakening the digest.
 *
 * It is a transcription of the FIPS 180-4 specification, not a hash designed
 * for this codebase: the round constants, the schedule recurrence and the eight
 * initial state words are the standard's, so the output is byte-identical to
 * `hashlib.sha256` / `crypto.createHash("sha256")` for the same input. That
 * equality is what lets the frontend, the backend and a replay-from-log
 * derivation of an edge id agree, which is the whole point of ADR-0023.
 *
 * Input is always UTF-8 bytes (`TextEncoder`), never UTF-16 code units: the
 * retired `fnv1a` walked `charCodeAt`, so a Cyrillic or astral-plane identifier
 * hashed a different byte sequence here than on the Python side, and one
 * relation acquired two ids.
 */

/** The 64 FIPS 180-4 round constants K[0..63]. */
const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

/** The eight initial state words H[0..7] — the fractional parts of the square roots of the first eight primes. */
const INITIAL_STATE = new Uint32Array([
  0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
]);

const HEX = "0123456789abcdef";

/** Rotate a 32-bit word right; `>>> 0` keeps the value unsigned. */
function rotr(word: number, bits: number): number {
  return ((word >>> bits) | (word << (32 - bits))) >>> 0;
}

/** Lowercase hex of one 32-bit word, 8 characters. */
function hex8(word: number): string {
  let out = "";
  for (let shift = 28; shift >= 0; shift -= 4) {
    out += HEX[(word >>> shift) & 0xf];
  }
  return out;
}

/**
 * SHA-256 digest of `bytes` as 64 lowercase hex characters.
 *
 * Synchronous by construction — no `await`, no worker, no WASM — which is the
 * only reason this exists rather than `crypto.subtle.digest`.
 */
export function sha256Hex(bytes: Uint8Array): string {
  // Pad to a multiple of 64 leaving room for the 0x80 marker and a 64-bit
  // big-endian bit length: floor((n + 8) / 64) + 1 blocks.
  const padded = new Uint8Array((Math.floor((bytes.length + 8) / 64) + 1) * 64);
  padded.set(bytes);
  padded[bytes.length] = 0x80;
  // Material is far below 2^32 bytes, but the high word is written honestly
  // rather than assumed zero.
  const bitLength = bytes.length * 8;
  const high = Math.floor(bitLength / 0x100000000);
  const low = bitLength >>> 0;
  const tail = padded.length;
  padded[tail - 8] = (high >>> 24) & 0xff;
  padded[tail - 7] = (high >>> 16) & 0xff;
  padded[tail - 6] = (high >>> 8) & 0xff;
  padded[tail - 5] = high & 0xff;
  padded[tail - 4] = (low >>> 24) & 0xff;
  padded[tail - 3] = (low >>> 16) & 0xff;
  padded[tail - 2] = (low >>> 8) & 0xff;
  padded[tail - 1] = low & 0xff;

  const state = INITIAL_STATE.slice();
  const w = new Uint32Array(64);

  for (let offset = 0; offset < padded.length; offset += 64) {
    for (let t = 0; t < 16; t += 1) {
      const i = offset + t * 4;
      w[t] =
        ((padded[i] << 24) | (padded[i + 1] << 16) | (padded[i + 2] << 8) | padded[i + 3]) >>> 0;
    }
    for (let t = 16; t < 64; t += 1) {
      const x = w[t - 15];
      const y = w[t - 2];
      const s0 = (rotr(x, 7) ^ rotr(x, 18) ^ (x >>> 3)) >>> 0;
      const s1 = (rotr(y, 17) ^ rotr(y, 19) ^ (y >>> 10)) >>> 0;
      w[t] = (w[t - 16] + s0 + w[t - 7] + s1) >>> 0;
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
      const ch = ((e & f) ^ (~e & g)) >>> 0;
      // Five 32-bit addends stay exact in a double, so the trailing `>>> 0`
      // truncation is a correct mod-2^32, not a rounding.
      const temp1 = (h + S1 + ch + K[t] + w[t]) >>> 0;
      const S0 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) >>> 0;
      const maj = ((a & b) ^ (a & c) ^ (b & c)) >>> 0;
      const temp2 = (S0 + maj) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d + temp1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) >>> 0;
    }

    state[0] = (state[0] + a) >>> 0;
    state[1] = (state[1] + b) >>> 0;
    state[2] = (state[2] + c) >>> 0;
    state[3] = (state[3] + d) >>> 0;
    state[4] = (state[4] + e) >>> 0;
    state[5] = (state[5] + f) >>> 0;
    state[6] = (state[6] + g) >>> 0;
    state[7] = (state[7] + h) >>> 0;
  }

  let hex = "";
  for (let i = 0; i < 8; i += 1) hex += hex8(state[i]);
  return hex;
}

/** SHA-256 of a string's UTF-8 encoding, as 64 lowercase hex characters. */
export function sha256HexOf(text: string): string {
  return sha256Hex(new TextEncoder().encode(text));
}
