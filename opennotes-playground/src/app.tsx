import { Router, A } from "@solidjs/router";
import { FileRoutes } from "@solidjs/start/router";
import { Suspense } from "solid-js";
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
          <Suspense>{props.children}</Suspense>
        </>
      )}
    >
      <FileRoutes />
    </Router>
  );
}
