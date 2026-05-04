export const MAX_PDF_BYTES = 50 * 1024 * 1024;
export const MAX_PDF_LABEL = "50 MB";

export function isPdfTooLarge(file: File): boolean {
  return file.size > MAX_PDF_BYTES;
}

export function isPdfFile(file: File): boolean {
  if (file.type === "application/pdf") return true;
  if (file.name.toLowerCase().endsWith(".pdf")) return true;
  return false;
}
