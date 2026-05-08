const GCS_PUT_TIMEOUT_MS = 10 * 60_000;

export async function uploadFileToSignedUrl(
  uploadUrl: string,
  file: File,
  contentType: string,
): Promise<void> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), GCS_PUT_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(uploadUrl, {
      method: "PUT",
      headers: {
        "content-type": contentType,
      },
      body: file,
      signal: controller.signal,
    });
  } catch (error) {
    clearTimeout(timeoutId);
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Upload to signed URL transport failure: ${message}`);
  }
  clearTimeout(timeoutId);

  if (!response.ok) {
    throw new Error(`Upload to signed URL failed (${response.status})`);
  }
}

export async function uploadPdfToSignedUrl(
  uploadUrl: string,
  file: File,
): Promise<void> {
  return uploadFileToSignedUrl(uploadUrl, file, "application/pdf");
}
