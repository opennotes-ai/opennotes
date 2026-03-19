import "./app.css";
import { Router, A } from "@solidjs/router";
import { FileRoutes } from "@solidjs/start/router";
import { ErrorBoundary, Suspense } from "solid-js";
import { MetaProvider } from "@solidjs/meta";
import AuthStatus from "~/components/AuthStatus";
import FontToggle from "~/components/FontToggle";
import ModeToggle from "~/components/ModeToggle";

export default function App() {
  return (
    <Router
      root={(props) => (
        <MetaProvider>
          <nav class="flex items-center gap-4 border-b border-border px-4 py-3">
            <A href="/" class="flex items-center">
              <img
                src="https://slelguoygbfzlpylpxfs.supabase.co/storage/v1/object/public/document-uploads/Open-Notes-Logo-Light-1760550305591.png"
                alt="OpenNotes"
                class="h-6 dark:hidden"
              />
              <img
                src="https://slelguoygbfzlpylpxfs.supabase.co/storage/v1/object/public/document-uploads/Open-Notes-Logo-Dark-1760550305520.png"
                alt="OpenNotes"
                class="hidden h-6 dark:block"
              />
            </A>
            <span class="ml-auto flex items-center gap-2">
              <AuthStatus />
              <FontToggle />
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
