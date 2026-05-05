import { describe, expect, it } from "vitest";
import {
  buildAnalyzeSuccessRedirectUrl,
  buildPdfSuccessRedirectUrl,
} from "~/routes/analyze.data";

describe("buildAnalyzeSuccessRedirectUrl", () => {
  it("includes url param on fresh submit", () => {
    const url = buildAnalyzeSuccessRedirectUrl("abc-123", false, "https://example.com/a");
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.get("job")).toBe("abc-123");
    expect(params.get("url")).toBe("https://example.com/a");
    expect(params.get("c")).toBeNull();
  });

  it("includes c=1 and url on cached submit", () => {
    const url = buildAnalyzeSuccessRedirectUrl("abc-123", true, "https://example.com/a");
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.get("c")).toBe("1");
    expect(params.get("url")).toBe("https://example.com/a");
  });

  it("encodes url with special characters", () => {
    const raw = "https://example.com/a?b=1&c=2#hash";
    const url = buildAnalyzeSuccessRedirectUrl("abc-123", false, raw);
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.get("url")).toBe(raw);
  });
});

describe("buildPdfSuccessRedirectUrl", () => {
  it("includes filename not url", () => {
    const url = buildPdfSuccessRedirectUrl("abc-123", false, "my-file.pdf");
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.get("filename")).toBe("my-file.pdf");
    expect(params.get("url")).toBeNull();
  });

  it("includes c=1 on cached result", () => {
    const url = buildPdfSuccessRedirectUrl("abc-123", true, "my-file.pdf");
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.get("c")).toBe("1");
    expect(params.get("filename")).toBe("my-file.pdf");
  });

  it("encodes filename with special characters", () => {
    const filename = "my file & report.pdf";
    const url = buildPdfSuccessRedirectUrl("abc-123", false, filename);
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.get("filename")).toBe(filename);
  });
});
