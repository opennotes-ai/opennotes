import { describe, expect, test } from "vitest";
import { render, screen } from "@solidjs/testing-library";
import { Button } from "@opennotes/ui/components/ui/button";

describe("@opennotes/ui Button consumption from platform", () => {
  test("renders with the link variant class from the shared primitive", () => {
    render(() => (
      <Button variant="link" size="sm">
        Try again
      </Button>
    ));

    const button = screen.getByRole("button", { name: /try again/i });
    expect(button).toBeDefined();
    expect(button.className).toContain("underline-offset-4");
  });

  test("forwards onClick through Kobalte primitive", async () => {
    let clicks = 0;
    render(() => (
      <Button variant="default" onClick={() => clicks++}>
        Click me
      </Button>
    ));

    const button = screen.getByRole("button", { name: /click me/i });
    button.click();
    expect(clicks).toBe(1);
  });
});
