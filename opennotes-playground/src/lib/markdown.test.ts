import { describe, expect, it } from "vitest";
import { renderMarkdown } from "./markdown";

describe("renderMarkdown", () => {
  it("converts headings to HTML elements", () => {
    expect(renderMarkdown("# Heading 1")).toContain("<h1");
    expect(renderMarkdown("## Heading 2")).toContain("<h2");
  });

  it("converts paragraphs to <p> tags", () => {
    const result = renderMarkdown("Hello world");
    expect(result).toContain("<p>");
    expect(result).toContain("Hello world");
  });

  it("converts code blocks with language class", () => {
    const result = renderMarkdown("```typescript\nconst x = 1;\n```");
    expect(result).toContain('<code class="language-typescript"');
    expect(result).toContain("const x = 1;");
  });

  it("converts links to <a> tags", () => {
    const result = renderMarkdown("[OpenNotes](https://opennotes.ai)");
    expect(result).toContain("<a");
    expect(result).toContain('href="https://opennotes.ai"');
    expect(result).toContain("OpenNotes");
  });

  it("returns empty string for empty input", () => {
    expect(renderMarkdown("")).toBe("");
  });

  it("strips script tags from output", () => {
    const result = renderMarkdown('<script>alert("xss")</script>');
    expect(result).not.toContain("<script");
  });

  it("strips img onerror XSS vectors", () => {
    const result = renderMarkdown('<img src=x onerror="alert(1)">');
    expect(result).not.toContain("onerror");
  });

  it("strips iframe tags", () => {
    const result = renderMarkdown('<iframe src="https://evil.com"></iframe>');
    expect(result).not.toContain("<iframe");
  });
});
