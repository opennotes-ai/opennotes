let currentPath = "/analyze";

export function setCurrentPath(path: string) {
  currentPath = path;
}

export function createMemoryHistory() {
  return {
    set: ({ value }: { value: string }) => {
      setCurrentPath(value);
    },
  };
}

export function MemoryRouter(props: { children?: unknown }) {
  return props.children;
}

export function Route(props: { component: () => unknown }) {
  return props.component();
}

export function A(props: { children?: unknown }) {
  return props.children;
}

export function createAsync() {
  return () => undefined;
}

export function revalidate() {
  return Promise.resolve();
}

export function useNavigate() {
  return () => undefined;
}

export function useSearchParams() {
  return [
    Object.fromEntries(new URLSearchParams(currentPath.split("?")[1] ?? "")),
  ] as const;
}
