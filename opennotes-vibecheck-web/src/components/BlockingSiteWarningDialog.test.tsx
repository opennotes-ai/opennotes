/// <reference types="@testing-library/jest-dom/vitest" />
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@solidjs/testing-library";
import { BlockingSiteWarningDialog } from "./BlockingSiteWarningDialog";

afterEach(() => {
  cleanup();
});

describe("BlockingSiteWarningDialog", () => {
  it("renders warning copy and actions", () => {
    render(() => (
      <BlockingSiteWarningDialog
        open={true}
        onOpenChange={() => {}}
        url="https://reddit.com/r/programming"
        hostFamily="reddit"
        onProceedAnyway={() => {}}
        onChoosePdf={() => {}}
        onChooseScreenshot={() => {}}
        onCancel={() => {}}
      />
    ));

    expect(
      screen.getByText(
        /this site usually blocks third-party access, we recommend you upload screenshots or a PDF printout of the page until our browser extension is ready\./i,
      ),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("button", { name: "Try accessing it anyways" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "PDF" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Screenshot" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it("does not close through action callbacks", async () => {
    const onOpenChange = vi.fn();
    const onProceedAnyway = vi.fn();
    const onChoosePdf = vi.fn();
    const onChooseScreenshot = vi.fn();
    const onCancel = vi.fn();

    render(() => (
      <BlockingSiteWarningDialog
        open={true}
        onOpenChange={onOpenChange}
        url="https://www.reddit.com"
        hostFamily="reddit"
        onProceedAnyway={onProceedAnyway}
        onChoosePdf={onChoosePdf}
        onChooseScreenshot={onChooseScreenshot}
        onCancel={onCancel}
      />
    ));

    await waitFor(() =>
      expect(
        document.querySelector('[data-slot="dialog-content"]'),
      ).not.toBeNull(),
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Try accessing it anyways" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "PDF" }));
    fireEvent.click(screen.getByRole("button", { name: "Screenshot" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onProceedAnyway).toHaveBeenCalledTimes(1);
    expect(onChoosePdf).toHaveBeenCalledTimes(1);
    expect(onChooseScreenshot).toHaveBeenCalledTimes(1);
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it("calls onOpenChange(false) when pressing escape and does not call action callbacks", async () => {
    const onOpenChange = vi.fn();
    const onProceedAnyway = vi.fn();
    const onChoosePdf = vi.fn();
    const onChooseScreenshot = vi.fn();
    const onCancel = vi.fn();

    render(() => (
      <BlockingSiteWarningDialog
        open={true}
        onOpenChange={onOpenChange}
        url="https://www.linkedin.com"
        hostFamily="linkedin"
        onProceedAnyway={onProceedAnyway}
        onChoosePdf={onChoosePdf}
        onChooseScreenshot={onChooseScreenshot}
        onCancel={onCancel}
      />
    ));

    await waitFor(() =>
      expect(
        document.querySelector('[data-slot="dialog-content"]'),
      ).not.toBeNull(),
    );

    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: "Escape",
    });

    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });

    expect(onProceedAnyway).not.toHaveBeenCalled();
    expect(onChoosePdf).not.toHaveBeenCalled();
    expect(onChooseScreenshot).not.toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("calls onOpenChange(false) when clicking outside and does not call action callbacks", async () => {
    const onOpenChange = vi.fn();
    const onProceedAnyway = vi.fn();
    const onChoosePdf = vi.fn();
    const onChooseScreenshot = vi.fn();
    const onCancel = vi.fn();

    render(() => (
      <BlockingSiteWarningDialog
        open={true}
        onOpenChange={onOpenChange}
        url="https://www.linkedin.com"
        hostFamily="linkedin"
        onProceedAnyway={onProceedAnyway}
        onChoosePdf={onChoosePdf}
        onChooseScreenshot={onChooseScreenshot}
        onCancel={onCancel}
      />
    ));

    const content = await waitFor(() => {
      const el = document.querySelector('[data-slot="dialog-content"]');
      if (!el) {
        throw new Error("dialog content not yet rendered");
      }
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
        throw new Error("dialog overlay not found");
      }
      return candidate;
    });

    fireEvent.pointerDown(overlay);
    fireEvent.pointerUp(overlay);
    fireEvent.click(overlay);

    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });

    expect(onProceedAnyway).not.toHaveBeenCalled();
    expect(onChoosePdf).not.toHaveBeenCalled();
    expect(onChooseScreenshot).not.toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
  });
});
