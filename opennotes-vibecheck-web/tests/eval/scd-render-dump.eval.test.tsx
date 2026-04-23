/**
 * TASK-1471.23.08 — render dump for SCD eval.
 *
 * Reads the OLD/NEW SCDReport JSON dumped by
 * `opennotes-vibecheck-server/scripts/eval_scd_register.py`, mounts each into
 * `<ScdReport />`, and writes the rendered text content to disk so the eval
 * markdown can show what the user actually sees in the sidebar slot.
 *
 * Not part of normal CI — run explicitly:
 *   pnpm exec vitest run tests/eval/scd-render-dump.eval.test.tsx
 */
import { describe, it, afterEach, expect } from "vitest";
import { render, cleanup } from "@solidjs/testing-library";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import ScdReport from "../../src/components/sidebar/ScdReport";
import type { components } from "../../src/lib/generated-types";

type SCDReport = components["schemas"]["SCDReport"];

const HERE = dirname(fileURLToPath(import.meta.url));
const EVAL_DIR = resolve(HERE, "../../../docs/specs/vibecheck/scd-register-eval");

function loadJson(name: string, variant: "old" | "new"): SCDReport {
  const path = resolve(EVAL_DIR, name, `${variant}.json`);
  const raw = JSON.parse(readFileSync(path, "utf-8")) as Record<string, unknown>;
  // Strip eval-only annotations so the component sees a clean payload.
  delete raw._eval_note;
  delete raw._eval_error;
  return raw as SCDReport;
}

function dumpRender(name: string, variant: "old" | "new"): string {
  const scd = loadJson(name, variant);
  const { container } = render(() => <ScdReport scd={scd} />);
  const text = (container.textContent ?? "").trim();
  cleanup();
  return text;
}

afterEach(() => {
  cleanup();
});

describe("ScdReport eval render dump", () => {
  for (const name of [
    "transcript-1-heated",
    "transcript-2-measured",
    "transcript-3-monologue",
  ]) {
    it(`dumps OLD + NEW rendered text for ${name}`, () => {
      const oldText = dumpRender(name, "old");
      const newText = dumpRender(name, "new");
      const out = [
        `# ${name} — rendered ScdReport text`,
        "",
        "## OLD prompt output rendered through new ScdReport.tsx",
        "",
        oldText || "(empty)",
        "",
        "## NEW prompt output rendered through new ScdReport.tsx",
        "",
        newText || "(empty)",
        "",
      ].join("\n");
      writeFileSync(resolve(EVAL_DIR, name, "rendered.md"), out, "utf-8");
      expect(oldText.length + newText.length).toBeGreaterThan(0);
    });
  }
});
