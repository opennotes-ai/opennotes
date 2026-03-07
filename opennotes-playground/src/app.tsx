import { Router, A } from "@solidjs/router";
import { FileRoutes } from "@solidjs/start/router";
import { ErrorBoundary, Suspense } from "solid-js";
import AuthStatus from "~/components/AuthStatus";

export default function App() {
  return (
    <Router
      root={(props) => (
        <>
          <nav style={{ display: "flex", gap: "1rem", padding: "1rem", "align-items": "center" }}>
            <A href="/">Home</A>
            <A href="/simulations">Simulations</A>
            <span style={{ "margin-left": "auto" }}>
              <AuthStatus />
            </span>
          </nav>
          <ErrorBoundary
            fallback={(err, reset) => (
              <div style={{ padding: "2rem", "text-align": "center" }}>
                <h1>Something went wrong</h1>
                <p style={{ color: "#666" }}>{err.message}</p>
                <button onClick={reset} style={{ "margin-top": "1rem", padding: "0.5rem 1rem", cursor: "pointer" }}>
                  Try again
                </button>
              </div>
            )}
          >
            <Suspense>{props.children}</Suspense>
          </ErrorBoundary>
        </>
      )}
    >
      <FileRoutes />
    </Router>
  );
}
