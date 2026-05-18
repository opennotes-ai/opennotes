import { batch, createEffect, createSignal, JSX, on, onCleanup, onMount, Show } from "solid-js";
import {
  getPermission,
  isSupported,
  NotificationPermissionState,
  requestPermission,
} from "~/lib/notifications";
import { loadNotifyPreference, NOTIFY_PREFERENCE_KEY, saveNotifyPreference } from "~/lib/notify-preference";
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
  const [pendingPermission, setPendingPermission] = createSignal(false);

  const hintId = "notify-on-complete-hint";

  onMount(() => {
    const perm = getPermission();
    const pref = loadNotifyPreference();
    batch(() => {
      setPermission(perm);
      setPersistedPref(pref);
    });
    props.onEnabledChange(pref && perm === "granted");

    if (typeof window !== "undefined") {
      const handler = (e: StorageEvent) => {
        if (e.key !== NOTIFY_PREFERENCE_KEY) return;
        const newPref = e.newValue === "true";
        const currentPerm = getPermission();
        batch(() => {
          setPersistedPref(newPref);
          setPermission(currentPerm);
        });
      };
      window.addEventListener("storage", handler);
      onCleanup(() => window.removeEventListener("storage", handler));
    }
  });

  const enabled = () => persistedPref() && permission() === "granted";

  createEffect(on(enabled, (e) => {
    props.onEnabledChange(e);
  }, { defer: true }));

  const disabled = () => permission() === "denied" || !isSupported() || pendingPermission();
  const showHint = () => permission() === "denied" || !isSupported();
  const hintText = () => !isSupported() ? "Notifications not supported" : "Notifications blocked";

  const handleToggle = async (checked: boolean) => {
    if (pendingPermission()) return;

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
      setPendingPermission(true);
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
        setPendingPermission(false);
      }
    }
  };

  return (
    <div class="flex flex-col gap-1">
      <div class="flex items-center gap-2">
        <Checkbox
          checked={enabled()}
          disabled={disabled()}
          onChange={handleToggle}
          inputProps={{ "aria-describedby": showHint() ? hintId : undefined }}
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
