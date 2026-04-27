import "./app.css";
import { Router } from "@solidjs/router";
import { FileRoutes } from "@solidjs/start/router";
import { ErrorBoundary, Suspense } from "solid-js";
import { MetaProvider, Title } from "@solidjs/meta";
import { Button } from "@opennotes/ui/components/ui/button";
import { NavBar } from "@opennotes/ui/components/nav-bar";
import ModeToggle from "@opennotes/ui/components/mode-toggle";

export default function App() {
  return (
    <Router
      root={(props) => (
        <MetaProvider>
          <Title>Open Notes Platform</Title>
          <NavBar
            logo={
              <img
                src="/opennotes-logo.svg"
                alt="Open Notes"
                class="h-9 w-auto"
              />
            }
            logoHref="/"
            items={[{ label: "Docs", href: "https://docs.opennotes.ai" }]}
            actions={
              <>
                <ModeToggle />
                <Button as="a" href="/login" variant="default" size="sm">
                  Sign In
                </Button>
              </>
            }
          />
          <ErrorBoundary
            fallback={(err, reset) => (
              <div class="p-8">
                <p class="text-red-600">Something went wrong: {err.message}</p>
                <Button variant="link" size="sm" onClick={reset} class="mt-2 px-0">
                  Try again
                </Button>
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
