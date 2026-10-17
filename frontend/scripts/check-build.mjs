// Fails the build when MapLibre's worker is not next to its script in dist/assets: without it
// the map shows no vector tiles and no routes, and nothing else reports it but the browser.
import { existsSync, readdirSync, statSync } from "node:fs";

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
