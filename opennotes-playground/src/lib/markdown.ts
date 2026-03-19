import { marked } from "marked";
import DOMPurify from "isomorphic-dompurify";

export function renderMarkdown(source: string): string {
  if (!source) return "";
  const raw = marked.parse(source, { async: false }) as string;
  return DOMPurify.sanitize(raw);
}

export function renderInlineMarkdown(source: string): string {
  if (!source) return "";
  const raw = marked.parseInline(source, { async: false }) as string;
  return DOMPurify.sanitize(raw);
}
