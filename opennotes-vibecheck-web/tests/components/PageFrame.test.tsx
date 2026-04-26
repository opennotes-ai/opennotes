import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@solidjs/testing-library";
import { createSignal } from "solid-js";
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
        previewMode="original"
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
        previewMode="original"
      />
    ));

    expect(screen.getByTestId("page-frame-screenshot")).not.toBeNull();
    expect(screen.getByTestId("page-frame-iframe").getAttribute("aria-hidden")).toBe(
      "true",
    );
  });

  it("falls back to the screenshot (not the archive) when Original is selected and the iframe is blocked", () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={false}
        blockingHeader="content-security-policy: frame-ancestors 'none'"
        archivedPreviewUrl="/api/archive-preview?url=https%3A%2F%2Fexample.com%2Farticle"
        screenshotUrl="https://cdn.example.com/shot.png"
        previewMode="original"
      />
    ));

    const screenshot = screen.getByTestId(
      "page-frame-screenshot",
    ) as HTMLImageElement;
    expect(screenshot.getAttribute("src")).toBe(
      "https://cdn.example.com/shot.png",
    );
    expect(screen.queryByTestId("page-frame-archived-iframe")).toBeNull();
  });

  it("never silently renders the archive when Original is selected, even without a screenshot", () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={false}
        blockingHeader="content-security-policy: frame-ancestors 'none'"
        archivedPreviewUrl="/api/archive-preview?url=https%3A%2F%2Fexample.com%2Farticle"
        screenshotUrl={null}
        previewMode="original"
      />
    ));

    expect(screen.queryByTestId("page-frame-archived-iframe")).toBeNull();
    expect(screen.queryByTestId("page-frame-unavailable")).not.toBeNull();
  });

  it("shows the archived iframe when the user explicitly selects Archived", () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={false}
        blockingHeader="content-security-policy: frame-ancestors 'none'"
        archivedPreviewUrl="/api/archive-preview?url=https%3A%2F%2Fexample.com%2Farticle"
        screenshotUrl="https://cdn.example.com/shot.png"
        previewMode="archived"
      />
    ));

    const archived = screen.getByTestId(
      "page-frame-archived-iframe",
    ) as HTMLIFrameElement;
    expect(archived.getAttribute("src")).toBe(
      "/api/archive-preview?url=https%3A%2F%2Fexample.com%2Farticle",
    );
    expect(archived.getAttribute("sandbox")).toBe("allow-same-origin");
    expect(screen.queryByTestId("page-frame-screenshot")).toBeNull();
  });

  it("falls from archived iframe to screenshot when archived errors and Archived was explicitly selected", async () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={false}
        archivedPreviewUrl="/api/archive-preview?url=https%3A%2F%2Fexample.com%2Farticle"
        screenshotUrl="https://cdn.example.com/shot.png"
        previewMode="archived"
      />
    ));

    const archived = screen.getByTestId(
      "page-frame-archived-iframe",
    ) as HTMLIFrameElement;
    archived.dispatchEvent(new Event("error"));

    const img = (await screen.findByTestId(
      "page-frame-screenshot",
    )) as HTMLImageElement;
    expect(img.getAttribute("src")).toBe("https://cdn.example.com/shot.png");
    expect(screen.queryByTestId("page-frame-archived-iframe")).toBeNull();
  });

  it("falls from archived iframe to screenshot when archived loads blank and Archived was explicitly selected", async () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={false}
        archivedPreviewUrl="/api/archive-preview?url=https%3A%2F%2Fexample.com%2Farticle"
        screenshotUrl="https://cdn.example.com/shot.png"
        previewMode="archived"
      />
    ));

    const archived = screen.getByTestId(
      "page-frame-archived-iframe",
    ) as HTMLIFrameElement;
    Object.defineProperty(archived, "contentDocument", {
      configurable: true,
      value: {
        body: { children: [], textContent: "" },
        title: "",
      },
    });
    archived.dispatchEvent(new Event("load"));

    const img = (await screen.findByTestId(
      "page-frame-screenshot",
    )) as HTMLImageElement;
    expect(img.getAttribute("src")).toBe("https://cdn.example.com/shot.png");
    expect(screen.queryByTestId("page-frame-archived-iframe")).toBeNull();
  });

  it("manual screenshot mode renders the screenshot immediately", () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={true}
        previewMode="screenshot"
        archivedPreviewUrl="/api/archive-preview?url=https%3A%2F%2Fexample.com%2Farticle"
        screenshotUrl="https://cdn.example.com/shot.png"
      />
    ));

    expect(screen.getByTestId("page-frame-screenshot")).not.toBeNull();
    expect(screen.queryByTestId("page-frame-archived-iframe")).toBeNull();
    expect(screen.getByTestId("page-frame-iframe").getAttribute("aria-hidden")).toBe(
      "true",
    );
  });

  it("swaps to the screenshot when the iframe errors", async () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={true}
        screenshotUrl="https://cdn.example.com/shot.png"
        previewMode="original"
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

  it("swaps to the screenshot when iframe load produces a blocked blank document", async () => {
    render(() => (
      <PageFrame
        url="https://blocked.example.com/article"
        canIframe={true}
        screenshotUrl="https://cdn.example.com/blocked.png"
        previewMode="original"
      />
    ));

    const iframe = screen.getByTestId(
      "page-frame-iframe",
    ) as HTMLIFrameElement;
    Object.defineProperty(iframe, "contentDocument", {
      configurable: true,
      value: {
        location: { href: "about:blank" },
        body: { children: [], textContent: "" },
        title: "",
      },
    });
    iframe.dispatchEvent(new Event("load"));

    const img = (await screen.findByTestId(
      "page-frame-screenshot",
    )) as HTMLImageElement;
    expect(img.getAttribute("src")).toBe("https://cdn.example.com/blocked.png");
  });

  it("falls back to the screenshot when blocking evidence arrives after the iframe verified as renderable", async () => {
    const [canIframe, setCanIframe] = createSignal(true);
    const [blockingHeader, setBlockingHeader] = createSignal<string | null>(
      null,
    );

    const { unmount } = render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={canIframe()}
        blockingHeader={blockingHeader()}
        screenshotUrl="https://cdn.example.com/late.png"
        previewMode="original"
      />
    ));

    const iframe = screen.getByTestId(
      "page-frame-iframe",
    ) as HTMLIFrameElement;
    Object.defineProperty(iframe, "contentDocument", {
      configurable: true,
      value: {
        location: { href: "https://example.com/article" },
        body: { children: [{}], textContent: "Hello world" },
        title: "Example",
      },
    });
    iframe.dispatchEvent(new Event("load"));

    setCanIframe(false);
    setBlockingHeader("content-security-policy: frame-ancestors 'none'");

    const img = (await screen.findByTestId(
      "page-frame-screenshot",
    )) as HTMLImageElement;
    expect(img.getAttribute("src")).toBe("https://cdn.example.com/late.png");
    unmount();
  });

  it("keeps the iframe when cross-origin access throws after load", async () => {
    render(() => (
      <PageFrame
        url="https://open.example.com/article"
        canIframe={true}
        screenshotUrl="https://cdn.example.com/open.png"
        previewMode="original"
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

  it("renders the screenshot at natural width inside a scrollable wrapper", () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={true}
        previewMode="screenshot"
        screenshotUrl="https://cdn.example.com/shot.png"
      />
    ));

    const img = screen.getByTestId(
      "page-frame-screenshot",
    ) as HTMLImageElement;
    const imgClass = img.getAttribute("class") ?? "";

    expect(imgClass).not.toContain("object-contain");
    expect(imgClass).not.toContain("w-full");
    expect(imgClass).toMatch(/max-w-none/);

    const wrapper = img.parentElement as HTMLElement;
    expect(wrapper).not.toBeNull();
    const wrapperClass = wrapper.getAttribute("class") ?? "";
    expect(wrapperClass).toMatch(/overflow-auto/);
  });

  it("keeps the bottom 'Open original' bar outside the scrollable screenshot wrapper", () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={true}
        previewMode="screenshot"
        screenshotUrl="https://cdn.example.com/shot.png"
      />
    ));

    const link = screen.getByRole("link", { name: /open original/i });
    const img = screen.getByTestId("page-frame-screenshot");
    const wrapper = img.parentElement as HTMLElement;

    expect(wrapper.contains(link)).toBe(false);
  });

  it("always shows an 'Open original' link", () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={true}
        screenshotUrl={null}
        previewMode="original"
      />
    ));

    const link = screen.getByRole("link", { name: /open original/i });
    expect(link.getAttribute("href")).toBe("https://example.com/article");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toMatch(/noreferrer|noopener/);
  });
});
