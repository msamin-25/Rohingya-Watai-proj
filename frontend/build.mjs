// Bundles src/js/main.js + src/styles.css into ONE self-contained file: dist/index.html.
// Output is deterministic so `make check` can verify that the committed dist/ is up to date.
import { build, transform } from "esbuild";
import { mkdir, readFile, writeFile } from "node:fs/promises";

const here = (p) => new URL(p, import.meta.url);

const js = await build({
  entryPoints: [here("src/js/main.js").pathname],
  bundle: true,
  format: "iife",
  minify: true,
  target: ["es2020"],
  legalComments: "none",
  write: false,
});
const css = await transform(await readFile(here("src/styles.css"), "utf8"), { loader: "css", minify: true });
const template = await readFile(here("src/index.html"), "utf8");

const script = js.outputFiles[0].text.trim().replace(/<\/script/gi, "<\\/script");
const html = template
  .replace("/*STYLE*/", () => css.code.trim())
  .replace("/*SCRIPT*/", () => script);

await mkdir(here("dist/"), { recursive: true });
await writeFile(here("dist/index.html"), html);
console.log(`dist/index.html  ${(html.length / 1024).toFixed(1)} KB`);
