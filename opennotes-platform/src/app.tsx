import "./app.css";
import { A, createAsync, query, Router } from "@solidjs/router";
import { FileRoutes } from "@solidjs/start/router";
import { ErrorBoundary, Show, Suspense, type JSX } from "solid-js";
import { MetaProvider, Title } from "@solidjs/meta";
import { Button, buttonVariants } from "@opennotes/ui/components/ui/button";
import { NavBar } from "@opennotes/ui/components/nav-bar";
import ModeToggle from "@opennotes/ui/components/mode-toggle";
import { getUser } from "~/lib/supabase-server";

export const NAV_USER_KEY = "nav-user";

const getNavUser = query(async () => {
  "use server";
  return getUser();
}, NAV_USER_KEY);

export function RootLayout(props: { children?: JSX.Element }): JSX.Element {
  const user = createAsync(() => getNavUser());
  return (
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
        actions={
          <>
            <ModeToggle />
            <Suspense fallback={null}>
              <Show
                when={user()}
                fallback={
                  <A
                    href="/login"
                    class={buttonVariants({ variant: "default", size: "sm" })}
                  >
                    Sign In
                  </A>
                }
              >
                <form action="/auth/signout" method="post">
                  <button
                    type="submit"
                    class={buttonVariants({ variant: "default", size: "sm" })}
                  >
                    Sign Out
                  </button>
                </form>
              </Show>
            </Suspense>
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
  );
}

export default function App() {
  return (
    <Router root={(props) => <RootLayout>{props.children}</RootLayout>}>
      <FileRoutes />
    </Router>
  );
}
