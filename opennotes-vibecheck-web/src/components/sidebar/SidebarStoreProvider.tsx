import { createContext, useContext, type JSX } from "solid-js";
import { createSidebarStore, type SidebarStore } from "./sidebar-store";

const SidebarStoreContext = createContext<SidebarStore | null>(null);

export function SidebarStoreProvider(props: { children: JSX.Element }) {
  const store = createSidebarStore();
  return (
    <SidebarStoreContext.Provider value={store}>
      {props.children}
    </SidebarStoreContext.Provider>
  );
}

export function useSidebarStore(): SidebarStore | null {
  return useContext(SidebarStoreContext);
}
