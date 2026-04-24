import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@solidjs/testing-library";
import PageFrame from "../../src/components/PageFrame";

afterEach(() => {
  cleanup();
});

describe("<PageFrame />", () => {
  it("renders an iframe when canIframe=true", () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={true}
        screenshotUrl={null}
      />
    ));

    const iframe = screen.getByTestId(
      "page-frame-iframe",
    ) as HTMLIFrameElement;
    expect(iframe).not.toBeNull();
    expect(iframe.tagName.toLowerCase()).toBe("iframe");
    expect(iframe.getAttribute("src")).toBe("https://example.com/article");
    expect(iframe.getAttribute("sandbox")).toBe(
      "allow-same-origin allow-scripts",
    );
    expect(screen.queryByTestId("page-frame-screenshot")).toBeNull();
  });

  it("shows the screenshot first when the backend reports a blocking header", () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={false}
        blockingHeader="content-security-policy: frame-ancestors 'none'"
        screenshotUrl="https://cdn.example.com/shot.png"
      />
    ));

    expect(screen.getByTestId("page-frame-screenshot")).not.toBeNull();
    expect(screen.getByTestId("page-frame-iframe").getAttribute("aria-hidden")).toBe(
      "true",
    );
  });

  it("does not inspect the iframe document when a blocking hint already selects the screenshot", async () => {
    render(() => (
      <PageFrame
        url="https://blocked.example.com/article"
        canIframe={false}
        blockingHeader="content-security-policy: frame-ancestors 'none'"
        screenshotUrl="https://cdn.example.com/blocked.png"
      />
    ));

    let inspectedIframeDocument = false;
    const iframe = screen.getByTestId(
      "page-frame-iframe",
    ) as HTMLIFrameElement;
    Object.defineProperty(iframe, "contentDocument", {
      configurable: true,
      get: () => {
        inspectedIframeDocument = true;
        throw new DOMException("Sandbox access violation", "SecurityError");
      },
    });

    iframe.dispatchEvent(new Event("load"));

    await waitFor(() => {
      expect(screen.getByTestId("page-frame-screenshot")).not.toBeNull();
    });
    expect(inspectedIframeDocument).toBe(false);
  });

  it("swaps to the screenshot when the iframe errors", async () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={true}
        screenshotUrl="https://cdn.example.com/shot.png"
      />
    ));

    const iframe = screen.getByTestId(
      "page-frame-iframe",
    ) as HTMLIFrameElement;
    iframe.dispatchEvent(new Event("error"));

    const img = (await screen.findByTestId(
      "page-frame-screenshot",
    )) as HTMLImageElement;
    expect(img.getAttribute("src")).toBe("https://cdn.example.com/shot.png");
    expect(screen.queryByTestId("page-frame-iframe")).toBeNull();
  });

  it("keeps the iframe on load when there is no backend blocking hint", async () => {
    render(() => (
      <PageFrame
        url="https://maybe-open.example.com/article"
        canIframe={true}
        screenshotUrl="https://cdn.example.com/fallback.png"
      />
    ));

    const iframe = screen.getByTestId(
      "page-frame-iframe",
    ) as HTMLIFrameElement;
    iframe.dispatchEvent(new Event("load"));

    await waitFor(() => {
      expect(screen.getByTestId("page-frame-iframe")).not.toBeNull();
    });
    expect(screen.queryByTestId("page-frame-screenshot")).toBeNull();
  });

  it("keeps the iframe when cross-origin access throws after load", async () => {
    render(() => (
      <PageFrame
        url="https://open.example.com/article"
        canIframe={true}
        screenshotUrl="https://cdn.example.com/open.png"
      />
    ));

    const iframe = screen.getByTestId(
      "page-frame-iframe",
    ) as HTMLIFrameElement;
    Object.defineProperty(iframe, "contentDocument", {
      configurable: true,
      get: () => {
        throw new DOMException("Blocked a frame with origin", "SecurityError");
      },
    });
    iframe.dispatchEvent(new Event("load"));

    await waitFor(() => {
      expect(screen.getByTestId("page-frame-iframe")).not.toBeNull();
    });
    expect(screen.queryByTestId("page-frame-screenshot")).toBeNull();
  });

  it("always shows an 'Open original' link", () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={true}
        screenshotUrl={null}
      />
    ));

    const link = screen.getByRole("link", { name: /open original/i });
    expect(link.getAttribute("href")).toBe("https://example.com/article");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toMatch(/noreferrer|noopener/);
  });
});
