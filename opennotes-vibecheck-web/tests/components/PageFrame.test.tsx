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

  it("auto-resolves to screenshot immediately (no deciding) when canIframe=false and no archive (TASK-1483.13.02)", () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={false}
        blockingHeader="content-security-policy: frame-ancestors 'none'"
        screenshotUrl="https://cdn.example.com/shot.png"
        previewMode="original"
      />
    ));

    expect(screen.queryByTestId("page-frame-deciding")).toBeNull();
    expect(screen.getByTestId("page-frame-screenshot")).not.toBeNull();
    expect(
      screen.getByTestId("page-frame-iframe").getAttribute("aria-hidden"),
    ).toBe("true");
  });

  it("auto-resolves to archive immediately (no deciding) when canIframe=false and archive is available (TASK-1483.13.02)", () => {
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

    expect(screen.queryByTestId("page-frame-deciding")).toBeNull();
    const archived = screen.getByTestId(
      "page-frame-archived-iframe",
    ) as HTMLIFrameElement;
    expect(archived.getAttribute("src")).toBe(
      "/api/archive-preview?url=https%3A%2F%2Fexample.com%2Farticle",
    );
    expect(screen.queryByTestId("page-frame-screenshot")).toBeNull();
  });

  it("auto-resolves to archive immediately when canIframe=false and no screenshot exists", () => {
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

    expect(screen.queryByTestId("page-frame-deciding")).toBeNull();
    expect(screen.getByTestId("page-frame-archived-iframe")).not.toBeNull();
    expect(screen.queryByTestId("page-frame-unavailable")).toBeNull();
  });

  it("auto-resolves to unavailable immediately when canIframe=false and neither archive nor screenshot exists", () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={false}
        blockingHeader="content-security-policy: frame-ancestors 'none'"
        screenshotUrl={null}
        previewMode="original"
      />
    ));

    expect(screen.queryByTestId("page-frame-deciding")).toBeNull();
    expect(screen.getByTestId("page-frame-unavailable")).not.toBeNull();
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

  it("auto-resolves to screenshot immediately when blocking evidence arrives after the iframe verified as renderable (TASK-1483.13.02)", async () => {
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
    await Promise.resolve();

    // Server reports blocked → auto-resolve straight to screenshot, no
    // deciding interstitial.
    expect(screen.queryByTestId("page-frame-deciding")).toBeNull();
    const img = screen.getByTestId(
      "page-frame-screenshot",
    ) as HTMLImageElement;
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

describe("countdown interstitial (TASK-1495.07 + TASK-1483.13.02 escape hatch)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  it("arms the countdown when canIframe=true but a blockingHeader/cspFrameAncestors hint is present (regression: Codex review)", async () => {
    // Regression: when the server reports canIframe=true alongside a blocking
    // header (e.g. a permissive `frame-ancestors *` CSP that the probe sees
    // but the iframe will load fine), activePreview() returns "deciding"
    // because hasBlockingHint() is true. The countdown trigger MUST also
    // arm a timer in this case, otherwise the UI gets stuck on
    // "Auto-switching in ~15s" forever.
    const onResolvedModeChange = vi.fn();
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={true}
        cspFrameAncestors="frame-ancestors *"
        archivedPreviewUrl="/api/archive-preview?url=https%3A%2F%2Fexample.com%2Farticle"
        screenshotUrl="https://cdn.example.com/shot.png"
        previewMode="original"
        onResolvedModeChange={onResolvedModeChange}
      />
    ));

    // Initially: hasBlockingHint=true (cspFrameAncestors set) but canIframe=true,
    // so activePreview returns "deciding" rather than auto-resolving.
    expect(screen.getByTestId("page-frame-deciding")).not.toBeNull();

    // The countdown timer MUST arm — after 15s, chain B fires.
    vi.advanceTimersByTime(15_000);
    await Promise.resolve();

    expect(screen.queryByTestId("page-frame-deciding")).toBeNull();
    expect(screen.getByTestId("page-frame-archived-iframe")).not.toBeNull();
    expect(onResolvedModeChange).toHaveBeenCalledWith("archived");
  });

  it("renders the deciding interstitial on runtime iframe failure (canIframe=true → onError)", () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={true}
        archivedPreviewUrl="/api/archive-preview?url=https%3A%2F%2Fexample.com%2Farticle"
        screenshotUrl="https://cdn.example.com/shot.png"
        previewMode="original"
      />
    ));
    const iframe = screen.getByTestId(
      "page-frame-iframe",
    ) as HTMLIFrameElement;
    iframe.dispatchEvent(new Event("error"));

    expect(screen.getByTestId("page-frame-deciding")).not.toBeNull();
    expect(screen.queryByTestId("page-frame-archived-iframe")).toBeNull();
    expect(screen.queryByTestId("page-frame-screenshot")).toBeNull();
  });

  it("auto-switches to archive after the countdown elapses on runtime failure (chain B has archive)", async () => {
    const onResolvedModeChange = vi.fn();
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={true}
        archivedPreviewUrl="/api/archive-preview?url=https%3A%2F%2Fexample.com%2Farticle"
        screenshotUrl="https://cdn.example.com/shot.png"
        previewMode="original"
        onResolvedModeChange={onResolvedModeChange}
      />
    ));
    const iframe = screen.getByTestId(
      "page-frame-iframe",
    ) as HTMLIFrameElement;
    iframe.dispatchEvent(new Event("error"));

    expect(screen.getByTestId("page-frame-deciding")).not.toBeNull();

    vi.advanceTimersByTime(15_000);
    await Promise.resolve();

    expect(screen.queryByTestId("page-frame-deciding")).toBeNull();
    expect(screen.getByTestId("page-frame-archived-iframe")).not.toBeNull();
    expect(onResolvedModeChange).toHaveBeenCalledWith("archived");
  });

  it("re-arms the deciding interstitial when the user clicks Original after a server-blocked auto-resolve (escape hatch)", async () => {
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

    // Initial render auto-resolves to archived; no deciding interstitial.
    expect(screen.queryByTestId("page-frame-deciding")).toBeNull();
    expect(screen.getByTestId("page-frame-archived-iframe")).not.toBeNull();
    expect(onResolvedModeChange).toHaveBeenCalledWith("archived");

    // Parent's handler would normally setPreviewMode("archived") at this point.
    setMode("archived");
    await Promise.resolve();

    // User clicks Original — flip back to "original" re-arms the deciding window.
    setMode("original");
    await Promise.resolve();

    expect(screen.getByTestId("page-frame-deciding")).not.toBeNull();

    // After 15s the countdown elapses and chain B fires again.
    vi.advanceTimersByTime(15_000);
    await Promise.resolve();
    expect(screen.queryByTestId("page-frame-deciding")).toBeNull();
    expect(screen.getByTestId("page-frame-archived-iframe")).not.toBeNull();
  });

  it("does not let parent auto-resolve feedback cancel a user-armed Original escape hatch", async () => {
    const [mode, setMode] = createSignal<PreviewMode>("original");
    const onResolvedModeChange = vi.fn(
      (resolved: PreviewMode | "unavailable") => {
        if (resolved !== "unavailable") {
          setMode(resolved);
        }
      },
    );

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

    await waitFor(() => expect(mode()).toBe("archived"));
    expect(screen.queryByTestId("page-frame-deciding")).toBeNull();
    expect(screen.getByTestId("page-frame-archived-iframe")).not.toBeNull();

    setMode("original");
    await Promise.resolve();

    expect(mode()).toBe("original");
    expect(screen.getByTestId("page-frame-deciding")).not.toBeNull();
    expect(screen.queryByTestId("page-frame-archived-iframe")).toBeNull();
  });

  it("auto-switches to screenshot after countdown when no archive is present (runtime failure)", async () => {
    const onResolvedModeChange = vi.fn();
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={true}
        screenshotUrl="https://cdn.example.com/shot.png"
        previewMode="original"
        onResolvedModeChange={onResolvedModeChange}
      />
    ));
    const iframe = screen.getByTestId(
      "page-frame-iframe",
    ) as HTMLIFrameElement;
    iframe.dispatchEvent(new Event("error"));

    vi.advanceTimersByTime(15_000);
    await Promise.resolve();

    expect(screen.getByTestId("page-frame-screenshot")).not.toBeNull();
    expect(onResolvedModeChange).toHaveBeenCalledWith("screenshot");
  });

  it("cancels the countdown when the user overrides via previewMode prop change (runtime-failure path)", async () => {
    const [mode, setMode] = createSignal<PreviewMode>("original");
    const onResolvedModeChange = vi.fn();
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={true}
        archivedPreviewUrl="/api/archive-preview?url=https%3A%2F%2Fexample.com%2Farticle"
        screenshotUrl="https://cdn.example.com/shot.png"
        previewMode={mode()}
        onResolvedModeChange={onResolvedModeChange}
      />
    ));
    const iframe = screen.getByTestId(
      "page-frame-iframe",
    ) as HTMLIFrameElement;
    iframe.dispatchEvent(new Event("error"));
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

  it("never emits 'deciding' to onResolvedModeChange (only resolved real modes)", async () => {
    const onResolvedModeChange = vi.fn();
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={true}
        archivedPreviewUrl="/api/archive-preview?url=https%3A%2F%2Fexample.com%2Farticle"
        screenshotUrl="https://cdn.example.com/shot.png"
        previewMode="original"
        onResolvedModeChange={onResolvedModeChange}
      />
    ));
    const iframe = screen.getByTestId(
      "page-frame-iframe",
    ) as HTMLIFrameElement;
    iframe.dispatchEvent(new Event("error"));
    await Promise.resolve();

    expect(screen.getByTestId("page-frame-deciding")).not.toBeNull();
    const calls = onResolvedModeChange.mock.calls.flat();
    expect(calls).not.toContain("deciding");
  });

  it("renders a progress bar inside the interstitial with the countdown animation", () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={true}
        archivedPreviewUrl="/api/archive-preview?url=https%3A%2F%2Fexample.com%2Farticle"
        screenshotUrl="https://cdn.example.com/shot.png"
        previewMode="original"
      />
    ));
    const iframe = screen.getByTestId(
      "page-frame-iframe",
    ) as HTMLIFrameElement;
    iframe.dispatchEvent(new Event("error"));

    const progress = screen.getByTestId(
      "page-frame-deciding-progress",
    ) as HTMLElement;
    expect(progress).not.toBeNull();
    const style = progress.getAttribute("style") ?? "";
    expect(style).toMatch(/pageFrameDecidingProgress/);
    expect(style).toMatch(/15000ms/);
  });
});
