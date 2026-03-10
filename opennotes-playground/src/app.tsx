import "./app.css";
import { Router, A } from "@solidjs/router";
import { FileRoutes } from "@solidjs/start/router";
import { ErrorBoundary, Suspense } from "solid-js";
import { MetaProvider } from "@solidjs/meta";
import AuthStatus from "~/components/AuthStatus";
import ModeToggle from "~/components/ModeToggle";

export default function App() {
  return (
    <Router
      root={(props) => (
        <MetaProvider>
          <nav class="flex items-center gap-4 border-b border-border px-4 py-3">
            <A href="/" class="text-sm font-medium hover:text-primary">
              Home
            </A>
            <A href="/simulations" class="text-sm font-medium hover:text-primary">
              Simulations
            </A>
            <span class="ml-auto flex items-center gap-2">
              <AuthStatus />
              <ModeToggle />
            </span>
          </nav>
          <ErrorBoundary
            fallback={(err, reset) => (
              <div class="p-8 text-center">
                <h1 class="text-xl font-bold">Something went wrong</h1>
                <p class="mt-2 text-muted-foreground">{err.message}</p>
                <button
                  onClick={reset}
                  class="mt-4 rounded-md bg-primary px-4 py-2 text-primary-foreground hover:bg-primary/90"
                >
                  Try again
                </button>
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
