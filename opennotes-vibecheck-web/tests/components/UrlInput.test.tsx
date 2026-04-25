import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@solidjs/testing-library";
import UrlInput, {
  validateAnalyzableUrl,
} from "../../src/components/UrlInput";

afterEach(() => {
  cleanup();
});

describe("validateAnalyzableUrl", () => {
  it("rejects empty input", () => {
    const result = validateAnalyzableUrl("");
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toMatch(/enter a url/i);
  });

  it("rejects whitespace-only input", () => {
    const result = validateAnalyzableUrl("   \t");
    expect(result.ok).toBe(false);
  });

  it("rejects strings without a scheme", () => {
    const result = validateAnalyzableUrl("example.com/article");
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toMatch(/valid url/i);
  });

  it("rejects ftp URLs", () => {
    const result = validateAnalyzableUrl("ftp://example.com/file");
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toMatch(/http/i);
  });

  it("rejects javascript: URLs", () => {
    const result = validateAnalyzableUrl("javascript:alert(1)");
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toMatch(/http/i);
  });

  it("rejects data: URLs", () => {
    const result = validateAnalyzableUrl("data:text/html,<h1>hi</h1>");
    expect(result.ok).toBe(false);
  });

  it("accepts https URLs", () => {
    const result = validateAnalyzableUrl("https://example.com/article");
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.normalized).toBe("https://example.com/article");
  });

  it("accepts http URLs", () => {
    const result = validateAnalyzableUrl("http://example.com/");
    expect(result.ok).toBe(true);
  });

  it("trims surrounding whitespace before validating", () => {
    const result = validateAnalyzableUrl("  https://example.com/  ");
    expect(result.ok).toBe(true);
  });
});

describe("<UrlInput />", () => {
  it("renders the URL input and Analyze button", () => {
    render(() => <UrlInput action="/submit" />);

    expect(screen.getByLabelText(/url to analyze/i)).toBeDefined();
    expect(
      screen.getByRole("button", { name: /analyze/i }),
    ).toBeDefined();
  });

  it("does not mark the field invalid before validation fails", () => {
    render(() => <UrlInput action="/submit" />);

    const input = screen.getByLabelText(
      /url to analyze/i,
    ) as HTMLInputElement;

    expect(input.getAttribute("aria-invalid")).toBeNull();
    expect(input.getAttribute("aria-describedby")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows an error and blocks submit when the input is empty", () => {
    const onValidSubmit = vi.fn();
    render(() => (
      <UrlInput action="/submit" onValidSubmit={onValidSubmit} />
    ));

    const form = screen.getByRole("button", { name: /analyze/i })
      .closest("form") as HTMLFormElement;

    const submitted = fireEvent.submit(form);

    expect(submitted).toBe(false);
    expect(onValidSubmit).not.toHaveBeenCalled();
    const input = screen.getByLabelText(
      /url to analyze/i,
    ) as HTMLInputElement;
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.getAttribute("aria-describedby")).toBe("vibecheck-url-error");
    expect(screen.getByRole("alert").textContent).toMatch(/enter a url/i);
  });

  it("shows an error and blocks submit for ftp:// scheme", () => {
    const onValidSubmit = vi.fn();
    render(() => (
      <UrlInput action="/submit" onValidSubmit={onValidSubmit} />
    ));

    const input = screen.getByLabelText(
      /url to analyze/i,
    ) as HTMLInputElement;
    fireEvent.input(input, { target: { value: "ftp://example.com/a" } });

    const form = input.closest("form") as HTMLFormElement;
    fireEvent.submit(form);

    expect(onValidSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toMatch(/http/i);
  });

  it("shows an error and blocks submit for javascript: scheme", () => {
    const onValidSubmit = vi.fn();
    render(() => (
      <UrlInput action="/submit" onValidSubmit={onValidSubmit} />
    ));

    const input = screen.getByLabelText(
      /url to analyze/i,
    ) as HTMLInputElement;
    fireEvent.input(input, {
      target: { value: "javascript:alert(1)" },
    });

    const form = input.closest("form") as HTMLFormElement;
    fireEvent.submit(form);

    expect(onValidSubmit).not.toHaveBeenCalled();
  });

  it("calls onValidSubmit with the normalized URL when valid", () => {
    const onValidSubmit = vi.fn();
    render(() => (
      <UrlInput action="/submit" onValidSubmit={onValidSubmit} />
    ));

    const input = screen.getByLabelText(
      /url to analyze/i,
    ) as HTMLInputElement;
    fireEvent.input(input, {
      target: { value: "  https://news.example.com/a  " },
    });

    const form = input.closest("form") as HTMLFormElement;
    fireEvent.submit(form);

    expect(onValidSubmit).toHaveBeenCalledTimes(1);
    expect(onValidSubmit).toHaveBeenCalledWith("https://news.example.com/a");
  });

  it("clears the error when the user edits the field", () => {
    render(() => <UrlInput action="/submit" />);
    const input = screen.getByLabelText(
      /url to analyze/i,
    ) as HTMLInputElement;
    const form = input.closest("form") as HTMLFormElement;

    fireEvent.submit(form);
    expect(screen.getByRole("alert")).toBeDefined();

    fireEvent.input(input, { target: { value: "h" } });

    expect(input.getAttribute("aria-invalid")).toBeNull();
    expect(input.getAttribute("aria-describedby")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("disables the submit button when pending", () => {
    render(() => <UrlInput action="/submit" pending />);
    const button = screen.getByRole("button", {
      name: /analyzing/i,
    }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it("renders the input and submit button at the same height", () => {
    render(() => <UrlInput action="/submit" />);
    const input = screen.getByLabelText(
      /url to analyze/i,
    ) as HTMLInputElement;
    const button = screen.getByRole("button", {
      name: /analyze/i,
    }) as HTMLButtonElement;

    const heightClass = /(?:^|\s)(h-\d+(?:\.\d+)?)(?:\s|$)/;
    const inputMatch = input.className.match(heightClass);
    const buttonMatch = button.className.match(heightClass);

    expect(
      inputMatch,
      `Input is missing an h-* class (got "${input.className}")`,
    ).not.toBeNull();
    expect(
      buttonMatch,
      `Button is missing an h-* class (got "${button.className}")`,
    ).not.toBeNull();
    expect(inputMatch![1]).toBe(buttonMatch![1]);
  });
});
