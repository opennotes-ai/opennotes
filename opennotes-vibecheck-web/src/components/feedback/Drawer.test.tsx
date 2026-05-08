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
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from "@opennotes/ui";

afterEach(() => {
  cleanup();
});

function ControlledDrawerHarness(props: { onOpenChange?: (v: boolean) => void }) {
  const [open, setOpen] = createSignal(false);

  const handleChange = (v: boolean) => {
    setOpen(v);
    props.onOpenChange?.(v);
  };

  return (
    <Drawer open={open()} onOpenChange={handleChange}>
      <DrawerTrigger as="button" type="button" data-testid="open-trigger">
        Open drawer
      </DrawerTrigger>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Drawer title</DrawerTitle>
        </DrawerHeader>
        <p>Drawer body</p>
        <button type="button" data-testid="inner-action">
          Inner action
        </button>
      </DrawerContent>
    </Drawer>
  );
}

function getDismissButton(): HTMLElement {
  const btn = document.querySelector(
    '[data-slot="drawer-content"] button[aria-label="Dismiss"]',
  );
  if (!btn) {
    throw new Error("Drawer dismiss button not found");
  }
  return btn as HTMLElement;
}

describe("Drawer (real DOM behaviour)", () => {
  it("trigger click renders the drawer content into the document", async () => {
    render(() => <ControlledDrawerHarness />);

    expect(document.querySelector('[data-slot="drawer-content"]')).toBeNull();

    fireEvent.click(screen.getByTestId("open-trigger"));

    const content = await waitFor(() => {
      const el = document.querySelector('[data-slot="drawer-content"]');
      if (!el) throw new Error("drawer not yet rendered");
      return el as HTMLElement;
    });

    expect(content).toBeInTheDocument();
    expect(screen.getByText("Drawer title")).toBeInTheDocument();
    expect(screen.getByText("Drawer body")).toBeInTheDocument();
  });

  it("Escape key closes the drawer and removes content from the DOM", async () => {
    const onOpenChange = vi.fn();
    render(() => <ControlledDrawerHarness onOpenChange={onOpenChange} />);

    fireEvent.click(screen.getByTestId("open-trigger"));
    await waitFor(() => {
      expect(
        document.querySelector('[data-slot="drawer-content"]'),
      ).not.toBeNull();
    });

    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: "Escape",
    });

    await waitFor(() => {
      expect(
        document.querySelector('[data-slot="drawer-content"]'),
      ).toBeNull();
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("close button dismisses the drawer", async () => {
    render(() => <ControlledDrawerHarness />);

    fireEvent.click(screen.getByTestId("open-trigger"));
    await waitFor(() => {
      expect(
        document.querySelector('[data-slot="drawer-content"]'),
      ).not.toBeNull();
    });

    const dismissBtn = getDismissButton();
    expect(dismissBtn).toBeInTheDocument();
    fireEvent.click(dismissBtn);

    await waitFor(() => {
      expect(
        document.querySelector('[data-slot="drawer-content"]'),
      ).toBeNull();
    });
  });

  it("drawer content contains a focus trap and inner focusable controls", async () => {
    render(() => <ControlledDrawerHarness />);

    fireEvent.click(screen.getByTestId("open-trigger"));
    const content = await waitFor(() => {
      const el = document.querySelector('[data-slot="drawer-content"]');
      if (!el) throw new Error("drawer not yet rendered");
      return el as HTMLElement;
    });

    const innerAction = screen.getByTestId("inner-action");
    expect(content.contains(innerAction)).toBe(true);

    const dismissBtn = getDismissButton();
    expect(content.contains(dismissBtn)).toBe(true);

    expect(content.querySelectorAll("[data-focus-trap]").length).toBeGreaterThan(
      0,
    );
  });
});
