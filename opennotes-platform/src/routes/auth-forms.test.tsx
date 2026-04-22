import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const loginSource = readFileSync(resolve("src/routes/login.tsx"), "utf8");
const registerSource = readFileSync(resolve("src/routes/register.tsx"), "utf8");

describe("platform auth form controls", () => {
  it("renders login form fields through shared primitives", () => {
    expect(loginSource).toContain(
      'import { Button } from "@opennotes/ui/components/ui/button";',
    );
    expect(loginSource).toContain(
      'import { Input } from "@opennotes/ui/components/ui/input";',
    );
    expect(loginSource).toContain(
      '<Input id="email" name="email" type="email" required />',
    );
    expect(loginSource).toContain(
      '<Input id="password" name="password" type="password" required />',
    );
    expect(loginSource).toContain(
      '<Button type="submit" class="w-full" disabled={submission.pending}>',
    );
  });

  it("renders register form fields through shared primitives", () => {
    expect(registerSource).toContain(
      'import { Button } from "@opennotes/ui/components/ui/button";',
    );
    expect(registerSource).toContain(
      'import { Input } from "@opennotes/ui/components/ui/input";',
    );
    expect(registerSource).toContain(
      '<Input id="email" name="email" type="email" required />',
    );
    expect(registerSource).toContain(
      '<Input id="password" name="password" type="password" required />',
    );
    expect(registerSource).toContain(
      '<Input id="confirmPassword" name="confirmPassword" type="password" required />',
    );
    expect(registerSource).toContain(
      '<Button type="submit" class="w-full" disabled={submission.pending}>',
    );
  });

  it("does not keep hand-rolled auth input or submit button styling", () => {
    expect(loginSource).not.toContain(
      'class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"',
    );
    expect(registerSource).not.toContain(
      'class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"',
    );
    expect(loginSource).not.toContain(
      'class="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"',
    );
    expect(registerSource).not.toContain(
      'class="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"',
    );
  });
});
