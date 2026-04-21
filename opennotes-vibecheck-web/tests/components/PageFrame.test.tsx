import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
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

  it("renders a screenshot when canIframe=false and a screenshot URL exists", () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={false}
        screenshotUrl="https://cdn.example.com/shot.png"
      />
    ));

    const img = screen.getByTestId(
      "page-frame-screenshot",
    ) as HTMLImageElement;
    expect(img).not.toBeNull();
    expect(img.tagName.toLowerCase()).toBe("img");
    expect(img.getAttribute("src")).toBe("https://cdn.example.com/shot.png");
    expect(screen.queryByTestId("page-frame-iframe")).toBeNull();
  });

  it("shows an unavailable state when iframe is blocked and no screenshot was produced", () => {
    render(() => (
      <PageFrame
        url="https://example.com/article"
        canIframe={false}
        screenshotUrl={null}
      />
    ));

    expect(screen.queryByTestId("page-frame-iframe")).toBeNull();
    expect(screen.queryByTestId("page-frame-screenshot")).toBeNull();
    expect(screen.getByTestId("page-frame-unavailable")).not.toBeNull();
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
