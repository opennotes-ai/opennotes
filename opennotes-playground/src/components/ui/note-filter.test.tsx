import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@solidjs/testing-library";
import NoteFilter from "./note-filter";

async function openMenu(trigger: HTMLElement) {
  await fireEvent.pointerDown(trigger, { button: 0, pointerType: "mouse" });
  await fireEvent.pointerUp(trigger, { button: 0, pointerType: "mouse" });
  await fireEvent.click(trigger);
}

describe("NoteFilter Clear all button", () => {
  it("exposes Clear all as a keyboard-reachable button with aria-label when filters are active", async () => {
    const onChange = vi.fn();
    render(() => (
      <NoteFilter
        classification={["NOT_MISLEADING"]}
        status={[]}
        onChange={onChange}
      />
    ));

    await openMenu(screen.getByTestId("note-filter-toggle"));

    const clearBtn = await screen.findByRole("button", {
      name: /clear all filters/i,
    });
    expect(clearBtn).toBeDefined();
    expect(clearBtn.tagName).toBe("BUTTON");
    expect(clearBtn.getAttribute("tabindex")).not.toBe("-1");
    expect(clearBtn.getAttribute("aria-label")).toBe("Clear all filters");
  });

  it("invokes onChange with empty arrays when Clear all is clicked", async () => {
    const onChange = vi.fn();
    render(() => (
      <NoteFilter
        classification={["NOT_MISLEADING"]}
        status={["CURRENTLY_RATED_HELPFUL"]}
        onChange={onChange}
      />
    ));

    await openMenu(screen.getByTestId("note-filter-toggle"));
    const clearBtn = await screen.findByRole("button", {
      name: /clear all filters/i,
    });
    await fireEvent.click(clearBtn);

    expect(onChange).toHaveBeenCalledWith({ classification: [], status: [] });
  });

  it("does not render Clear all when no filters are active", async () => {
    const onChange = vi.fn();
    render(() => (
      <NoteFilter classification={[]} status={[]} onChange={onChange} />
    ));

    await openMenu(screen.getByTestId("note-filter-toggle"));
    expect(
      screen.queryByRole("button", { name: /clear all filters/i }),
    ).toBeNull();
  });
});
