import { readFileSync } from "node:fs";

import { makeEdgeId, makeObservationId } from "../../apps/webapp/src/lib/edgeFormation.ts";

interface DonorCase {
  a: string;
  b: string;
  kind: "assertion" | "evidence" | "possible_match" | "relationship" | "source_host" | "co_occurrence";
  source: string;
  material: string;
  digest: string;
}

const donor = JSON.parse(
  readFileSync(new URL("./donor_vectors.json", import.meta.url), "utf8"),
) as DonorCase[];

let failures = 0;
for (const row of donor) {
  const mine = makeEdgeId(row.a, row.b, row.kind, row.source);
  const expected = `UI-${row.digest}`;
  const ok = mine === expected;
  if (!ok) failures += 1;
  console.log(`${ok ? "OK  " : "FAIL"} ${row.kind.padEnd(15)} ${row.a} -> ${row.b}  ${mine}`);
}

const obsId = makeObservationId("co_occurrence", ["ENT-1", "ENT-2", "ENT-3"], "OBS-1");
console.log(`OBS  ${obsId}`);

console.log(failures === 0 ? "ALL MATCH THE PYTHON DONOR" : `${failures} FAILURES`);
process.exit(failures === 0 ? 0 : 1);
