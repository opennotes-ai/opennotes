import { createContext, useContext, type JSX } from "solid-js";
import { createHighlightsStore, type HighlightsStore } from "./highlights-store";

const HighlightsStoreContext = createContext<HighlightsStore | null>(null);

export function HighlightsStoreProvider(props: { children: JSX.Element }) {
  const store = createHighlightsStore();

  return (
    <HighlightsStoreContext.Provider value={store}>
      {props.children}
    </HighlightsStoreContext.Provider>
  );
}

export function useHighlights(): HighlightsStore {
  const store = useContext(HighlightsStoreContext);
  if (store === null) {
    throw new Error("useHighlights must be used within HighlightsStoreProvider");
  }
  return store;
}

export function tryUseHighlights(): HighlightsStore | null {
  return useContext(HighlightsStoreContext);
}
