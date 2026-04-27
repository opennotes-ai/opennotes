import "./app.css";
import { Router, A } from "@solidjs/router";
import { FileRoutes } from "@solidjs/start/router";
import { ErrorBoundary, Suspense } from "solid-js";
import { MetaProvider, Title } from "@solidjs/meta";
import AuthStatus from "~/components/AuthStatus";
import ModeToggle from "@opennotes/ui/components/mode-toggle";
import EmptyState from "@opennotes/ui/components/ui/empty-state";
import { AlertCircle } from "@opennotes/ui/components/ui/icons";

export default function App() {
  return (
    <Router
      root={(props) => (
        <MetaProvider>
          <Title>Open Notes Playground</Title>
          <nav class="flex h-16 items-center gap-4 border-b border-border bg-background/80 backdrop-blur-lg px-4 sm:px-6 lg:px-8">
            <A href="/" class="flex items-center">
              <img
                src="https://slelguoygbfzlpylpxfs.supabase.co/storage/v1/object/public/document-uploads/Open-Notes-Logo-Light-1760550305591.png"
                alt="Open Notes"
                class="h-10 w-auto sm:h-12 md:h-16 dark:hidden"
              />
              <img
                src="https://slelguoygbfzlpylpxfs.supabase.co/storage/v1/object/public/document-uploads/Open-Notes-Logo-Dark-1760550305520.png"
                alt="Open Notes"
                class="hidden h-10 w-auto sm:h-12 md:h-16 dark:block"
              />
            </A>
            <span class="ml-auto flex items-center gap-2">
              <AuthStatus />
              <ModeToggle />
            </span>
          </nav>
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
