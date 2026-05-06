import "./app.css";
import { Router } from "@solidjs/router";
import { FileRoutes } from "@solidjs/start/router";
import { ErrorBoundary, Suspense } from "solid-js";
import { MetaProvider, Title } from "@solidjs/meta";
import AuthStatus from "~/components/AuthStatus";
import { NavBar } from "@opennotes/ui/components/nav-bar";
import ModeToggle from "@opennotes/ui/components/mode-toggle";
import EmptyState from "@opennotes/ui/components/ui/empty-state";
import { AlertCircle } from "@opennotes/ui/components/ui/icons";

export default function App() {
  return (
    <Router
      root={(props) => (
        <MetaProvider>
          <Title>Open Notes Playground</Title>
          <NavBar
            logo={
              <img
                src="/opennotes-logo.svg"
                alt="Open Notes"
                class="h-9 w-auto"
              />
            }
            logoHref="/"
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
            actions={<><AuthStatus /><ModeToggle /></>}
          />
          <ErrorBoundary
            fallback={(err, reset) => (
              <div class="p-8">
                <EmptyState
                  variant="error"
                  icon={<AlertCircle class="size-6" />}
                  message="Something went wrong"
                  description={err.message}
                  actionLabel="Try again"
                  onAction={reset}
                />
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
