import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@solidjs/testing-library";

vi.mock("~/lib/notifications", () => ({
  isSupported: vi.fn(() => true),
  getPermission: vi.fn(() => "default"),
  requestPermission: vi.fn(async () => "granted"),
}));

import * as notifications from "~/lib/notifications";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("<NotifyOnComplete />", () => {
  let isSupported: ReturnType<typeof vi.fn>;
  let getPermission: ReturnType<typeof vi.fn>;
  let requestPermission: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    isSupported = vi.mocked(notifications.isSupported);
    getPermission = vi.mocked(notifications.getPermission);
    requestPermission = vi.mocked(notifications.requestPermission);
  });

  it("renders nothing when isSupported() is false", async () => {
    isSupported.mockReturnValue(false);
    const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

    render(() => (
      <NotifyOnComplete jobStatus="running" onEnabledChange={() => {}} />
    ));

    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByTestId("notify-on-complete-enabled")).toBeNull();
  });

  it("renders button when permission is 'default'", async () => {
    isSupported.mockReturnValue(true);
    getPermission.mockReturnValue("default");
    const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

    render(() => (
      <NotifyOnComplete jobStatus="running" onEnabledChange={() => {}} />
    ));

    expect(screen.getByRole("button")).toBeTruthy();
    expect(screen.getByRole("button").textContent).toContain("Notify me when ready");
  });

  it("clicking button calls requestPermission and then onEnabledChange(true) on granted", async () => {
    isSupported.mockReturnValue(true);
    getPermission.mockReturnValue("default");
    requestPermission.mockResolvedValue("granted");
    const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

    const onEnabledChange = vi.fn();
    render(() => (
      <NotifyOnComplete jobStatus="running" onEnabledChange={onEnabledChange} />
    ));

    fireEvent.click(screen.getByRole("button"));

    await waitFor(() => {
      expect(requestPermission).toHaveBeenCalledTimes(1);
      expect(onEnabledChange).toHaveBeenCalledWith(true);
    });
  });

  it("renders 'blocked' hint when permission is 'denied' and never calls onEnabledChange(true)", async () => {
    isSupported.mockReturnValue(true);
    getPermission.mockReturnValue("denied");
    const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

    const onEnabledChange = vi.fn();
    render(() => (
      <NotifyOnComplete jobStatus="running" onEnabledChange={onEnabledChange} />
    ));

    expect(screen.queryByRole("button")).toBeNull();
    const hint = screen.getByText(/notifications blocked/i);
    expect(hint).toBeTruthy();
    expect(onEnabledChange).not.toHaveBeenCalledWith(true);
  });

  it("hides itself when jobStatus is 'done'", async () => {
    isSupported.mockReturnValue(true);
    getPermission.mockReturnValue("default");
    const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

    render(() => (
      <NotifyOnComplete jobStatus="done" onEnabledChange={() => {}} />
    ));

    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByTestId("notify-on-complete-enabled")).toBeNull();
  });

  it("renders enabled label when permission is 'granted' and opted in", async () => {
    isSupported.mockReturnValue(true);
    getPermission.mockReturnValue("default");
    requestPermission.mockResolvedValue("granted");
    const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

    render(() => (
      <NotifyOnComplete jobStatus="running" onEnabledChange={() => {}} />
    ));

    fireEvent.click(screen.getByRole("button"));

    await waitFor(() => {
      expect(screen.getByTestId("notify-on-complete-enabled")).toBeTruthy();
    });
  });

  it("shows enabled label immediately when permission is already 'granted' at mount (pre-granted)", async () => {
    isSupported.mockReturnValue(true);
    getPermission.mockReturnValue("granted");
    const { default: NotifyOnComplete } = await import("./NotifyOnComplete");

    render(() => (
      <NotifyOnComplete jobStatus="running" onEnabledChange={() => {}} />
    ));

    await waitFor(() => {
      expect(screen.getByTestId("notify-on-complete-enabled")).toBeTruthy();
    });
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("hides itself when jobStatus transitions from 'analyzing' to 'done'", async () => {
    isSupported.mockReturnValue(true);
    getPermission.mockReturnValue("default");
    const { default: NotifyOnComplete } = await import("./NotifyOnComplete");
    const { createSignal } = await import("solid-js");

    const [jobStatus, setJobStatus] = createSignal<string | undefined>("analyzing");

    render(() => (
      <NotifyOnComplete jobStatus={jobStatus()} onEnabledChange={() => {}} />
    ));

    expect(screen.getByRole("button")).toBeTruthy();

    setJobStatus("done");

    await waitFor(() => {
      expect(screen.queryByRole("button")).toBeNull();
      expect(screen.queryByTestId("notify-on-complete-enabled")).toBeNull();
    });
  });
});
