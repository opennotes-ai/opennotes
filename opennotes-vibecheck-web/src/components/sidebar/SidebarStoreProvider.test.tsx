import { afterEach, describe, it, expect } from "vitest";
import { cleanup, render, waitFor } from "@solidjs/testing-library";
import { createRoot, createSignal } from "solid-js";
import { SidebarStoreProvider, useSidebarStore } from "./SidebarStoreProvider";
import { ALL_LABELS } from "./sidebar-store";

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

  it("when jobId changes after collapseAllByDefault becomes true, groups reset closed", async () => {
    const [collapse, setCollapse] = createSignal(false);
    const [jobId, setJobId] = createSignal("job-aaa");
    let capturedStore: ReturnType<typeof useSidebarStore> | undefined;

    const TestConsumer = () => {
      capturedStore = useSidebarStore();
      return null;
    };

    render(() => (
      <SidebarStoreProvider
        opts={{ collapseAllByDefault: collapse(), jobId: jobId() }}
      >
        <TestConsumer />
      </SidebarStoreProvider>
    ));

    expect(capturedStore!.isOpen("Safety")).toBe(true);

    setCollapse(true);

    await waitFor(() => {
      expect(capturedStore!.isOpen("Safety")).toBe(false);
      expect(capturedStore!.isOpen("Tone/dynamics")).toBe(false);
      expect(capturedStore!.isOpen("Facts/claims")).toBe(false);
      expect(capturedStore!.isOpen("Opinions")).toBe(false);
    });

    capturedStore!.setOpen("Safety", true);
    expect(capturedStore!.isOpen("Safety")).toBe(true);

    setJobId("job-bbb");

    await waitFor(() => {
      expect(capturedStore!.isOpen("Safety")).toBe(false);
      expect(capturedStore!.isOpen("Tone/dynamics")).toBe(false);
      expect(capturedStore!.isOpen("Facts/claims")).toBe(false);
      expect(capturedStore!.isOpen("Opinions")).toBe(false);
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

  it("when collapseAllByDefault transitions false→true, all groups are closed", async () => {
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

    expect(capturedStore!.isOpen("Safety")).toBe(true);
    expect(capturedStore!.isOpen("Tone/dynamics")).toBe(true);
    expect(capturedStore!.isOpen("Facts/claims")).toBe(true);
    expect(capturedStore!.isOpen("Opinions")).toBe(true);

    setCollapse(true);

    await waitFor(() => {
      expect(capturedStore!.isOpen("Safety")).toBe(false);
      expect(capturedStore!.isOpen("Tone/dynamics")).toBe(false);
      expect(capturedStore!.isOpen("Facts/claims")).toBe(false);
      expect(capturedStore!.isOpen("Opinions")).toBe(false);
    });
  });

  it("with reactive collapseAllByDefault=true, non-sticky groups start closed; Sentiments stays open", () => {
    createRoot((dispose) => {
      const [collapse] = createSignal(true);
      const capturedOpen = new Map<string, boolean | undefined>();

      const TestConsumer = () => {
        const store = useSidebarStore();
        for (const label of ALL_LABELS) {
          capturedOpen.set(label, store?.isOpen(label));
        }
        return null;
      };

      SidebarStoreProvider({
        get opts() {
          return { collapseAllByDefault: collapse() };
        },
        get children() {
          return TestConsumer();
        },
      });

      for (const label of ALL_LABELS) {
        const expected = label === "Sentiments";
        expect(capturedOpen.get(label)).toBe(expected);
      }
      dispose();
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

  it("Sentiments stays open when collapseAllByDefault transitions false→true", async () => {
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

    expect(capturedStore!.isOpen("Sentiments")).toBe(true);

    setCollapse(true);

    await waitFor(() => {
      expect(capturedStore!.isOpen("Safety")).toBe(false);
    });
    expect(capturedStore!.isOpen("Sentiments")).toBe(true);
  });

  it("user can manually collapse Sentiments after collapseAllByDefault sticky preserves it", async () => {
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

    setCollapse(true);
    await waitFor(() => {
      expect(capturedStore!.isOpen("Safety")).toBe(false);
    });
    expect(capturedStore!.isOpen("Sentiments")).toBe(true);

    capturedStore!.setOpen("Sentiments", false);
    expect(capturedStore!.isOpen("Sentiments")).toBe(false);
  });

  it("user-collapsed Sentiments survives a subsequent collapseAllByDefault false→true transition", async () => {
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

    // User manually collapses Sentiments BEFORE the transition fires.
    capturedStore!.setOpen("Sentiments", false);
    expect(capturedStore!.isOpen("Sentiments")).toBe(false);

    setCollapse(true);

    await waitFor(() => {
      expect(capturedStore!.isOpen("Safety")).toBe(false);
    });
    // Sentiments stays closed — the false→true effect skips STICKY labels and
    // therefore must not re-open them either.
    expect(capturedStore!.isOpen("Sentiments")).toBe(false);
  });

  it("reset() on jobId change re-opens Sentiments even if the user had collapsed it (sticky reset wins)", async () => {
    // Policy: each new vibecheck job starts with the sentiment summary visible,
    // since it is the only top-level "always-on" temperature read. If the user
    // collapsed it on the previous job, the next job still gets a fresh view.
    const [jobId, setJobId] = createSignal("job-aaa");
    let capturedStore: ReturnType<typeof useSidebarStore> | undefined;

    const TestConsumer = () => {
      capturedStore = useSidebarStore();
      return null;
    };

    render(() => (
      <SidebarStoreProvider opts={{ collapseAllByDefault: false, jobId: jobId() }}>
        <TestConsumer />
      </SidebarStoreProvider>
    ));

    capturedStore!.setOpen("Sentiments", false);
    expect(capturedStore!.isOpen("Sentiments")).toBe(false);

    setJobId("job-bbb");

    await waitFor(() => {
      expect(capturedStore!.isOpen("Sentiments")).toBe(true);
    });
  });
});
