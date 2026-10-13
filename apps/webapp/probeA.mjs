import { chromium } from "playwright";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
const logs = [];
p.on("console", (m) => logs.push(m.type() + ": " + m.text().slice(0, 160)));
p.on("pageerror", (e) => logs.push("PAGEERROR " + String(e).slice(0, 200)));
await p.goto("http://localhost:5173/investigations", { waitUntil: "domcontentloaded" });
await p.waitForTimeout(11000);
await p.evaluate(() => {
  const c = [...document.querySelectorAll("button")].find((e) => e.innerText.trim() === "1111");
  if (c) c.click();
});
await p.waitForTimeout(8000);
const r = await p.evaluate(async () => {
  const hosts = document.querySelectorAll(".ui-graph-host").length;
  let imp = "n/a";
  try {
    const m = await import("/node_modules/.vite/deps/cytoscape.js");
    imp = "ok " + typeof m.default;
  } catch (e) { imp = "FAIL " + String(e).slice(0, 120); }
  return { hosts, imp, canvas: document.querySelectorAll("canvas").length };
});
console.log(JSON.stringify(r));
console.log(logs.filter((l) => /error|warn|cyto/i.test(l)).slice(0, 8).join("\n"));
await b.close();
