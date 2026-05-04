import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@solidjs/testing-library";

import JobFailureCard from "./JobFailureCard";

afterEach(() => {
  cleanup();
});

describe("<JobFailureCard />", () => {
  it("renders PDF-specific copy for pdf_too_large", () => {
    render(() => (
      <JobFailureCard
        url="/tmp/file.pdf"
        errorCode="pdf_too_large"
        errorHost="ignored.example.com"
      />
    ));

    expect(screen.getByTestId("job-failure-copy").textContent).toContain(
      "too large",
    );
    expect(screen.getByTestId("job-failure-detail").textContent).toContain("50 MB");
    expect(screen.getByTestId("job-failure-copy").textContent).not.toContain(
      "ignored.example.com",
    );
  });

  it("renders PDF-specific detail for pdf_extraction_failed", () => {
    render(() => (
      <JobFailureCard
        url="/tmp/bad.pdf"
        errorCode="pdf_extraction_failed"
      />
    ));

    expect(screen.getByTestId("job-failure-copy").textContent).toContain(
      "couldn't extract",
    );
    expect(screen.getByTestId("job-failure-detail").textContent).toContain(
      "encrypted",
    );
  });

  it("hides Try again button when url is a GCS UUID (non-HTTP string)", () => {
    render(() => (
      <JobFailureCard
        url="abc123-uuid-style-gcs-key"
        errorCode="pdf_extraction_failed"
      />
    ));

    expect(screen.queryByTestId("job-failure-try-again-form")).toBeNull();
    expect(screen.queryByTestId("job-failure-try-again")).toBeNull();
  });

  it("shows Try again button when url is a normal HTTP URL", () => {
    render(() => (
      <JobFailureCard
        url="https://example.com/article"
        errorCode="extraction_failed"
      />
    ));

    expect(screen.getByTestId("job-failure-try-again-form")).toBeTruthy();
    expect(screen.getByTestId("job-failure-try-again")).toBeTruthy();
  });
});
