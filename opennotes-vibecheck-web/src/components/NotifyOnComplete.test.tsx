import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@solidjs/testing-library";

vi.mock("~/lib/notifications", () => ({
  isSupported: vi.fn(() => true),
  getPermission: vi.fn(() => "default"),
  requestPermission: vi.fn(async () => "granted"),
}));

vi.mock("~/lib/notify-preference", () => ({
  loadNotifyPreference: vi.fn(() => false),
  saveNotifyPreference: vi.fn(),
  NOTIFY_PREFERENCE_KEY: "vibecheck.notifyOnComplete",
}));

import * as notifications from "~/lib/notifications";
import * as notifyPreference from "~/lib/notify-preference";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("<NotifyOnComplete />", () => {
  let isSupported: ReturnType<typeof vi.fn>;
  let getPermission: ReturnType<typeof vi.fn>;
  let requestPermission: ReturnType<typeof vi.fn>;
  let loadNotifyPreference: ReturnType<typeof vi.fn>;
  let saveNotifyPreference: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    isSupported = vi.mocked(notifications.isSupported);
    getPermission = vi.mocked(notifications.getPermission);
    requestPermission = vi.mocked(notifications.requestPermission);
    loadNotifyPreference = vi.mocked(notifyPreference.loadNotifyPreference);
    saveNotifyPreference = vi.mocked(notifyPreference.saveNotifyPreference);
  });

  describe("visibility", () => {
    it("renders checkbox when supported and jobStatus is 'done'", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("default");
      loadNotifyPreference.mockReturnValue(false);
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      render(() => (
        <NotifyOnComplete jobStatus="done" onEnabledChange={() => {}} />
      ));

      expect(screen.getByRole("checkbox", { name: /notify me when ready/i })).toBeTruthy();
    });

    it("renders checkbox when supported and jobStatus is undefined", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("default");
      loadNotifyPreference.mockReturnValue(false);
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      render(() => (
        <NotifyOnComplete jobStatus={undefined} onEnabledChange={() => {}} />
      ));

      expect(screen.getByRole("checkbox", { name: /notify me when ready/i })).toBeTruthy();
    });

    it("renders disabled checkbox with hint when isSupported() is false", async () => {
      isSupported.mockReturnValue(false);
      getPermission.mockReturnValue("unsupported");
      loadNotifyPreference.mockReturnValue(false);
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      render(() => (
        <NotifyOnComplete jobStatus="running" onEnabledChange={() => {}} />
      ));

      const checkbox = screen.getByRole("checkbox", { name: /notify me when ready/i });
      expect(checkbox).toBeTruthy();
      expect(checkbox).toBeDisabled();
      expect(screen.getByText(/notifications not supported/i)).toBeTruthy();
    });
  });

  describe("initial state from persisted preference", () => {
    it("initial checked state reflects persisted preference true", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("granted");
      loadNotifyPreference.mockReturnValue(true);
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      render(() => (
        <NotifyOnComplete jobStatus="running" onEnabledChange={() => {}} />
      ));

      await waitFor(() => {
        const checkbox = screen.getByRole("checkbox", { name: /notify me when ready/i });
        expect(checkbox).toBeChecked();
      });
    });

    it("initial checked state reflects persisted preference false even when permission is granted", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("granted");
      loadNotifyPreference.mockReturnValue(false);
      const onEnabledChange = vi.fn();
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      render(() => (
        <NotifyOnComplete jobStatus="running" onEnabledChange={onEnabledChange} />
      ));

      await waitFor(() => {
        const checkbox = screen.getByRole("checkbox", { name: /notify me when ready/i });
        expect(checkbox).not.toBeChecked();
      });
      expect(onEnabledChange).not.toHaveBeenCalledWith(true);
    });
  });

  describe("toggle behavior", () => {
    it("toggle on when permission='default' calls requestPermission, persists true, emits onEnabledChange(true) on granted", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("default");
      loadNotifyPreference.mockReturnValue(false);
      requestPermission.mockResolvedValue("granted");
      const onEnabledChange = vi.fn();
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      render(() => (
        <NotifyOnComplete jobStatus="running" onEnabledChange={onEnabledChange} />
      ));

      fireEvent.click(screen.getByRole("checkbox", { name: /notify me when ready/i }));

      await waitFor(() => {
        expect(requestPermission).toHaveBeenCalledTimes(1);
        expect(saveNotifyPreference).toHaveBeenCalledWith(true);
        expect(onEnabledChange).toHaveBeenCalledWith(true);
      });
    });

    it("toggle on when permission='default' and requestPermission returns 'denied' does not persist true", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("default");
      loadNotifyPreference.mockReturnValue(false);
      requestPermission.mockResolvedValue("denied");
      const onEnabledChange = vi.fn();
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      render(() => (
        <NotifyOnComplete jobStatus="running" onEnabledChange={onEnabledChange} />
      ));

      fireEvent.click(screen.getByRole("checkbox", { name: /notify me when ready/i }));

      await waitFor(() => {
        expect(requestPermission).toHaveBeenCalledTimes(1);
        expect(saveNotifyPreference).not.toHaveBeenCalledWith(true);
        expect(screen.getByText(/notifications blocked/i)).toBeTruthy();
      });
      expect(onEnabledChange).not.toHaveBeenCalledWith(true);
    });

    it("toggle on when permission='granted' persists true and emits onEnabledChange(true)", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("granted");
      loadNotifyPreference.mockReturnValue(false);
      const onEnabledChange = vi.fn();
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      render(() => (
        <NotifyOnComplete jobStatus="running" onEnabledChange={onEnabledChange} />
      ));

      fireEvent.click(screen.getByRole("checkbox", { name: /notify me when ready/i }));

      await waitFor(() => {
        expect(saveNotifyPreference).toHaveBeenCalledWith(true);
        expect(onEnabledChange).toHaveBeenCalledWith(true);
      });
      expect(requestPermission).not.toHaveBeenCalled();
    });

    it("toggle off persists false and emits onEnabledChange(false)", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("granted");
      loadNotifyPreference.mockReturnValue(true);
      const onEnabledChange = vi.fn();
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      render(() => (
        <NotifyOnComplete jobStatus="running" onEnabledChange={onEnabledChange} />
      ));

      await waitFor(() => {
        expect(screen.getByRole("checkbox", { name: /notify me when ready/i })).toBeChecked();
      });

      fireEvent.click(screen.getByRole("checkbox", { name: /notify me when ready/i }));

      await waitFor(() => {
        expect(saveNotifyPreference).toHaveBeenCalledWith(false);
        expect(onEnabledChange).toHaveBeenCalledWith(false);
      });
    });
  });

  describe("onEnabledChange contract", () => {
    it("emits onEnabledChange(true) only when persisted=true AND permission='granted'", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("denied");
      loadNotifyPreference.mockReturnValue(true);
      const onEnabledChange = vi.fn();
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      render(() => (
        <NotifyOnComplete jobStatus="running" onEnabledChange={onEnabledChange} />
      ));

      await waitFor(() => {
        expect(screen.getByRole("checkbox", { name: /notify me when ready/i })).toBeDisabled();
      });
      expect(onEnabledChange).not.toHaveBeenCalledWith(true);
    });
  });

  describe("permission='denied' state", () => {
    it("renders disabled checkbox and blocked hint when permission='denied'", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("denied");
      loadNotifyPreference.mockReturnValue(false);
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      render(() => (
        <NotifyOnComplete jobStatus="running" onEnabledChange={() => {}} />
      ));

      await waitFor(() => {
        const checkbox = screen.getByRole("checkbox", { name: /notify me when ready/i });
        expect(checkbox).toBeDisabled();
        expect(screen.getByText(/notifications blocked/i)).toBeTruthy();
      });
    });

    it("hint is linked via aria-describedby when permission='denied'", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("denied");
      loadNotifyPreference.mockReturnValue(false);
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      render(() => (
        <NotifyOnComplete jobStatus="running" onEnabledChange={() => {}} />
      ));

      await waitFor(() => {
        const hint = screen.getByText(/notifications blocked/i);
        expect(hint.id).toBeTruthy();
        const container = document.querySelector('[aria-describedby]');
        expect(container?.getAttribute("aria-describedby")).toContain(hint.id);
      });
    });
  });

  describe("race: requestPermission pending during job completion", () => {
    it("fires notify exactly once when requestPermission resolves 'granted' after toggle", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("default");
      loadNotifyPreference.mockReturnValue(false);

      let resolvePermission!: (v: "granted" | "denied") => void;
      const permissionPromise = new Promise<"granted" | "denied">((resolve) => {
        resolvePermission = resolve;
      });
      requestPermission.mockReturnValue(permissionPromise);

      const onEnabledChange = vi.fn();
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");
      const { createSignal } = await import("solid-js");

      const [jobStatus, setJobStatus] = createSignal<string | undefined>("running");

      render(() => (
        <NotifyOnComplete jobStatus={jobStatus()} onEnabledChange={onEnabledChange} />
      ));

      fireEvent.click(screen.getByRole("checkbox", { name: /notify me when ready/i }));

      setJobStatus("done");

      resolvePermission("granted");

      await waitFor(() => {
        expect(saveNotifyPreference).toHaveBeenCalledWith(true);
        const trueCallCount = onEnabledChange.mock.calls.filter(([v]) => v === true).length;
        expect(trueCallCount).toBe(1);
      });
    });

    it("does not fire notify when requestPermission resolves 'denied' after job completes", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("default");
      loadNotifyPreference.mockReturnValue(false);

      let resolvePermission!: (v: "granted" | "denied") => void;
      const permissionPromise = new Promise<"granted" | "denied">((resolve) => {
        resolvePermission = resolve;
      });
      requestPermission.mockReturnValue(permissionPromise);

      const onEnabledChange = vi.fn();
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");
      const { createSignal } = await import("solid-js");

      const [jobStatus, setJobStatus] = createSignal<string | undefined>("running");

      render(() => (
        <NotifyOnComplete jobStatus={jobStatus()} onEnabledChange={onEnabledChange} />
      ));

      fireEvent.click(screen.getByRole("checkbox", { name: /notify me when ready/i }));

      setJobStatus("done");

      resolvePermission("denied");

      await waitFor(() => {
        expect(saveNotifyPreference).not.toHaveBeenCalledWith(true);
        expect(onEnabledChange).not.toHaveBeenCalledWith(true);
      });
    });
  });

  describe("cross-tab sync via storage event", () => {
    it("storage event with matching key and newValue='true' checks the checkbox when permission is granted", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("granted");
      loadNotifyPreference.mockReturnValue(false);
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      render(() => (
        <NotifyOnComplete jobStatus="running" onEnabledChange={() => {}} />
      ));

      await waitFor(() => {
        expect(screen.getByRole("checkbox", { name: /notify me when ready/i })).not.toBeChecked();
      });

      window.dispatchEvent(
        new StorageEvent("storage", {
          key: notifyPreference.NOTIFY_PREFERENCE_KEY,
          newValue: "true",
        })
      );

      await waitFor(() => {
        expect(screen.getByRole("checkbox", { name: /notify me when ready/i })).toBeChecked();
      });
    });

    it("storage event with matching key and newValue='false' unchecks the checkbox", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("granted");
      loadNotifyPreference.mockReturnValue(true);
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      render(() => (
        <NotifyOnComplete jobStatus="running" onEnabledChange={() => {}} />
      ));

      await waitFor(() => {
        expect(screen.getByRole("checkbox", { name: /notify me when ready/i })).toBeChecked();
      });

      window.dispatchEvent(
        new StorageEvent("storage", {
          key: notifyPreference.NOTIFY_PREFERENCE_KEY,
          newValue: "false",
        })
      );

      await waitFor(() => {
        expect(screen.getByRole("checkbox", { name: /notify me when ready/i })).not.toBeChecked();
      });
    });

    it("storage event with an unrelated key does not change state", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("granted");
      loadNotifyPreference.mockReturnValue(false);
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      render(() => (
        <NotifyOnComplete jobStatus="running" onEnabledChange={() => {}} />
      ));

      await waitFor(() => {
        expect(screen.getByRole("checkbox", { name: /notify me when ready/i })).not.toBeChecked();
      });

      window.dispatchEvent(
        new StorageEvent("storage", {
          key: "some.other.key",
          newValue: "true",
        })
      );

      await waitFor(() => {
        expect(screen.getByRole("checkbox", { name: /notify me when ready/i })).not.toBeChecked();
      });
    });

    it("storage event does not call saveNotifyPreference (other tab already saved)", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("granted");
      loadNotifyPreference.mockReturnValue(false);
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      render(() => (
        <NotifyOnComplete jobStatus="running" onEnabledChange={() => {}} />
      ));

      window.dispatchEvent(
        new StorageEvent("storage", {
          key: notifyPreference.NOTIFY_PREFERENCE_KEY,
          newValue: "true",
        })
      );

      await waitFor(() => {
        expect(screen.getByRole("checkbox", { name: /notify me when ready/i })).toBeChecked();
      });

      expect(saveNotifyPreference).not.toHaveBeenCalled();
    });

    it("after unmount, storage events do not throw and do not mutate state", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("granted");
      loadNotifyPreference.mockReturnValue(false);
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      const { unmount } = render(() => (
        <NotifyOnComplete jobStatus="running" onEnabledChange={() => {}} />
      ));

      unmount();

      expect(() => {
        window.dispatchEvent(
          new StorageEvent("storage", {
            key: notifyPreference.NOTIFY_PREFERENCE_KEY,
            newValue: "true",
          })
        );
      }).not.toThrow();
    });
  });

  describe("accessibility", () => {
    it("checkbox is findable by role and accessible name", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("default");
      loadNotifyPreference.mockReturnValue(false);
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      render(() => (
        <NotifyOnComplete jobStatus="running" onEnabledChange={() => {}} />
      ));

      expect(screen.getByRole("checkbox", { name: /notify me when ready/i })).toBeTruthy();
    });

    it("checkbox input is keyboard-accessible (focusable hidden input with accessible label)", async () => {
      isSupported.mockReturnValue(true);
      getPermission.mockReturnValue("granted");
      loadNotifyPreference.mockReturnValue(false);
      const onEnabledChange = vi.fn();
      const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

      render(() => (
        <NotifyOnComplete jobStatus="running" onEnabledChange={onEnabledChange} />
      ));

      const checkbox = screen.getByRole("checkbox", { name: /notify me when ready/i });
      expect(checkbox.tagName.toLowerCase()).toBe("input");
      expect(checkbox.getAttribute("type")).toBe("checkbox");
      expect(checkbox).not.toBeDisabled();

      fireEvent.click(checkbox);

      await waitFor(() => {
        expect(saveNotifyPreference).toHaveBeenCalledWith(true);
      });
    });
  });
});
