export type NotificationPermissionState =
  | "default"
  | "granted"
  | "denied"
  | "unsupported";

export function isSupported(): boolean {
  return false;
}

export function getPermission(): NotificationPermissionState {
  return "unsupported";
}

export async function requestPermission(): Promise<NotificationPermissionState> {
  return "unsupported";
}

export function notify(
  _title: string,
  _options?: unknown,
): null {
  return null;
}
