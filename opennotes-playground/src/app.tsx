import { Router } from "@solidjs/router";
import { FileRoutes } from "@solidjs/start/router";
import { Suspense } from "solid-js";
import AuthStatus from "~/components/AuthStatus";

export default function App() {
  return (
    <Router
      root={(props) => (
        <>
          <nav>
            <AuthStatus />
          </nav>
          <Suspense>{props.children}</Suspense>
        </>
      )}
    >
      <FileRoutes />
    </Router>
  );
}
