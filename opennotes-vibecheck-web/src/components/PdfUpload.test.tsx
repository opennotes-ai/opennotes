import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor } from "@solidjs/testing-library";
import PdfUpload from "./PdfUpload";
import { MAX_PDF_BYTES } from "~/lib/pdf-constraints";

const { requestUploadUrlMock, submitPdfAnalysisMock, useActionMock } =
  vi.hoisted(() => {
    const requestUploadUrlMock = vi.fn();
    const submitPdfAnalysisMock = vi.fn();
    const useActionMock = vi.fn((action: unknown) => {
      if (action === requestUploadUrlMock || (action as { toString?: () => string })?.toString?.()?.includes?.("upload-url")) {
        return requestUploadUrlMock;
      }
      return submitPdfAnalysisMock;
    });
    return { requestUploadUrlMock, submitPdfAnalysisMock, useActionMock };
  });

vi.mock("@solidjs/router", async () => {
  const actual = await vi.importActual<typeof import("@solidjs/router")>(
    "@solidjs/router",
  );
  return {
    ...actual,
    useAction: useActionMock,
  };
});

vi.mock("~/routes/analyze.data", () => ({
  requestUploadUrlAction: requestUploadUrlMock,
  submitPdfAnalysisAction: submitPdfAnalysisMock,
}));

vi.mock("~/lib/pdf-upload", () => ({
  uploadPdfToSignedUrl: vi.fn().mockResolvedValue(undefined),
}));

afterEach(() => {
  cleanup();
  requestUploadUrlMock.mockReset();
  submitPdfAnalysisMock.mockReset();
});

describe("<PdfUpload />", () => {
  it("renders a PDF input, submit button, and copy that states the 50 MB limit", () => {
    render(() => <PdfUpload />);

    expect(screen.getByLabelText("PDF to analyze")).toBeTruthy();
    expect(screen.getByTestId("pdf-upload-copy").textContent).toContain("50 MB");
    expect(
      (screen.getByTestId("vibecheck-pdf-input") as HTMLInputElement).accept,
    ).toContain("application/pdf");
    expect(
      screen.getByRole("button", { name: "Upload PDF" }),
    ).toBeTruthy();
  });

  it("prevents submit for oversized PDFs with an inline clear error", async () => {
    render(() => <PdfUpload />);
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
    fireEvent.submit(form);
    const alert = await screen.findByRole("alert");

    expect(requestUploadUrlMock).not.toHaveBeenCalled();
    expect(alert.textContent).toContain("50 MB");
  });

  it("prevents submit for non-PDF files with an inline error", async () => {
    render(() => <PdfUpload />);
    const input = screen.getByTestId(
      "vibecheck-pdf-input",
    ) as HTMLInputElement;
    fireEvent.change(input, {
      target: {
        files: [new File(["hello"], "notes.txt", { type: "text/plain" })],
      },
    });

    fireEvent.submit(input.closest("form") as HTMLFormElement);

    expect(requestUploadUrlMock).not.toHaveBeenCalled();
    expect((await screen.findByRole("alert")).textContent).toMatch(
      /choose a pdf/i,
    );
  });

  it("prevents submit when no file is selected", async () => {
    render(() => <PdfUpload />);
    const form = screen
      .getByRole("button", { name: "Upload PDF" })
      .closest("form") as HTMLFormElement;

    fireEvent.submit(form);

    expect(requestUploadUrlMock).not.toHaveBeenCalled();
    expect((await screen.findByRole("alert")).textContent).toMatch(
      /choose a pdf file/i,
    );
  });

  it("shows step labels during the multi-step upload flow", async () => {
    let resolveUrl!: (v: unknown) => void;
    let resolveUpload!: (v: unknown) => void;

    requestUploadUrlMock.mockReturnValue(
      new Promise((r) => {
        resolveUrl = r;
      }),
    );
    vi.mocked(
      (await import("~/lib/pdf-upload")).uploadPdfToSignedUrl,
    ).mockReturnValue(
      new Promise((r) => {
        resolveUpload = r as (v: unknown) => void;
      }),
    );
    submitPdfAnalysisMock.mockResolvedValue(undefined);

    render(() => <PdfUpload />);
    const input = screen.getByTestId(
      "vibecheck-pdf-input",
    ) as HTMLInputElement;
    const file = new File([new Uint8Array(16)], "doc.pdf", {
      type: "application/pdf",
    });
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    await waitFor(() => {
      expect(screen.getByTestId("vibecheck-pdf-submit").textContent).toBe(
        "Preparing...",
      );
    });

    resolveUrl({ gcs_key: "k", upload_url: "https://storage.example.com/x" });

    await waitFor(() => {
      expect(screen.getByTestId("vibecheck-pdf-submit").textContent).toBe(
        "Uploading...",
      );
    });

    resolveUpload(undefined);

    await waitFor(() => {
      expect(screen.getByTestId("vibecheck-pdf-submit").textContent).toBe(
        "Analyzing...",
      );
    });
  });
});
