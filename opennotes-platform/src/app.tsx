import "./app.css";
import { Router } from "@solidjs/router";
import { FileRoutes } from "@solidjs/start/router";
import { ErrorBoundary, Suspense } from "solid-js";
import { MetaProvider, Title } from "@solidjs/meta";

export default function App() {
  return (
    <Router
      root={(props) => (
        <MetaProvider>
          <Title>Open Notes Platform</Title>
          <nav class="flex h-16 items-center gap-4 border-b border-border bg-background/80 backdrop-blur-lg px-4 sm:px-6 lg:px-8">
            <span class="text-lg font-semibold tracking-tight">Open Notes Platform</span>
          </nav>
          <ErrorBoundary
            fallback={(err, reset) => (
              <div class="p-8">
                <p class="text-red-600">Something went wrong: {err.message}</p>
                <button onClick={reset} class="mt-2 text-primary hover:underline">Try again</button>
              </div>
            )}
          >
            <Suspense>{props.children}</Suspense>
          </ErrorBoundary>
        </MetaProvider>
      )}
    >
      <FileRoutes />
    </Router>
  );
}
