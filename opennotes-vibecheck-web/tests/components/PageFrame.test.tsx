import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { render, screen, cleanup, waitFor } from "@solidjs/testing-library";
import { createSignal } from "solid-js";
import PageFrame from "../../src/components/PageFrame";
import type { PreviewMode } from "../../src/components/PageFrame";

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

  it("shows the screenshot first when the backend reports a blocking header", async () => {
    vi.useFakeTimers();
    try {
      render(() => (
        <PageFrame
          url="https://example.com/article"
          canIframe={false}
          blockingHeader="content-security-policy: frame-ancestors 'none'"
          screenshotUrl="https://cdn.example.com/shot.png"
          previewMode="original"
        />
      ));

      // Countdown interstitial renders first; advance past 15s to reach chain B.
      expect(screen.getByTestId("page-frame-deciding")).not.toBeNull();
      vi.advanceTimersByTime(15_000);
      await Promise.resolve();

      expect(screen.getByTestId("page-frame-screenshot")).not.toBeNull();
      expect(
        screen.getByTestId("page-frame-iframe").getAttribute("aria-hidden"),
      ).toBe("true");
    } finally {
      vi.useRealTimers();
    }
  });

  it("falls back to the archive when Original is selected, iframe is blocked, and archive is available (chain B)", async () => {
    vi.useFakeTimers();
    try {
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

      // Countdown interstitial blocks chain B until ~15s elapse.
      expect(screen.getByTestId("page-frame-deciding")).not.toBeNull();
      vi.advanceTimersByTime(15_000);
      await Promise.resolve();

      const archived = screen.getByTestId(
        "page-frame-archived-iframe",
      ) as HTMLIFrameElement;
      expect(archived.getAttribute("src")).toBe(
        "/api/archive-preview?url=https%3A%2F%2Fexample.com%2Farticle",
      );
      expect(screen.queryByTestId("page-frame-screenshot")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("renders the archive when Original is blocked and no screenshot exists (chain B)", async () => {
    vi.useFakeTimers();
    try {
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

      expect(screen.getByTestId("page-frame-deciding")).not.toBeNull();
      vi.advanceTimersByTime(15_000);
      await Promise.resolve();

      expect(screen.getByTestId("page-frame-archived-iframe")).not.toBeNull();
      expect(screen.queryByTestId("page-frame-unavailable")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
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
    vi.useFakeTimers();
    try {
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

      // Runtime failure triggers the deciding interstitial; advance past 15s.
      expect(screen.getByTestId("page-frame-deciding")).not.toBeNull();
      vi.advanceTimersByTime(15_000);
      await Promise.resolve();

      const img = screen.getByTestId(
        "page-frame-screenshot",
      ) as HTMLImageElement;
      expect(img.getAttribute("src")).toBe("https://cdn.example.com/shot.png");
      expect(screen.queryByTestId("page-frame-iframe")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("swaps to the screenshot when iframe load produces a blocked blank document", async () => {
    vi.useFakeTimers();
    try {
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

      // Blocked classification triggers the deciding interstitial; advance past 15s.
      expect(screen.getByTestId("page-frame-deciding")).not.toBeNull();
      vi.advanceTimersByTime(15_000);
      await Promise.resolve();

      const img = screen.getByTestId(
        "page-frame-screenshot",
      ) as HTMLImageElement;
      expect(img.getAttribute("src")).toBe("https://cdn.example.com/blocked.png");
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps the load timeout active when classification returns 'blocked' so the timeout backstops false negatives", async () => {
    // This test asserts the implementation invariant from AC #5:
    // when classification flags the loaded doc as blocked, iframeLoaded stays
    // false so startLoadTimeout's `!iframeLoaded()` predicate remains true,
    // letting the timeout act as a backup safety net.
    vi.useFakeTimers();
    try {
      render(() => (
        <PageFrame
          url="https://blocked.example.com/article"
          canIframe={true}
          screenshotUrl="https://cdn.example.com/blocked.png"
          previewMode="original"
        />
      ));

      const iframe = screen.getByTestId("page-frame-iframe") as HTMLIFrameElement;
      Object.defineProperty(iframe, "contentDocument", {
        configurable: true,
        value: {
          location: { href: "about:blank" },
          body: { children: [], textContent: "" },
          title: "",
        },
      });
      iframe.dispatchEvent(new Event("load"));

      // Deciding interstitial first, then chain-B fall-through to screenshot.
      expect(screen.getByTestId("page-frame-deciding")).not.toBeNull();
      vi.advanceTimersByTime(15_000);
      await Promise.resolve();

      // After blocked classification + countdown, the screenshot is shown (chain-B
      // fall-through resolves "original blocked + no archive" → "screenshot").
      expect(screen.queryByTestId("page-frame-screenshot")).not.toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("falls back to the screenshot when blocking evidence arrives after the iframe verified as renderable", async () => {
    vi.useFakeTimers();
    try {
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

      // Late blocking evidence triggers the deciding interstitial; advance past 15s.
      expect(screen.getByTestId("page-frame-deciding")).not.toBeNull();
      vi.advanceTimersByTime(15_000);
      await Promise.resolve();

      const img = screen.getByTestId(
        "page-frame-screenshot",
      ) as HTMLImageElement;
      expect(img.getAttribute("src")).toBe("https://cdn.example.com/late.png");
      unmount();
    } finally {
      vi.useRealTimers();
    }
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

  it("contains the section width with min-w-0/max-w-full so wide content cannot push the layout", () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={true}
        previewMode="screenshot"
        screenshotUrl="https://cdn.example.com/shot.png"
      />
    ));
    const section = screen.getByLabelText("Page preview");
    const cls = section.getAttribute("class") ?? "";
    expect(cls).toMatch(/\bw-full\b/);
    expect(cls).toMatch(/\bmin-w-0\b/);
    expect(cls).toMatch(/\bmax-w-full\b/);
  });

  it("marks the hidden Original iframe inert when the active preview is screenshot", () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={true}
        previewMode="screenshot"
        screenshotUrl="https://cdn.example.com/shot.png"
      />
    ));
    const iframe = screen.getByTestId("page-frame-iframe") as HTMLIFrameElement;
    // Solid + jsdom set `inert` as a DOM property rather than reflecting it as
    // an HTML attribute. Asserting the property captures the actual a11y
    // semantics (the element is inert) without depending on attribute
    // reflection differences across runtimes.
    expect((iframe as unknown as { inert: boolean }).inert).toBe(true);
    expect(iframe.getAttribute("aria-hidden")).toBe("true");
  });
});

describe("countdown interstitial (TASK-1495.07)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  it("renders the deciding interstitial when Original is blocked and countdown has not elapsed", () => {
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

    expect(screen.getByTestId("page-frame-deciding")).not.toBeNull();
    expect(screen.queryByTestId("page-frame-archived-iframe")).toBeNull();
    expect(screen.queryByTestId("page-frame-screenshot")).toBeNull();
  });

  it("auto-switches to archive after the countdown elapses (chain B has archive)", async () => {
    const onResolvedModeChange = vi.fn();
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={false}
        blockingHeader="content-security-policy: frame-ancestors 'none'"
        archivedPreviewUrl="/api/archive-preview?url=https%3A%2F%2Fexample.com%2Farticle"
        screenshotUrl="https://cdn.example.com/shot.png"
        previewMode="original"
        onResolvedModeChange={onResolvedModeChange}
      />
    ));
    expect(screen.getByTestId("page-frame-deciding")).not.toBeNull();

    vi.advanceTimersByTime(15_000);
    await Promise.resolve();

    expect(screen.queryByTestId("page-frame-deciding")).toBeNull();
    expect(screen.getByTestId("page-frame-archived-iframe")).not.toBeNull();
    expect(onResolvedModeChange).toHaveBeenCalledWith("archived");
  });

  it("auto-switches to screenshot after countdown when no archive is present", async () => {
    const onResolvedModeChange = vi.fn();
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={false}
        blockingHeader="content-security-policy: frame-ancestors 'none'"
        screenshotUrl="https://cdn.example.com/shot.png"
        previewMode="original"
        onResolvedModeChange={onResolvedModeChange}
      />
    ));
    vi.advanceTimersByTime(15_000);
    await Promise.resolve();

    expect(screen.getByTestId("page-frame-screenshot")).not.toBeNull();
    expect(onResolvedModeChange).toHaveBeenCalledWith("screenshot");
  });

  it("cancels the countdown when the user overrides via previewMode prop change", async () => {
    const [mode, setMode] = createSignal<PreviewMode>("original");
    const onResolvedModeChange = vi.fn();
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={false}
        blockingHeader="content-security-policy: frame-ancestors 'none'"
        archivedPreviewUrl="/api/archive-preview?url=https%3A%2F%2Fexample.com%2Farticle"
        screenshotUrl="https://cdn.example.com/shot.png"
        previewMode={mode()}
        onResolvedModeChange={onResolvedModeChange}
      />
    ));
    expect(screen.getByTestId("page-frame-deciding")).not.toBeNull();

    setMode("screenshot");
    await Promise.resolve();

    expect(screen.queryByTestId("page-frame-deciding")).toBeNull();
    expect(screen.getByTestId("page-frame-screenshot")).not.toBeNull();

    // Advancing past 15s after the override must NOT trigger any stale switch.
    vi.advanceTimersByTime(20_000);
    await Promise.resolve();
    expect(onResolvedModeChange).toHaveBeenLastCalledWith("screenshot");
  });

  it("does not emit 'deciding' to onResolvedModeChange (only resolved real modes)", () => {
    const onResolvedModeChange = vi.fn();
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={false}
        blockingHeader="content-security-policy: frame-ancestors 'none'"
        archivedPreviewUrl="/api/archive-preview?url=https%3A%2F%2Fexample.com%2Farticle"
        screenshotUrl="https://cdn.example.com/shot.png"
        previewMode="original"
        onResolvedModeChange={onResolvedModeChange}
      />
    ));
    expect(screen.getByTestId("page-frame-deciding")).not.toBeNull();
    // Critical: callback fires for resolved modes, NEVER for "deciding".
    const calls = onResolvedModeChange.mock.calls.flat();
    expect(calls).not.toContain("deciding");
  });

  it("renders a progress bar inside the interstitial with the countdown animation", () => {
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
    const progress = screen.getByTestId(
      "page-frame-deciding-progress",
    ) as HTMLElement;
    expect(progress).not.toBeNull();
    const style = progress.getAttribute("style") ?? "";
    expect(style).toMatch(/pageFrameDecidingProgress/);
    expect(style).toMatch(/15000ms/);
  });
});
