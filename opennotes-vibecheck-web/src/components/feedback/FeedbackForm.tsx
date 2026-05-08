import { createSignal, Show, type JSX } from "solid-js";
import { ThumbsUp, ThumbsDown, MessageSquare } from "lucide-solid";
import { Input } from "@opennotes/ui/components/ui/input";
import { Button } from "@opennotes/ui/components/ui/button";
import {
  ToggleGroup,
  ToggleGroupItem,
} from "@opennotes/ui/components/ui/toggle-group";

export type FeedbackType = "thumbs_up" | "thumbs_down" | "message";

export interface FeedbackFormProps {
  initialType: FeedbackType;
  onSend: (payload: {
    email: string | null;
    message: string | null;
    final_type: FeedbackType;
  }) => Promise<void>;
  onCancel?: () => void;
  class?: string;
}

export function FeedbackForm(props: FeedbackFormProps): JSX.Element {
  const [email, setEmail] = createSignal("");
  const [message, setMessage] = createSignal("");
  const [currentType, setCurrentType] = createSignal<FeedbackType>(
    props.initialType,
  );
  const [busy, setBusy] = createSignal(false);
  const [sendError, setSendError] = createSignal<string | null>(null);

  const isSendDisabled = () =>
    busy() ||
    (currentType() === "message" && message().trim().length <= 4);

  const handleSubmit: JSX.EventHandler<HTMLFormElement, SubmitEvent> = async (
    event,
  ) => {
    event.preventDefault();
    if (isSendDisabled()) return;

    setBusy(true);
    setSendError(null);

    try {
      await props.onSend({
        email: email().trim() || null,
        message: message().trim() || null,
        final_type: currentType(),
      });
    } catch {
      setSendError("Couldn't send — try again?");
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      class={props.class}
      novalidate
    >
      <div class="flex flex-col gap-4">
        <div class="flex flex-col gap-1.5">
          <label for="feedback-email" class="sr-only">
            Email
          </label>
          <Input
            id="feedback-email"
            type="email"
            placeholder="name@example.com"
            value={email()}
            onInput={(e) => setEmail(e.currentTarget.value)}
            autocomplete="email"
            disabled={busy()}
          />
        </div>

        <div class="flex flex-col gap-1.5">
          <label for="feedback-message" class="sr-only">
            Message
          </label>
          <textarea
            id="feedback-message"
            placeholder="Message…"
            rows={3}
            value={message()}
            onInput={(e) => setMessage(e.currentTarget.value)}
            disabled={busy()}
            class="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50 field-sizing-content min-rows-3 max-rows-8"
            style={{ "field-sizing": "content" }}
          />
        </div>

        <ToggleGroup
          aria-label="Feedback type"
          value={currentType()}
          onChange={(v) => {
            if (v) setCurrentType(v as FeedbackType);
          }}
          class="justify-start"
        >
          <ToggleGroupItem value="thumbs_up" aria-label="Thumbs up">
            <ThumbsUp size={16} />
          </ToggleGroupItem>
          <ToggleGroupItem value="thumbs_down" aria-label="Thumbs down">
            <ThumbsDown size={16} />
          </ToggleGroupItem>
          <ToggleGroupItem value="message" aria-label="Send a message">
            <MessageSquare size={16} />
          </ToggleGroupItem>
        </ToggleGroup>

        <Show when={sendError()}>
          {(msg) => (
            <p role="alert" class="text-sm text-destructive">
              {msg()}
            </p>
          )}
        </Show>

        <Button
          type="submit"
          disabled={isSendDisabled()}
          class="w-full"
        >
          {busy() ? "Sending…" : "Send"}
        </Button>

        <Show when={props.onCancel}>
          <Button
            type="button"
            variant="ghost"
            onClick={props.onCancel}
            class="w-full"
          >
            Cancel
          </Button>
        </Show>
      </div>
    </form>
  );
}
