import { createEffect, createSignal, JSX, Show } from "solid-js";
import {
  getPermission,
  isSupported,
  requestPermission,
} from "~/lib/notifications";

const TERMINAL_JOB_STATUSES = new Set(["done", "partial", "failed"]);

export interface NotifyOnCompleteProps {
  jobStatus: string | undefined;
  onEnabledChange: (enabled: boolean) => void;
}

export default function NotifyOnComplete(
  props: NotifyOnCompleteProps,
): JSX.Element {
  const [optedIn, setOptedIn] = createSignal(false);
  const [permission, setPermission] = createSignal(getPermission());

  const enabled = () => optedIn() && permission() === "granted";

  createEffect(() => {
    props.onEnabledChange(enabled());
  });

  const handleClick = async () => {
    const result = await requestPermission();
    setPermission(result);
    if (result === "granted") {
      setOptedIn(true);
    }
  };

  const visible = () =>
    isSupported() &&
    props.jobStatus !== undefined &&
    !TERMINAL_JOB_STATUSES.has(props.jobStatus);

  return (
    <Show when={visible()}>
      <Show when={permission() === "granted" && optedIn()}>
        <p data-testid="notify-on-complete-enabled">
          We'll notify you when it's ready
        </p>
      </Show>
      <Show when={permission() === "default"}>
        <button
          class="text-xs text-muted-foreground"
          onClick={handleClick}
          type="button"
        >
          Notify me when ready
        </button>
      </Show>
      <Show when={permission() === "denied"}>
        <p class="text-muted-foreground text-xs">Notifications blocked</p>
      </Show>
    </Show>
  );
}
