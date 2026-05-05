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
          <Title>vibecheck</Title>
          <ErrorBoundary
            fallback={(err, reset) => (
              <div class="p-8" data-testid="root-error-boundary">
                <p class="text-red-600">Something went wrong: {err.message}</p>
                <button
                  type="button"
                  onClick={reset}
                  class="mt-2 text-sm text-muted-foreground underline"
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
