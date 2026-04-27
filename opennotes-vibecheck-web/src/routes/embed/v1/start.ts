import type { APIEvent } from "@solidjs/start/server";
import { resolveAnalyzeRedirect } from "~/routes/analyze.data";

const NO_STORE = "no-store, private";
const ALLOW_POST: Record<string, string> = {
  Allow: "POST",
  "Cache-Control": NO_STORE,
};

function methodNotAllowed(): Response {
  return new Response(null, { status: 405, headers: ALLOW_POST });
}

function rewriteAs303(response: Response): Response {
  if (response.status >= 300 && response.status < 400) {
    const headers = new Headers(response.headers);
    if (!headers.has("Cache-Control")) headers.set("Cache-Control", NO_STORE);
    return new Response(null, { status: 303, headers });
  }
  return response;
}

export async function POST(event: APIEvent): Promise<Response> {
  let formData: FormData;
  try {
    formData = await event.request.formData();
  } catch {
    return new Response(null, {
      status: 303,
      headers: { Location: "/?error=invalid_url", "Cache-Control": NO_STORE },
    });
  }
  try {
    await resolveAnalyzeRedirect(formData);
  } catch (thrown) {
    if (thrown instanceof Response) {
      if (thrown.status >= 300 && thrown.status < 400) return rewriteAs303(thrown);
      return new Response(null, {
        status: 500,
        headers: { "Cache-Control": NO_STORE },
      });
    }
    throw thrown;
  }
  return new Response(null, {
    status: 500,
    headers: { "Cache-Control": NO_STORE },
  });
}

export async function GET(): Promise<Response> {
  return methodNotAllowed();
}

export async function PUT(): Promise<Response> {
  return methodNotAllowed();
}

export async function DELETE(): Promise<Response> {
  return methodNotAllowed();
}

export async function PATCH(): Promise<Response> {
  return methodNotAllowed();
}

export async function HEAD(): Promise<Response> {
  return methodNotAllowed();
}

export async function OPTIONS(): Promise<Response> {
  return methodNotAllowed();
}
