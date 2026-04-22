import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const dashboardSource = readFileSync(resolve("src/routes/dashboard.tsx"), "utf8");

describe("platform dashboard controls", () => {
  it("uses shared primitives for dashboard inputs and buttons", () => {
    expect(dashboardSource).toContain(
      'import { Button } from "@opennotes/ui/components/ui/button";',
    );
    expect(dashboardSource).toContain(
      'import { Input } from "@opennotes/ui/components/ui/input";',
    );
    expect(dashboardSource).toContain("<Input");
    expect(dashboardSource).toContain("<Button");
  });

  it("preserves the API key name input contract", () => {
    expect(dashboardSource).toContain('id="keyName"');
    expect(dashboardSource).toContain('placeholder="e.g. Production Discourse"');
    expect(dashboardSource).toContain('onInput={(e) => setKeyName(e.currentTarget.value)}');
    expect(dashboardSource).toContain("required");
  });

  it("preserves key dashboard control states", () => {
    expect(dashboardSource).toContain("selectedScopes().has(scope)");
    expect(dashboardSource).toContain("isTemplateActive(name)");
    expect(dashboardSource).toContain("disabled={props.pending}");
    expect(dashboardSource).toContain('role="alertdialog"');
  });

  it("does not keep raw dashboard form controls", () => {
    expect(dashboardSource).not.toContain("<input");
    expect(dashboardSource).not.toContain("<button");
    expect(dashboardSource).not.toContain("</button>");
  });
});
