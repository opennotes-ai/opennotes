import type { APIEvent } from "@solidjs/start/server";
import { resolveAnalyzeRedirect } from "~/routes/analyze.data";

const ALLOW_HEADER: Record<string, string> = { Allow: "POST" };

function rewriteAs303(response: Response): Response {
  if (response.status >= 300 && response.status < 400) {
    const location = response.headers.get("Location") ?? "";
    return new Response(null, {
      status: 303,
      headers: { Location: location },
    });
  }
  return response;
}

export async function POST(event: APIEvent): Promise<Response> {
  let formData: FormData;
  try {
    formData = await event.request.formData();
  } catch {
    return Response.redirect(
      new URL("/?error=invalid_url", event.request.url),
      303,
    );
  }
  try {
    await resolveAnalyzeRedirect(formData);
  } catch (thrown) {
    if (thrown instanceof Response) return rewriteAs303(thrown);
    throw thrown;
  }
  return new Response("internal: redirect missing", { status: 500 });
}

export async function GET(): Promise<Response> {
  return new Response(null, { status: 405, headers: ALLOW_HEADER });
}

export async function PUT(): Promise<Response> {
  return new Response(null, { status: 405, headers: ALLOW_HEADER });
}

export async function DELETE(): Promise<Response> {
  return new Response(null, { status: 405, headers: ALLOW_HEADER });
}

export async function PATCH(): Promise<Response> {
  return new Response(null, { status: 405, headers: ALLOW_HEADER });
}
