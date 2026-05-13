export type NotificationPermissionState =
  | "default"
  | "granted"
  | "denied"
  | "unsupported";

function apiAvailable(): boolean {
  return typeof window !== "undefined" && "Notification" in window;
}

export function isSupported(): boolean {
  return apiAvailable();
}

export function getPermission(): NotificationPermissionState {
  if (!apiAvailable()) return "unsupported";
  return Notification.permission as NotificationPermissionState;
}

export async function requestPermission(): Promise<NotificationPermissionState> {
  if (!apiAvailable()) return "unsupported";
  const result = await Notification.requestPermission();
  return result as NotificationPermissionState;
}

export function notify(
  title: string,
  options?: NotificationOptions & { onClick?: () => void },
): Notification | null {
  if (!apiAvailable()) return null;
  if (Notification.permission !== "granted") return null;

  const { onClick, ...notificationOptions } = options ?? {};
  let notification: Notification;
  try {
    notification = new Notification(
      title,
      Object.keys(notificationOptions).length > 0
        ? notificationOptions
        : undefined,
    );
  } catch {
    return null;
  }

  notification.onclick = (_e: Event) => {
    window.focus();
    onClick?.();
  };

  return notification;
}
