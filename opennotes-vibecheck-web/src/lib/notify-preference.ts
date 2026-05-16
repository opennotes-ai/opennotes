export const NOTIFY_PREFERENCE_KEY = "vibecheck.notifyOnComplete";

export function loadNotifyPreference(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(NOTIFY_PREFERENCE_KEY) === "true";
  } catch {
    return false;
  }
}

export function saveNotifyPreference(value: boolean): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(NOTIFY_PREFERENCE_KEY, value ? "true" : "false");
  } catch {
  }
}
