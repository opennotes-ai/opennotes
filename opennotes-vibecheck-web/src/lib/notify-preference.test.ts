import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import {
  loadNotifyPreference,
  saveNotifyPreference,
  NOTIFY_PREFERENCE_KEY,
} from "./notify-preference";

function makeFakeStorage(): Storage {
  const store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      for (const key of Object.keys(store)) delete store[key];
    },
    key: (index: number) => Object.keys(store)[index] ?? null,
    get length() {
      return Object.keys(store).length;
    },
  };
}

let fakeStorage: Storage;

beforeEach(() => {
  fakeStorage = makeFakeStorage();
  Object.defineProperty(window, "localStorage", {
    value: fakeStorage,
    writable: true,
    configurable: true,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("loadNotifyPreference", () => {
  it("returns false when key is absent", () => {
    expect(loadNotifyPreference()).toBe(false);
  });

  it("returns true after saveNotifyPreference(true)", () => {
    saveNotifyPreference(true);
    expect(loadNotifyPreference()).toBe(true);
  });

  it("returns false after saveNotifyPreference(false)", () => {
    saveNotifyPreference(true);
    saveNotifyPreference(false);
    expect(loadNotifyPreference()).toBe(false);
  });

  it("returns false when localStorage.getItem throws", () => {
    Object.defineProperty(window, "localStorage", {
      value: {
        ...fakeStorage,
        getItem: () => {
          throw new Error("SecurityError");
        },
      },
      writable: true,
      configurable: true,
    });

    expect(loadNotifyPreference()).toBe(false);
  });
});

describe("saveNotifyPreference", () => {
  it("does not throw when setItem throws", () => {
    Object.defineProperty(window, "localStorage", {
      value: {
        ...fakeStorage,
        setItem: () => {
          throw new DOMException("QuotaExceededError");
        },
      },
      writable: true,
      configurable: true,
    });

    expect(() => saveNotifyPreference(true)).not.toThrow();
  });

  it("persists under the stable key", () => {
    saveNotifyPreference(true);
    expect(window.localStorage.getItem(NOTIFY_PREFERENCE_KEY)).toBe("true");
  });
});
