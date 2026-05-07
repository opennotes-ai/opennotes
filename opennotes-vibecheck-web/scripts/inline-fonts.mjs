#!/usr/bin/env node
// Regenerates src/assets/fonts/fonts-data.ts from the .ttf binaries in
// src/assets/fonts/. Run after replacing/adding a font.
//
// Why inline as base64 rather than load from disk? Vinxi/Nitro production
// bundles do not reliably ship src/assets/fonts/*.ttf into the runtime
// container, and `import.meta.url` resolves to different paths in vitest
// vs vinxi-dev vs vinxi-build. A checked-in TS module of base64 strings
// works identically in every runtime — Rollup/Vite tree-shake it like any
// other source import, and Satori receives plain Buffers at module init.

import { readFileSync, writeFileSync } from "node:fs";

const FONTS = [
  ["PLEX_SANS_700_B64", "src/assets/fonts/IBMPlexSansCond-Bold.ttf"],
  ["PLEX_SANS_600_B64", "src/assets/fonts/IBMPlexSansCond-SemiBold.ttf"],
  ["PLEX_SERIF_400_B64", "src/assets/fonts/IBMPlexSerif-Regular.ttf"],
];

const lines = [
  "// AUTO-GENERATED — regenerate with: node scripts/inline-fonts.mjs",
  "// Source TTFs live under src/assets/fonts/. Inlining as base64 lets the",
  "// /api/og Satori endpoint load fonts at module init in any runtime",
  "// (vitest, vinxi dev, vinxi build/Cloud Run) without filesystem path resolution.",
  "",
];

for (const [name, path] of FONTS) {
  const b64 = readFileSync(path).toString("base64");
  lines.push(`export const ${name} = ${JSON.stringify(b64)};`);
}
lines.push("");

writeFileSync("src/assets/fonts/fonts-data.ts", lines.join("\n"));
console.log(`wrote ${lines.join("\n").length} bytes to src/assets/fonts/fonts-data.ts`);
