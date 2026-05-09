import { afterEach, describe, it, expect } from "vitest";
import { cleanup, render, waitFor } from "@solidjs/testing-library";
import { createRoot, createSignal } from "solid-js";
import { SidebarStoreProvider, useSidebarStore } from "./SidebarStoreProvider";

afterEach(cleanup);

describe("SidebarStoreProvider", () => {
  it("with collapseAllByDefault=true, isOpen returns false synchronously on first render (no flicker)", () => {
    createRoot((dispose) => {
      let capturedIsOpen: boolean | undefined;
      const TestConsumer = () => {
        const store = useSidebarStore();
        capturedIsOpen = store?.isOpen("Safety");
        return null;
      };
      SidebarStoreProvider({
        opts: { collapseAllByDefault: true },
        get children() {
          return TestConsumer();
        },
      });
      expect(capturedIsOpen).toBe(false);
      dispose();
    });
  });

  it("with collapseAllByDefault=false (default), isOpen returns true synchronously on first render", () => {
    createRoot((dispose) => {
      let capturedIsOpen: boolean | undefined;
      const TestConsumer = () => {
        const store = useSidebarStore();
        capturedIsOpen = store?.isOpen("Safety");
        return null;
      };
      SidebarStoreProvider({
        opts: { collapseAllByDefault: false },
        get children() {
          return TestConsumer();
        },
      });
      expect(capturedIsOpen).toBe(true);
      dispose();
    });
  });

  it("when jobId changes, group state resets to default (collapseAllByDefault=true)", async () => {
    const [jobId, setJobId] = createSignal("job-aaa");
    let capturedStore: ReturnType<typeof useSidebarStore> | undefined;

    const TestConsumer = () => {
      capturedStore = useSidebarStore();
      return null;
    };

    render(() => (
      <SidebarStoreProvider
        opts={{ collapseAllByDefault: true, jobId: jobId() }}
      >
        <TestConsumer />
      </SidebarStoreProvider>
    ));

    capturedStore!.setOpen("Safety", true);
    expect(capturedStore!.isOpen("Safety")).toBe(true);

    setJobId("job-bbb");

    await waitFor(() => {
      expect(capturedStore!.isOpen("Safety")).toBe(false);
    });
  });

  it("when jobId changes, group state resets to default (collapseAllByDefault=false)", async () => {
    const [jobId, setJobId] = createSignal("job-aaa");
    let capturedStore: ReturnType<typeof useSidebarStore> | undefined;

    const TestConsumer = () => {
      capturedStore = useSidebarStore();
      return null;
    };

    render(() => (
      <SidebarStoreProvider
        opts={{ collapseAllByDefault: false, jobId: jobId() }}
      >
        <TestConsumer />
      </SidebarStoreProvider>
    ));

    capturedStore!.setOpen("Safety", false);
    expect(capturedStore!.isOpen("Safety")).toBe(false);

    setJobId("job-bbb");

    await waitFor(() => {
      expect(capturedStore!.isOpen("Safety")).toBe(true);
    });
  });

  it("when collapseAllByDefault changes false→true, user group state is preserved (no over-correction)", async () => {
    const [collapse, setCollapse] = createSignal(false);
    let capturedStore: ReturnType<typeof useSidebarStore> | undefined;

    const TestConsumer = () => {
      capturedStore = useSidebarStore();
      return null;
    };

    render(() => (
      <SidebarStoreProvider opts={{ collapseAllByDefault: collapse() }}>
        <TestConsumer />
      </SidebarStoreProvider>
    ));

    capturedStore!.setOpen("Safety", false);
    expect(capturedStore!.isOpen("Safety")).toBe(false);

    setCollapse(true);

    await waitFor(() => {
      expect(capturedStore!.isOpen("Safety")).toBe(false);
    });
  });
});
