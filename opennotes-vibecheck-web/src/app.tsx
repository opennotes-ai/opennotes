import "./app.css";
import { Router } from "@solidjs/router";
import { FileRoutes } from "@solidjs/start/router";
import { ErrorBoundary, Suspense } from "solid-js";
import { MetaProvider, Title } from "@solidjs/meta";
import { NavBar } from "@opennotes/ui/components/nav-bar";
import ModeToggle from "@opennotes/ui/components/mode-toggle";

export default function App() {
  return (
    <Router
      root={(props) => (
        <MetaProvider>
          <Title>vibecheck</Title>
          <NavBar
            logo={
              <img
                src="/opennotes-logo.svg"
                alt="Open Notes"
                class="h-9 w-auto"
              />
            }
            logoHref="https://opennotes.ai"
            items={[
              { label: "Home", href: "https://opennotes.ai", external: true },
              { label: "Pricing", href: "https://opennotes.ai/pricing", external: true },
              {
                label: "Open Tools",
                items: [
                  { label: "Discord Bot", href: "https://opennotes.ai/discord-bot", external: true },
                  { label: "Playground", href: "https://opennotes.ai/playground", external: true },
                  { label: "Free Eval", href: "https://opennotes.ai/eval", external: true },
                  { label: "Vibe Check", href: "https://vibecheck.opennotes.ai/", external: true },
                ],
              },
              { label: "Blog", href: "https://opennotes.ai/#blog", external: true },
            ]}
            actions={<ModeToggle />}
          />
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
