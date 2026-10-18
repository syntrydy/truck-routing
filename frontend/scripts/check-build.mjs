// Fails the build when MapLibre's worker is not next to its script in dist/assets: without it
// the map shows no vector tiles and no routes, and nothing else reports it but the browser.
// Also holds the initial script to its size budget (SPEC section 7), MapLibre's chunk excluded.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { gzipSync } from "node:zlib";

const INITIAL_JS_BUDGET_BYTES = 300 * 1000;

const assets = new URL("../dist/assets/", import.meta.url);
const files = readdirSync(assets);
const script = files.find((name) => /^maplibre-gl-.*\.js$/.test(name));
if (script === undefined) {
  console.error("check-build: no MapLibre chunk in dist/assets");
  process.exit(1);
}
const worker = new URL("maplibre-gl-worker.mjs", assets);
if (!existsSync(worker) || statSync(worker).size === 0) {
  console.error(
    `check-build: dist/assets/maplibre-gl-worker.mjs is missing, but ${script} will look for it`,
  );
  process.exit(1);
}
console.log(`check-build: MapLibre worker found next to ${script}`);

const initialBytes = files
  .filter((name) => name.endsWith(".js") && name !== script)
  .reduce((total, name) => total + gzipSync(readFileSync(new URL(name, assets))).length, 0);
if (initialBytes > INITIAL_JS_BUDGET_BYTES) {
  console.error(
    `check-build: the initial scripts are ${String(initialBytes)} bytes gzipped, over the ` +
      `${String(INITIAL_JS_BUDGET_BYTES)} byte budget`,
  );
  process.exit(1);
}
console.log(
  `check-build: initial scripts ${String(initialBytes)} of ${String(INITIAL_JS_BUDGET_BYTES)} bytes gzipped`,
);
