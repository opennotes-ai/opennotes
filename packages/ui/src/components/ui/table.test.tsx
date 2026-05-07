import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableRow,
  TableHead,
  TableCell,
  TableCaption,
} from "./table";

const tableSource = readFileSync(
  resolve("src/components/ui/table.tsx"),
  "utf8",
);

describe("<Table /> source contract", () => {
  it("merges caller class via cn() helper", () => {
    expect(tableSource).toContain("cn(");
    expect(tableSource).toMatch(/cn\([^)]*\.class/);
  });

  it("uses splitProps to extract class so other props forward", () => {
    expect(tableSource).toContain('splitProps(props, ["class"])');
    expect(tableSource).toContain("...others");
  });

  it("renders semantic table elements (table/thead/tbody/tr/th/td/caption)", () => {
    expect(tableSource).toMatch(/<table\b/);
    expect(tableSource).toMatch(/<thead\b/);
    expect(tableSource).toMatch(/<tbody\b/);
    expect(tableSource).toMatch(/<tr\b/);
    expect(tableSource).toMatch(/<th\b/);
    expect(tableSource).toMatch(/<td\b/);
    expect(tableSource).toMatch(/<caption\b/);
  });

  it("tags subcomponents with data-slot for design-system attribution", () => {
    expect(tableSource).toContain('data-slot="table"');
    expect(tableSource).toContain('data-slot="table-header"');
    expect(tableSource).toContain('data-slot="table-body"');
    expect(tableSource).toContain('data-slot="table-row"');
    expect(tableSource).toContain('data-slot="table-head"');
    expect(tableSource).toContain('data-slot="table-cell"');
    expect(tableSource).toContain('data-slot="table-caption"');
  });

  it("wraps the <table> in an overflow-auto container", () => {
    expect(tableSource).toMatch(/data-slot="table-wrapper"/);
    expect(tableSource).toContain("overflow-auto");
  });

  it("rows have hover affordance and selected state hooks", () => {
    expect(tableSource).toMatch(/hover:bg-muted/);
    expect(tableSource).toMatch(/data-\[state=selected\]:bg-muted/);
  });

  it("uses tailwind tokens only (no inline hex)", () => {
    expect(tableSource).not.toMatch(/#[0-9a-fA-F]{3,8}/);
  });
});

describe("<Table /> module surface", () => {
  it("exports Table and all subcomponents as function components", () => {
    expect(typeof Table).toBe("function");
    expect(typeof TableHeader).toBe("function");
    expect(typeof TableBody).toBe("function");
    expect(typeof TableFooter).toBe("function");
    expect(typeof TableRow).toBe("function");
    expect(typeof TableHead).toBe("function");
    expect(typeof TableCell).toBe("function");
    expect(typeof TableCaption).toBe("function");
  });
});
