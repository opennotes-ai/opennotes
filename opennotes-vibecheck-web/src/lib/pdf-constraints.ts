export const MAX_PDF_BYTES = 50 * 1024 * 1024;
export const MAX_PDF_LABEL = "50 MB";
export const MAX_IMAGE_BATCH_BYTES = 45 * 1024 * 1024;
export const MAX_IMAGE_BATCH_LABEL = "45 MB";
export const MAX_IMAGE_COUNT = 100;

export const ALLOWED_IMAGE_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/tiff",
  "image/bmp",
]);

export function isPdfTooLarge(file: File): boolean {
  return file.size > MAX_PDF_BYTES;
}

export function isPdfFile(file: File): boolean {
  if (file.type === "application/pdf") return true;
  if (file.name.toLowerCase().endsWith(".pdf")) return true;
  return false;
}

export function isImageFile(file: File): boolean {
  return ALLOWED_IMAGE_TYPES.has(file.type.toLowerCase());
}

export function imageBatchBytes(files: readonly File[]): number {
  return files.reduce((total, file) => total + file.size, 0);
}

export function isImageBatchTooLarge(files: readonly File[]): boolean {
  return imageBatchBytes(files) > MAX_IMAGE_BATCH_BYTES;
}
