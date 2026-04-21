import { Show } from "solid-js";
import { useSearchParams, useSubmission } from "@solidjs/router";
import { Title } from "@solidjs/meta";
import UrlInput from "~/components/UrlInput";
import { analyzeAction } from "./analyze.data";

function errorLabelFor(code: string | undefined): string | null {
  if (!code) return null;
  switch (code) {
    case "invalid_url":
      return "That URL couldn't be parsed. Double-check the scheme and host.";
    case "upstream_error":
      return "The analyzer couldn't reach that page. Try again in a moment.";
    default:
      return "Something went wrong. Please try another URL.";
  }
}

export default function HomePage() {
  const [searchParams] = useSearchParams();
  const submission = useSubmission(analyzeAction);

  const errorMessage = () =>
    errorLabelFor(
      typeof searchParams.error === "string" ? searchParams.error : undefined,
    );

  return (
    <>
      <Title>vibecheck — URL analysis</Title>
      <main class="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-10 px-4 py-16 text-center">
        <header class="space-y-4">
          <h1 class="text-5xl font-semibold tracking-tight sm:text-6xl">
            vibecheck
          </h1>
          <p class="mx-auto max-w-md text-lg text-muted-foreground">
            Analyze any URL for tone, claims, safety, and opinions.
          </p>
        </header>

        <UrlInput
          action={analyzeAction}
          pending={submission.pending}
          autofocus
        />

        <Show when={errorMessage()}>
          {(message) => (
            <p role="alert" class="text-sm text-destructive">
              {message()}
            </p>
          )}
        </Show>

        <p class="text-xs text-muted-foreground">
          Results appear instantly for recently analyzed URLs. New URLs take
          about 30-60 seconds to analyze.
        </p>
      </main>
    </>
  );
}
