/// <reference types="@testing-library/jest-dom/vitest" />
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
  fireEvent,
} from "@solidjs/testing-library";
import UrlInput from "./UrlInput";

afterEach(() => {
  cleanup();
});

describe("<UrlInput />", () => {
  it("blocks reddit URLs and calls onBlockingHost after validation", () => {
    const onBlockingHost = vi.fn();
    const onValidSubmit = vi.fn();
    render(() => (
      <UrlInput
        action="analyze"
        onBlockingHost={onBlockingHost}
        onValidSubmit={onValidSubmit}
      />
    ));

    const input = screen.getByLabelText("URL to analyze") as HTMLInputElement;
    fireEvent.input(input, {
      target: {
        value: "https://www.reddit.com/r/politics",
      },
    });

    const form = input.closest("form") as HTMLFormElement;
    const submitEvent = new SubmitEvent("submit", {
      bubbles: true,
      cancelable: true,
    });
    const preventDefaultSpy = vi.spyOn(submitEvent, "preventDefault");

    form.dispatchEvent(submitEvent);

    expect(preventDefaultSpy).toHaveBeenCalledTimes(1);
    expect(onBlockingHost).toHaveBeenCalledTimes(1);
    expect(onBlockingHost).toHaveBeenCalledWith({
      url: "https://www.reddit.com/r/politics",
      family: "reddit",
      host: "www.reddit.com",
    });
    expect(onValidSubmit).not.toHaveBeenCalled();
  });

  it("blocks linkedin subdomains and calls onBlockingHost after validation", () => {
    const onBlockingHost = vi.fn();
    const onValidSubmit = vi.fn();
    render(() => (
      <UrlInput
        action="analyze"
        onBlockingHost={onBlockingHost}
        onValidSubmit={onValidSubmit}
      />
    ));

    const input = screen.getByLabelText("URL to analyze") as HTMLInputElement;
    fireEvent.input(input, {
      target: {
        value: "https://careers.linkedin.com/jobs",
      },
    });

    const form = input.closest("form") as HTMLFormElement;
    fireEvent.submit(form);

    expect(onBlockingHost).toHaveBeenCalledTimes(1);
    expect(onBlockingHost).toHaveBeenCalledWith({
      url: "https://careers.linkedin.com/jobs",
      family: "linkedin",
      host: "careers.linkedin.com",
    });
    expect(onValidSubmit).not.toHaveBeenCalled();
  });

  it.each([
    ["https://x.com/some/path"],
    ["https://mobile.x.com/some/path"],
  ])("allows %s through validate and calls onValidSubmit", (url) => {
    const onBlockingHost = vi.fn();
    const onValidSubmit = vi.fn();
    render(() => (
      <UrlInput
        action="analyze"
        onBlockingHost={onBlockingHost}
        onValidSubmit={onValidSubmit}
      />
    ));

    const input = screen.getByLabelText("URL to analyze") as HTMLInputElement;
    fireEvent.input(input, {
      target: {
        value: url,
      },
    });

    const form = input.closest("form") as HTMLFormElement;
    fireEvent.submit(form);

    expect(onBlockingHost).not.toHaveBeenCalled();
    expect(onValidSubmit).toHaveBeenCalledTimes(1);
    expect(onValidSubmit).toHaveBeenCalledWith(url);
  });

  it("submits non-blocking example.com URLs via onValidSubmit", () => {
    const onBlockingHost = vi.fn();
    const onValidSubmit = vi.fn();
    render(() => (
      <UrlInput
        action="analyze"
        onBlockingHost={onBlockingHost}
        onValidSubmit={onValidSubmit}
      />
    ));

    const input = screen.getByLabelText("URL to analyze") as HTMLInputElement;
    fireEvent.input(input, {
      target: {
        value: "https://example.com/article",
      },
    });

    const form = input.closest("form") as HTMLFormElement;
    fireEvent.submit(form);

    expect(onBlockingHost).not.toHaveBeenCalled();
    expect(onValidSubmit).toHaveBeenCalledTimes(1);
    expect(onValidSubmit).toHaveBeenCalledWith("https://example.com/article");
  });

  it("shows inline validation errors for invalid URLs and calls neither callback", async () => {
    const onBlockingHost = vi.fn();
    const onValidSubmit = vi.fn();
    render(() => (
      <UrlInput
        action="analyze"
        onBlockingHost={onBlockingHost}
        onValidSubmit={onValidSubmit}
      />
    ));

    const input = screen.getByLabelText("URL to analyze") as HTMLInputElement;
    fireEvent.input(input, {
      target: {
        value: "not a URL",
      },
    });

    const form = input.closest("form") as HTMLFormElement;
    const submitEvent = new SubmitEvent("submit", {
      bubbles: true,
      cancelable: true,
    });
    const preventDefaultSpy = vi.spyOn(submitEvent, "preventDefault");

    form.dispatchEvent(submitEvent);

    expect(preventDefaultSpy).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("alert").textContent).toContain(
      "That doesn't look like a valid URL. Include https://",
    );
    expect(onBlockingHost).not.toHaveBeenCalled();
    expect(onValidSubmit).not.toHaveBeenCalled();
  });
});
