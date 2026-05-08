/// <reference types="@testing-library/jest-dom/vitest" />
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@solidjs/testing-library";
import { createSignal } from "solid-js";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@opennotes/ui";

afterEach(() => {
  cleanup();
});

function ControlledDialogHarness(props: { onOpenChange?: (v: boolean) => void }) {
  const [open, setOpen] = createSignal(false);

  const handleChange = (v: boolean) => {
    setOpen(v);
    props.onOpenChange?.(v);
  };

  return (
    <Dialog open={open()} onOpenChange={handleChange}>
      <DialogTrigger as="button" type="button" data-testid="open-trigger">
        Open dialog
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Dialog title</DialogTitle>
        </DialogHeader>
        <p>Body content</p>
        <button type="button" data-testid="inner-button">
          Inner button
        </button>
      </DialogContent>
    </Dialog>
  );
}

function getDismissButton(): HTMLElement {
  const btn = document.querySelector(
    '[data-slot="dialog-content"] button[aria-label="Dismiss"]',
  );
  if (!btn) {
    throw new Error("Dialog dismiss button not found");
  }
  return btn as HTMLElement;
}

describe("Dialog (real DOM behaviour)", () => {
  it("trigger click renders the dialog content into the document", async () => {
    render(() => <ControlledDialogHarness />);

    expect(
      document.querySelector('[data-slot="dialog-content"]'),
    ).toBeNull();

    fireEvent.click(screen.getByTestId("open-trigger"));

    const content = await waitFor(() => {
      const el = document.querySelector('[data-slot="dialog-content"]');
      if (!el) throw new Error("dialog content not yet rendered");
      return el as HTMLElement;
    });

    expect(content).toBeInTheDocument();
    expect(screen.getByText("Dialog title")).toBeInTheDocument();
    expect(screen.getByText("Body content")).toBeInTheDocument();
  });

  it("Escape key closes the dialog and removes content from the DOM", async () => {
    const onOpenChange = vi.fn();
    render(() => <ControlledDialogHarness onOpenChange={onOpenChange} />);

    fireEvent.click(screen.getByTestId("open-trigger"));
    await waitFor(() => {
      expect(
        document.querySelector('[data-slot="dialog-content"]'),
      ).not.toBeNull();
    });

    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: "Escape",
    });

    await waitFor(() => {
      expect(
        document.querySelector('[data-slot="dialog-content"]'),
      ).toBeNull();
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("pointerdown outside the content (on the overlay) closes the dialog", async () => {
    const onOpenChange = vi.fn();
    render(() => <ControlledDialogHarness onOpenChange={onOpenChange} />);

    fireEvent.click(screen.getByTestId("open-trigger"));
    const content = await waitFor(() => {
      const el = document.querySelector('[data-slot="dialog-content"]');
      if (!el) throw new Error("dialog content not yet rendered");
      return el as HTMLElement;
    });

    const overlay = await waitFor(() => {
      const candidate = Array.from(
        document.querySelectorAll<HTMLElement>("div[data-expanded]"),
      ).find(
        (el) =>
          el !== content &&
          !content.contains(el) &&
          !el.contains(content),
      );
      if (!candidate) {
        throw new Error("dialog overlay not yet rendered");
      }
      return candidate;
    });

    expect(overlay).not.toBe(content);
    expect(content.contains(overlay)).toBe(false);

    await new Promise((r) => setTimeout(r, 0));

    fireEvent.pointerDown(overlay);

    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });

    await waitFor(() => {
      expect(
        document.querySelector('[data-slot="dialog-content"]'),
      ).toBeNull();
    });
  });

  it("close button dismisses the dialog", async () => {
    render(() => <ControlledDialogHarness />);

    fireEvent.click(screen.getByTestId("open-trigger"));
    await waitFor(() => {
      expect(
        document.querySelector('[data-slot="dialog-content"]'),
      ).not.toBeNull();
    });

    const dismissBtn = getDismissButton();
    expect(dismissBtn).toBeInTheDocument();
    fireEvent.click(dismissBtn);

    await waitFor(() => {
      expect(
        document.querySelector('[data-slot="dialog-content"]'),
      ).toBeNull();
    });
  });

  it("dialog content stays in the document after open and contains focusable inner controls", async () => {
    render(() => <ControlledDialogHarness />);

    fireEvent.click(screen.getByTestId("open-trigger"));
    const content = await waitFor(() => {
      const el = document.querySelector('[data-slot="dialog-content"]');
      if (!el) throw new Error("dialog content not yet rendered");
      return el as HTMLElement;
    });

    const innerButton = screen.getByTestId("inner-button");
    expect(content.contains(innerButton)).toBe(true);

    const dismissBtn = getDismissButton();
    expect(content.contains(dismissBtn)).toBe(true);

    expect(content.querySelectorAll("[data-focus-trap]").length).toBeGreaterThan(
      0,
    );
  });
});
