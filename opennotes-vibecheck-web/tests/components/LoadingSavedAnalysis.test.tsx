import { render, screen, cleanup } from "@solidjs/testing-library";
import { afterEach, describe, expect, it } from "vitest";
import LoadingSavedAnalysis from "../../src/components/LoadingSavedAnalysis";

afterEach(() => {
  cleanup();
});

describe("LoadingSavedAnalysis", () => {
  it("renders neutral saved-analysis loading copy", () => {
    render(() => <LoadingSavedAnalysis />);

    expect(screen.getByRole("status").textContent).toContain(
      "Loading analysis",
    );
    expect(screen.getByText(/loading analysis/i)).not.toBeNull();
    expect(document.body.textContent?.toLowerCase()).not.toContain(
      "extracting",
    );
    expect(document.body.textContent?.toLowerCase()).not.toContain(
      "analyzing",
    );
  });
});
