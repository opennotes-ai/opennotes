import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { StepsList, type Step, type StepsListProps } from "./steps-list";

const stepsSource = readFileSync(
  resolve("src/components/steps-list.tsx"),
  "utf8",
);

describe("<StepsList /> source contract", () => {
  it("uses semantic <ol> as outer element", () => {
    expect(stepsSource).toContain("<ol");
  });

  it("renders zero-padded numerals via padStart(2, '0')", () => {
    expect(stepsSource).toContain('padStart(2, "0")');
  });

  it("marks numerals as decorative with aria-hidden", () => {
    expect(stepsSource).toContain('aria-hidden="true"');
  });

  it("uses tabular-nums for numeral alignment", () => {
    expect(stepsSource).toContain("tabular-nums");
  });

  it("supports optional 2-column layout via columns prop", () => {
    expect(stepsSource).toContain("sm:grid-cols-2");
    expect(stepsSource).toContain("columns()");
  });

  it("conditionally renders detail via Show", () => {
    expect(stepsSource).toContain("Show when={step.detail}");
  });

  it("uses token color classes only (no inline hex)", () => {
    expect(stepsSource).not.toMatch(/#[0-9a-fA-F]{3,8}/);
    expect(stepsSource).toContain("text-muted-foreground");
    expect(stepsSource).toContain("text-foreground");
  });

  it("does not use icons-above-heading or border-stripe patterns", () => {
    expect(stepsSource).not.toMatch(/border-l-\[/);
    expect(stepsSource).not.toMatch(/border-r-\[/);
  });

  it("caps body width at 70ch for readability", () => {
    expect(stepsSource).toContain("max-w-[70ch]");
  });
});

describe("<StepsList /> module surface", () => {
  it("exports StepsList as a function", () => {
    expect(typeof StepsList).toBe("function");
  });

  it("accepts steps array and optional columns 1|2", () => {
    const step: Step = { title: "T", body: "B" };
    const stepWithDetail: Step = {
      title: "T",
      body: "B",
      detail: null,
    };
    const props1: StepsListProps = { steps: [step] };
    const props2: StepsListProps = { steps: [step], columns: 2 };
    expect(props1.steps[0].title).toBe("T");
    expect(props2.columns).toBe(2);
    expect(stepWithDetail.detail).toBeNull();
  });
});
