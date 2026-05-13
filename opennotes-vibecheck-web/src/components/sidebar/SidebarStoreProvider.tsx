import { createContext, createEffect, useContext, type JSX } from "solid-js";
import { createSidebarStore, ALL_LABELS, type SidebarStore } from "./sidebar-store";

export interface SidebarStoreProviderOpts {
  collapseAllByDefault?: boolean;
  jobId?: string;
}

const SidebarStoreContext = createContext<SidebarStore | null>(null);

export function SidebarStoreProvider(props: {
  opts?: SidebarStoreProviderOpts;
  children: JSX.Element;
}) {
  const store = createSidebarStore({
    defaultOpen: () => props.opts?.collapseAllByDefault !== true,
  });

  createEffect<string | undefined>((prevJobId) => {
    const currentJobId = props.opts?.jobId;
    if (prevJobId !== undefined && currentJobId !== prevJobId) {
      store.reset();
    }
    return currentJobId;
  }, undefined);

  createEffect<boolean | undefined>((prev) => {
    const current = props.opts?.collapseAllByDefault;
    if (current === true && prev !== true) {
      for (const label of ALL_LABELS) {
        store.setOpen(label, false);
      }
    }
    return current;
  }, undefined);

  return (
    <SidebarStoreContext.Provider value={store}>
      {props.children}
    </SidebarStoreContext.Provider>
  );
}

export function useSidebarStore(): SidebarStore | null {
  return useContext(SidebarStoreContext);
}
