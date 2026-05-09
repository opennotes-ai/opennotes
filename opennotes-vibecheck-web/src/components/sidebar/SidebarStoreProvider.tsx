import { createContext, createEffect, useContext, type JSX } from "solid-js";
import { createSidebarStore, type SidebarStore } from "./sidebar-store";

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
    defaultOpen: props.opts?.collapseAllByDefault !== true,
  });

  createEffect<string | undefined>((prevJobId) => {
    const currentJobId = props.opts?.jobId;
    if (prevJobId !== undefined && currentJobId !== prevJobId) {
      store.reset();
    }
    return currentJobId;
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
