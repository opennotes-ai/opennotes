import { batch, createEffect, createSignal, JSX, onMount, Show, untrack } from "solid-js";
import {
  getPermission,
  isSupported,
  NotificationPermissionState,
  requestPermission,
} from "~/lib/notifications";
import { TERMINAL_JOB_STATUSES } from "~/routes/analyze.notifications";

export interface NotifyOnCompleteProps {
  jobStatus: string | undefined;
  onEnabledChange: (enabled: boolean) => void;
}

export default function NotifyOnComplete(
  props: NotifyOnCompleteProps,
): JSX.Element {
  const [optedIn, setOptedIn] = createSignal(false);
  const [permission, setPermission] = createSignal<NotificationPermissionState>("unsupported");
  const [inFlight, setInFlight] = createSignal(false);

  onMount(() => {
    const p = getPermission();
    setPermission(p);
    if (p === "granted") setOptedIn(true);
  });

  const enabled = () => optedIn() && permission() === "granted";

  createEffect(() => {
    const e = enabled();
    untrack(() => props.onEnabledChange(e));
  });

  const handleClick = async () => {
    if (inFlight()) return;
    setInFlight(true);
    try {
      const result = await requestPermission();
      batch(() => {
        setPermission(result);
        if (result === "granted") setOptedIn(true);
      });
    } finally {
      setInFlight(false);
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
