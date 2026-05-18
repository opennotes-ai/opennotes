import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@solidjs/testing-library";
import { MetaProvider } from "@solidjs/meta";

const {
  analyzeActionMock,
  analyzeActionSubmitMock,
  requestUploadUrlActionMock,
  requestImageUploadUrlsActionMock,
  submitImageAnalysisActionMock,
  submitPdfAnalysisActionMock,
  useActionMock,
  useSubmissionMock,
  useSearchParamsMock,
  createAsyncMock,
  setAnalyzePending,
} = vi.hoisted(() => {
  let analyzePending = false;

  const analyzeActionMock = vi.fn();
  const analyzeActionSubmitMock = vi.fn(async (formData: FormData) => {
    return new Promise((resolve) => {
      setTimeout(resolve, 0);
    });
  });
  const requestUploadUrlActionMock = vi.fn();
  const requestImageUploadUrlsActionMock = vi.fn();
  const submitImageAnalysisActionMock = vi.fn();
  const submitPdfAnalysisActionMock = vi.fn();

  const setAnalyzePending = (value: boolean) => {
    analyzePending = value;
  };

  const getAnalyzePending = () => analyzePending;

  const useActionMock = vi.fn((action: unknown) => {
    if (action === analyzeActionMock) {
      return analyzeActionSubmitMock;
    }
    if (action === requestUploadUrlActionMock) {
      return requestUploadUrlActionMock;
    }
    if (action === requestImageUploadUrlsActionMock) {
      return requestImageUploadUrlsActionMock;
    }
    if (action === submitPdfAnalysisActionMock) {
      return vi.fn();
    }
    if (action === submitImageAnalysisActionMock) {
      return vi.fn();
    }
    return vi.fn();
  });

  const useSubmissionMock = vi.fn((action: unknown) => {
    if (action === analyzeActionMock) {
      return {
        pending: getAnalyzePending,
      };
    }
    return {
      pending: () => false,
    };
  });

  const useSearchParamsMock = vi.fn(() => [
    {
      error: undefined,
      host: undefined,
    },
  ]);

  const createAsyncMock = vi.fn(() => () => []);

  return {
    analyzeActionMock,
    analyzeActionSubmitMock,
    requestUploadUrlActionMock,
    requestImageUploadUrlsActionMock,
    submitImageAnalysisActionMock,
    submitPdfAnalysisActionMock,
    useActionMock,
    useSubmissionMock,
    useSearchParamsMock,
    createAsyncMock,
    setAnalyzePending,
  };
});

vi.mock("@solidjs/router", async () => {
  const actual = await vi.importActual<typeof import("@solidjs/router")>(
    "@solidjs/router",
  );
  return {
    ...actual,
    useAction: useActionMock,
    useSubmission: useSubmissionMock,
    useSearchParams: useSearchParamsMock,
    createAsync: createAsyncMock,
  };
});

vi.mock("~/routes/analyze.data", () => ({
  analyzeAction: analyzeActionMock,
  requestUploadUrlAction: requestUploadUrlActionMock,
  requestImageUploadUrlsAction: requestImageUploadUrlsActionMock,
  submitImageAnalysisAction: submitImageAnalysisActionMock,
  submitPdfAnalysisAction: submitPdfAnalysisActionMock,
}));

vi.mock("~/components/RecentlyVibeChecked", () => ({
  default: () => <div data-testid="recently-vibe-checked" />,
  RecentlyVibeCheckedSkeleton: () => (
    <div data-testid="recent-vibe-checked-skeleton" />
  ),
}));

import HomePage from "./index";

beforeEach(() => {
  setAnalyzePending(false);
  window.scrollTo = vi.fn();
  window.HTMLElement.prototype.scrollIntoView = vi.fn();
  analyzeActionSubmitMock.mockReset();
});

afterEach(() => {
  cleanup();
  useActionMock.mockClear();
  useSubmissionMock.mockClear();
  useSearchParamsMock.mockClear();
  createAsyncMock.mockClear();
  analyzeActionMock.mockClear();
  analyzeActionSubmitMock.mockReset();
  submitPdfAnalysisActionMock.mockReset();
  submitImageAnalysisActionMock.mockReset();
});

describe("HomePage", () => {
  const renderHomePage = () =>
    render(() => (
      <MetaProvider>
        <HomePage />
      </MetaProvider>
    ));

  it("opens warning dialog for reddit URLs and does not submit yet", () => {
    renderHomePage();

    const input = screen.getByLabelText("URL to analyze") as HTMLInputElement;
    fireEvent.input(input, {
      target: {
        value: "https://www.reddit.com/r/politics",
      },
    });
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    expect(
      screen.getByText("We can’t access this site reliably"),
    ).toBeInTheDocument();
    expect(analyzeActionSubmitMock).not.toHaveBeenCalled();
  });

  it("opens warning dialog for linkedin URLs and does not submit yet", () => {
    renderHomePage();

    const input = screen.getByLabelText("URL to analyze") as HTMLInputElement;
    fireEvent.input(input, {
      target: {
        value: "https://www.linkedin.com/feed/",
      },
    });
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    expect(
      screen.getByText("We can’t access this site reliably"),
    ).toBeInTheDocument();
    expect(analyzeActionSubmitMock).not.toHaveBeenCalled();
  });

  it("does not show warning dialog for x.com URLs", () => {
    renderHomePage();

    const input = screen.getByLabelText("URL to analyze") as HTMLInputElement;
    fireEvent.input(input, {
      target: {
        value: "https://x.com/some/page",
      },
    });
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    expect(screen.queryByText("We can’t access this site reliably")).toBeNull();
  });

  it("tries blocked URL again by submitting normalized URL via analyzeAction", async () => {
    analyzeActionSubmitMock.mockImplementation(async (formData: FormData) => {
      setAnalyzePending(true);
      await Promise.resolve(formData);
      return { ok: true };
    });

    renderHomePage();

    const input = screen.getByLabelText("URL to analyze") as HTMLInputElement;
    fireEvent.input(input, {
      target: {
        value: "https://www.reddit.com/r/politics/",
      },
    });
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    fireEvent.click(
      screen.getByRole("button", { name: "Try accessing it anyways" }),
    );

    expect(analyzeActionSubmitMock).toHaveBeenCalledTimes(1);
    const [submittedFormData] = analyzeActionSubmitMock.mock.calls[0] as [
      FormData,
    ];
    expect(submittedFormData.get("url")).toBe(
      "https://www.reddit.com/r/politics/",
    );

    expect(
      screen.queryByText("We can’t access this site reliably"),
    ).toBeNull();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Analyzing..." })).toBeInTheDocument();
    });
  });

  it.each(["PDF", "Screenshot"])(
    "closes warning dialog and focuses upload region on %s",
    async (choice) => {
      renderHomePage();
      const input = screen.getByLabelText("URL to analyze") as HTMLInputElement;
      const blockedUrl = "https://reddit.com/r/test";

      fireEvent.input(input, {
        target: {
          value: blockedUrl,
        },
      });
      fireEvent.submit(input.closest("form") as HTMLFormElement);

      fireEvent.click(screen.getByRole("button", { name: choice }));

      const uploadRegion = screen.getByTestId("pdf-upload-region");
      expect(uploadRegion).toBeInTheDocument();
      await waitFor(() => {
        expect(document.activeElement).toBe(uploadRegion);
      });
      expect(screen.getByText(`You tried to analyze ${blockedUrl} - upload a PDF or screenshot of that page below.`)).toBeInTheDocument();
      expect(uploadRegion.className).toContain("ring-2");
      expect(analyzeActionSubmitMock).not.toHaveBeenCalled();
    },
  );

  it("closes warning dialog on cancel without submission or focus", () => {
    renderHomePage();

    const input = screen.getByLabelText("URL to analyze") as HTMLInputElement;
    fireEvent.input(input, {
      target: {
        value: "https://www.reddit.com/r/cancel",
      },
    });
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(
      screen.queryByText("We can’t access this site reliably"),
    ).toBeNull();
    expect(document.activeElement).not.toBe(
      screen.getByTestId("pdf-upload-region"),
    );
    expect(analyzeActionSubmitMock).not.toHaveBeenCalled();
  });
});
