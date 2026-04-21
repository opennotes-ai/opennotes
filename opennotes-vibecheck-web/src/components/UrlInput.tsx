import { createSignal, Show, type JSX } from "solid-js";

export type UrlValidationResult =
  | { ok: true; normalized: string }
  | { ok: false; reason: string };

export function validateAnalyzableUrl(raw: string): UrlValidationResult {
  const trimmed = raw.trim();
  if (!trimmed) {
    return { ok: false, reason: "Enter a URL to analyze." };
  }

  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    return {
      ok: false,
      reason: "That doesn't look like a valid URL. Include https://",
    };
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return {
      ok: false,
      reason: "Only http and https URLs can be analyzed.",
    };
  }

  if (!parsed.hostname) {
    return { ok: false, reason: "URL must include a hostname." };
  }

  return { ok: true, normalized: parsed.toString() };
}

export interface UrlInputProps {
  action: unknown;
  initialValue?: string;
  pending?: boolean;
  autofocus?: boolean;
  onValidSubmit?: (url: string) => void;
}

export default function UrlInput(props: UrlInputProps) {
  const [value, setValue] = createSignal(props.initialValue ?? "");
  const [error, setError] = createSignal<string | null>(null);

  const handleSubmit: JSX.EventHandler<HTMLFormElement, SubmitEvent> = (
    event,
  ) => {
    const result = validateAnalyzableUrl(value());
    if (!result.ok) {
      event.preventDefault();
      setError(result.reason);
      return;
    }
    setError(null);
    if (props.onValidSubmit) {
      props.onValidSubmit(result.normalized);
    }
  };

  return (
    <form
      action={props.action as string | undefined}
      method="post"
      onSubmit={handleSubmit}
      class="mx-auto flex w-full max-w-xl flex-col gap-3"
      novalidate
    >
      <label for="vibecheck-url" class="sr-only">
        URL to analyze
      </label>
      <div class="flex flex-col gap-2 sm:flex-row">
        <input
          id="vibecheck-url"
          name="url"
          type="url"
          inputmode="url"
          autocomplete="url"
          autocapitalize="none"
          spellcheck={false}
          autofocus={props.autofocus}
          placeholder="https://example.com/article"
          value={value()}
          onInput={(e) => {
            setValue(e.currentTarget.value);
            if (error()) setError(null);
          }}
          aria-invalid={error() ? "true" : "false"}
          aria-describedby={error() ? "vibecheck-url-error" : undefined}
          class="flex-1 rounded-md border border-input bg-background px-4 py-3 text-base shadow-xs outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 aria-[invalid=true]:border-destructive aria-[invalid=true]:ring-destructive/40"
        />
        <button
          type="submit"
          disabled={props.pending}
          class="inline-flex items-center justify-center rounded-md bg-primary px-5 py-3 text-sm font-medium text-primary-foreground shadow-xs transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {props.pending ? "Analyzing..." : "Analyze"}
        </button>
      </div>
      <Show when={error()}>
        {(message) => (
          <p
            id="vibecheck-url-error"
            role="alert"
            class="text-sm text-destructive"
          >
            {message()}
          </p>
        )}
      </Show>
    </form>
  );
}
