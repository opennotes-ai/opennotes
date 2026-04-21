export function softHyphenate(s: string): string {
  return s.replace(/([a-z])([A-Z])/g, "$1\u00AD$2");
}
