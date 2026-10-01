import { createHash } from "node:crypto";

import { sha256HexOf } from "../../apps/webapp/src/lib/sha256.ts";

const cases = [
  "",
  "abc",
  "a".repeat(55),
  "a".repeat(56),
  "a".repeat(63),
  "a".repeat(64),
  "a".repeat(65),
  "a".repeat(1000),
  "ИВАН",
  "ОРГАНИЗАЦИЯ",
  "идентичность-Ω",
  "😀 astral",
  '{"mode":"directed","type":"possible_match","object":"ENT-2","source":"CE-1","subject":"ENT-1"}',
];

let failures = 0;
for (const input of cases) {
  const mine = sha256HexOf(input);
  const theirs = createHash("sha256").update(input, "utf8").digest("hex");
  const ok = mine === theirs;
  if (!ok) failures += 1;
  console.log(`${ok ? "OK  " : "FAIL"} len=${input.length} ${mine}${ok ? "" : ` != ${theirs}`}`);
}

// NIST FIPS 180-4 published vectors, independent of node's crypto.
const nist: Array<[string, string]> = [
  ["", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"],
  ["abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"],
  [
    "a".repeat(1000000),
    "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0",
  ],
];
for (const [input, expected] of nist) {
  const mine = sha256HexOf(input);
  const ok = mine === expected;
  if (!ok) failures += 1;
  console.log(`${ok ? "OK  " : "FAIL"} NIST len=${input.length} ${mine}`);
}

console.log(failures === 0 ? "ALL MATCH" : `${failures} FAILURES`);
process.exit(failures === 0 ? 0 : 1);
