import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@solidjs/testing-library";
import PdfUpload from "./PdfUpload";
import { MAX_PDF_BYTES } from "~/lib/pdf-constraints";

afterEach(() => {
  cleanup();
});

describe("<PdfUpload />", () => {
  it("renders a PDF input, submit button, and copy that states the 50 MB limit", () => {
    render(() => <PdfUpload action="/analyze-pdf" />);

    expect(screen.getByLabelText("PDF to analyze")).toBeTruthy();
    expect(screen.getByTestId("pdf-upload-copy").textContent).toContain("50 MB");
    expect(
      (screen.getByTestId("vibecheck-pdf-input") as HTMLInputElement).accept,
    ).toContain("application/pdf");
    expect(
      screen.getByRole("button", { name: "Upload PDF" }).closest("form")
        ?.enctype,
    ).toBe("multipart/form-data");
  });

  it("prevents submit for oversized PDFs with an inline clear error", async () => {
    const onSubmit = vi.fn();
    render(() => (
      <div onSubmit={onSubmit}>
        <PdfUpload action="/analyze-pdf" />
      </div>
    ));
    const input = screen.getByTestId(
      "vibecheck-pdf-input",
    ) as HTMLInputElement;
    const oversized = new File(
      [new Uint8Array(MAX_PDF_BYTES + 1)],
      "too-big.pdf",
      {
        type: "application/pdf",
      },
    );
    fireEvent.change(input, {
      target: {
        files: [oversized],
      },
    });

    const form = input.closest("form") as HTMLFormElement;
    const submitted = fireEvent.submit(form);
    const alert = await screen.findByRole("alert");

    expect(submitted).toBe(false);
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(alert.textContent).toContain("50 MB");
  });

  it("prevents submit for non-PDF files with an inline error", async () => {
    render(() => <PdfUpload action="/analyze-pdf" />);
    const input = screen.getByTestId(
      "vibecheck-pdf-input",
    ) as HTMLInputElement;
    fireEvent.change(input, {
      target: {
        files: [new File(["hello"], "notes.txt", { type: "text/plain" })],
      },
    });

    const submitted = fireEvent.submit(input.closest("form") as HTMLFormElement);

    expect(submitted).toBe(false);
    expect((await screen.findByRole("alert")).textContent).toMatch(
      /choose a pdf/i,
    );
  });

  it("prevents submit when no file is selected", async () => {
    render(() => <PdfUpload action="/analyze-pdf" />);
    const form = screen
      .getByRole("button", { name: "Upload PDF" })
      .closest("form") as HTMLFormElement;

    const submitted = fireEvent.submit(form);

    expect(submitted).toBe(false);
    expect((await screen.findByRole("alert")).textContent).toMatch(
      /choose a pdf file/i,
    );
  });
});
