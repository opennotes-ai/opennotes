import { batch, createEffect, createSignal, JSX, onMount, Show, untrack } from "solid-js";
import {
  getPermission,
  isSupported,
  NotificationPermissionState,
  requestPermission,
} from "~/lib/notifications";
import { loadNotifyPreference, saveNotifyPreference } from "~/lib/notify-preference";
import { Checkbox, CheckboxLabel } from "@opennotes/ui/components/ui/checkbox";

export interface NotifyOnCompleteProps {
  jobStatus: string | undefined;
  onEnabledChange: (enabled: boolean) => void;
}

export default function NotifyOnComplete(
  props: NotifyOnCompleteProps,
): JSX.Element {
  const [persistedPref, setPersistedPref] = createSignal(false);
  const [permission, setPermission] = createSignal<NotificationPermissionState>("default");
  const [inFlight, setInFlight] = createSignal(false);

  const hintId = "notify-on-complete-hint";

  onMount(() => {
    setPermission(getPermission());
    setPersistedPref(loadNotifyPreference());
  });

  const enabled = () => persistedPref() && permission() === "granted";

  createEffect(() => {
    const e = enabled();
    untrack(() => props.onEnabledChange(e));
  });

  const disabled = () => permission() === "denied" || !isSupported();
  const showHint = () => permission() === "denied" || !isSupported();
  const hintText = () => !isSupported() ? "Notifications not supported" : "Notifications blocked";

  const handleToggle = async (checked: boolean) => {
    if (inFlight()) return;

    if (!checked) {
      batch(() => {
        setPersistedPref(false);
        saveNotifyPreference(false);
      });
      return;
    }

    const currentPermission = permission();

    if (currentPermission === "granted") {
      batch(() => {
        setPersistedPref(true);
        saveNotifyPreference(true);
      });
      return;
    }

    if (currentPermission === "default") {
      setInFlight(true);
      try {
        const result = await requestPermission();
        batch(() => {
          setPermission(result);
          if (result === "granted") {
            setPersistedPref(true);
            saveNotifyPreference(true);
          } else {
            setPersistedPref(false);
            saveNotifyPreference(false);
          }
        });
      } finally {
        setInFlight(false);
      }
    }
  };

  return (
    <div class="flex flex-col gap-1">
      <div
        class="flex items-center gap-2"
        aria-describedby={showHint() ? hintId : undefined}
      >
        <Checkbox
          checked={enabled()}
          disabled={disabled()}
          onChange={handleToggle}
        >
          <CheckboxLabel>Notify me when ready</CheckboxLabel>
        </Checkbox>
      </div>
      <Show when={showHint()}>
        <p id={hintId} class="text-xs text-muted-foreground">
          {hintText()}
        </p>
      </Show>
    </div>
  );
}
