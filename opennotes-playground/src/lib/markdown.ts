import { marked } from "marked";

export function renderMarkdown(source: string): string {
  if (!source) return "";
  return marked.parse(source, { async: false }) as string;
}
