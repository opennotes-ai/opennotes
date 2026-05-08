import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor } from "@solidjs/testing-library";
import PdfUpload from "./PdfUpload";
import { MAX_IMAGE_BATCH_BYTES, MAX_PDF_BYTES } from "~/lib/pdf-constraints";

const {
  requestUploadUrlMock,
  requestImageUploadUrlsMock,
  submitPdfAnalysisMock,
  submitImageAnalysisMock,
  useActionMock,
} =
  vi.hoisted(() => {
    const requestUploadUrlMock = vi.fn();
    const requestImageUploadUrlsMock = vi.fn();
    const submitPdfAnalysisMock = vi.fn();
    const submitImageAnalysisMock = vi.fn();
    const useActionMock = vi.fn((action: unknown) => {
      if (action === requestUploadUrlMock) {
        return requestUploadUrlMock;
      }
      if (action === requestImageUploadUrlsMock) return requestImageUploadUrlsMock;
      if (action === submitImageAnalysisMock) return submitImageAnalysisMock;
      return submitPdfAnalysisMock;
    });
    return {
      requestUploadUrlMock,
      requestImageUploadUrlsMock,
      submitPdfAnalysisMock,
      submitImageAnalysisMock,
      useActionMock,
    };
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
  requestImageUploadUrlsAction: requestImageUploadUrlsMock,
  submitPdfAnalysisAction: submitPdfAnalysisMock,
  submitImageAnalysisAction: submitImageAnalysisMock,
}));

vi.mock("~/lib/pdf-upload", () => ({
  uploadPdfToSignedUrl: vi.fn().mockResolvedValue(undefined),
  uploadFileToSignedUrl: vi.fn().mockResolvedValue(undefined),
}));

afterEach(() => {
  cleanup();
  requestUploadUrlMock.mockReset();
  requestImageUploadUrlsMock.mockReset();
  submitPdfAnalysisMock.mockReset();
  submitImageAnalysisMock.mockReset();
});

describe("<PdfUpload />", () => {
  it("renders a PDF input, submit button, and copy that states the 50 MB limit", () => {
    render(() => <PdfUpload />);

    expect(screen.getByLabelText("PDF or images to analyze")).toBeTruthy();
    expect(screen.getByTestId("pdf-upload-copy").textContent).toContain("50 MB");
    expect(
      (screen.getByTestId("vibecheck-pdf-input") as HTMLInputElement).accept,
    ).toContain("application/pdf");
    expect(
      (screen.getByTestId("vibecheck-pdf-input") as HTMLInputElement).accept,
    ).toContain("image/png");
    expect(
      screen.getByRole("button", { name: "Upload" }),
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
      /image type is not supported/i,
    );
  });

  it("prevents submit when no file is selected", async () => {
    render(() => <PdfUpload />);
    const form = screen
      .getByRole("button", { name: "Upload" })
      .closest("form") as HTMLFormElement;

    fireEvent.submit(form);

    expect(requestUploadUrlMock).not.toHaveBeenCalled();
    expect((await screen.findByRole("alert")).textContent).toMatch(
      /choose a pdf or image files/i,
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
        "Preparing upload",
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

  it("shows selected image count and rejects image batches over 45 MB", async () => {
    render(() => <PdfUpload />);
    const input = screen.getByTestId(
      "vibecheck-pdf-input",
    ) as HTMLInputElement;
    fireEvent.change(input, {
      target: {
        files: [
          new File([new Uint8Array(MAX_IMAGE_BATCH_BYTES + 1)], "scan.png", {
            type: "image/png",
          }),
        ],
      },
    });

    expect(screen.getByTestId("upload-selection-copy").textContent).toContain(
      "1 images selected",
    );
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    expect(requestImageUploadUrlsMock).not.toHaveBeenCalled();
    expect((await screen.findByRole("alert")).textContent).toContain("45 MB");
  });

  it("uploads image files in selected order and submits conversion", async () => {
    requestImageUploadUrlsMock.mockResolvedValue({
      job_id: "job-images",
      images: [
        { ordinal: 0, gcs_key: "k0", upload_url: "https://storage.example/0" },
        { ordinal: 1, gcs_key: "k1", upload_url: "https://storage.example/1" },
      ],
    });
    submitImageAnalysisMock.mockResolvedValue(undefined);

    render(() => <PdfUpload />);
    const input = screen.getByTestId(
      "vibecheck-pdf-input",
    ) as HTMLInputElement;
    fireEvent.change(input, {
      target: {
        files: [
          new File([new Uint8Array(8)], "first.png", { type: "image/png" }),
          new File([new Uint8Array(8)], "second.jpg", { type: "image/jpeg" }),
        ],
      },
    });
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    await waitFor(() => {
      expect(requestImageUploadUrlsMock).toHaveBeenCalledWith([
        { filename: "first.png", content_type: "image/png", size_bytes: 8 },
        { filename: "second.jpg", content_type: "image/jpeg", size_bytes: 8 },
      ]);
    });
    const { uploadFileToSignedUrl } = await import("~/lib/pdf-upload");
    await waitFor(() => {
      expect(uploadFileToSignedUrl).toHaveBeenNthCalledWith(
        1,
        "https://storage.example/0",
        expect.objectContaining({ name: "first.png" }),
        "image/png",
      );
      expect(uploadFileToSignedUrl).toHaveBeenNthCalledWith(
        2,
        "https://storage.example/1",
        expect.objectContaining({ name: "second.jpg" }),
        "image/jpeg",
      );
      expect(submitImageAnalysisMock).toHaveBeenCalled();
    });
  });
});
