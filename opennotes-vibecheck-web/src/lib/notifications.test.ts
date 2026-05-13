import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("isSupported", () => {
  it("returns false when window.Notification is absent", async () => {
    const win = { ...globalThis.window } as typeof window & {
      Notification?: unknown;
    };
    Reflect.deleteProperty(win, "Notification");
    vi.stubGlobal("window", win);

    const { isSupported } = await import("./notifications");
    expect(isSupported()).toBe(false);
  });

  it("returns true when window.Notification is present", async () => {
    const mockNotification = {
      permission: "default" as NotificationPermission,
      requestPermission: vi.fn(),
    };
    vi.stubGlobal("Notification", mockNotification);

    const { isSupported } = await import("./notifications");
    expect(isSupported()).toBe(true);
  });
});

describe("getPermission", () => {
  it("returns 'unsupported' when Notification API is absent", async () => {
    const win = { ...globalThis.window } as typeof window & {
      Notification?: unknown;
    };
    Reflect.deleteProperty(win, "Notification");
    vi.stubGlobal("window", win);

    const { getPermission } = await import("./notifications");
    expect(getPermission()).toBe("unsupported");
  });

  it("returns the underlying Notification.permission value when present", async () => {
    vi.stubGlobal("Notification", {
      permission: "granted" as NotificationPermission,
      requestPermission: vi.fn(),
    });

    const { getPermission } = await import("./notifications");
    expect(getPermission()).toBe("granted");
  });

  it("returns 'denied' when Notification.permission is 'denied'", async () => {
    vi.stubGlobal("Notification", {
      permission: "denied" as NotificationPermission,
      requestPermission: vi.fn(),
    });

    const { getPermission } = await import("./notifications");
    expect(getPermission()).toBe("denied");
  });
});

describe("requestPermission", () => {
  it("resolves to 'unsupported' when Notification API is absent", async () => {
    const win = { ...globalThis.window } as typeof window & {
      Notification?: unknown;
    };
    Reflect.deleteProperty(win, "Notification");
    vi.stubGlobal("window", win);

    const { requestPermission } = await import("./notifications");
    await expect(requestPermission()).resolves.toBe("unsupported");
  });

  it("delegates to Notification.requestPermission and returns the result", async () => {
    const mockRequestPermission = vi
      .fn()
      .mockResolvedValue("granted" as NotificationPermission);
    vi.stubGlobal("Notification", {
      permission: "default" as NotificationPermission,
      requestPermission: mockRequestPermission,
    });

    const { requestPermission } = await import("./notifications");
    const result = await requestPermission();
    expect(result).toBe("granted");
    expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  });
});

describe("notify", () => {
  it("returns null when Notification API is absent", async () => {
    const win = { ...globalThis.window } as typeof window & {
      Notification?: unknown;
    };
    Reflect.deleteProperty(win, "Notification");
    vi.stubGlobal("window", win);

    const { notify } = await import("./notifications");
    expect(notify("test")).toBeNull();
  });

  it("returns null when permission is not 'granted'", async () => {
    vi.stubGlobal("Notification", {
      permission: "default" as NotificationPermission,
      requestPermission: vi.fn(),
    });

    const { notify } = await import("./notifications");
    expect(notify("test")).toBeNull();
  });

  it("returns null when permission is 'denied'", async () => {
    vi.stubGlobal("Notification", {
      permission: "denied" as NotificationPermission,
      requestPermission: vi.fn(),
    });

    const { notify } = await import("./notifications");
    expect(notify("test")).toBeNull();
  });

  it("returns a Notification instance when permission is 'granted'", async () => {
    const mockNotificationInstance = { onclick: null as ((e: Event) => void) | null };
    function MockNotification(this: unknown) {
      return mockNotificationInstance;
    }
    MockNotification.permission = "granted" as NotificationPermission;
    MockNotification.requestPermission = vi.fn();
    vi.stubGlobal("Notification", MockNotification);
    vi.stubGlobal("window", { ...globalThis.window, focus: vi.fn() });

    const { notify } = await import("./notifications");
    const result = notify("Hello");
    expect(result).toBe(mockNotificationInstance);
  });

  it("wires onClick and calls window.focus() before delegating", async () => {
    const mockNotificationInstance = { onclick: null as ((e: Event) => void) | null };
    function MockNotification(this: unknown) {
      return mockNotificationInstance;
    }
    MockNotification.permission = "granted" as NotificationPermission;
    MockNotification.requestPermission = vi.fn();
    vi.stubGlobal("Notification", MockNotification);

    const focusSpy = vi.fn();
    vi.stubGlobal("window", { ...globalThis.window, focus: focusSpy });

    const onClick = vi.fn();
    const { notify } = await import("./notifications");
    notify("Hello", { onClick });

    expect(mockNotificationInstance.onclick).toBeTypeOf("function");

    const fakeEvent = new Event("click");
    mockNotificationInstance.onclick!(fakeEvent);

    expect(focusSpy).toHaveBeenCalledTimes(1);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("window.focus() is called even without an onClick handler", async () => {
    const mockNotificationInstance = { onclick: null as ((e: Event) => void) | null };
    function MockNotification(this: unknown) {
      return mockNotificationInstance;
    }
    MockNotification.permission = "granted" as NotificationPermission;
    MockNotification.requestPermission = vi.fn();
    vi.stubGlobal("Notification", MockNotification);

    const focusSpy = vi.fn();
    vi.stubGlobal("window", { ...globalThis.window, focus: focusSpy });

    const { notify } = await import("./notifications");
    notify("Hello");

    const fakeEvent = new Event("click");
    mockNotificationInstance.onclick!(fakeEvent);

    expect(focusSpy).toHaveBeenCalledTimes(1);
  });
});
